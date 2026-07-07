"""MCP server — expose CLI commands as tools via JSON-RPC on stdin/stdout."""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from typing import TYPE_CHECKING, Any

from milo import __version__ as _server_version
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import SUPPORTED_MCP_VERSIONS as _SUPPORTED_MCP_VERSIONS
from milo._jsonrpc import _parse_request, _stderr, _write_error, _write_notification, _write_result
from milo._mcp_router import MethodNotFoundError, UnsupportedProtocolVersionError, dispatch
from milo.observability import RequestLogger, log_request, new_correlation_id

if TYPE_CHECKING:
    from milo.commands import CLI, CommandDef, LazyCommandDef

_SERVER_NAME = "milo"


def _server_capabilities(*, include_ui: bool = False) -> dict[str, Any]:
    capabilities: dict[str, Any] = {"tools": {}, "resources": {}, "prompts": {}}
    if include_ui:
        from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

        capabilities["extensions"] = {MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}}
    return capabilities


def _client_supports_ui(params: dict[str, Any]) -> bool:
    """Return whether initialize params negotiate Milo's MCP Apps MIME type."""
    from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

    capabilities = params.get("capabilities")
    if not isinstance(capabilities, dict):
        meta = params.get("_meta")
        if isinstance(meta, dict):
            capabilities = meta.get("io.modelcontextprotocol/clientCapabilities")
    if not isinstance(capabilities, dict):
        return False
    extensions = capabilities.get("extensions")
    if not isinstance(extensions, dict):
        return False
    ui = extensions.get(MCP_APPS_EXTENSION_ID)
    if not isinstance(ui, dict):
        return False
    mime_types = ui.get("mimeTypes")
    return isinstance(mime_types, list) and MCP_APPS_MIME_TYPE in mime_types


def _server_info(cli: CLI) -> dict[str, Any]:
    return {
        "name": cli.name or _SERVER_NAME,
        "version": cli.version or _server_version,
        "title": cli.description,
    }


def _to_text(result: Any) -> str:
    """Convert a result to text for MCP content responses."""
    return result if isinstance(result, str) else json.dumps(result, indent=2, default=str)


class _CLIHandler:
    """MCPHandler implementation for a single CLI (leaf server)."""

    def __init__(self, cli: CLI, cached_tools: list[dict[str, Any]] | None = None) -> None:
        self._cli = cli
        self._cached_tools = cached_tools
        self._cached_version: int = cli._command_version
        self._ui_enabled = False
        self._logger = RequestLogger()

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        ui_enabled = _client_supports_ui(params)
        if ui_enabled != self._ui_enabled:
            self._cached_tools = None
        self._ui_enabled = ui_enabled
        return {
            "protocolVersion": _MCP_VERSION,
            "capabilities": _server_capabilities(include_ui=ui_enabled),
            "serverInfo": _server_info(self._cli),
            "instructions": self._cli.description,
        }

    def server_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "supportedVersions": list(_SUPPORTED_MCP_VERSIONS),
            "capabilities": _server_capabilities(include_ui=True),
            "serverInfo": _server_info(self._cli),
            "instructions": self._cli.description,
        }

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        new_correlation_id()
        start = time.monotonic()
        # Invalidate cache when commands have been added or removed
        if self._cached_tools is None or self._cached_version != self._cli._command_version:
            self._cached_tools = _list_tools(self._cli, include_ui=self._ui_enabled)
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
        resources = _list_resources(self._cli)
        if self._ui_enabled:
            resources += _list_ui_resources(self._cli)
        resources += _builtin_resources()
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
            if isinstance(uri, str) and uri.startswith("ui://"):
                result = _read_ui_resource(self._cli, params, enabled=self._ui_enabled)
            else:
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
    tools = _list_tools(cli, include_ui=False)
    tool_names = [t["name"] for t in tools]

    _stderr(f"MCP server ready — {cli.name}")
    _stderr(f"  Protocol:  {_MCP_VERSION}")
    _stderr(f"  Tools:     {len(tools)} ({', '.join(tool_names)})")
    _stderr(f"  Resources: {len(cli._resources) + len(cli._ui_resources)}")
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

    handler = _CLIHandler(cli)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parsed = _parse_request(line)
        if parsed is None:
            continue  # silent: error already sent via JSON-RPC
        req_id, method, params, is_notification = parsed

        try:
            result = dispatch(handler, method, params)
            if result is not None and not is_notification:
                _write_result(req_id, result)
        except Exception as e:
            if is_notification:
                continue  # silent: JSON-RPC notifications do not receive responses
            code, data = _classify_exception(e)
            _write_error(req_id, code, str(e), data=data)


def _classify_exception(exc: Exception) -> tuple[int, dict[str, Any] | None]:
    """Map an exception to a JSON-RPC error code and optional data payload.

    Returns (code, data) where:
    - MiloError with validation/config codes -> -32602 (Invalid params)
    - MiloError with not-found codes -> -32601 (Method not found)
    - All others -> -32603 (Internal error) with traceback in data

    When the MiloError carries ``argument`` or ``constraint`` context, those
    fields are included in the data payload so callers can tell agents *which*
    parameter failed and *what* constraint was violated.
    """
    import traceback as tb_mod

    from milo._errors import MiloError

    if isinstance(exc, MiloError):
        code_val = exc.code.value
        data = _milo_error_data(exc)
        # Validation-related error codes -> Invalid params
        if code_val.startswith(("M-CFG-", "M-FRM-", "M-INP-", "M-UI-")):
            return -32602, data
        # Not-found codes -> Method not found
        if code_val in ("M-CMD-001",):
            return -32601, data
        # Other MiloErrors -> Internal with structured data (plus traceback)
        data["traceback"] = "".join(tb_mod.format_exception(exc))
        return -32603, data

    if isinstance(exc, MethodNotFoundError):
        return -32601, {"type": type(exc).__name__}

    if isinstance(exc, UnsupportedProtocolVersionError):
        return exc.code, {
            "type": type(exc).__name__,
            "supported": exc.supported,
            "requested": exc.requested,
        }

    # Unknown exceptions -> Internal error with traceback
    return -32603, {
        "type": type(exc).__name__,
        "traceback": "".join(tb_mod.format_exception(exc)),
    }


def _milo_error_data(exc: Any) -> dict[str, Any]:
    """Build the structured data payload for a MiloError."""
    data: dict[str, Any] = {
        "errorCode": exc.code.value,
        "type": type(exc).__name__,
        "suggestion": exc.suggestion,
    }
    if getattr(exc, "argument", None):
        data["argument"] = exc.argument
    if getattr(exc, "constraint", None):
        data["constraint"] = exc.constraint
        example = _constraint_example(exc.constraint)
        if example is not None:
            data["example"] = example
    for key, value in getattr(exc, "context", {}).items():
        data.setdefault(key, value)
    return data


def _constraint_example(constraint: dict[str, Any]) -> Any:
    """Derive an example value from a JSON-Schema-style constraint dict.

    Never uses user input. Returns ``None`` when no safe example applies.
    """
    if constraint.get("enum"):
        return constraint["enum"][0]
    if "minLength" in constraint:
        return "x" * max(1, int(constraint["minLength"]))
    if "minimum" in constraint:
        return constraint["minimum"]
    if "exclusiveMinimum" in constraint:
        return constraint["exclusiveMinimum"] + 1
    if "pattern" in constraint:
        return None  # cannot safely synthesize
    return None


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


def _list_tools(cli: CLI, *, include_ui: bool = True) -> list[dict[str, Any]]:
    """Generate MCP tools/list response from all commands including groups.

    Group commands use dot-notation names: ``site.build``, ``site.config.show``.
    Includes outputSchema when return type annotations are available.
    Skips commands that fail to import with a warning.
    """
    from milo._command_defs import LazyImportError

    tools = []
    for dotted_name, cmd in cli.walk_commands():
        if _tool_is_hidden(cli, dotted_name, cmd):
            continue
        ui = getattr(cmd, "ui", None)
        if ui is not None and "model" not in ui.visibility:
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

        if ui is not None and include_ui:
            _validate_ui_link(cli, dotted_name, ui.resource_uri)
            from milo.mcp_apps import _tool_meta_to_protocol

            tool["_meta"] = _tool_meta_to_protocol(ui)

        tools.append(tool)
    return tools


def _validate_ui_link(cli: CLI, tool_name: str, resource_uri: str) -> None:
    """Require every advertised tool UI link to resolve on this server."""
    if resource_uri in cli._ui_resources:
        return
    from milo._errors import ErrorCode, MCPAppError

    raise MCPAppError(
        ErrorCode.UI_RESOURCE_NOT_FOUND,
        f"Tool {tool_name!r} references missing MCP Apps resource {resource_uri!r}.",
        context={
            "reason": "missing_ui_resource",
            "tool": tool_name,
            "resourceUri": resource_uri,
        },
        suggestion=f"Register {resource_uri!r} with cli.ui_resource().",
    )


def _tool_is_hidden(
    cli: CLI,
    dotted_name: str,
    command: CommandDef | LazyCommandDef,
) -> bool:
    """Return whether a tool or any group in its dotted path is hidden."""
    if command.hidden or "mcp" not in command.surfaces:
        return True

    parts = dotted_name.split(".")[:-1]
    groups = cli._groups
    aliases = cli._group_alias_map
    for part in parts:
        resolved = aliases.get(part, part)
        group = groups.get(resolved)
        if group is None:
            return False
        if group.hidden:
            return True
        groups = group._groups
        aliases = group._group_alias_map
    return False


def _ensure_public_tool(cli: CLI, tool_name: str) -> None:
    """Reject unknown or hidden tools before MCP dispatch resolves handlers."""
    from milo._errors import ErrorCode, MiloError

    command = cli.get_command(tool_name)
    hidden = command is not None and _tool_is_hidden(cli, tool_name, command)
    if command is None or hidden:
        reason = "hidden_command" if hidden else "unknown_tool"
        raise MiloError(
            ErrorCode.CMD_NOT_FOUND,
            f"Unknown tool: {tool_name!r}.",
            context={"reason": reason},
            suggestion="Call tools/list and use one of the advertised tool names.",
        )


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
        _ensure_public_tool(cli, tool_name)
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
        return _tool_error_response(e, tool_name, cli)

    text = _to_text(result)

    response: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
    }

    # Include structuredContent for structured data (dict, list, number, bool)
    if not isinstance(result, str) and result is not None:
        response["structuredContent"] = result

    return response


_MISSING_ARG_RE = re.compile(r"missing \d+ required (?:positional|keyword) argument(?:s)?: (.+)")
_UNEXPECTED_ARG_RE = re.compile(r"got an unexpected keyword argument '([^']+)'")


def _tool_error_response(exc: Exception, tool_name: str, cli: CLI) -> dict[str, Any]:
    """Build the ``tools/call`` error response with structured context.

    MiloError subclasses contribute their ``argument``, ``constraint``,
    ``suggestion``, and ``errorCode`` fields. Plain :class:`TypeError`
    messages about missing or unexpected keyword arguments are parsed so
    agents see which argument was wrong, and the ``schema`` field points
    them at the tool's declared parameter schema for repair.
    """
    from milo._errors import MiloError

    error_data: dict[str, Any] = {"tool": tool_name}

    if isinstance(exc, MiloError):
        error_data.update(_milo_error_data(exc))
    elif isinstance(exc, TypeError):
        match_missing = _MISSING_ARG_RE.search(str(exc))
        match_unexpected = _UNEXPECTED_ARG_RE.search(str(exc))
        if match_missing:
            raw = match_missing.group(1)
            names = [n.strip().strip("'\"") for n in raw.replace(" and ", ",").split(",") if n]
            error_data["argument"] = names[0] if len(names) == 1 else names
            error_data["reason"] = "missing_required_argument"
            error_data["suggestion"] = f"Provide {raw}."
        elif match_unexpected:
            error_data["argument"] = match_unexpected.group(1)
            error_data["reason"] = "unexpected_argument"
            error_data["suggestion"] = (
                f"Remove '{match_unexpected.group(1)}' — it is not a parameter of this tool."
            )
        error_data["type"] = "TypeError"

    schema = _tool_schema(cli, tool_name)
    if schema is not None:
        error_data["schema"] = schema

    return {
        "content": [{"type": "text", "text": f"Error: {exc}"}],
        "isError": True,
        "errorData": error_data,
    }


def _tool_schema(cli: CLI, tool_name: str) -> dict[str, Any] | None:
    """Return the input schema for a named tool, if known."""
    cmd = cli.get_command(tool_name)
    if cmd is None or _tool_is_hidden(cli, tool_name, cmd):
        return None
    try:
        schema = cmd.schema
    except Exception:  # silent: error enrichment must not mask the original tool failure
        return None
    return schema if isinstance(schema, dict) else None


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


def _list_ui_resources(cli: CLI) -> list[dict[str, Any]]:
    """Generate negotiated MCP Apps resources/list entries."""
    from milo.mcp_apps import _resource_meta_to_protocol

    resources: list[dict[str, Any]] = []
    for _uri, resource in cli.walk_ui_resources():
        item: dict[str, Any] = {
            "uri": resource.uri,
            "name": resource.name,
            "description": resource.description,
            "mimeType": resource.mime_type,
        }
        meta = _resource_meta_to_protocol(resource.meta)
        if meta:
            item["_meta"] = meta
        resources.append(item)
    return resources


def _ui_resource_error(
    code_name: str,
    message: str,
    *,
    reason: str,
    uri: str,
    suggestion: str,
):
    """Build a structured MCP Apps boundary error without exposing internals."""
    from milo._errors import ErrorCode, MCPAppError

    return MCPAppError(
        ErrorCode[code_name],
        message,
        context={"reason": reason, "resourceUri": uri},
        suggestion=suggestion,
    )


def _read_ui_resource(
    cli: CLI,
    params: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Read a negotiated MCP Apps HTML resource as text or a base64 blob."""
    from milo.mcp_apps import _resource_meta_to_protocol

    uri = params.get("uri")
    if not isinstance(uri, str) or not uri.startswith("ui://") or not uri[5:]:
        raise _ui_resource_error(
            "UI_INVALID_RESOURCE",
            "MCP Apps resource reads require a 'ui://' URI.",
            reason="invalid_ui_resource_uri",
            uri=str(uri or ""),
            suggestion="Call resources/list and use an advertised ui:// URI.",
        )
    if not enabled:
        raise _ui_resource_error(
            "UI_UNSUPPORTED",
            "MCP Apps UI support was not negotiated for this connection.",
            reason="ui_extension_not_negotiated",
            uri=uri,
            suggestion=(
                "Initialize with the io.modelcontextprotocol/ui extension and "
                "text/html;profile=mcp-app MIME type."
            ),
        )
    resource = cli._ui_resources.get(uri)
    if resource is None:
        raise _ui_resource_error(
            "UI_RESOURCE_NOT_FOUND",
            f"Unknown MCP Apps resource: {uri!r}.",
            reason="missing_ui_resource",
            uri=uri,
            suggestion="Call resources/list and use an advertised ui:// URI.",
        )

    try:
        if cli._middleware:
            from milo.context import Context as ContextClass
            from milo.middleware import MCPCall

            ctx = ContextClass()
            call = MCPCall(method="resources/read", name=uri, arguments={})
            result = cli._middleware.execute(ctx, call, lambda _call: resource.handler())
        else:
            result = resource.handler()
    except Exception as exc:
        raise _ui_resource_error(
            "UI_RESOURCE_READ",
            f"MCP Apps resource {uri!r} failed to render: {type(exc).__name__}: {exc}",
            reason="ui_resource_read_failed",
            uri=uri,
            suggestion="Fix the UI resource handler and retry resources/read.",
        ) from exc

    content: dict[str, Any] = {"uri": uri, "mimeType": resource.mime_type}
    if isinstance(result, str):
        content["text"] = result
    elif isinstance(result, bytes):
        content["blob"] = base64.b64encode(result).decode("ascii")
    else:
        raise _ui_resource_error(
            "UI_INVALID_RESOURCE",
            f"MCP Apps resource {uri!r} returned {type(result).__name__}, not str or bytes.",
            reason="invalid_ui_resource_content",
            uri=uri,
            suggestion="Return a valid HTML5 document as str or UTF-8 bytes.",
        )
    meta = _resource_meta_to_protocol(resource.meta)
    if meta:
        content["_meta"] = meta
    return {"contents": [content]}


def _read_resource(cli: CLI, params: dict[str, Any]) -> dict[str, Any]:
    """Handle resources/read by calling the resource handler."""
    uri = params.get("uri", "")

    if isinstance(uri, str) and uri.startswith("ui://"):
        return _read_ui_resource(cli, params, enabled=True)

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
