"""MCP server — expose CLI commands as tools via JSON-RPC on stdin/stdout."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from milo import __version__ as _SERVER_VERSION
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import _stderr, _write_error, _write_result
from milo._mcp_router import dispatch

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

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": _MCP_VERSION,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {
                "name": self._cli.name or _SERVER_NAME,
                "version": self._cli.version or _SERVER_VERSION,
                "title": self._cli.description,
            },
            "instructions": self._cli.description,
        }

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        tools = self._cached_tools if self._cached_tools is not None else _list_tools(self._cli)
        return {"tools": tools}

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        return _call_tool(self._cli, params)

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"resources": _list_resources(self._cli)}

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        return _read_resource(self._cli, params)

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"prompts": _list_prompts(self._cli)}

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        return _get_prompt(self._cli, params)


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
            continue

        req_id = request.get("id")
        method = request.get("method", "")

        try:
            result = dispatch(handler, method, request.get("params", {}))
            if result is not None:
                _write_result(req_id, result)
        except Exception as e:
            _write_error(req_id, -32603, str(e))


def _list_tools(cli: CLI) -> list[dict[str, Any]]:
    """Generate MCP tools/list response from all commands including groups.

    Group commands use dot-notation names: ``site.build``, ``site.config.show``.
    Includes outputSchema when return type annotations are available.
    """
    tools = []
    for dotted_name, cmd in cli.walk_commands():
        if cmd.hidden:
            continue
        tool: dict[str, Any] = {
            "name": dotted_name,
            "description": cmd.description,
            "inputSchema": cmd.schema,
        }

        # title: human-readable display name from docstring or description
        title = _tool_title(cmd)
        if title:
            tool["title"] = title

        # outputSchema: generated from handler return type annotation
        output_schema = _output_schema(cmd)
        if output_schema:
            tool["outputSchema"] = output_schema

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
    """Handle tools/call by dispatching to the command handler."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        result = cli.call(tool_name, **arguments)
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
