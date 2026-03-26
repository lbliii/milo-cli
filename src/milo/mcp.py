"""MCP server — expose CLI commands as tools via JSON-RPC on stdin/stdout."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from milo.commands import CLI

_MCP_VERSION = "2024-11-05"
_SERVER_NAME = "milo"
_SERVER_VERSION = "0.1.0"


def run_mcp_server(cli: CLI) -> None:
    """Run MCP JSON-RPC server on stdin/stdout.

    Implements the MCP protocol (initialize, tools/list, tools/call).
    """
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
            _write_result(req_id, result)
        except Exception as e:
            _write_error(req_id, -32603, str(e))


def _handle_method(cli: CLI, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an MCP method."""
    match method:
        case "initialize":
            return {
                "protocolVersion": _MCP_VERSION,
                "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
                "capabilities": {"tools": {}},
            }
        case "tools/list":
            return {"tools": _list_tools(cli)}
        case "tools/call":
            return _call_tool(cli, params)
        case _:
            raise ValueError(f"Unknown method: {method!r}")


def _list_tools(cli: CLI) -> list[dict[str, Any]]:
    """Generate MCP tools/list response from registered commands."""
    tools = []
    for cmd in cli.commands.values():
        if cmd.hidden:
            continue
        tools.append(
            {
                "name": cmd.name,
                "description": cmd.description,
                "inputSchema": cmd.schema,
            }
        )
    return tools


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

    # Convert result to MCP content
    text = result if isinstance(result, str) else json.dumps(result, indent=2, default=str)

    return {
        "content": [{"type": "text", "text": text}],
    }


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
