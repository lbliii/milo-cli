"""MCP server — expose CLI commands as tools via JSON-RPC on stdin/stdout."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from milo.commands import CLI, CommandDef, LazyCommandDef

_MCP_VERSION = "2025-11-25"
_SERVER_NAME = "milo"
_SERVER_VERSION = "0.1.0"


def run_mcp_server(cli: CLI) -> None:
    """Run MCP JSON-RPC server on stdin/stdout.

    Implements the MCP protocol (initialize, tools/list, tools/call).
    """
    tools = _list_tools(cli)
    tool_names = [t["name"] for t in tools]

    _stderr(f"MCP server ready — {cli.name}")
    _stderr(f"  Protocol:  {_MCP_VERSION}")
    _stderr(f"  Tools:     {len(tools)} ({', '.join(tool_names)})")
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
            result = _handle_method(cli, method, request.get("params", {}))
            if result is not None:
                _write_result(req_id, result)
        except Exception as e:
            _write_error(req_id, -32603, str(e))


def _handle_method(cli: CLI, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch an MCP method."""
    match method:
        case "initialize":
            return {
                "protocolVersion": _MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": cli.name or _SERVER_NAME,
                    "version": cli.version or _SERVER_VERSION,
                    "title": cli.description,
                },
                "instructions": cli.description,
            }
        case "notifications/initialized":
            # Client confirms initialization — no response required
            return None
        case "tools/list":
            return {"tools": _list_tools(cli)}
        case "tools/call":
            return _call_tool(cli, params)
        case _:
            raise ValueError(f"Unknown method: {method!r}")


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

    # Convert result to MCP content with structuredContent for non-string results
    text = result if isinstance(result, str) else json.dumps(result, indent=2, default=str)

    response: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
    }

    # Include structuredContent for structured data (dict, list, number, bool)
    if not isinstance(result, str) and result is not None:
        response["structuredContent"] = result

    return response


def _write_result(req_id: Any, result: dict[str, Any]) -> None:
    """Write a JSON-RPC success response."""
    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _write_error(req_id: Any, code: int, message: str) -> None:
    """Write a JSON-RPC error response."""
    response = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _stderr(message: str) -> None:
    """Write an informational line to stderr."""
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
