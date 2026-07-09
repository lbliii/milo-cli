"""Shared MCP method dispatch for leaf servers and gateway."""

from __future__ import annotations

from typing import Any, Protocol

from milo._jsonrpc import (
    LEGACY_MCP_VERSION,
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
    SUPPORTED_MCP_VERSIONS,
    UNSUPPORTED_PROTOCOL_VERSION,
)


class MethodNotFoundError(ValueError):
    """Raised when a JSON-RPC method is not implemented."""


class UnsupportedProtocolVersionError(ValueError):
    """Raised when per-request metadata asks for an unsupported MCP version."""

    code = UNSUPPORTED_PROTOCOL_VERSION

    def __init__(self, requested: str) -> None:
        self.requested = requested
        self.supported = list(SUPPORTED_MCP_VERSIONS)
        super().__init__(f"Unsupported protocol version: {requested}")


class InvalidRequestMetadataError(ValueError):
    """Raised when a modern request omits required per-request metadata."""

    code = -32602

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Modern MCP request metadata is missing: {', '.join(missing)}")


class ResourceNotFoundError(ValueError):
    """Raised when resources/read names a URI the server does not expose."""

    code = -32602

    def __init__(self, uri: str) -> None:
        self.uri = uri
        super().__init__(f"Unknown resource: {uri!r}")


class MCPHandler(Protocol):
    """Protocol for MCP method handlers.

    Implemented by the leaf MCP server (direct CLI calls) and the
    gateway (proxy to child processes). The router dispatches to the
    appropriate method without duplicating the match/case structure.
    """

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def server_discover(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def list_tools(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def list_resources(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def read_resource(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def list_prompts(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def get_prompt(self, params: dict[str, Any]) -> dict[str, Any]: ...


def dispatch(handler: MCPHandler, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Route an MCP method to the appropriate handler method.

    Returns None for notification methods (no response required).
    Raises ValueError for unknown methods.
    """
    protocol_version = _validate_requested_protocol(params)
    match method:
        case "initialize":
            if protocol_version == MCP_VERSION:
                raise MethodNotFoundError("initialize is not part of modern MCP")
            result = handler.initialize(params)
        case "server/discover":
            result = handler.server_discover(params)
        case "notifications/initialized":
            if protocol_version == MCP_VERSION:
                raise MethodNotFoundError("notifications/initialized is not part of modern MCP")
            return None
        case "tools/list":
            result = handler.list_tools(params)
        case "tools/call":
            result = handler.call_tool(params)
        case "resources/list":
            result = handler.list_resources(params)
        case "resources/read":
            result = handler.read_resource(params)
        case "prompts/list":
            result = handler.list_prompts(params)
        case "prompts/get":
            result = handler.get_prompt(params)
        case _:
            raise MethodNotFoundError(f"Unknown method: {method!r}")
    return _decorate_result(method, protocol_version, result)


def _validate_requested_protocol(params: dict[str, Any]) -> str:
    """Reject explicit per-request MCP versions Milo does not implement.

    Legacy 2025-11-25 clients negotiate with ``initialize`` and do not send
    request metadata, so absent metadata remains accepted for backward
    compatibility.
    """
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return LEGACY_MCP_VERSION
    required_keys = (
        MCP_PROTOCOL_VERSION_META_KEY,
        MCP_CLIENT_INFO_META_KEY,
        MCP_CLIENT_CAPABILITIES_META_KEY,
    )
    requested = meta.get(MCP_PROTOCOL_VERSION_META_KEY)
    if requested is None:
        if any(key in meta for key in required_keys[1:]):
            raise InvalidRequestMetadataError([MCP_PROTOCOL_VERSION_META_KEY])
        return LEGACY_MCP_VERSION
    if requested not in SUPPORTED_MCP_VERSIONS:
        raise UnsupportedProtocolVersionError(str(requested))
    if requested == MCP_VERSION:
        missing = [key for key in required_keys[1:] if not isinstance(meta.get(key), dict)]
        client_info = meta.get(MCP_CLIENT_INFO_META_KEY)
        if isinstance(client_info, dict):
            missing.extend(
                f"{MCP_CLIENT_INFO_META_KEY}.{field}"
                for field in ("name", "version")
                if not isinstance(client_info.get(field), str) or not client_info[field]
            )
        if missing:
            raise InvalidRequestMetadataError(missing)
    return str(requested)


def _decorate_result(
    method: str,
    protocol_version: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Add modern result and cache metadata without changing legacy replies."""
    modern = protocol_version == MCP_VERSION or method == "server/discover"
    if not modern:
        return result
    decorated = dict(result)
    decorated.setdefault("resultType", "complete")
    if method in {"tools/list", "resources/list", "prompts/list"}:
        decorated.setdefault("ttlMs", 30_000)
        decorated.setdefault("cacheScope", "private")
    elif method == "resources/read":
        decorated.setdefault("ttlMs", 0)
        decorated.setdefault("cacheScope", "private")
    return decorated
