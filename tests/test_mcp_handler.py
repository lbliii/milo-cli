"""Tests for milo.mcp — MCP handler, tool listing, resource reading, prompts."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from milo.commands import CLI
from milo.mcp import (
    _CLIHandler,
    _builtin_resources,
    _call_tool,
    _get_prompt,
    _list_prompts,
    _list_resources,
    _list_tools,
    _output_schema,
    _read_resource,
    _stats_resource,
    _to_text,
    _tool_title,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cli() -> CLI:
    """Build a small CLI for testing."""
    cli = CLI(name="testapp", description="A test app", version="1.0.0")

    @cli.command("greet", description="Say hello")
    def greet(name: str = "world") -> dict:
        """Greet someone warmly."""
        return {"message": f"Hello {name}"}

    @cli.command("fail", description="Always fails")
    def fail() -> str:
        raise RuntimeError("boom")

    @cli.command("hidden-cmd", description="Secret", hidden=True)
    def hidden_cmd() -> str:
        return "secret"

    @cli.resource("config://app", name="App Config", description="App configuration")
    def app_config() -> dict:
        return {"debug": True}

    @cli.prompt("deploy-checklist", description="Deployment checklist")
    def deploy_checklist(env: str = "staging") -> str:
        return f"Deploy to {env}: check 1, check 2"

    return cli


# ---------------------------------------------------------------------------
# _to_text
# ---------------------------------------------------------------------------


class TestToText:
    def test_string_passthrough(self) -> None:
        assert _to_text("hello") == "hello"

    def test_dict_to_json(self) -> None:
        result = _to_text({"key": "value"})
        assert json.loads(result) == {"key": "value"}

    def test_list_to_json(self) -> None:
        result = _to_text([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_none_to_json(self) -> None:
        result = _to_text(None)
        assert result == "null"


# ---------------------------------------------------------------------------
# _list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_lists_non_hidden_commands(self) -> None:
        cli = _make_cli()
        tools = _list_tools(cli)
        names = [t["name"] for t in tools]
        assert "greet" in names
        assert "fail" in names
        assert "hidden-cmd" not in names

    def test_tool_has_input_schema(self) -> None:
        cli = _make_cli()
        tools = _list_tools(cli)
        greet = next(t for t in tools if t["name"] == "greet")
        assert "inputSchema" in greet
        assert "properties" in greet["inputSchema"]
        assert "name" in greet["inputSchema"]["properties"]

    def test_tool_has_description(self) -> None:
        cli = _make_cli()
        tools = _list_tools(cli)
        greet = next(t for t in tools if t["name"] == "greet")
        assert greet["description"] == "Say hello"


# ---------------------------------------------------------------------------
# _tool_title
# ---------------------------------------------------------------------------


class TestToolTitle:
    def test_title_from_docstring(self) -> None:
        cli = _make_cli()
        cmd = cli.get_command("greet")
        title = _tool_title(cmd)
        assert title == "Greet someone warmly"

    def test_title_fallback_for_no_doc(self) -> None:
        cli = _make_cli()
        cmd = cli.get_command("fail")
        title = _tool_title(cmd)
        # "fail" -> "Fail" (title-cased)
        assert title == "Fail"


# ---------------------------------------------------------------------------
# _call_tool
# ---------------------------------------------------------------------------


class TestCallTool:
    def test_successful_call(self) -> None:
        cli = _make_cli()
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Alice"}})
        assert "isError" not in result
        content = result["content"][0]
        assert content["type"] == "text"
        parsed = json.loads(content["text"])
        assert parsed["message"] == "Hello Alice"

    def test_default_arguments(self) -> None:
        cli = _make_cli()
        result = _call_tool(cli, {"name": "greet", "arguments": {}})
        content = result["content"][0]
        parsed = json.loads(content["text"])
        assert parsed["message"] == "Hello world"

    def test_error_call(self) -> None:
        cli = _make_cli()
        result = _call_tool(cli, {"name": "fail", "arguments": {}})
        assert result["isError"] is True
        assert "boom" in result["content"][0]["text"]

    def test_unknown_tool(self) -> None:
        cli = _make_cli()
        result = _call_tool(cli, {"name": "nonexistent", "arguments": {}})
        assert result["isError"] is True

    def test_structured_content_for_dict_result(self) -> None:
        cli = _make_cli()
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Bob"}})
        assert "structuredContent" in result
        assert result["structuredContent"]["message"] == "Hello Bob"


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class TestListResources:
    def test_lists_registered_resources(self) -> None:
        cli = _make_cli()
        resources = _list_resources(cli)
        uris = [r["uri"] for r in resources]
        assert "config://app" in uris

    def test_resource_has_metadata(self) -> None:
        cli = _make_cli()
        resources = _list_resources(cli)
        app_res = next(r for r in resources if r["uri"] == "config://app")
        assert app_res["name"] == "App Config"
        assert app_res["description"] == "App configuration"


class TestReadResource:
    def test_read_registered_resource(self) -> None:
        cli = _make_cli()
        result = _read_resource(cli, {"uri": "config://app"})
        contents = result["contents"]
        assert len(contents) == 1
        parsed = json.loads(contents[0]["text"])
        assert parsed["debug"] is True

    def test_read_unknown_resource(self) -> None:
        cli = _make_cli()
        result = _read_resource(cli, {"uri": "nonexistent://x"})
        assert result["contents"] == []


class TestBuiltinResources:
    def test_includes_stats_and_pipeline(self) -> None:
        resources = _builtin_resources()
        uris = [r["uri"] for r in resources]
        assert "milo://stats" in uris
        assert "milo://pipeline/timeline" in uris


class TestStatsResource:
    def test_returns_json_content(self) -> None:
        from milo.observability import RequestLogger

        logger = RequestLogger()
        result = _stats_resource(logger)
        contents = result["contents"]
        assert len(contents) == 1
        stats = json.loads(contents[0]["text"])
        assert "total" in stats
        assert stats["total"] == 0


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class TestListPrompts:
    def test_lists_registered_prompts(self) -> None:
        cli = _make_cli()
        prompts = _list_prompts(cli)
        names = [p["name"] for p in prompts]
        assert "deploy-checklist" in names

    def test_prompt_has_description(self) -> None:
        cli = _make_cli()
        prompts = _list_prompts(cli)
        p = next(p for p in prompts if p["name"] == "deploy-checklist")
        assert p["description"] == "Deployment checklist"


class TestGetPrompt:
    def test_get_registered_prompt(self) -> None:
        cli = _make_cli()
        result = _get_prompt(cli, {"name": "deploy-checklist", "arguments": {"env": "prod"}})
        messages = result["messages"]
        assert len(messages) == 1
        assert "prod" in messages[0]["content"]["text"]

    def test_get_unknown_prompt(self) -> None:
        cli = _make_cli()
        result = _get_prompt(cli, {"name": "nonexistent", "arguments": {}})
        assert result["messages"] == []

    def test_prompt_default_arguments(self) -> None:
        cli = _make_cli()
        result = _get_prompt(cli, {"name": "deploy-checklist", "arguments": {}})
        messages = result["messages"]
        assert "staging" in messages[0]["content"]["text"]


# ---------------------------------------------------------------------------
# _CLIHandler integration
# ---------------------------------------------------------------------------


class TestCLIHandler:
    def test_initialize(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.initialize({})
        assert "protocolVersion" in result
        assert result["serverInfo"]["name"] == "testapp"
        assert result["serverInfo"]["version"] == "1.0.0"

    def test_list_tools(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.list_tools({})
        assert "tools" in result
        assert len(result["tools"]) >= 2

    def test_call_tool(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.call_tool({"name": "greet", "arguments": {"name": "Test"}})
        assert "content" in result
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["message"] == "Hello Test"

    def test_list_resources(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.list_resources({})
        assert "resources" in result
        # Should include user-defined + builtin resources
        uris = [r["uri"] for r in result["resources"]]
        assert "config://app" in uris
        assert "milo://stats" in uris

    def test_read_resource_stats(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.read_resource({"uri": "milo://stats"})
        stats = json.loads(result["contents"][0]["text"])
        assert "total" in stats

    def test_list_prompts(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.list_prompts({})
        assert "prompts" in result

    def test_get_prompt(self) -> None:
        cli = _make_cli()
        handler = _CLIHandler(cli)
        result = handler.get_prompt({"name": "deploy-checklist", "arguments": {}})
        assert "messages" in result

    def test_cached_tools(self) -> None:
        cli = _make_cli()
        cached = [{"name": "cached-tool", "description": "test", "inputSchema": {}}]
        handler = _CLIHandler(cli, cached_tools=cached)
        result = handler.list_tools({})
        assert result["tools"] == cached
