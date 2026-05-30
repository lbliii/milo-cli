"""Shared MCP method dispatch for leaf servers and gateway."""

from __future__ import annotations

from typing import Any, Protocol

from milo._jsonrpc import (
    MCP_PROTOCOL_VERSION_META_KEY,
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
    _validate_requested_protocol(params)
    match method:
        case "initialize":
            return handler.initialize(params)
        case "server/discover":
            return handler.server_discover(params)
        case "notifications/initialized":
            return None
        case "tools/list":
            return handler.list_tools(params)
        case "tools/call":
            return handler.call_tool(params)
        case "resources/list":
            return handler.list_resources(params)
        case "resources/read":
            return handler.read_resource(params)
        case "prompts/list":
            return handler.list_prompts(params)
        case "prompts/get":
            return handler.get_prompt(params)
        case _:
            raise MethodNotFoundError(f"Unknown method: {method!r}")


def _validate_requested_protocol(params: dict[str, Any]) -> None:
    """Reject explicit per-request MCP versions Milo does not implement.

    Legacy 2025-11-25 clients negotiate with ``initialize`` and do not send
    request metadata, so absent metadata remains accepted for backward
    compatibility.
    """
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return
    requested = meta.get(MCP_PROTOCOL_VERSION_META_KEY)
    if requested is None:
        return
    if requested not in SUPPORTED_MCP_VERSIONS:
        raise UnsupportedProtocolVersionError(str(requested))
