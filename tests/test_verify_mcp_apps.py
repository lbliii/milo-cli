"""MCP Apps conformance proof for ``milo verify`` (issue #81)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from milo.verify import VerifyCheck, VerifyReport, verify


def _write_app(tmp_path: Path, source: str) -> Path:
    app = tmp_path / "app.py"
    app.write_text(textwrap.dedent(source), encoding="utf-8")
    return app


def _checks(report: VerifyReport) -> dict[str, VerifyCheck]:
    return {check.name: check for check in report.checks}


def test_verify_mcp_apps_good_fixture_covers_text_blob_metadata_and_gateway(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import (
            CLI,
            MCPAppCSP,
            MCPAppPermissions,
            MCPAppResourceMeta,
            MCPAppToolMeta,
        )

        cli = CLI(name="weather")

        @cli.ui_resource(
            "ui://weather/dashboard",
            name="Weather dashboard",
            meta=MCPAppResourceMeta(
                csp=MCPAppCSP(
                    connect_domains=("https://api.weather.test",),
                    resource_domains=("https://cdn.weather.test",),
                ),
                permissions=MCPAppPermissions(geolocation=True),
                domain="weather.example.test",
                prefers_border=False,
            ),
        )
        def dashboard() -> str:
            return "<!doctype html><html><body>Weather</body></html>"

        @cli.ui_resource("ui://weather/icon", name="Weather icon")
        def icon() -> bytes:
            return b"not-interpreted-html-bytes"

        @cli.command("forecast", ui=MCPAppToolMeta("ui://weather/dashboard"))
        def forecast(city: str = "Boston") -> dict[str, str]:
            \"\"\"Return a forecast.

            Args:
                city: City to forecast.
            \"\"\"
            return {"city": city}

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 0, report.format()
    checks = _checks(report)
    assert checks["mcp_apps_in_process"].status == "ok"
    assert checks["mcp_apps_in_process"].message == (
        "1 tool link(s) and 2 UI resource(s) agree; 2 resource(s) readable"
    )
    assert checks["mcp_apps_gateway"].status == "ok"
    assert checks["mcp_apps_gateway"].message == (
        "gateway preserves 1 tool link(s) and 2 UI resource(s)"
    )
    assert checks["mcp_apps_transport"].status == "ok"
    assert "2 resource(s) readable" in checks["mcp_apps_transport"].message


def test_verify_does_not_parse_application_html(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="opaque-html")

        @cli.ui_resource("ui://opaque/view")
        def view() -> str:
            return "application-owned payload; Milo deliberately does not parse this"

        @cli.command("show", ui=MCPAppToolMeta("ui://opaque/view"))
        def show() -> str:
            return "fallback"

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 0, report.format()
    assert _checks(report)["mcp_apps_in_process"].status == "ok"
    assert _checks(report)["mcp_apps_transport"].status == "ok"


def test_verify_missing_link_fails_all_apps_views_with_repair_data(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="broken-link")

        @cli.command("show", ui=MCPAppToolMeta("ui://broken/missing"))
        def show() -> str:
            return "fallback"

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    for name in ("mcp_apps_in_process", "mcp_apps_gateway", "mcp_apps_transport"):
        assert checks[name].status == "fail"
        assert "M-UI-002" in checks[name].details
        assert "cli.ui_resource" in checks[name].details


def test_verify_checks_registered_app_only_links_absent_from_model_tools_list(
    tmp_path: Path,
) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="app-only-link")

        @cli.command(
            "refresh",
            ui=MCPAppToolMeta("ui://app-only/missing", visibility=("app",)),
        )
        def refresh() -> str:
            return "fallback"

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    assert checks["mcp_apps_in_process"].status == "fail"
    assert "M-UI-002" in checks["mcp_apps_in_process"].details
    assert "app-only/missing" in checks["mcp_apps_in_process"].details
    assert checks["mcp_apps_transport"].status == "fail"


@pytest.mark.parametrize(
    ("corruption", "expected_detail"),
    [
        (
            'object.__setattr__(resource, "uri", "https://invalid.test/view")',
            "non-empty ui:// URI",
        ),
        (
            'object.__setattr__(resource, "mime_type", "text/html")',
            "text/html;profile=mcp-app",
        ),
        (
            'object.__setattr__(resource.meta, "domain", 7)',
            "_meta.ui.domain must be a non-empty string",
        ),
    ],
    ids=("uri", "mime-profile", "metadata"),
)
def test_verify_rejects_malformed_ui_resource_views(
    tmp_path: Path,
    corruption: str,
    expected_detail: str,
) -> None:
    app = _write_app(
        tmp_path,
        f"""
        from milo import CLI, MCPAppResourceMeta, MCPAppToolMeta

        cli = CLI(name="malformed-view")

        @cli.ui_resource(
            "ui://malformed/view",
            meta=MCPAppResourceMeta(domain="valid.example.test"),
        )
        def view() -> str:
            return "<!doctype html><html></html>"

        @cli.command("show", ui=MCPAppToolMeta("ui://malformed/view"))
        def show() -> str:
            return "fallback"

        resource = cli._ui_resources["ui://malformed/view"]
        {corruption}

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    for name in ("mcp_apps_in_process", "mcp_apps_gateway", "mcp_apps_transport"):
        assert checks[name].status == "fail"
        assert expected_detail in checks[name].details
    assert checks["mcp_transport"].status == "ok"


@pytest.mark.parametrize(
    ("handler_body", "error_code", "expected_detail"),
    [
        (
            'return {"not": "html"}',
            "M-UI-001",
            "Return a valid HTML5 document",
        ),
        (
            'raise RuntimeError("template exploded")',
            "M-UI-004",
            "Fix the UI resource handler",
        ),
    ],
    ids=("invalid-return", "render-error"),
)
def test_verify_resource_payload_failures_are_actionable(
    tmp_path: Path,
    handler_body: str,
    error_code: str,
    expected_detail: str,
) -> None:
    app = _write_app(
        tmp_path,
        f"""
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="broken-payload")

        @cli.ui_resource("ui://broken/view")
        def view() -> str:
            {handler_body}

        @cli.command("show", ui=MCPAppToolMeta("ui://broken/view"))
        def show() -> str:
            return "fallback"

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    assert checks["mcp_apps_in_process"].status == "fail"
    assert error_code in checks["mcp_apps_in_process"].details
    assert expected_detail in checks["mcp_apps_in_process"].details
    assert checks["mcp_apps_gateway"].status == "ok"
    assert checks["mcp_apps_transport"].status == "fail"
    assert error_code in checks["mcp_apps_transport"].details


def test_verify_rejects_ui_handler_stdout_that_would_corrupt_json_rpc(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="stdout-leak")

        @cli.ui_resource("ui://stdout/view")
        def view() -> str:
            print("debug output that corrupts MCP stdout")
            return "<!doctype html><html></html>"

        @cli.command("show", ui=MCPAppToolMeta("ui://stdout/view"))
        def show() -> str:
            return "fallback"

        if __name__ == "__main__":
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    assert checks["mcp_apps_in_process"].status == "ok"
    assert checks["mcp_apps_gateway"].status == "ok"
    assert checks["mcp_transport"].status == "fail"
    assert checks["mcp_apps_transport"].status == "fail"
    assert "non-JSON MCP stdout" in checks["mcp_apps_transport"].details
    assert "write diagnostics to stderr or Context" in checks["mcp_apps_transport"].details


def test_verify_subprocess_capability_mismatch_has_stable_transport_identity(
    tmp_path: Path,
) -> None:
    app = _write_app(
        tmp_path,
        """
        from milo import CLI, MCPAppToolMeta

        cli = CLI(name="wire-mismatch")

        @cli.ui_resource("ui://wire/view")
        def view() -> str:
            return "<!doctype html><html></html>"

        @cli.command("show", ui=MCPAppToolMeta("ui://wire/view"))
        def show() -> str:
            return "fallback"

        if __name__ == "__main__":
            import milo.mcp as _mcp

            def _without_extensions(*, include_ui=False):
                return {"tools": {}, "resources": {}, "prompts": {}}

            _mcp._server_capabilities = _without_extensions
            cli.run()
        """,
    )

    report = verify(str(app))
    assert report.exit_code == 1
    checks = _checks(report)
    assert checks["mcp_apps_in_process"].status == "ok"
    assert checks["mcp_apps_gateway"].status == "ok"
    assert checks["mcp_transport"].status == "ok"
    assert checks["mcp_apps_transport"].status == "fail"
    assert "io.modelcontextprotocol/ui" in checks["mcp_apps_transport"].details
    assert "Advertise" in checks["mcp_apps_transport"].details
