"""Cross-surface command contract tests."""

from __future__ import annotations

from typing import Annotated, Literal

from milo import CLI, Context, MinLen
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
