"""Shared MCP method dispatch for leaf servers and gateway."""

from __future__ import annotations

from typing import Any, Protocol


class MCPHandler(Protocol):
    """Protocol for MCP method handlers.

    Implemented by the leaf MCP server (direct CLI calls) and the
    gateway (proxy to child processes). The router dispatches to the
    appropriate method without duplicating the match/case structure.
    """

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]: ...

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
    match method:
        case "initialize":
            return handler.initialize(params)
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
            raise ValueError(f"Unknown method: {method!r}")
