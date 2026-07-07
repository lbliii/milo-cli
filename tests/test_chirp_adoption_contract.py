"""Executable proof for the Chirp CLI adoption contract (issues #75 and #76)."""

from __future__ import annotations

import json
from typing import Annotated

import pytest

from milo import CLI, ErrorCode, MiloError, Option, Positional, generate_llms_txt
from milo.testing import MCPClient


def _chirp_shaped_cli() -> CLI:
    cli = CLI(
        name="chirp",
        description="Chirp — A Python web framework for the modern web platform.",
        version="0.8.2",
    )

    @cli.command("check", description="Validate hypermedia contracts")
    def check(
        app: Annotated[str, Positional("APP")],
        warnings_as_errors: bool = False,
        coverage: bool = False,
        deploy: bool = False,
        json: bool = False,
        baseline: str | None = None,
        include_info: bool = False,
    ) -> dict[str, str | bool | None]:
        """Return a representative Chirp contract report.

        Args:
            app: Chirp app import string.
            warnings_as_errors: Treat warnings as failures.
            coverage: Include contract coverage.
            deploy: Use production posture.
            json: Preserve Chirp's legacy JSON-output selector.
            baseline: Optional baseline path.
            include_info: Include informational findings.
        """
        return {
            "app": app,
            "warnings_as_errors": warnings_as_errors,
            "coverage": coverage,
            "deploy": deploy,
            "json": json,
            "baseline": baseline,
            "include_info": include_info,
        }

    @cli.command(
        "migrate",
        description="Apply pending schema migrations",
        annotations={"destructiveHint": True, "idempotentHint": True},
    )
    def migrate(
        db: Annotated[str, Positional("DB")],
        migrations_dir: Annotated[
            str, Option(aliases=("--migrations",), metavar="DIR")
        ] = "migrations",
    ) -> dict[str, str]:
        """Return a representative migration result.

        Args:
            db: Database URL.
            migrations_dir: Directory containing migrations.
        """
        return {"db": db, "migrations_dir": migrations_dir, "status": "ok"}

    @cli.command("security-check", description="Audit app security")
    def security_check(app: Annotated[str, Positional("APP")]) -> dict[str, str]:
        """Return a representative security result.

        Args:
            app: Chirp app import string.
        """
        return {"app": app, "status": "ok"}

    return cli


def test_public_milo_surfaces_share_the_chirp_shaped_contract() -> None:
    cli = _chirp_shaped_cli()

    invoked = cli.invoke(
        [
            "check",
            "myapp:app",
            "--warnings-as-errors",
            "--json",
            "--format",
            "json",
        ]
    )
    assert invoked.exit_code == 0
    assert json.loads(invoked.output)["app"] == "myapp:app"

    called = cli.call_raw("check", app="myapp:app", deploy=True)
    assert called["deploy"] is True

    mcp_result = MCPClient(cli).call("check", app="myapp:app", include_info=True)
    assert mcp_result.is_error is False
    assert mcp_result.structured["include_info"] is True

    llms = generate_llms_txt(cli)
    assert "**check**: Validate hypermedia contracts" in llms
    assert "`APP` (string, **required**)" in llms


def test_public_milo_supports_hyphenated_commands_and_mcp_annotations() -> None:
    cli = _chirp_shaped_cli()
    names = {tool.name for tool in MCPClient(cli).list_tools()}
    migrate = next(tool for tool in MCPClient(cli).list_tools() if tool.name == "migrate")
    migrate_definition = cli.get_command("migrate")

    assert "security-check" in names
    assert migrate.input_schema["required"] == ["db"]
    assert migrate_definition is not None
    assert migrate_definition.annotations["destructiveHint"] is True
    assert cli.invoke(["security-check", "myapp:app"]).exit_code == 0


def test_precomputed_lazy_schema_preserves_help_and_discovery_without_import() -> None:
    cli = CLI(name="chirp")
    schema = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Chirp app import string."},
        },
        "required": ["app"],
    }
    cli.lazy_command(
        "run",
        "module_that_must_not_import:run_server",
        description="Start the server",
        schema=schema,
    )

    help_result = cli.invoke(["run", "--help"])
    assert help_result.exit_code == 0
    assert "--app" in help_result.output
    assert [tool.name for tool in MCPClient(cli).list_tools()] == ["run"]


def test_typed_presentation_supports_positionals_and_option_aliases() -> None:
    cli = _chirp_shaped_cli()

    chirp_syntax = cli.invoke(["check", "myapp:app"])
    migration = cli.invoke(["migrate", "sqlite:///db.sqlite", "--migrations", "schema/migrations"])

    assert chirp_syntax.exit_code == 0
    assert migration.exit_code == 0
    assert migration.result["migrations_dir"] == "schema/migrations"
    schema = cli.get_command("migrate").schema  # type: ignore[union-attr]
    assert schema["properties"]["db"]["x-milo-cli"] == {
        "kind": "positional",
        "metavar": "DB",
    }
    assert "--migrations" in cli.invoke(["migrate", "--help"]).output


def test_command_policy_can_be_cli_visible_but_not_agent_visible() -> None:
    cli = CLI(name="chirp")

    @cli.command("run", surfaces=("cli",))
    def run(app: str) -> str:
        return app

    assert cli.invoke(["run", "--app", "myapp:app"]).exit_code == 0
    assert "run" not in {tool.name for tool in MCPClient(cli).list_tools()}
    assert "**run**" not in generate_llms_txt(cli)
    assert cli.call("run", app="myapp:app") == "myapp:app"


def test_root_version_alias_and_report_are_lazy_and_customizable() -> None:
    calls = 0

    def report() -> str:
        nonlocal calls
        calls += 1
        return "chirp 0.8.2\nkida 1.4.0"

    cli = CLI(
        name="chirp",
        version="0.8.2",
        version_flags=("-V", "--version"),
        version_report=report,
    )
    cli.build_parser()
    assert calls == 0

    short = cli.invoke(["-V"])
    long = cli.invoke(["--version"])

    assert short.exit_code == 0
    assert long.exit_code == 0
    assert short.output == long.output == "chirp 0.8.2\nkida 1.4.0\n"
    assert calls == 2


@pytest.mark.parametrize(
    "import_path",
    [
        "missing_chirp_command_module:handler",
        "_lazy_handlers:missing_chirp_handler",
    ],
)
def test_lazy_import_failure_is_structured_across_surfaces(import_path: str) -> None:
    cli = CLI(name="chirp")
    cli.lazy_command(
        "broken",
        import_path,
        schema={"type": "object", "properties": {}},
    )

    result = cli.invoke(["broken"])

    assert result.exit_code == 1
    assert "M-CMD-004" in result.stderr
    assert import_path in result.stderr

    for method in (cli.call, cli.call_raw):
        with pytest.raises(MiloError) as exc_info:
            method("broken")
        assert exc_info.value.code is ErrorCode.CMD_IMPORT
        assert exc_info.value.context["reason"] == "lazy_import_failed"

    mcp = MCPClient(cli).call("broken")
    assert mcp.is_error is True
    assert mcp.error_data is not None
    assert mcp.error_data["errorCode"] == "M-CMD-004"
    assert mcp.error_data["importPath"] == import_path


def test_terminal_renderer_is_terminal_only() -> None:
    cli = CLI(name="chirp")
    renders = 0

    def render(result: dict[str, int], _ctx: object) -> str:
        nonlocal renders
        renders += 1
        return f"Found {result['findings']} findings"

    @cli.command("check", terminal_renderer=render)
    def check() -> dict[str, int]:
        return {"findings": 3}

    terminal = cli.invoke(["check"])
    assert terminal.output == "Found 3 findings\n"
    assert cli.call("check") == {"findings": 3}
    assert MCPClient(cli).call("check").structured == {"findings": 3}
    json_output = cli.invoke(["check", "--format", "json"])
    assert json.loads(json_output.output) == {"findings": 3}
    assert renders == 1
