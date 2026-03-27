"""Milo MCP gateway — one MCP server that proxies to all registered CLIs.

Register this once with your AI host:

    claude mcp add milo -- uv run python -m milo.gateway --mcp

Then every CLI registered via ``--mcp-install`` is discoverable.
Tools are namespaced: ``taskman.add``, ``ghub.repo.list``, etc.

Can also be run directly for debugging:

    uv run python -m milo.gateway --mcp
    uv run python -m milo.gateway --list
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from milo.registry import list_clis

_MCP_VERSION = "2025-11-25"


def main() -> None:
    """Entry point for ``python -m milo.gateway``."""
    if "--list" in sys.argv:
        _print_registry()
        return
    if "--mcp" in sys.argv:
        _run_gateway()
        return
    # Default: show help
    sys.stderr.write("milo gateway — one MCP server for all your CLIs\n\n")
    sys.stderr.write("Usage:\n")
    sys.stderr.write("  python -m milo.gateway --mcp      Run as MCP server\n")
    sys.stderr.write("  python -m milo.gateway --list      List registered CLIs\n")
    sys.stderr.write("\nRegister CLIs with: myapp --mcp-install\n")


def _print_registry() -> None:
    """Print all registered CLIs."""
    clis = list_clis()
    if not clis:
        sys.stderr.write("No CLIs registered. Use --mcp-install on a milo CLI.\n")
        return
    for name, info in clis.items():
        desc = info.get("description", "")
        ver = info.get("version", "")
        cmd = " ".join(info.get("command", []))
        label = f"{name} {ver}".strip()
        sys.stdout.write(f"{label}\n")
        if desc:
            sys.stdout.write(f"  {desc}\n")
        sys.stdout.write(f"  {cmd}\n\n")


def _run_gateway() -> None:
    """Run the MCP gateway server."""
    clis = list_clis()

    # Discover tools from all registered CLIs
    all_tools, tool_routing = _discover_tools(clis)
    tool_names = [t["name"] for t in all_tools]

    _stderr("milo gateway ready")
    _stderr(f"  Protocol:  {_MCP_VERSION}")
    _stderr(f"  CLIs:      {len(clis)} ({', '.join(clis.keys()) if clis else 'none'})")
    _stderr(f"  Tools:     {len(all_tools)}")
    if tool_names:
        _stderr(f"  Available: {', '.join(tool_names)}")
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
            result = _handle_method(
                clis, all_tools, tool_routing, method, request.get("params", {})
            )
            if result is not None:
                _write_result(req_id, result)
        except Exception as e:
            _write_error(req_id, -32603, str(e))


def _discover_tools(
    clis: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Discover tools from all registered CLIs by calling tools/list.

    Returns (tools_list, routing_map) where routing_map maps
    namespaced tool name -> (cli_name, original_tool_name).
    """
    all_tools: list[dict[str, Any]] = []
    routing: dict[str, tuple[str, str]] = {}

    for cli_name, info in clis.items():
        command = info.get("command", [])
        if not command:
            continue

        try:
            tools = _fetch_tools(command)
        except Exception as e:
            _stderr(f"  Warning: failed to discover {cli_name}: {e}")
            continue

        for tool in tools:
            original_name = tool["name"]
            namespaced = f"{cli_name}.{original_name}"
            tool["name"] = namespaced
            if "title" not in tool:
                tool["title"] = f"{cli_name}: {tool.get('description', original_name)}"
            all_tools.append(tool)
            routing[namespaced] = (cli_name, original_name)

    return all_tools, routing


def _fetch_tools(command: list[str]) -> list[dict[str, Any]]:
    """Call tools/list on a CLI subprocess and return the tools."""
    # Send initialize + tools/list, read responses
    input_lines = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )
    result = subprocess.run(
        command,
        input=input_lines,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Parse the tools/list response (second line)
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            response = json.loads(line)
            if response.get("id") == 2:
                return response.get("result", {}).get("tools", [])
        except json.JSONDecodeError:
            continue
    return []


def _handle_method(
    clis: dict[str, dict[str, Any]],
    all_tools: list[dict[str, Any]],
    tool_routing: dict[str, tuple[str, str]],
    method: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Dispatch an MCP method."""
    match method:
        case "initialize":
            cli_names = list(clis.keys())
            return {
                "protocolVersion": _MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "milo-gateway",
                    "version": "0.1.0",
                    "title": "Milo Gateway",
                },
                "instructions": (
                    f"Gateway to {len(clis)} milo CLIs: {', '.join(cli_names)}. "
                    "Tools are namespaced as cli_name.command_name."
                ),
            }
        case "notifications/initialized":
            return None
        case "tools/list":
            return {"tools": all_tools}
        case "tools/call":
            return _proxy_call(clis, tool_routing, params)
        case _:
            raise ValueError(f"Unknown method: {method!r}")


def _proxy_call(
    clis: dict[str, dict[str, Any]],
    tool_routing: dict[str, tuple[str, str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Proxy a tools/call to the appropriate CLI subprocess."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in tool_routing:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name!r}"}],
            "isError": True,
        }

    cli_name, original_name = tool_routing[tool_name]
    info = clis.get(cli_name)
    if not info:
        return {
            "content": [{"type": "text", "text": f"CLI {cli_name!r} not found in registry"}],
            "isError": True,
        }

    command = info.get("command", [])
    call_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": original_name, "arguments": arguments},
    })

    # Send initialize + tools/call
    input_lines = (
        '{"jsonrpc":"2.0","id":0,"method":"initialize"}\n'
        f"{call_request}\n"
    )

    try:
        result = subprocess.run(
            command,
            input=input_lines,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {
            "content": [{"type": "text", "text": f"Timeout calling {cli_name}.{original_name}"}],
            "isError": True,
        }

    # Parse the tools/call response (second line)
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            response = json.loads(line)
            if response.get("id") == 1:
                return response.get("result", {})
        except json.JSONDecodeError:
            continue

    return {
        "content": [{"type": "text", "text": f"No response from {cli_name}"}],
        "isError": True,
    }


def _write_result(req_id: Any, result: dict[str, Any]) -> None:
    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _write_error(req_id: Any, code: int, message: str) -> None:
    response = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _stderr(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()
