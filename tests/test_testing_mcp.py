"""Tests for milo.testing._mcp — MCP test client."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo.testing._mcp import CallResult, MCPClient, ToolInfo


@pytest.fixture
def cli() -> CLI:
    """Build a fixture CLI with commands, groups, hidden commands."""
    app = CLI(name="testapp", description="Test application", version="1.0.0")

    @app.command("greet", description="Say hello")
    def greet(name: str, loud: bool = False) -> str:
        msg = f"Hello, {name}!"
        return msg.upper() if loud else msg

    @app.command("add", description="Add numbers")
    def add(a: int, b: int) -> int:
        return a + b

    @app.command("fail", description="Always fails")
    def fail() -> str:
        msg = "Something went wrong"
        raise RuntimeError(msg)

    @app.command("secret", description="Hidden command", hidden=True)
    def secret() -> str:
        return "secret"

    site = app.group("site", description="Site operations")

    @site.command("build", description="Build the site")
    def build(output: str = "_site") -> str:
        return f"Built to {output}"

    return app


class TestToolInfo:
    def test_frozen(self) -> None:
        info = ToolInfo(name="x", description="d", input_schema={}, output_schema=None)
        with pytest.raises(AttributeError):
            info.name = "y"  # type: ignore[misc]

    def test_fields(self) -> None:
        info = ToolInfo(name="greet", description="Say hello", input_schema={"type": "object"}, output_schema={"type": "string"})
        assert info.name == "greet"
        assert info.output_schema == {"type": "string"}


class TestCallResult:
    def test_frozen(self) -> None:
        r = CallResult(text="ok", is_error=False, structured=None)
        with pytest.raises(AttributeError):
            r.text = "nope"  # type: ignore[misc]


class TestMCPClient:
    def test_initialize(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.initialize()
        assert result["serverInfo"]["name"] == "testapp"
        assert "tools" in result["capabilities"]

    def test_list_tools(self, cli: CLI) -> None:
        client = MCPClient(cli)
        tools = client.list_tools()
        names = [t.name for t in tools]
        assert "greet" in names
        assert "add" in names
        assert "site.build" in names
        # Hidden commands should not appear
        assert "secret" not in names

    def test_list_tools_returns_tool_info(self, cli: CLI) -> None:
        client = MCPClient(cli)
        tools = client.list_tools()
        for t in tools:
            assert isinstance(t, ToolInfo)
            assert isinstance(t.input_schema, dict)

    def test_call_success(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.call("greet", name="Alice")
        assert result.text == "Hello, Alice!"
        assert result.is_error is False

    def test_call_structured(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.call("add", a=2, b=3)
        assert result.structured == 5
        assert result.is_error is False

    def test_call_group_command(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.call("site.build", output="/tmp/out")
        assert result.text == "Built to /tmp/out"

    def test_call_error(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.call("fail")
        assert result.is_error is True
        assert "Something went wrong" in result.text

    def test_call_unknown_tool(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.call("nonexistent")
        assert result.is_error is True
        assert "Unknown command" in result.text
