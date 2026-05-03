"""Cross-surface command contract tests."""

from __future__ import annotations

from typing import Annotated

from milo import CLI, Context, MinLen
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
        _ = ctx
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
