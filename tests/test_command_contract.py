"""Cross-surface command contract tests."""

from __future__ import annotations

from typing import Annotated, Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from milo import CLI, Context, MaxLen, MinLen, Option, Pattern, Positional
from milo._errors import InputError
from milo.llms import generate_llms_txt
from milo.mcp import _call_tool, _list_tools


def _make_contract_cli() -> CLI:
    cli = CLI(name="contract", description="Command contract fixture")

    @cli.command("deploy", description="Deploy a service")
    def deploy(
        environment: Annotated[str, MinLen(1)],
        service: Annotated[str, MinLen(1)],
        version: str = "latest",
        ctx: Context = None,
    ) -> dict[str, str]:
        """Deploy a service through every Milo dispatch surface."""
        assert isinstance(ctx, Context)
        return {
            "environment": environment,
            "service": service,
            "version": version,
        }

    site = cli.group("site", description="Site commands")

    @site.command("build", description="Build a site")
    def build(output: str = "_site", clean: bool = False) -> dict[str, str | bool]:
        """Build a site with grouped command resolution."""
        return {"output": output, "clean": clean}

    return cli


def test_command_result_matches_call_call_raw_invoke_and_mcp() -> None:
    cli = _make_contract_cli()
    expected = {
        "environment": "staging",
        "service": "api",
        "version": "2026.05",
    }

    assert (
        cli.call(
            "deploy",
            environment="staging",
            service="api",
            version="2026.05",
        )
        == expected
    )
    assert (
        cli.call_raw(
            "deploy",
            environment="staging",
            service="api",
            version="2026.05",
        )
        == expected
    )

    invoked = cli.invoke(
        [
            "deploy",
            "--environment",
            "staging",
            "--service",
            "api",
            "--version",
            "2026.05",
        ]
    )
    assert invoked.exit_code == 0
    assert invoked.exception is None
    assert invoked.result == expected

    mcp = _call_tool(
        cli,
        {
            "name": "deploy",
            "arguments": {
                "environment": "staging",
                "service": "api",
                "version": "2026.05",
            },
        },
    )
    assert "isError" not in mcp
    assert mcp["structuredContent"] == expected

    deploy_tool = next(tool for tool in _list_tools(cli) if tool["name"] == "deploy")
    assert "ctx" not in deploy_tool["inputSchema"]["properties"]


def test_grouped_command_result_matches_call_invoke_and_mcp() -> None:
    cli = _make_contract_cli()
    expected = {"output": "public", "clean": True}

    assert cli.call("site.build", output="public", clean=True) == expected

    invoked = cli.invoke(["site", "build", "--output", "public", "--clean"])
    assert invoked.exit_code == 0
    assert invoked.exception is None
    assert invoked.result == expected

    mcp = _call_tool(
        cli,
        {"name": "site.build", "arguments": {"output": "public", "clean": True}},
    )
    assert "isError" not in mcp
    assert mcp["structuredContent"] == expected


def test_context_injected_for_call_call_raw_and_mcp() -> None:
    cli = CLI(name="contract", description="")

    @cli.command("who")
    def who(ctx: Context = None) -> dict[str, str]:
        return {"ctx": type(ctx).__name__}

    assert cli.call("who") == {"ctx": "Context"}
    assert cli.call_raw("who") == {"ctx": "Context"}
    mcp = _call_tool(cli, {"name": "who", "arguments": {}})
    assert mcp["structuredContent"] == {"ctx": "Context"}


def test_required_bool_is_required_on_cli_and_mcp() -> None:
    cli = CLI(name="contract", description="")

    @cli.command("set")
    def set_flag(active: bool) -> bool:
        return active

    missing = cli.invoke(["set"])
    assert missing.exit_code == 2
    assert "--active" in missing.stderr

    assert cli.invoke(["set", "--active"]).result is True
    assert cli.call("set", active=True) is True

    mcp = _call_tool(cli, {"name": "set", "arguments": {}})
    assert mcp["isError"] is True
    assert mcp["errorData"]["argument"] == "active"


def test_integer_literal_cli_matches_programmatic_and_mcp() -> None:
    cli = CLI(name="contract", description="")

    @cli.command("pick")
    def pick(level: Literal[1, 2]) -> int:
        return level

    assert cli.invoke(["pick", "--level", "1"]).result == 1
    assert cli.call("pick", level=1) == 1
    mcp = _call_tool(cli, {"name": "pick", "arguments": {"level": 1}})
    assert mcp["structuredContent"] == 1


def test_llms_txt_uses_cli_flag_names() -> None:
    cli = CLI(name="contract", description="")

    @cli.command("deploy")
    def deploy(dry_run: bool = False) -> bool:
        return dry_run

    output = generate_llms_txt(cli)
    assert "--dry-run" in output
    assert "--dry_run" not in output


def test_parameter_descriptions_match_schema_mcp_and_llms_txt() -> None:
    cli = CLI(name="contract", description="")

    @cli.command("serve")
    def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
        """Serve requests.

        Args:
            host: Bind address.
            port: Bind port.
        """

    schema = cli.commands["serve"].schema
    tools = _list_tools(cli)
    mcp_schema = tools[0]["inputSchema"]
    output = generate_llms_txt(cli)

    for name, description in {"host": "Bind address.", "port": "Bind port."}.items():
        assert schema["properties"][name]["description"] == description
        assert mcp_schema["properties"][name]["description"] == description
        assert f"— {description}" in output

    assert "  Parameters:\n    - `--host`" in output
    assert "\n    - `--port`" in output


def test_positionals_and_option_aliases_preserve_programmatic_schema_names() -> None:
    cli = CLI(name="contract")

    @cli.command("copy")
    def copy(
        sources: Annotated[list[str], Positional("SOURCE"), MinLen(1)],
        destination: Annotated[str, Option(aliases=("-d",), metavar="DIR")] = ".",
    ) -> dict[str, object]:
        return {"sources": sources, "destination": destination}

    expected = {"sources": ["one", "two"], "destination": "out"}
    invoked = cli.invoke(["copy", "one", "two", "-d", "out"])
    assert invoked.exit_code == 0
    assert invoked.result == expected
    assert cli.call("copy", sources=["one", "two"], destination="out") == expected
    mcp = _call_tool(cli, {"name": "copy", "arguments": expected})
    assert mcp["structuredContent"] == expected
    assert "`SOURCE` (array, **required**)" in generate_llms_txt(cli)


def test_surface_policy_is_enforced_but_programmatic_calls_remain_available() -> None:
    cli = CLI(name="contract")

    @cli.command("terminal", surfaces=("cli",))
    def terminal() -> str:
        return "terminal"

    @cli.command("agent", surfaces=("mcp", "llms"))
    def agent() -> str:
        return "agent"

    root_help = cli.invoke([]).output
    help_lines = [line.strip() for line in root_help.splitlines()]
    assert "terminal" in help_lines
    assert "agent" not in help_lines
    assert [tool["name"] for tool in _list_tools(cli)] == ["agent"]
    assert "**agent**" in generate_llms_txt(cli)
    assert "**terminal**" not in generate_llms_txt(cli)
    assert cli.call("agent") == "agent"
    assert cli.invoke(["agent"]).exit_code == 2


def test_string_sourced_arguments_coerce_across_programmatic_and_mcp_paths() -> None:
    cli = CLI(name="contract")

    @cli.command("typed")
    def typed(count: int, ratio: float, active: bool, values: list[int]) -> dict:
        return {
            "count": count,
            "ratio": ratio,
            "active": active,
            "values": values,
        }

    expected = {"count": 2, "ratio": 1.5, "active": True, "values": [3, 4]}
    string_arguments = {
        "count": "2",
        "ratio": "1.5",
        "active": "true",
        "values": '["3", "4"]',
    }

    assert cli.call("typed", **string_arguments) == expected
    assert cli.call_raw("typed", **string_arguments) == expected

    invoked = cli.invoke(
        [
            "typed",
            "--count",
            "2",
            "--ratio",
            "1.5",
            "--active",
            "--values",
            "3",
            "4",
        ]
    )
    assert invoked.exit_code == 0
    assert invoked.result == expected

    mcp = _call_tool(cli, {"name": "typed", "arguments": string_arguments})
    assert mcp["structuredContent"] == expected


def test_unknown_arguments_are_rejected_across_every_dispatch_surface() -> None:
    cli = CLI(name="contract")

    @cli.command("greet")
    def greet(name: str) -> str:
        return name

    for call in (cli.call, cli.call_raw):
        with pytest.raises(InputError) as exc_info:
            call("greet", name="Alice", bogus=1)
        assert exc_info.value.argument == "bogus"
        assert exc_info.value.context["reason"] == "unexpected_argument"

    invoked = cli.invoke(["greet", "--name", "Alice", "--bogus", "1"])
    assert invoked.exit_code == 2
    assert "unrecognized arguments" in invoked.stderr

    mcp = _call_tool(
        cli,
        {"name": "greet", "arguments": {"name": "Alice", "bogus": 1}},
    )
    assert mcp["isError"] is True
    assert mcp["errorData"]["argument"] == "bogus"
    assert mcp["errorData"]["reason"] == "unexpected_argument"


@settings(max_examples=40)
@given(st.text(alphabet="ab", max_size=8))
def test_generated_schema_constraints_match_every_dispatch_surface(value: str) -> None:
    cli = CLI(name="contract")
    calls: list[str] = []

    @cli.command("bounded")
    def bounded(
        name: Annotated[
            str,
            MinLen(2),
            MaxLen(5),
            Pattern(r"^a+$"),
        ],
    ) -> str:
        calls.append(name)
        return name

    accepted = 2 <= len(value) <= 5 and set(value) <= {"a"}
    if accepted:
        assert cli.call("bounded", name=value) == value
        assert cli.call_raw("bounded", name=value) == value
        invoked = cli.invoke(["bounded", "--name", value])
        assert invoked.exit_code == 0
        assert invoked.result == value
        mcp = _call_tool(cli, {"name": "bounded", "arguments": {"name": value}})
        assert "isError" not in mcp
        assert calls == [value, value, value, value]
    else:
        with pytest.raises(InputError):
            cli.call("bounded", name=value)
        with pytest.raises(InputError):
            cli.call_raw("bounded", name=value)
        invoked = cli.invoke(["bounded", "--name", value])
        assert invoked.exit_code == 1
        assert "M-INP-007" in invoked.stderr
        mcp = _call_tool(cli, {"name": "bounded", "arguments": {"name": value}})
        assert mcp["isError"] is True
        assert mcp["errorData"]["errorCode"] == "M-INP-007"
        assert mcp["errorData"]["argument"] == "name"
        assert mcp["errorData"]["reason"] == "constraint_violation"
        assert calls == []
