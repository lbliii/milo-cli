"""Milo MCP gateway — one MCP server that proxies to all registered CLIs.

Register this once with your AI host:

    claude mcp add milo -- uv run python -m milo.gateway --mcp

Then every CLI registered via ``--mcp-install`` is discoverable.
Tools are namespaced: ``taskman.add``, ``ghub.repo.list``, etc.

Can also be run directly for debugging:

    uv run python -m milo.gateway --mcp
    uv run python -m milo.gateway --list
    uv run python -m milo.gateway --doctor
    uv run python -m milo.gateway --status
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any

from milo._child import ChildProcess
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import _stderr, _write_error, _write_result
from milo.registry import list_clis


def main() -> None:
    """Entry point for ``python -m milo.gateway``."""
    if "--list" in sys.argv:
        _print_registry()
        return
    if "--doctor" in sys.argv:
        from milo.registry import doctor

        sys.stdout.write(doctor())
        return
    if "--status" in sys.argv:
        _print_status()
        return
    if "--mcp" in sys.argv:
        _run_gateway()
        return
    # Default: show help
    sys.stderr.write("milo gateway — one MCP server for all your CLIs\n\n")
    sys.stderr.write("Usage:\n")
    sys.stderr.write("  python -m milo.gateway --mcp      Run as MCP server\n")
    sys.stderr.write("  python -m milo.gateway --list      List registered CLIs\n")
    sys.stderr.write("  python -m milo.gateway --doctor    Health check all CLIs\n")
    sys.stderr.write("  python -m milo.gateway --status    Show stats and children\n")
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


def _print_status() -> None:
    """Print gateway status (placeholder for F7 observability)."""
    clis = list_clis()
    sys.stdout.write(f"Registered CLIs: {len(clis)}\n")
    for name in clis:
        sys.stdout.write(f"  {name}\n")


def _run_gateway() -> None:
    """Run the MCP gateway server with persistent child processes."""
    clis = list_clis()

    # Create persistent children for each CLI
    children: dict[str, ChildProcess] = {}
    for cli_name, info in clis.items():
        command = info.get("command", [])
        if command:
            children[cli_name] = ChildProcess(cli_name, command)

    # Discover tools from all registered CLIs
    all_tools, tool_routing = _discover_tools(clis, children)
    tool_names = [t["name"] for t in all_tools]

    # Discover resources and prompts
    all_resources, resource_routing = _discover_resources(clis, children)
    all_prompts, prompt_routing = _discover_prompts(clis, children)

    _stderr("milo gateway ready")
    _stderr(f"  Protocol:  {_MCP_VERSION}")
    _stderr(f"  CLIs:      {len(clis)} ({', '.join(clis.keys()) if clis else 'none'})")
    _stderr(f"  Tools:     {len(all_tools)}")
    _stderr(f"  Resources: {len(all_resources)}")
    _stderr(f"  Prompts:   {len(all_prompts)}")
    if tool_names:
        _stderr(f"  Available: {', '.join(tool_names)}")
    _stderr("")
    _stderr("Press Ctrl+C to stop.")
    _stderr("")

    # Start idle reaper thread
    reaper = threading.Thread(target=_idle_reaper, args=(children,), daemon=True)
    reaper.start()

    try:
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
                    clis,
                    all_tools,
                    tool_routing,
                    all_resources,
                    resource_routing,
                    all_prompts,
                    prompt_routing,
                    children,
                    method,
                    request.get("params", {}),
                )
                if result is not None:
                    _write_result(req_id, result)
            except Exception as e:
                _write_error(req_id, -32603, str(e))
    finally:
        # Clean up children on exit
        for child in children.values():
            child.kill()


def _idle_reaper(children: dict[str, ChildProcess]) -> None:
    """Periodically check and kill idle children."""
    while True:
        time.sleep(60)
        for child in list(children.values()):
            if child.is_idle():
                _stderr(f"  Reaping idle child: {child.name}")
                child.kill()


def _discover_tools(
    clis: dict[str, dict[str, Any]],
    children: dict[str, ChildProcess],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Discover tools from all registered CLIs via persistent children."""
    all_tools: list[dict[str, Any]] = []
    routing: dict[str, tuple[str, str]] = {}

    for cli_name in clis:
        child = children.get(cli_name)
        if not child:
            continue

        try:
            tools = child.fetch_tools()
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


def _discover_resources(
    clis: dict[str, dict[str, Any]],
    children: dict[str, ChildProcess],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Discover resources from all registered CLIs."""
    all_resources: list[dict[str, Any]] = []
    routing: dict[str, tuple[str, str]] = {}

    for cli_name in clis:
        child = children.get(cli_name)
        if not child:
            continue

        try:
            result = child.send_call("resources/list", {})
            resources = result.get("resources", [])
        except Exception:
            continue

        for resource in resources:
            original_uri = resource["uri"]
            namespaced_uri = f"{cli_name}/{original_uri}"
            resource["uri"] = namespaced_uri
            all_resources.append(resource)
            routing[namespaced_uri] = (cli_name, original_uri)

    return all_resources, routing


def _discover_prompts(
    clis: dict[str, dict[str, Any]],
    children: dict[str, ChildProcess],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Discover prompts from all registered CLIs."""
    all_prompts: list[dict[str, Any]] = []
    routing: dict[str, tuple[str, str]] = {}

    for cli_name in clis:
        child = children.get(cli_name)
        if not child:
            continue

        try:
            result = child.send_call("prompts/list", {})
            prompts = result.get("prompts", [])
        except Exception:
            continue

        for prompt in prompts:
            original_name = prompt["name"]
            namespaced = f"{cli_name}.{original_name}"
            prompt["name"] = namespaced
            all_prompts.append(prompt)
            routing[namespaced] = (cli_name, original_name)

    return all_prompts, routing


def _handle_method(
    clis: dict[str, dict[str, Any]],
    all_tools: list[dict[str, Any]],
    tool_routing: dict[str, tuple[str, str]],
    all_resources: list[dict[str, Any]],
    resource_routing: dict[str, tuple[str, str]],
    all_prompts: list[dict[str, Any]],
    prompt_routing: dict[str, tuple[str, str]],
    children: dict[str, ChildProcess],
    method: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Dispatch an MCP method."""
    match method:
        case "initialize":
            cli_names = list(clis.keys())
            return {
                "protocolVersion": _MCP_VERSION,
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
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
            return _proxy_call(children, tool_routing, params)
        case "resources/list":
            return {"resources": all_resources}
        case "resources/read":
            return _proxy_resource(children, resource_routing, params)
        case "prompts/list":
            return {"prompts": all_prompts}
        case "prompts/get":
            return _proxy_prompt(children, prompt_routing, params)
        case _:
            raise ValueError(f"Unknown method: {method!r}")


def _proxy_call(
    children: dict[str, ChildProcess],
    tool_routing: dict[str, tuple[str, str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Proxy a tools/call to the appropriate child process."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in tool_routing:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name!r}"}],
            "isError": True,
        }

    cli_name, original_name = tool_routing[tool_name]
    child = children.get(cli_name)
    if not child:
        return {
            "content": [{"type": "text", "text": f"CLI {cli_name!r} not available"}],
            "isError": True,
        }

    result = child.send_call("tools/call", {"name": original_name, "arguments": arguments})
    if "error" in result:
        return {
            "content": [{"type": "text", "text": result["error"].get("message", "Unknown error")}],
            "isError": True,
        }
    return result


def _proxy_resource(
    children: dict[str, ChildProcess],
    resource_routing: dict[str, tuple[str, str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Proxy a resources/read to the appropriate child process."""
    uri = params.get("uri", "")
    if uri not in resource_routing:
        return {"contents": []}

    cli_name, original_uri = resource_routing[uri]
    child = children.get(cli_name)
    if not child:
        return {"contents": []}

    return child.send_call("resources/read", {"uri": original_uri})


def _proxy_prompt(
    children: dict[str, ChildProcess],
    prompt_routing: dict[str, tuple[str, str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Proxy a prompts/get to the appropriate child process."""
    name = params.get("name", "")
    if name not in prompt_routing:
        return {"messages": []}

    cli_name, original_name = prompt_routing[name]
    child = children.get(cli_name)
    if not child:
        return {"messages": []}

    return child.send_call(
        "prompts/get", {"name": original_name, "arguments": params.get("arguments", {})}
    )




if __name__ == "__main__":
    main()
