"""Tests for milo.commands — CLI registration, dispatch, resolution, invoke."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo._command_defs import LazyCommandDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cli() -> CLI:
    cli = CLI(name="testcli", description="Test CLI")

    @cli.command("greet", description="Greet someone")
    def greet(name: str = "world") -> dict:
        return {"message": f"Hello {name}"}

    @cli.command("add", description="Add numbers")
    def add(a: int, b: int) -> int:
        return a + b

    @cli.command("secret", description="Hidden cmd", hidden=True)
    def secret() -> str:
        return "hidden"

    @cli.command("aliased", description="Has aliases", aliases=("al", "a"))
    def aliased() -> str:
        return "aliased"

    return cli


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestCommandRegistration:
    def test_register_basic_command(self) -> None:
        cli = _make_cli()
        cmd = cli.get_command("greet")
        assert cmd is not None
        assert cmd.name == "greet"
        assert cmd.description == "Greet someone"

    def test_register_hidden_command(self) -> None:
        cli = _make_cli()
        cmd = cli.get_command("secret")
        assert cmd is not None
        assert cmd.hidden is True

    def test_register_with_aliases(self) -> None:
        cli = _make_cli()
        cmd = cli.get_command("aliased")
        assert cmd is not None
        # Aliases resolve to the same command
        assert cli.get_command("al") is cmd
        assert cli.get_command("a") is cmd

    def test_get_command_unknown(self) -> None:
        cli = _make_cli()
        assert cli.get_command("nonexistent") is None

    def test_walk_commands(self) -> None:
        cli = _make_cli()
        names = [name for name, _ in cli.walk_commands()]
        assert "greet" in names
        assert "add" in names
        assert "secret" in names
        assert "aliased" in names


class TestLazyCommand:
    def test_register_lazy_command(self) -> None:
        cli = CLI(name="test", description="")
        cli.lazy_command(
            "dumps",
            import_path="json:dumps",
            description="JSON encode",
        )
        cmd = cli.get_command("dumps")
        assert isinstance(cmd, LazyCommandDef)
        assert cmd.name == "dumps"

    def test_lazy_command_resolves_on_call(self) -> None:
        cli = CLI(name="test", description="")
        cli.lazy_command(
            "loads",
            import_path="json:loads",
            description="JSON decode",
        )
        # call triggers resolve
        result = cli.call("loads", s='{"key": "value"}')
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


class TestGroups:
    def test_register_group(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")

        @site.command("build", description="Build site")
        def build() -> str:
            return "built"

        groups = cli.groups
        assert "site" in groups

    def test_dotted_path_resolution(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")

        @site.command("build", description="Build site")
        def build() -> str:
            return "built"

        cmd = cli.get_command("site.build")
        assert cmd is not None
        assert cmd.name == "build"

    def test_dotted_path_nonexistent_group(self) -> None:
        cli = CLI(name="test", description="")
        assert cli.get_command("nonexistent.build") is None

    def test_dotted_path_nonexistent_command(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")
        assert cli.get_command("site.nonexistent") is None

    def test_walk_commands_includes_groups(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")

        @site.command("build", description="Build site")
        def build() -> str:
            return "built"

        @cli.command("status", description="Status")
        def status() -> str:
            return "ok"

        paths = [name for name, _ in cli.walk_commands()]
        assert "status" in paths
        assert "site.build" in paths


# ---------------------------------------------------------------------------
# Programmatic dispatch (call / call_raw)
# ---------------------------------------------------------------------------


class TestCall:
    def test_call_basic(self) -> None:
        cli = _make_cli()
        result = cli.call("greet", name="Alice")
        assert result == {"message": "Hello Alice"}

    def test_call_default_args(self) -> None:
        cli = _make_cli()
        result = cli.call("greet")
        assert result == {"message": "Hello world"}

    def test_call_with_types(self) -> None:
        cli = _make_cli()
        result = cli.call("add", a=3, b=4)
        assert result == 7

    def test_call_unknown_command(self) -> None:
        cli = _make_cli()
        with pytest.raises(ValueError, match="Unknown command"):
            cli.call("nonexistent")

    def test_call_via_alias(self) -> None:
        cli = _make_cli()
        result = cli.call("al")
        assert result == "aliased"

    def test_call_dotted_path(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")

        @site.command("build", description="Build site")
        def build() -> str:
            return "built"

        result = cli.call("site.build")
        assert result == "built"

    def test_call_raw_returns_result(self) -> None:
        cli = _make_cli()
        result = cli.call_raw("greet", name="Bob")
        assert result == {"message": "Hello Bob"}

    def test_call_handler_exception_propagates(self) -> None:
        cli = CLI(name="test", description="")

        @cli.command("fail", description="Always fails")
        def fail() -> str:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            cli.call("fail")


# ---------------------------------------------------------------------------
# Suggest command
# ---------------------------------------------------------------------------


class TestSuggestCommand:
    def test_close_match(self) -> None:
        cli = _make_cli()
        suggestion = cli.suggest_command("gret")
        assert suggestion == "greet"

    def test_no_match(self) -> None:
        cli = _make_cli()
        suggestion = cli.suggest_command("zzzzzzz")
        assert suggestion is None

    def test_dotted_suggestion(self) -> None:
        cli = CLI(name="test", description="")
        site = cli.group("site", description="Site commands")

        @site.command("build", description="Build")
        def build() -> str:
            return ""

        @site.command("deploy", description="Deploy")
        def deploy() -> str:
            return ""

        suggestion = cli.suggest_command("site.buld")
        assert suggestion == "site.build"


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------


class TestGlobalOptions:
    def test_global_option_registration(self) -> None:
        cli = CLI(name="test", description="")
        cli.global_option("--verbose", short="-v", is_flag=True, description="Verbose")

        @cli.command("show", description="Show")
        def show() -> str:
            return "ok"

        # Global options should be accessible via context
        assert len(cli._global_options) == 1


# ---------------------------------------------------------------------------
# invoke
# ---------------------------------------------------------------------------


class TestInvoke:
    def test_invoke_basic(self) -> None:
        cli = _make_cli()
        result = cli.invoke(["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello Alice" in result.output

    def test_invoke_missing_required_arg(self) -> None:
        cli = CLI(name="test", description="")

        @cli.command("need-arg", description="Needs arg")
        def need_arg(x: int) -> int:
            return x

        result = cli.invoke(["need-arg"])
        assert result.exit_code != 0

    def test_invoke_unknown_command(self) -> None:
        cli = _make_cli()
        result = cli.invoke(["nonexistent"])
        # argparse returns exit code 2 for invalid choices
        assert result.exit_code == 2
        assert "nonexistent" in result.stderr

    def test_invoke_json_format(self) -> None:
        cli = _make_cli()
        result = cli.invoke(["greet", "--name", "Bob", "--format", "json"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Resources and prompts
# ---------------------------------------------------------------------------


class TestResources:
    def test_register_resource(self) -> None:
        cli = CLI(name="test", description="")

        @cli.resource("config://app", name="Config", description="App config")
        def app_config() -> dict:
            return {"debug": True}

        resources = cli.walk_resources()
        assert len(resources) == 1
        assert resources[0][0] == "config://app"

    def test_register_prompt(self) -> None:
        cli = CLI(name="test", description="")

        @cli.prompt("my-prompt", description="A prompt")
        def my_prompt() -> str:
            return "content"

        prompts = cli.walk_prompts()
        assert len(prompts) == 1
        assert prompts[0][0] == "my-prompt"


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


class TestMount:
    def test_mount_another_cli(self) -> None:
        parent = CLI(name="parent", description="Parent")
        child = CLI(name="child", description="Child")

        @child.command("hello", description="Hello")
        def hello() -> str:
            return "hi"

        parent.mount("child", child)
        cmd = parent.get_command("child.hello")
        assert cmd is not None

    def test_mount_with_custom_prefix(self) -> None:
        parent = CLI(name="parent", description="Parent")
        child = CLI(name="child", description="Child")

        @child.command("hello", description="Hello")
        def hello() -> str:
            return "hi"

        parent.mount("c", child)
        groups = parent.groups
        assert "c" in groups
        cmd = parent.get_command("c.hello")
        assert cmd is not None
