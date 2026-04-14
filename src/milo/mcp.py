"""MCP server — expose CLI commands as tools via JSON-RPC on stdin/stdout."""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING, Any

from milo import __version__ as _server_version
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import _stderr, _write_error, _write_notification, _write_result
from milo._mcp_router import dispatch
from milo.observability import RequestLogger, log_request, new_correlation_id

if TYPE_CHECKING:
    from milo.commands import CLI, CommandDef, LazyCommandDef

_SERVER_NAME = "milo"


def _to_text(result: Any) -> str:
    """Convert a result to text for MCP content responses."""
    return result if isinstance(result, str) else json.dumps(result, indent=2, default=str)


class _CLIHandler:
    """MCPHandler implementation for a single CLI (leaf server)."""

    def __init__(self, cli: CLI, cached_tools: list[dict[str, Any]] | None = None) -> None:
        self._cli = cli
        self._cached_tools = cached_tools
        self._cached_version: int = cli._command_version
        self._logger = RequestLogger()

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": _MCP_VERSION,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {
                "name": self._cli.name or _SERVER_NAME,
                "version": self._cli.version or _server_version,
                "title": self._cli.description,
            },
            "instructions": self._cli.description,
        }

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        # Invalidate cache when commands have been added or removed
        if self._cached_tools is None or self._cached_version != self._cli._command_version:
            self._cached_tools = _list_tools(self._cli)
            self._cached_version = self._cli._command_version
        log_request(self._logger, "tools/list", "", start)
        return {"tools": self._cached_tools}

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        result = _call_tool(self._cli, params)
        error = "" if not result.get("isError") else result["content"][0].get("text", "")
        log_request(
            self._logger,
            "tools/call",
            params.get("name", ""),
            start,
            error=error,
        )
        return result

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        resources = _list_resources(self._cli) + _builtin_resources()
        log_request(self._logger, "resources/list", "", start)
        return {"resources": resources}

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri", "")
        if uri == "milo://stats":
            return _stats_resource(self._logger)
        if uri == "milo://pipeline/timeline":
            return _pipeline_timeline_resource()
        new_correlation_id()
        start = time.monotonic()
        try:
            result = _read_resource(self._cli, params)
        except Exception as e:
            log_request(self._logger, "resources/read", uri, start, error=str(e))
            raise
        log_request(self._logger, "resources/read", uri, start)
        return result

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        prompts = _list_prompts(self._cli)
        log_request(self._logger, "prompts/list", "", start)
        return {"prompts": prompts}

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        result = _get_prompt(self._cli, params)
        # Detect errors returned as message payloads
        error = ""
        for message in result.get("messages", []):
            content = message.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
            if text.startswith("Error:"):
                error = text
                break
        log_request(self._logger, "prompts/get", params.get("name", ""), start, error=error)
        return result


def run_mcp_server(cli: CLI) -> None:
    """Run MCP JSON-RPC server on stdin/stdout.

    Implements the MCP protocol (initialize, tools/list, tools/call,
    resources/list, resources/read, prompts/list, prompts/get).
    """
    tools = _list_tools(cli)
    tool_names = [t["name"] for t in tools]

    _stderr(f"MCP server ready — {cli.name}")
    _stderr(f"  Protocol:  {_MCP_VERSION}")
    _stderr(f"  Tools:     {len(tools)} ({', '.join(tool_names)})")
    _stderr(f"  Resources: {len(cli._resources)}")
    _stderr(f"  Prompts:   {len(cli._prompts)}")
    _stderr("  Transport: stdin/stdout (JSON-RPC, one request per line)")
    _stderr("")
    _stderr("Send requests as JSON, for example:")
    _stderr('  {"jsonrpc":"2.0","id":1,"method":"initialize"}')
    _stderr('  {"jsonrpc":"2.0","id":2,"method":"tools/list"}')
    if tool_names:
        example_tool = tool_names[0]
        example_schema = tools[0].get("inputSchema", {})
        example_args = dict.fromkeys(example_schema.get("properties", {}), "...")
        args_json = json.dumps(example_args) if example_args else "{}"
        _stderr(
            f'  {{"jsonrpc":"2.0","id":3,"method":"tools/call",'
            f'"params":{{"name":"{example_tool}","arguments":{args_json}}}}}'
        )
    _stderr("")
    _stderr("Or pipe from a file:")
    _stderr(f"  cat requests.jsonl | {cli.name} --mcp")
    _stderr("")
    _stderr("Press Ctrl+C to stop.")
    _stderr("")

    handler = _CLIHandler(cli, cached_tools=tools)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write_error(None, -32700, "Parse error")
            continue  # silent: error already sent via JSON-RPC

        req_id = request.get("id")
        method = request.get("method", "")

        try:
            result = dispatch(handler, method, request.get("params", {}))
            if result is not None:
                _write_result(req_id, result)
        except Exception as e:
            code, data = _classify_exception(e)
            _write_error(req_id, code, str(e), data=data)


def _classify_exception(exc: Exception) -> tuple[int, dict[str, Any] | None]:
    """Map an exception to a JSON-RPC error code and optional data payload.

    Returns (code, data) where:
    - MiloError with validation/config codes -> -32602 (Invalid params)
    - MiloError with not-found codes -> -32601 (Method not found)
    - All others -> -32603 (Internal error) with traceback in data
    """
    import traceback as tb_mod

    from milo._errors import MiloError

    if isinstance(exc, MiloError):
        code_val = exc.code.value
        # Validation-related error codes -> Invalid params
        if code_val.startswith(("M-CFG-", "M-FRM-", "M-INP-")):
            return -32602, {
                "errorCode": code_val,
                "type": type(exc).__name__,
                "suggestion": exc.suggestion,
            }
        # Not-found codes -> Method not found
        if code_val in ("M-CMD-001",):
            return -32601, {
                "errorCode": code_val,
                "type": type(exc).__name__,
                "suggestion": exc.suggestion,
            }
        # Other MiloErrors -> Internal with structured data
        return -32603, {
            "errorCode": code_val,
            "type": type(exc).__name__,
            "suggestion": exc.suggestion,
            "traceback": "".join(tb_mod.format_exception(exc)),
        }

    # Unknown exceptions -> Internal error with traceback
    return -32603, {
        "type": type(exc).__name__,
        "traceback": "".join(tb_mod.format_exception(exc)),
    }


def _builtin_resources() -> list[dict[str, Any]]:
    """Built-in MCP resources provided by the milo runtime."""
    return [
        {
            "uri": "milo://stats",
            "name": "Server Statistics",
            "description": "Request latency, error counts, and throughput for this MCP server",
            "mimeType": "application/json",
        },
        {
            "uri": "milo://pipeline/timeline",
            "name": "Pipeline Timeline",
            "description": "Phase execution timeline for the active pipeline (timing, status, log counts)",
            "mimeType": "application/json",
        },
    ]


def _stats_resource(logger: RequestLogger) -> dict[str, Any]:
    """Return server statistics as an MCP resource."""
    stats = logger.stats()
    text = json.dumps(stats, indent=2)
    return {"contents": [{"uri": "milo://stats", "text": text, "mimeType": "application/json"}]}


def _pipeline_timeline_resource() -> dict[str, Any]:
    """Return the active pipeline's execution timeline as an MCP resource."""
    from milo.pipeline import get_active_pipeline, pipeline_to_timeline

    state = get_active_pipeline()
    if state is None:
        data: dict[str, Any] = {"pipeline": None, "status": "no active pipeline", "phases": []}
    else:
        data = pipeline_to_timeline(state)
    text = json.dumps(data, indent=2)
    return {
        "contents": [
            {"uri": "milo://pipeline/timeline", "text": text, "mimeType": "application/json"}
        ]
    }


def _list_tools(cli: CLI) -> list[dict[str, Any]]:
    """Generate MCP tools/list response from all commands including groups.

    Group commands use dot-notation names: ``site.build``, ``site.config.show``.
    Includes outputSchema when return type annotations are available.
    Skips commands that fail to import with a warning.
    """
    from milo._command_defs import LazyImportError

    tools = []
    for dotted_name, cmd in cli.walk_commands():
        if cmd.hidden:
            continue
        try:
            input_schema = cmd.schema
        except LazyImportError as exc:
            _stderr(f"warning: skipping tool {dotted_name!r}: {exc.cause}")
            continue
        tool: dict[str, Any] = {
            "name": dotted_name,
            "description": cmd.description,
            "inputSchema": input_schema,
        }

        # title: human-readable display name from docstring or description
        title = _tool_title(cmd)
        if title:
            tool["title"] = title

        # outputSchema: generated from handler return type annotation
        output_schema = _output_schema(cmd)
        if output_schema:
            tool["outputSchema"] = output_schema

        # annotations: MCP behavioral hints (readOnlyHint, destructiveHint, etc.)
        if cmd.annotations:
            tool["annotations"] = cmd.annotations

        tools.append(tool)
    return tools


def _tool_title(cmd: CommandDef | LazyCommandDef) -> str:
    """Derive a human-readable title for a tool.

    Uses the handler's docstring first line if available and different
    from the description. Falls back to a title-cased command name.
    """
    from milo.commands import LazyCommandDef

    # For lazy commands, use name-derived title to avoid triggering imports
    if isinstance(cmd, LazyCommandDef) and cmd._resolved is None:
        return cmd.name.replace("-", " ").replace("_", " ").title()

    doc = getattr(cmd.handler, "__doc__", None)
    if doc:
        first_line = doc.strip().split("\n")[0].strip().rstrip(".")
        if first_line and first_line != cmd.description:
            return first_line

    return cmd.name.replace("-", " ").replace("_", " ").title()


def _output_schema(cmd: CommandDef | LazyCommandDef) -> dict[str, Any] | None:
    """Generate outputSchema from handler return type annotation.

    Returns None for lazy commands that haven't been resolved (avoids imports).
    """
    from milo.commands import LazyCommandDef
    from milo.schema import return_to_schema

    # Don't trigger imports on lazy commands just for output schema
    if isinstance(cmd, LazyCommandDef) and cmd._resolved is None:
        return None

    return return_to_schema(cmd.handler)


def _call_tool(cli: CLI, params: dict[str, Any]) -> dict[str, Any]:
    """Handle tools/call by dispatching to the command handler.

    Routes through the CLI's middleware stack when present, so middleware
    can intercept MCP-originated calls just like CLI-originated ones.

    If the handler returns a generator yielding Progress objects, each
    Progress is emitted as a ``notifications/progress`` JSON-RPC
    notification before the final result is returned.
    """
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        result = cli.call_raw(tool_name, **arguments)

        # Stream progress notifications for generator results
        from milo.streaming import Progress, is_generator_result

        if is_generator_result(result):
            final_value = None
            try:
                while True:
                    value = next(result)
                    if isinstance(value, Progress):
                        _write_notification(
                            "notifications/progress",
                            {
                                "progressToken": tool_name,
                                "progress": value.step,
                                "total": value.total or None,
                                "message": value.status,
                            },
                        )
            except StopIteration as e:
                final_value = e.value
            result = final_value

    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {e}"}],
            "isError": True,
        }

    text = _to_text(result)

    response: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
    }

    # Include structuredContent for structured data (dict, list, number, bool)
    if not isinstance(result, str) and result is not None:
        response["structuredContent"] = result

    return response


def _list_resources(cli: CLI) -> list[dict[str, Any]]:
    """Generate MCP resources/list response from registered resources."""
    resources = []
    for _uri, res in cli.walk_resources():
        resources.append(
            {
                "uri": res.uri,
                "name": res.name,
                "description": res.description,
                "mimeType": res.mime_type,
            }
        )
    return resources


def _read_resource(cli: CLI, params: dict[str, Any]) -> dict[str, Any]:
    """Handle resources/read by calling the resource handler."""
    uri = params.get("uri", "")

    res = cli._resources.get(uri)
    if not res:
        return {"contents": []}

    try:
        if cli._middleware:
            from milo.context import Context as ContextClass
            from milo.middleware import MCPCall

            ctx = ContextClass()
            call = MCPCall(method="resources/read", name=uri, arguments={})
            result = cli._middleware.execute(ctx, call, lambda _c: res.handler())
        else:
            result = res.handler()
    except Exception as e:
        return {"contents": [{"uri": uri, "text": f"Error: {e}", "mimeType": "text/plain"}]}

    text = _to_text(result)

    return {"contents": [{"uri": uri, "text": text, "mimeType": res.mime_type}]}


def _list_prompts(cli: CLI) -> list[dict[str, Any]]:
    """Generate MCP prompts/list response from registered prompts."""
    prompts = []
    for _name, p in cli.walk_prompts():
        prompt_info: dict[str, Any] = {
            "name": p.name,
            "description": p.description,
        }
        if p.arguments:
            prompt_info["arguments"] = list(p.arguments)
        prompts.append(prompt_info)
    return prompts


def _get_prompt(cli: CLI, params: dict[str, Any]) -> dict[str, Any]:
    """Handle prompts/get by calling the prompt handler."""
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    p = cli._prompts.get(name)
    if not p:
        return {"messages": []}

    try:
        if cli._middleware:
            from milo.context import Context as ContextClass
            from milo.middleware import MCPCall

            ctx = ContextClass()
            call = MCPCall(method="prompts/get", name=name, arguments=arguments)
            result = cli._middleware.execute(ctx, call, lambda c: p.handler(**c.arguments))
        else:
            result = p.handler(**arguments)
    except Exception as e:
        return {"messages": [{"role": "user", "content": {"type": "text", "text": f"Error: {e}"}}]}

    # If handler returns list of dicts, treat as messages
    if isinstance(result, list):
        return {"messages": result}

    # If handler returns a string, wrap as single user message
    if isinstance(result, str):
        return {"messages": [{"role": "user", "content": {"type": "text", "text": result}}]}

    return {
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": json.dumps(result, default=str)},
            }
        ]
    }
