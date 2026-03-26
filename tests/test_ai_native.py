"""Tests for AI-native CLI: schema, commands, output, MCP, llms.txt."""

from __future__ import annotations

import json

import pytest

from milo.commands import CLI, CommandDef
from milo.llms import generate_llms_txt
from milo.mcp import _call_tool, _handle_method, _list_tools
from milo.output import format_output
from milo.schema import function_to_schema


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestFunctionToSchema:
    def test_basic_types(self):
        def func(name: str, age: int, score: float, active: bool):
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["age"]["type"] == "integer"
        assert schema["properties"]["score"]["type"] == "number"
        assert schema["properties"]["active"]["type"] == "boolean"
        assert set(schema["required"]) == {"name", "age", "score", "active"}

    def test_defaults_not_required(self):
        def func(name: str, limit: int = 10):
            pass

        schema = function_to_schema(func)
        assert schema["required"] == ["name"]

    def test_optional_type(self):
        def func(name: str | None):
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["name"]["type"] == "string"
        assert "required" not in schema

    def test_list_type(self):
        def func(tags: list[str]):
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["tags"]["type"] == "array"
        assert schema["properties"]["tags"]["items"]["type"] == "string"

    def test_unannotated_defaults_to_string(self):
        def func(x):
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["x"]["type"] == "string"

    def test_no_params(self):
        def func():
            pass

        schema = function_to_schema(func)
        assert schema["properties"] == {}
        assert "required" not in schema


# ---------------------------------------------------------------------------
# Output tests
# ---------------------------------------------------------------------------


class TestFormatOutput:
    def test_plain_string(self):
        assert format_output("hello") == "hello"

    def test_plain_dict(self):
        out = format_output({"name": "Alice", "age": 30})
        assert "name" in out
        assert "Alice" in out

    def test_plain_list(self):
        out = format_output([{"a": 1}, {"a": 2}])
        assert "1" in out
        assert "2" in out

    def test_json_string(self):
        out = format_output("hello", fmt="json")
        assert json.loads(out) == "hello"

    def test_json_dict(self):
        data = {"name": "Alice", "age": 30}
        out = format_output(data, fmt="json")
        assert json.loads(out) == data

    def test_json_list(self):
        data = [{"x": 1}, {"x": 2}]
        out = format_output(data, fmt="json")
        assert json.loads(out) == data

    def test_table_list_of_dicts(self):
        data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        out = format_output(data, fmt="table")
        assert "Alice" in out
        assert "Bob" in out

    def test_table_empty(self):
        assert format_output([], fmt="table") == "(empty)"


# ---------------------------------------------------------------------------
# CLI / Commands tests
# ---------------------------------------------------------------------------


class TestCLI:
    def _make_cli(self):
        cli = CLI(name="test", description="Test app", version="1.0")

        @cli.command("greet", description="Say hello", aliases=("g",))
        def greet(name: str, loud: bool = False) -> str:
            msg = f"Hello, {name}!"
            return msg.upper() if loud else msg

        @cli.command("add", description="Add numbers")
        def add(a: int, b: int = 0) -> int:
            return a + b

        @cli.command("secret", description="Hidden", hidden=True)
        def secret():
            return "shh"

        return cli

    def test_command_registration(self):
        cli = self._make_cli()
        assert "greet" in cli.commands
        assert "add" in cli.commands
        assert "secret" in cli.commands

    def test_command_def(self):
        cli = self._make_cli()
        cmd = cli.commands["greet"]
        assert isinstance(cmd, CommandDef)
        assert cmd.name == "greet"
        assert cmd.description == "Say hello"
        assert cmd.aliases == ("g",)

    def test_get_command_by_name(self):
        cli = self._make_cli()
        assert cli.get_command("greet") is not None
        assert cli.get_command("nonexistent") is None

    def test_get_command_by_alias(self):
        cli = self._make_cli()
        cmd = cli.get_command("g")
        assert cmd is not None
        assert cmd.name == "greet"

    def test_call(self):
        cli = self._make_cli()
        assert cli.call("greet", name="Alice") == "Hello, Alice!"
        assert cli.call("greet", name="Bob", loud=True) == "HELLO, BOB!"

    def test_call_alias(self):
        cli = self._make_cli()
        assert cli.call("g", name="World") == "Hello, World!"

    def test_call_unknown(self):
        cli = self._make_cli()
        with pytest.raises(ValueError, match="Unknown command"):
            cli.call("nope")

    def test_call_int_params(self):
        cli = self._make_cli()
        assert cli.call("add", a=3, b=4) == 7

    def test_call_filters_extra_kwargs(self):
        cli = self._make_cli()
        # Extra kwargs should be ignored
        assert cli.call("greet", name="Hi", extra="ignored") == "Hello, Hi!"

    def test_run_dispatches(self):
        cli = self._make_cli()
        result = cli.run(["greet", "--name", "Test"])
        assert result == "Hello, Test!"

    def test_run_with_bool_flag(self):
        cli = self._make_cli()
        result = cli.run(["greet", "--name", "X", "--loud"])
        assert result == "HELLO, X!"

    def test_run_int_args(self):
        cli = self._make_cli()
        result = cli.run(["add", "--a", "5", "--b", "3"])
        assert result == 8

    def test_build_parser(self):
        cli = self._make_cli()
        parser = cli.build_parser()
        # Should have --llms-txt and --mcp on the root
        args = parser.parse_args(["--llms-txt"])
        assert args.llms_txt is True

    def test_schema_on_command(self):
        cli = self._make_cli()
        cmd = cli.commands["greet"]
        assert cmd.schema["properties"]["name"]["type"] == "string"
        assert "name" in cmd.schema["required"]


# ---------------------------------------------------------------------------
# MCP tests
# ---------------------------------------------------------------------------


class TestMCP:
    def _make_cli(self):
        cli = CLI(name="test", description="Test", version="1.0")

        @cli.command("greet", description="Say hello")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @cli.command("fail", description="Always fails")
        def fail():
            raise RuntimeError("boom")

        @cli.command("hidden", description="Secret", hidden=True)
        def hidden():
            return "secret"

        return cli

    def test_initialize(self):
        cli = self._make_cli()
        result = _handle_method(cli, "initialize", {})
        assert result["protocolVersion"] == "2024-11-05"
        assert result["capabilities"]["tools"] == {}

    def test_list_tools(self):
        cli = self._make_cli()
        tools = _list_tools(cli)
        names = [t["name"] for t in tools]
        assert "greet" in names
        assert "hidden" not in names  # hidden commands excluded

    def test_tool_schema(self):
        cli = self._make_cli()
        tools = _list_tools(cli)
        greet = next(t for t in tools if t["name"] == "greet")
        assert greet["inputSchema"]["properties"]["name"]["type"] == "string"

    def test_call_tool(self):
        cli = self._make_cli()
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Agent"}})
        assert result["content"][0]["text"] == "Hello, Agent!"
        assert "isError" not in result

    def test_call_tool_error(self):
        cli = self._make_cli()
        result = _call_tool(cli, {"name": "fail", "arguments": {}})
        assert result["isError"] is True
        assert "boom" in result["content"][0]["text"]

    def test_unknown_method(self):
        cli = self._make_cli()
        with pytest.raises(ValueError, match="Unknown method"):
            _handle_method(cli, "unknown/method", {})


# ---------------------------------------------------------------------------
# llms.txt tests
# ---------------------------------------------------------------------------


class TestLlmsTxt:
    def test_basic_output(self):
        cli = CLI(name="myapp", description="My tool", version="2.0")

        @cli.command("init", description="Initialize project")
        def init(name: str):
            pass

        txt = generate_llms_txt(cli)
        assert "# myapp" in txt
        assert "> My tool" in txt
        assert "Version: 2.0" in txt
        assert "**init**" in txt
        assert "`--name`" in txt

    def test_tags_create_sections(self):
        cli = CLI(name="app")

        @cli.command("list", description="List items", tags=("data",))
        def list_cmd():
            pass

        @cli.command("deploy", description="Deploy", tags=("ops",))
        def deploy():
            pass

        @cli.command("help", description="Show help")
        def help_cmd():
            pass

        txt = generate_llms_txt(cli)
        assert "## Commands" in txt  # untagged
        assert "## Data" in txt  # tag: data
        assert "## Ops" in txt  # tag: ops

    def test_aliases_shown(self):
        cli = CLI(name="app")

        @cli.command("list", description="List", aliases=("ls", "l"))
        def list_cmd():
            pass

        txt = generate_llms_txt(cli)
        assert "(ls, l)" in txt

    def test_hidden_excluded(self):
        cli = CLI(name="app")

        @cli.command("public", description="Public")
        def pub():
            pass

        @cli.command("secret", description="Secret", hidden=True)
        def sec():
            pass

        txt = generate_llms_txt(cli)
        assert "public" in txt
        assert "secret" not in txt
