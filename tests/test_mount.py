"""Tests for CLI composition via mount (F8)."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo.testing._mcp import MCPClient


@pytest.fixture
def main_cli() -> CLI:
    """Build a main CLI with a mounted sub-CLI."""
    main = CLI(name="main", description="Main app", version="1.0.0")

    @main.command("hello", description="Say hello")
    def hello(name: str = "World") -> str:
        return f"Hello, {name}!"

    # Sub CLI
    sub = CLI(name="sub", description="Sub app")

    @sub.command("add", description="Add numbers")
    def add(a: int, b: int) -> int:
        return a + b

    @sub.resource("config://sub", description="Sub config")
    def sub_config() -> dict:
        return {"key": "value"}

    @sub.prompt("sub-help", description="Sub help")
    def sub_help() -> str:
        return "This is the sub app help."

    grp = sub.group("nested", description="Nested group")

    @grp.command("status", description="Status check")
    def status() -> str:
        return "ok"

    main.mount("sub", sub)
    return main


class TestMountCommands:
    def test_walk_includes_mounted(self, main_cli: CLI) -> None:
        paths = [name for name, _ in main_cli.walk_commands()]
        assert "hello" in paths
        assert "sub.add" in paths
        assert "sub.nested.status" in paths

    def test_call_mounted_command(self, main_cli: CLI) -> None:
        result = main_cli.call("sub.add", a=2, b=3)
        assert result == 5

    def test_call_mounted_nested(self, main_cli: CLI) -> None:
        result = main_cli.call("sub.nested.status")
        assert result == "ok"


class TestMountResources:
    def test_resources_prefixed(self, main_cli: CLI) -> None:
        uris = [uri for uri, _ in main_cli.walk_resources()]
        assert "sub/config://sub" in uris


class TestMountPrompts:
    def test_prompts_prefixed(self, main_cli: CLI) -> None:
        names = [name for name, _ in main_cli.walk_prompts()]
        assert "sub.sub-help" in names


class TestMountMCP:
    def test_tools_list(self, main_cli: CLI) -> None:
        client = MCPClient(main_cli)
        tools = client.list_tools()
        names = [t.name for t in tools]
        assert "hello" in names
        assert "sub.add" in names
        assert "sub.nested.status" in names

    def test_call_mounted_via_mcp(self, main_cli: CLI) -> None:
        client = MCPClient(main_cli)
        result = client.call("sub.add", a=10, b=20)
        assert result.structured == 30

    def test_resources_list(self, main_cli: CLI) -> None:
        client = MCPClient(main_cli)
        resources = client.list_resources()
        uris = [r["uri"] for r in resources]
        assert "sub/config://sub" in uris

    def test_prompts_list(self, main_cli: CLI) -> None:
        client = MCPClient(main_cli)
        prompts = client.list_prompts()
        names = [p["name"] for p in prompts]
        assert "sub.sub-help" in names
