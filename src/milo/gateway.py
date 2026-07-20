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

import logging
import sys
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from milo import __version__ as _server_version
from milo._child import ChildProcess
from milo._jsonrpc import LEGACY_MCP_VERSION as _LEGACY_MCP_VERSION
from milo._jsonrpc import MCP_VERSION as _MCP_VERSION
from milo._jsonrpc import SUPPORTED_MCP_VERSIONS as _SUPPORTED_MCP_VERSIONS
from milo._jsonrpc import _parse_request, _stderr, _write_error, _write_result
from milo._mcp_router import dispatch
from milo.registry import list_clis

_logger = logging.getLogger("milo.gateway")


def _gateway_capabilities(*, include_ui: bool = False) -> dict[str, Any]:
    capabilities: dict[str, Any] = {"tools": {}, "resources": {}, "prompts": {}}
    if include_ui:
        from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

        capabilities["extensions"] = {MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}}
    return capabilities


def _gateway_ui_uri(cli_name: str, resource_uri: str) -> str:
    """Return a collision-free stable UI URI for one child resource."""
    encoded_cli = quote(cli_name, safe="")
    encoded_resource = quote(resource_uri, safe="")
    return f"ui://milo-gateway/{encoded_cli}/{encoded_resource}"


def _gateway_server_info() -> dict[str, Any]:
    return {
        "name": "milo-gateway",
        "version": _server_version,
        "title": "Milo Gateway",
    }


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
                    _write_child_protocol_status(child)
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


def _write_child_protocol_status(child: ChildProcess) -> None:
    mode = child.protocol_mode
    version = child.protocol_version or "unknown"
    sys.stdout.write(f"    protocol: {mode} ({version})\n")
    if child.last_error:
        sys.stdout.write(f"    last_error: {child.last_error}\n")


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
    _stderr(f"  Protocols: {_MCP_VERSION}, {_LEGACY_MCP_VERSION}")
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
                code, data = _classify_gateway_exception(e)
                _write_error(req_id, code, str(e), data=data)
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


def _classify_gateway_exception(exc: Exception) -> tuple[int, dict[str, Any] | None]:
    from milo.mcp import _classify_exception

    return _classify_exception(exc)


@dataclass
class GatewayState:
    """Bundled discovery results for the gateway."""

    tools: list[dict[str, Any]]
    tool_routing: dict[str, tuple[str, str]]
    resources: list[dict[str, Any]]
    resource_routing: dict[str, tuple[str, str]]
    prompts: list[dict[str, Any]]
    prompt_routing: dict[str, tuple[str, str]]
    ui_resource_uris: frozenset[str] = frozenset()


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

    from milo.mcp_apps import MCP_APPS_MIME_TYPE

    all_tools: list[dict[str, Any]] = []
    tool_routing: dict[str, tuple[str, str]] = {}
    all_resources: list[dict[str, Any]] = []
    resource_routing: dict[str, tuple[str, str]] = {}
    all_prompts: list[dict[str, Any]] = []
    prompt_routing: dict[str, tuple[str, str]] = {}
    ui_resource_uris: set[str] = set()

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

        child_ui_resource_uris: dict[str, str] = {}
        for resource in resources:
            original_uri = resource.get("uri")
            if not isinstance(original_uri, str) or not original_uri:
                _logger.warning("Ignoring resource without a valid URI from %s", cli_name)
                continue

            mime_type = resource.get("mimeType")
            ui_candidate = original_uri.startswith("ui://") or mime_type == MCP_APPS_MIME_TYPE
            if ui_candidate and not (
                original_uri.startswith("ui://") and mime_type == MCP_APPS_MIME_TYPE
            ):
                _logger.warning(
                    "Ignoring malformed MCP Apps resource from %s: %s", cli_name, original_uri
                )
                continue

            namespaced_uri = (
                _gateway_ui_uri(cli_name, original_uri)
                if ui_candidate
                else f"{cli_name}/{original_uri}"
            )
            if namespaced_uri in resource_routing:
                _logger.warning("Ignoring duplicate resource from %s: %s", cli_name, original_uri)
                continue

            exposed_resource = deepcopy(resource)
            exposed_resource["uri"] = namespaced_uri
            all_resources.append(exposed_resource)
            resource_routing[namespaced_uri] = (cli_name, original_uri)
            if ui_candidate:
                child_ui_resource_uris[original_uri] = namespaced_uri
                ui_resource_uris.add(namespaced_uri)

        for tool in tools:
            original_name = tool.get("name")
            if not isinstance(original_name, str) or not original_name:
                _logger.warning("Ignoring tool without a valid name from %s", cli_name)
                continue
            namespaced = f"{cli_name}.{original_name}"
            if namespaced in tool_routing:
                _logger.warning("Ignoring duplicate tool from %s: %s", cli_name, original_name)
                continue

            exposed_tool = deepcopy(tool)
            exposed_tool["name"] = namespaced
            if "title" not in exposed_tool:
                exposed_tool["title"] = (
                    f"{cli_name}: {exposed_tool.get('description', original_name)}"
                )
            meta = exposed_tool.get("_meta")
            if isinstance(meta, dict):
                ui = meta.get("ui")
                if "ui" in meta and not isinstance(ui, dict):
                    meta.pop("ui")
                elif isinstance(ui, dict) and "resourceUri" in ui:
                    resource_uri = ui.get("resourceUri")
                    gateway_uri = (
                        child_ui_resource_uris.get(resource_uri)
                        if isinstance(resource_uri, str)
                        else None
                    )
                    if gateway_uri is None:
                        _logger.warning(
                            "Removing broken MCP Apps link from %s.%s: %s",
                            cli_name,
                            original_name,
                            resource_uri,
                        )
                        ui.pop("resourceUri", None)
                        if not ui:
                            meta.pop("ui", None)
                    else:
                        ui["resourceUri"] = gateway_uri
                if not meta:
                    exposed_tool.pop("_meta", None)

            all_tools.append(exposed_tool)
            tool_routing[namespaced] = (cli_name, original_name)

        for prompt in prompts:
            original_name = prompt.get("name")
            if not isinstance(original_name, str) or not original_name:
                _logger.warning("Ignoring prompt without a valid name from %s", cli_name)
                continue
            namespaced = f"{cli_name}.{original_name}"
            if namespaced in prompt_routing:
                _logger.warning("Ignoring duplicate prompt from %s: %s", cli_name, original_name)
                continue
            exposed_prompt = deepcopy(prompt)
            exposed_prompt["name"] = namespaced
            all_prompts.append(exposed_prompt)
            prompt_routing[namespaced] = (cli_name, original_name)

    return GatewayState(
        tools=all_tools,
        tool_routing=tool_routing,
        resources=all_resources,
        resource_routing=resource_routing,
        prompts=all_prompts,
        prompt_routing=prompt_routing,
        ui_resource_uris=frozenset(ui_resource_uris),
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
        self._ui_enabled = False
        self._fallback_tools = [_without_ui_metadata(tool) for tool in state.tools]
        self._fallback_resources = [
            resource
            for resource in state.resources
            if resource.get("uri") not in state.ui_resource_uris
        ]

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        from milo.mcp import _client_supports_ui

        self._ui_enabled = _client_supports_ui(params)
        return {
            "protocolVersion": _LEGACY_MCP_VERSION,
            "capabilities": _gateway_capabilities(include_ui=self._ui_enabled),
            "serverInfo": _gateway_server_info(),
            "instructions": self._instructions(),
        }

    def server_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "supportedVersions": list(_SUPPORTED_MCP_VERSIONS),
            "capabilities": _gateway_capabilities(include_ui=True),
            "serverInfo": _gateway_server_info(),
            "instructions": self._instructions(),
        }

    def _instructions(self) -> str:
        cli_names = list(self._clis.keys())
        return (
            f"Gateway to {len(self._clis)} milo CLIs: {', '.join(cli_names)}. "
            "Tools are namespaced as cli_name.command_name."
        )

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        tools = self._state.tools if self._ui_enabled_for(params) else self._fallback_tools
        return {"tools": tools}

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        return _proxy_call(self._children, self._state.tool_routing, params)

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]:
        resources = (
            self._state.resources if self._ui_enabled_for(params) else self._fallback_resources
        )
        return {"resources": resources}

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri", "")
        is_gateway_ui = isinstance(uri, str) and uri.startswith("ui://milo-gateway/")
        if is_gateway_ui and not self._ui_enabled_for(params):
            from milo._errors import ErrorCode, MCPAppError

            raise MCPAppError(
                ErrorCode.UI_UNSUPPORTED,
                "MCP Apps UI support was not negotiated for this gateway connection.",
                context={
                    "reason": "ui_extension_not_negotiated",
                    "resourceUri": uri,
                },
                suggestion=(
                    "Initialize with the io.modelcontextprotocol/ui extension and "
                    "text/html;profile=mcp-app MIME type."
                ),
            )
        return _proxy_resource(self._children, self._state.resource_routing, params)

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"prompts": self._state.prompts}

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        return _proxy_prompt(self._children, self._state.prompt_routing, params)

    def _ui_enabled_for(self, params: dict[str, Any]) -> bool:
        """Use connection state, or per-request capabilities for stateless clients."""
        meta = params.get("_meta")
        if isinstance(meta, dict) and "io.modelcontextprotocol/clientCapabilities" in meta:
            from milo.mcp import _client_supports_ui

            return _client_supports_ui(params)
        return self._ui_enabled


def _without_ui_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    """Copy a tool descriptor while preserving non-UI metadata."""
    fallback = deepcopy(tool)
    meta = fallback.get("_meta")
    if not isinstance(meta, dict):
        return fallback
    meta.pop("ui", None)
    if not meta:
        fallback.pop("_meta", None)
    return fallback


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
            "errorData": {
                "tool": tool_name,
                "errorCode": "M-CMD-001",
                "reason": "unknown_tool",
                "suggestion": "Call tools/list and use one of the advertised tool names.",
            },
        }

    cli_name, original_name = tool_routing[tool_name]
    child = children.get(cli_name)
    if not child:
        return {
            "content": [{"type": "text", "text": f"CLI {cli_name!r} not available"}],
            "isError": True,
            "errorData": {
                "tool": tool_name,
                "errorCode": "M-CMD-001",
                "reason": "cli_unavailable",
                "suggestion": "Restart the gateway or repair the registered CLI command.",
            },
        }

    result = child.send_call(
        "tools/call",
        {"name": original_name, "arguments": arguments, **_forwarded_meta(params)},
    )
    if "error" in result:
        error = result["error"]
        return {
            "content": [{"type": "text", "text": error.get("message", "Unknown error")}],
            "isError": True,
            "errorData": error.get("data", {}),
        }
    return result


def _proxy_resource(
    children: dict[str, ChildProcess],
    resource_routing: dict[str, tuple[str, str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Proxy a resources/read to the appropriate child process."""
    uri = params.get("uri", "")
    is_ui = isinstance(uri, str) and uri.startswith("ui://milo-gateway/")
    if uri not in resource_routing:
        if is_ui:
            from milo._errors import ErrorCode, MCPAppError

            raise MCPAppError(
                ErrorCode.UI_RESOURCE_NOT_FOUND,
                f"Unknown gateway MCP Apps resource: {uri!r}.",
                context={
                    "reason": "unknown_gateway_ui_resource",
                    "resourceUri": uri,
                },
                suggestion="Call resources/list and use an advertised ui:// URI.",
            )
        from milo._mcp_router import ResourceNotFoundError

        raise ResourceNotFoundError(str(uri))

    cli_name, original_uri = resource_routing[uri]
    child = children.get(cli_name)
    if not child:
        if is_ui:
            from milo._errors import ErrorCode, MCPAppError

            raise MCPAppError(
                ErrorCode.UI_RESOURCE_READ,
                f"MCP Apps child {cli_name!r} is not available.",
                context={
                    "reason": "cli_unavailable",
                    "child": cli_name,
                    "resourceUri": uri,
                    "originalResourceUri": original_uri,
                },
                suggestion="Restart the gateway or repair the registered CLI command.",
            )
        raise RuntimeError(f"MCP child {cli_name!r} is not available for resources/read")

    try:
        result = child.send_call(
            "resources/read",
            {"uri": original_uri, **_forwarded_meta(params)},
        )
    except Exception as exc:
        if not is_ui:
            raise
        from milo._errors import ErrorCode, MCPAppError

        raise MCPAppError(
            ErrorCode.UI_RESOURCE_READ,
            f"MCP Apps child {cli_name!r} failed during resource read: {exc}",
            context={
                "reason": "child_transport_error",
                "child": cli_name,
                "resourceUri": uri,
                "originalResourceUri": original_uri,
            },
            suggestion="Retry the read or inspect the child CLI's gateway status.",
        ) from exc
    error = result.get("error")
    if is_ui and isinstance(error, dict):
        from milo._errors import ErrorCode, MCPAppError

        child_data = error.get("data")
        reason = (
            child_data.get("reason")
            if isinstance(child_data, dict) and isinstance(child_data.get("reason"), str)
            else "child_resource_error"
        )
        raise MCPAppError(
            ErrorCode.UI_RESOURCE_READ,
            error.get("message", f"MCP Apps child {cli_name!r} failed to read the resource."),
            context={
                "reason": reason,
                "child": cli_name,
                "childCode": error.get("code"),
                "resourceUri": uri,
                "originalResourceUri": original_uri,
            },
            suggestion="Retry the read or inspect the child CLI's gateway status.",
        )

    if not is_ui:
        return result

    exposed = deepcopy(result)
    for content in exposed.get("contents", []):
        if isinstance(content, dict):
            content["uri"] = uri
    return exposed


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
        "prompts/get",
        {
            "name": original_name,
            "arguments": params.get("arguments", {}),
            **_forwarded_meta(params),
        },
    )


def _forwarded_meta(params: dict[str, Any]) -> dict[str, Any]:
    """Preserve request metadata for the child; ChildProcess sets its own identity."""
    meta = params.get("_meta")
    return {"_meta": dict(meta)} if isinstance(meta, dict) else {}


if __name__ == "__main__":
    main()
