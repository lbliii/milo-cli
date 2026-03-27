"""MCP test client — synchronous wrapper around milo.mcp internals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from milo.commands import CLI
from milo.mcp import _call_tool, _handle_method, _list_tools


@dataclass(frozen=True, slots=True)
class ToolInfo:
    """Frozen snapshot of an MCP tool descriptor."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class CallResult:
    """Frozen snapshot of an MCP tools/call response."""

    text: str
    is_error: bool
    structured: Any


class MCPClient:
    """Synchronous test client for exercising a CLI's MCP surface."""

    def __init__(self, cli: CLI) -> None:
        self._cli = cli

    def initialize(self) -> dict[str, Any]:
        """Send ``initialize`` and return the server info dict."""
        result = _handle_method(self._cli, "initialize", {})
        assert result is not None, "initialize must return a result"
        return result

    def list_tools(self) -> list[ToolInfo]:
        """Return all visible tools as ToolInfo objects."""
        raw = _list_tools(self._cli)
        return [
            ToolInfo(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                output_schema=t.get("outputSchema"),
            )
            for t in raw
        ]

    def call(self, tool_name: str, **arguments: Any) -> CallResult:
        """Invoke a tool by name and return a CallResult."""
        raw = _call_tool(self._cli, {"name": tool_name, "arguments": arguments})
        content = raw.get("content", [])
        text = content[0]["text"] if content else ""
        return CallResult(
            text=text,
            is_error=raw.get("isError", False),
            structured=raw.get("structuredContent"),
        )

    def list_resources(self) -> list[dict[str, Any]]:
        """Return all resources (requires F3 resources support)."""
        result = _handle_method(self._cli, "resources/list", {})
        return result.get("resources", []) if result else []

    def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI (requires F3 resources support)."""
        result = _handle_method(self._cli, "resources/read", {"uri": uri})
        return result or {}

    def list_prompts(self) -> list[dict[str, Any]]:
        """Return all prompts (requires F3 prompts support)."""
        result = _handle_method(self._cli, "prompts/list", {})
        return result.get("prompts", []) if result else []

    def get_prompt(self, prompt_name: str, **arguments: Any) -> dict[str, Any]:
        """Get a prompt by name (requires F3 prompts support)."""
        result = _handle_method(
            self._cli, "prompts/get", {"name": prompt_name, "arguments": arguments}
        )
        return result or {}
