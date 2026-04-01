"""Tests for AI-native CLI: schema, commands, output, MCP, llms.txt, registry, gateway."""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch

import pytest

from milo._mcp_router import dispatch as _mcp_dispatch
from milo.commands import CLI, CommandDef, InvokeResult
from milo.context import Context
from milo.llms import generate_llms_txt
from milo.mcp import _call_tool, _CLIHandler, _list_tools
from milo.output import format_output
from milo.schema import function_to_schema, return_to_schema

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
        result = _mcp_dispatch(_CLIHandler(cli), "initialize", {})
        assert result["protocolVersion"] == "2025-11-25"
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
            _mcp_dispatch(_CLIHandler(cli), "unknown/method", {})


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


# ---------------------------------------------------------------------------
# MCP extended tests (title, outputSchema, structuredContent, banner, notifications)
# ---------------------------------------------------------------------------


class TestMCPExtended:
    def _make_cli(self):
        cli = CLI(name="test", description="Test CLI", version="1.0")

        @cli.command("stats", description="Get statistics")
        def stats() -> dict:
            """Return usage statistics."""
            return {"total": 10, "done": 7}

        @cli.command("greet", description="Say hello")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        return cli

    def test_tool_title(self):
        cli = self._make_cli()
        tools = _list_tools(cli)
        stats_tool = next(t for t in tools if t["name"] == "stats")
        assert "title" in stats_tool

    def test_output_schema(self):
        cli = self._make_cli()
        tools = _list_tools(cli)
        stats_tool = next(t for t in tools if t["name"] == "stats")
        assert stats_tool["outputSchema"] == {"type": "object"}

    def test_output_schema_string(self):
        cli = self._make_cli()
        tools = _list_tools(cli)
        greet_tool = next(t for t in tools if t["name"] == "greet")
        assert greet_tool["outputSchema"] == {"type": "string"}

    def test_structured_content(self):
        cli = self._make_cli()
        result = _call_tool(cli, {"name": "stats", "arguments": {}})
        assert result["structuredContent"] == {"total": 10, "done": 7}
        assert "content" in result

    def test_string_result_no_structured_content(self):
        cli = self._make_cli()
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "World"}})
        assert "structuredContent" not in result
        assert result["content"][0]["text"] == "Hello, World!"

    def test_notifications_initialized(self):
        cli = self._make_cli()
        result = _mcp_dispatch(_CLIHandler(cli), "notifications/initialized", {})
        assert result is None

    def test_initialize_includes_server_info(self):
        cli = self._make_cli()
        result = _mcp_dispatch(_CLIHandler(cli), "initialize", {})
        assert result["serverInfo"]["name"] == "test"
        assert result["serverInfo"]["version"] == "1.0"
        assert result["serverInfo"]["title"] == "Test CLI"
        assert result["instructions"] == "Test CLI"

    def test_mcp_banner(self):
        """run_mcp_server writes banner to stderr."""
        cli = self._make_cli()
        import io

        from milo.mcp import run_mcp_server

        with (
            patch("sys.stdin", io.StringIO("")),
            patch("sys.stderr", new_callable=io.StringIO) as mock_err,
        ):
            run_mcp_server(cli)

        banner = mock_err.getvalue()
        assert "MCP server ready" in banner
        assert "2025-11-25" in banner
        assert "stats" in banner


# ---------------------------------------------------------------------------
# return_to_schema tests
# ---------------------------------------------------------------------------


class TestReturnToSchema:
    def test_returns_dict(self):
        def f() -> dict:
            pass

        assert return_to_schema(f) == {"type": "object"}

    def test_returns_list(self):
        def f() -> list:
            pass

        assert return_to_schema(f) == {"type": "array"}

    def test_returns_str(self):
        def f() -> str:
            pass

        assert return_to_schema(f) == {"type": "string"}

    def test_returns_none(self):
        def f() -> None:
            pass

        assert return_to_schema(f) is None

    def test_no_annotation(self):
        def f():
            pass

        assert return_to_schema(f) is None

    def test_optional_return(self):
        def f() -> str | None:
            pass

        assert return_to_schema(f) == {"type": "string"}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_install_and_list(self, tmp_path):
        reg_file = tmp_path / "registry.json"
        with (
            patch("milo.registry._REGISTRY_FILE", reg_file),
            patch("milo.registry._REGISTRY_DIR", tmp_path),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            from milo.registry import install, list_clis

            install("myapp", ["python", "app.py", "--mcp"], description="My app", version="1.0")
            clis = list_clis()
            assert "myapp" in clis
            assert clis["myapp"]["command"] == ["python", "app.py", "--mcp"]
            assert clis["myapp"]["description"] == "My app"
            assert clis["myapp"]["version"] == "1.0"

    def test_uninstall(self, tmp_path):
        reg_file = tmp_path / "registry.json"
        with (
            patch("milo.registry._REGISTRY_FILE", reg_file),
            patch("milo.registry._REGISTRY_DIR", tmp_path),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            from milo.registry import install, list_clis, uninstall

            install("myapp", ["python", "app.py", "--mcp"])
            assert uninstall("myapp") is True
            assert "myapp" not in list_clis()

    def test_uninstall_missing(self, tmp_path):
        reg_file = tmp_path / "registry.json"
        with (
            patch("milo.registry._REGISTRY_FILE", reg_file),
            patch("milo.registry._REGISTRY_DIR", tmp_path),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            from milo.registry import uninstall

            assert uninstall("nonexistent") is False

    def test_list_empty(self, tmp_path):
        reg_file = tmp_path / "registry.json"
        with (
            patch("milo.registry._REGISTRY_FILE", reg_file),
            patch("milo.registry._REGISTRY_DIR", tmp_path),
        ):
            from milo.registry import list_clis

            assert list_clis() == {}

    def test_registry_path(self):
        from milo.registry import registry_path

        path = registry_path()
        assert path.name == "registry.json"


# ---------------------------------------------------------------------------
# Gateway tests
# ---------------------------------------------------------------------------


class TestGateway:
    def test_handle_method_initialize(self):
        from milo.gateway import GatewayState, _GatewayHandler

        clis = {"app1": {"command": ["python", "app.py"]}}
        state = GatewayState([], {}, [], {}, [], {})
        handler = _GatewayHandler(clis, state, {})
        result = _mcp_dispatch(handler, "initialize", {})
        assert result["protocolVersion"] == "2025-11-25"
        assert result["serverInfo"]["name"] == "milo-gateway"

    def test_handle_method_tools_list(self):
        from milo.gateway import GatewayState, _GatewayHandler

        tools = [{"name": "app1.greet", "description": "Say hello"}]
        state = GatewayState(tools, {}, [], {}, [], {})
        handler = _GatewayHandler({}, state, {})
        result = _mcp_dispatch(handler, "tools/list", {})
        assert result["tools"] == tools

    def test_handle_method_notifications_initialized(self):
        from milo.gateway import GatewayState, _GatewayHandler

        state = GatewayState([], {}, [], {}, [], {})
        handler = _GatewayHandler({}, state, {})
        result = _mcp_dispatch(handler, "notifications/initialized", {})
        assert result is None

    def test_handle_method_unknown(self):
        from milo.gateway import GatewayState, _GatewayHandler

        state = GatewayState([], {}, [], {}, [], {})
        handler = _GatewayHandler({}, state, {})
        with pytest.raises(ValueError, match="Unknown method"):
            _mcp_dispatch(handler, "unknown/method", {})

    def test_proxy_call_unknown_tool(self):
        from milo.gateway import _proxy_call

        result = _proxy_call({}, {}, {"name": "unknown.tool", "arguments": {}})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_proxy_call_missing_cli(self):
        from milo.gateway import _proxy_call

        routing = {"app.greet": ("app", "greet")}
        result = _proxy_call({}, routing, {"name": "app.greet", "arguments": {}})
        assert result["isError"] is True
        assert "not available" in result["content"][0]["text"]

    def test_discover_tools_empty(self):
        from milo.gateway import _discover_all

        state = _discover_all({}, {})
        assert state.tools == []
        assert state.tool_routing == {}

    def test_discover_tools_no_command(self):
        from milo.gateway import _discover_all

        state = _discover_all({"app": {"command": []}}, {})
        assert state.tools == []

    def test_print_registry_empty(self):
        import io

        from milo.gateway import _print_registry

        with (
            patch("milo.gateway.list_clis", return_value={}),
            patch("sys.stderr", new_callable=io.StringIO) as mock_err,
        ):
            _print_registry()
        assert "No CLIs registered" in mock_err.getvalue()

    def test_print_registry_with_clis(self):
        import io

        from milo.gateway import _print_registry

        clis = {
            "myapp": {"command": ["python", "app.py"], "description": "My app", "version": "1.0"}
        }
        with (
            patch("milo.gateway.list_clis", return_value=clis),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _print_registry()
        output = mock_out.getvalue()
        assert "myapp" in output
        assert "My app" in output

    def test_write_result(self):
        import io

        from milo.gateway import _write_result

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _write_result(1, {"tools": []})
        response = json.loads(mock_out.getvalue())
        assert response["id"] == 1
        assert response["result"] == {"tools": []}

    def test_write_error(self):
        import io

        from milo.gateway import _write_error

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _write_error(1, -32603, "Internal error")
        response = json.loads(mock_out.getvalue())
        assert response["error"]["code"] == -32603

    def test_main_help(self):
        import io

        from milo.gateway import main

        with (
            patch("sys.argv", ["gateway"]),
            patch("sys.stderr", new_callable=io.StringIO) as mock_err,
        ):
            main()
        assert "milo gateway" in mock_err.getvalue()

    def test_main_list(self):
        import io

        from milo.gateway import main

        with (
            patch("sys.argv", ["gateway", "--list"]),
            patch("milo.gateway.list_clis", return_value={}),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            main()  # Should not raise


class TestCLIDryRun:
    def test_dry_run_flag_parsed(self):
        cli = CLI(name="test")

        @cli.command("greet", description="Greet")
        def greet(name: str = "World", ctx: Context = None) -> str:
            return f"dry={ctx.dry_run}"

        result = cli.run(["--dry-run", "greet"])
        assert result == "dry=True"

    def test_dry_run_short_flag(self):
        cli = CLI(name="test")

        @cli.command("greet", description="Greet")
        def greet(ctx: Context = None) -> str:
            return f"dry={ctx.dry_run}"

        result = cli.run(["-n", "greet"])
        assert result == "dry=True"


class TestCLIOutputFile:
    def test_output_to_file(self, tmp_path):
        cli = CLI(name="test")

        @cli.command("hello", description="Hello")
        def hello() -> str:
            return "hello world"

        outfile = tmp_path / "out.txt"
        cli.run(["--output-file", str(outfile), "hello"])
        assert outfile.read_text().strip() == "hello world"


class TestCLIInvoke:
    def test_invoke_captures_output(self):
        cli = CLI(name="test")

        @cli.command("greet", description="Greet")
        def greet(name: str = "World") -> str:
            return f"Hello, {name}!"

        result = cli.invoke(["greet", "--name", "Alice"])
        assert isinstance(result, InvokeResult)
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output

    def test_invoke_captures_errors(self):
        cli = CLI(name="test")

        @cli.command("fail", description="Fail")
        def fail() -> str:
            raise RuntimeError("boom")

        result = cli.invoke(["fail"])
        assert result.exit_code == 1
        assert "boom" in result.stderr


class TestCLIHooks:
    def test_before_command_hook(self):
        cli = CLI(name="test")
        calls = []

        @cli.before_command
        def hook(ctx, name, kwargs):
            calls.append(("before", name))

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hi"

        cli.run(["greet"])
        assert ("before", "greet") in calls

    def test_after_command_hook(self):
        cli = CLI(name="test")
        calls = []

        @cli.after_command
        def hook(ctx, name, result):
            calls.append(("after", name, result))

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hi"

        cli.run(["greet"])
        assert ("after", "greet", "hi") in calls


class TestCLIConfirm:
    def test_confirm_abort_non_interactive(self, capsys):
        cli = CLI(name="test")

        @cli.command("delete", description="Delete", confirm="Are you sure?")
        def delete() -> str:
            return "deleted"

        # Non-interactive stdin -> confirm returns False -> aborted
        if not sys.stdin.isatty():
            result = cli.run(["delete"])
            assert result is None
            assert "Aborted" in capsys.readouterr().err

    def test_confirm_skipped_in_dry_run(self, capsys):
        cli = CLI(name="test")

        @cli.command("delete", description="Delete", confirm="Are you sure?")
        def delete() -> str:
            return "deleted"

        # Dry-run skips confirmation gate, runs the command
        result = cli.run(["-n", "delete"])
        assert result == "deleted"


class TestCLIDidYouMean:
    def test_suggest_on_typo(self, capsys):
        cli = CLI(name="test")

        @cli.command("status", description="Status")
        def status() -> str:
            return "ok"

        with pytest.raises(SystemExit):
            cli.run(["stattus"])
        err = capsys.readouterr().err
        assert "Did you mean" in err or "status" in err

    def test_suggest_via_invoke(self):
        cli = CLI(name="test")

        @cli.command("status", description="Status")
        def status() -> str:
            return "ok"

        result = cli.invoke(["stattus"])
        assert result.exit_code != 0


class TestGenerateHelpAll:
    def test_basic_output(self):
        cli = CLI(name="test", description="Test CLI", version="1.0.0")

        @cli.command("greet", description="Say hello")
        def greet(name: str) -> str:
            return f"Hello, {name}"

        site = cli.group("site", description="Site ops")

        @site.command("build", description="Build site")
        def build() -> str:
            return "built"

        md = cli.generate_help_all()
        assert "# test" in md
        assert "Test CLI" in md
        assert "greet" in md
        assert "site" in md
        assert "build" in md
        assert "--dry-run" in md


class TestCLICompletions:
    def test_bash_completions(self, capsys):
        cli = CLI(name="myapp")

        @cli.command("greet", description="Greet")
        def greet(name: str = "World") -> str:
            return f"Hello, {name}"

        cli.run(["--completions", "bash"])
        out = capsys.readouterr().out
        assert "myapp" in out
        assert "complete" in out

    def test_zsh_completions(self, capsys):
        cli = CLI(name="myapp")

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hi"

        cli.run(["--completions", "zsh"])
        out = capsys.readouterr().out
        assert "#compdef" in out

    def test_fish_completions(self, capsys):
        cli = CLI(name="myapp")

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hi"

        cli.run(["--completions", "fish"])
        out = capsys.readouterr().out
        assert "complete -c myapp" in out


class TestSuggestCommand:
    def test_suggest_group_names(self):
        cli = CLI(name="test")
        cli.group("deploy", description="Deploy ops")

        suggestion = cli.suggest_command("deplpy")
        assert suggestion == "deploy"


class TestInvokeSeparateStreams:
    def test_stdout_and_stderr_separated(self):
        cli = CLI(name="test")

        @cli.command("greet", description="Greet")
        def greet(name: str = "World", ctx: Context = None) -> str:
            ctx.info("greeting user")
            return f"Hello, {name}!"

        result = cli.invoke(["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output
        assert "greeting user" in result.stderr
        assert "greeting user" not in result.output

    def test_error_in_stderr(self):
        cli = CLI(name="test")

        @cli.command("fail", description="Fail")
        def fail() -> str:
            raise ValueError("bad input")

        result = cli.invoke(["fail"])
        assert result.exit_code == 1
        assert "bad input" in result.stderr
        assert result.output == ""

    def test_milo_error_formatted(self):
        from milo._errors import ErrorCode, MiloError

        cli = CLI(name="test")

        @cli.command("fail", description="Fail")
        def fail() -> str:
            raise MiloError(
                ErrorCode.CFG_PARSE,
                "Invalid config",
                suggestion="Check your config.toml",
            )

        result = cli.invoke(["fail"])
        assert result.exit_code == 1
        assert "M-CFG-001" in result.stderr
        assert "Invalid config" in result.stderr
        assert "Check your config.toml" in result.stderr


class TestExamplesInHelp:
    def test_examples_rendered_in_help(self):
        cli = CLI(name="myapp", description="My tool")

        @cli.command(
            "deploy",
            description="Deploy the app",
            examples=(
                {"command": "myapp deploy --env production", "description": "Deploy to prod"},
                {
                    "command": "myapp deploy --env staging --dry-run",
                    "description": "Preview staging deploy",
                },
            ),
        )
        def deploy(env: str = "local") -> str:
            return f"Deployed to {env}"

        result = cli.invoke(["deploy", "--help"])
        # Help is on stdout (argparse writes --help to stdout)
        combined = result.output + result.stderr
        assert "myapp deploy --env production" in combined

    def test_examples_in_generate_help_all(self):
        cli = CLI(name="myapp", description="My tool")

        @cli.command(
            "deploy",
            description="Deploy the app",
            examples=(
                {"command": "myapp deploy --env production", "description": "Deploy to prod"},
            ),
        )
        def deploy(env: str = "local") -> str:
            return f"Deployed to {env}"

        md = cli.generate_help_all()
        assert "myapp deploy --env production" in md
        assert "Deploy to prod" in md


class TestGenerateHelpAllBacktickFix:
    def test_global_option_short_flag_formatting(self):
        cli = CLI(name="myapp")
        cli.global_option("env", short="-e", default="local", description="Environment")

        @cli.command("build", description="Build")
        def build() -> str:
            return "built"

        md = cli.generate_help_all()
        # Should have matched backticks, not an unclosed backtick
        assert "`-e, --env`" in md
