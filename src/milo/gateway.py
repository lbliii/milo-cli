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
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from milo import __version__ as _server_version
from milo._child import ChildProcess
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import _stderr, _write_error, _write_result
from milo._mcp_router import dispatch
from milo.registry import list_clis

_logger = logging.getLogger("milo.gateway")


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
    """Print gateway status: registered CLIs, child health, and request metrics."""
    clis = list_clis()
    if not clis:
        sys.stdout.write("No CLIs registered. Use --mcp-install on a milo CLI.\n")
        return

    sys.stdout.write(f"Registered CLIs: {len(clis)}\n\n")

    for name, info in clis.items():
        ver = info.get("version", "")
        desc = info.get("description", "")
        label = f"  {name} {ver}".rstrip()
        sys.stdout.write(f"{label}\n")
        if desc:
            sys.stdout.write(f"    {desc}\n")

        # Probe child for stats and pipeline timeline
        command = info.get("command", [])
        if command:
            try:
                child = ChildProcess(name, command, request_timeout=5.0)
                try:
                    result = child.send_call("resources/read", {"uri": "milo://stats"})
                    contents = result.get("contents", [])
                    if contents:
                        import json as _json

                        stats = _json.loads(contents[0].get("text", "{}"))
                        total = stats.get("total", 0)
                        errors = stats.get("errors", 0)
                        avg_ms = stats.get("avg_latency_ms", 0.0)
                        sys.stdout.write(
                            f"    requests: {total}  errors: {errors}  avg_latency: {avg_ms}ms\n"
                        )
                except Exception as e:
                    sys.stdout.write(f"    status: unreachable ({e})\n")

                try:
                    result = child.send_call("resources/read", {"uri": "milo://pipeline/timeline"})
                    contents = result.get("contents", [])
                    if contents:
                        import json as _json

                        timeline = _json.loads(contents[0].get("text", "{}"))
                        if timeline.get("pipeline"):
                            pipe_name = timeline["pipeline"]
                            pipe_status = timeline["status"]
                            n_phases = len(timeline.get("phases", []))
                            sys.stdout.write(
                                f"    pipeline: {pipe_name} ({pipe_status}, {n_phases} phases)\n"
                            )
                except Exception as e:
                    _logger.debug("Failed to read pipeline timeline from %s: %s", name, e)
            finally:
                child.kill()

        sys.stdout.write("\n")


def _run_gateway() -> None:
    """Run the MCP gateway server with persistent child processes."""
    clis = list_clis()

    # Create persistent children for each CLI
    children: dict[str, ChildProcess] = {}
    for cli_name, info in clis.items():
        command = info.get("command", [])
        if command:
            children[cli_name] = ChildProcess(cli_name, command)

    # Discover tools, resources, and prompts from all CLIs in parallel
    discovery = _discover_all(clis, children)
    all_tools = discovery.tools
    tool_names = [t["name"] for t in all_tools]
    all_resources = discovery.resources
    all_prompts = discovery.prompts

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

    handler = _GatewayHandler(clis, discovery, children)

    try:
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


@dataclass
class GatewayState:
    """Bundled discovery results for the gateway."""

    tools: list[dict[str, Any]]
    tool_routing: dict[str, tuple[str, str]]
    resources: list[dict[str, Any]]
    resource_routing: dict[str, tuple[str, str]]
    prompts: list[dict[str, Any]]
    prompt_routing: dict[str, tuple[str, str]]


def _discover_one_child(
    cli_name: str,
    child: ChildProcess,
) -> tuple[str, list[dict], list[dict], list[dict]]:
    """Discover tools, resources, and prompts from a single child."""
    tools: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    prompts: list[dict[str, Any]] = []

    try:
        tools = child.fetch_tools()
    except Exception as e:
        _stderr(f"  Warning: failed to discover tools from {cli_name}: {e}")

    try:
        result = child.send_call("resources/list", {})
        resources = result.get("resources", [])
    except Exception as e:
        _logger.warning("Failed to discover resources from %s: %s", cli_name, e)

    try:
        result = child.send_call("prompts/list", {})
        prompts = result.get("prompts", [])
    except Exception as e:
        _logger.warning("Failed to discover prompts from %s: %s", cli_name, e)

    return cli_name, tools, resources, prompts


def _discover_all(
    clis: dict[str, dict[str, Any]],
    children: dict[str, ChildProcess],
) -> GatewayState:
    """Discover tools, resources, and prompts from all CLIs in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_tools: list[dict[str, Any]] = []
    tool_routing: dict[str, tuple[str, str]] = {}
    all_resources: list[dict[str, Any]] = []
    resource_routing: dict[str, tuple[str, str]] = {}
    all_prompts: list[dict[str, Any]] = []
    prompt_routing: dict[str, tuple[str, str]] = {}

    # Discover all children in parallel
    valid_children = {name: children[name] for name in clis if name in children}
    if not valid_children:
        return GatewayState([], {}, [], {}, [], {})

    from kida import WorkloadType, get_optimal_workers

    max_workers = get_optimal_workers(len(valid_children), workload_type=WorkloadType.IO_BOUND)
    results: dict[str, tuple[str, list, list, list]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_discover_one_child, name, child): name
            for name, child in valid_children.items()
        }
        for future in as_completed(futures):
            cli_name, tools, resources, prompts = future.result()
            results[cli_name] = (cli_name, tools, resources, prompts)

    # Merge results in original CLI order for deterministic output
    for cli_name in clis:
        if cli_name not in results:
            continue
        _, tools, resources, prompts = results[cli_name]

        for tool in tools:
            original_name = tool["name"]
            namespaced = f"{cli_name}.{original_name}"
            tool["name"] = namespaced
            if "title" not in tool:
                tool["title"] = f"{cli_name}: {tool.get('description', original_name)}"
            all_tools.append(tool)
            tool_routing[namespaced] = (cli_name, original_name)

        for resource in resources:
            original_uri = resource["uri"]
            namespaced_uri = f"{cli_name}/{original_uri}"
            resource["uri"] = namespaced_uri
            all_resources.append(resource)
            resource_routing[namespaced_uri] = (cli_name, original_uri)

        for prompt in prompts:
            original_name = prompt["name"]
            namespaced = f"{cli_name}.{original_name}"
            prompt["name"] = namespaced
            all_prompts.append(prompt)
            prompt_routing[namespaced] = (cli_name, original_name)

    return GatewayState(
        tools=all_tools,
        tool_routing=tool_routing,
        resources=all_resources,
        resource_routing=resource_routing,
        prompts=all_prompts,
        prompt_routing=prompt_routing,
    )


class _GatewayHandler:
    """MCPHandler implementation for the gateway (proxy to children)."""

    def __init__(
        self,
        clis: dict[str, dict[str, Any]],
        state: GatewayState,
        children: dict[str, ChildProcess],
    ) -> None:
        self._clis = clis
        self._state = state
        self._children = children

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        cli_names = list(self._clis.keys())
        return {
            "protocolVersion": _MCP_VERSION,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {
                "name": "milo-gateway",
                "version": _server_version,
                "title": "Milo Gateway",
            },
            "instructions": (
                f"Gateway to {len(self._clis)} milo CLIs: {', '.join(cli_names)}. "
                "Tools are namespaced as cli_name.command_name."
            ),
        }

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"tools": self._state.tools}

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        return _proxy_call(self._children, self._state.tool_routing, params)

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"resources": self._state.resources}

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        return _proxy_resource(self._children, self._state.resource_routing, params)

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"prompts": self._state.prompts}

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        return _proxy_prompt(self._children, self._state.prompt_routing, params)


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
