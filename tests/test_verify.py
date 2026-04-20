"""Tests for the `milo verify` self-diagnosis pipeline."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from milo._scaffold import scaffold
from milo.verify import VerifyCheck, VerifyReport, verify

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES_DIR = _REPO_ROOT / "examples"


# Examples that legitimately cannot pass `milo verify` as-is — not bugs in
# verify, just incompatibility with the one-CLI-instance model. Document *why*
# so future contributors don't silently grow the list.
_SKIP_EXAMPLES: dict[str, str] = {
    # Add entries here with a reason. Empty by default — every example should
    # be verifiable, so new exceptions are a regression signal.
}


class TestVerifyReport:
    def test_empty_report_has_zero_counts(self):
        r = VerifyReport(target="x", checks=())
        assert r.passed == 0
        assert r.failures == 0
        assert r.warnings == 0
        assert r.exit_code == 0

    def test_failure_sets_exit_code_one(self):
        r = VerifyReport(
            target="x",
            checks=(VerifyCheck(name="k", status="fail", message="m"),),
        )
        assert r.exit_code == 1

    def test_warning_does_not_set_exit_code(self):
        r = VerifyReport(
            target="x",
            checks=(VerifyCheck(name="k", status="warn", message="m"),),
        )
        assert r.exit_code == 0

    def test_format_contains_target_and_all_checks(self):
        r = VerifyReport(
            target="my.py",
            checks=(
                VerifyCheck(name="a", status="ok", message="good"),
                VerifyCheck(name="b", status="fail", message="bad", details="line1\nline2"),
            ),
        )
        out = r.format()
        assert "milo verify my.py" in out
        assert "a: good" in out
        assert "b: bad" in out
        assert "line1" in out
        assert "line2" in out


class TestVerifyScaffold:
    """End-to-end: scaffold a project, then verify it passes."""

    def test_freshly_scaffolded_project_passes(self, tmp_path):
        project = scaffold("verify_scaffold", tmp_path)
        report = verify(str(project / "app.py"))
        assert report.exit_code == 0, report.format()
        assert report.failures == 0
        assert report.passed >= 6
        # Confirm every expected check is present and passed
        check_names = {c.name for c in report.checks}
        for expected in {
            "imports",
            "cli_located",
            "commands_registered",
            "schemas_generate",
            "mcp_list_tools",
            "mcp_transport",
        }:
            assert expected in check_names


class TestVerifyFailurePaths:
    def test_missing_file_fails_imports(self, tmp_path):
        report = verify(str(tmp_path / "does_not_exist.py"))
        assert report.exit_code == 1
        assert report.checks[0].name == "imports"
        assert report.checks[0].status == "fail"

    def test_import_error_fails_imports(self, tmp_path):
        broken = tmp_path / "syntax_error.py"
        broken.write_text("this is not valid python :(")
        report = verify(str(broken))
        assert report.exit_code == 1
        assert report.checks[0].status == "fail"
        assert "SyntaxError" in report.checks[0].message

    def test_module_without_cli_instance_fails(self, tmp_path):
        no_cli = tmp_path / "no_cli.py"
        no_cli.write_text("def hello(): return 'hi'\n")
        report = verify(str(no_cli))
        assert report.exit_code == 1
        names_and_statuses = [(c.name, c.status) for c in report.checks]
        assert ("cli_located", "fail") in names_and_statuses

    def test_cli_with_no_commands_fails(self, tmp_path):
        empty = tmp_path / "empty_cli.py"
        empty.write_text(
            textwrap.dedent(
                """
                from milo import CLI
                cli = CLI(name="empty", version="0.1")
                """
            )
        )
        report = verify(str(empty))
        assert report.exit_code == 1
        names_and_statuses = [(c.name, c.status) for c in report.checks]
        assert ("commands_registered", "fail") in names_and_statuses

    def test_undocumented_param_produces_warning(self, tmp_path):
        undoc = tmp_path / "undoc.py"
        undoc.write_text(
            textwrap.dedent(
                """
                from milo import CLI
                cli = CLI(name="undoc", version="0.1")

                @cli.command("hello", description="Say hi")
                def hello(name: str, extra: int = 0) -> str:
                    \"\"\"Say hi.

                    Args:
                        name: Who to greet.
                    \"\"\"
                    return f"hi {name} ({extra})"

                if __name__ == "__main__":
                    cli.run()
                """
            )
        )
        report = verify(str(undoc))
        assert report.exit_code == 0  # warning only, not failure
        assert report.warnings >= 1
        schemas_check = next(c for c in report.checks if c.name == "schemas_generate")
        assert schemas_check.status == "warn"
        assert "extra" in schemas_check.details

    def test_unknown_target_format_fails_imports(self):
        report = verify("not-a-path-not-a-module")
        assert report.exit_code == 1
        assert report.checks[0].name == "imports"
        assert report.checks[0].status == "fail"


class TestVerifyModuleAttrForm:
    def test_module_attr_form_skips_subprocess_check(self, tmp_path, monkeypatch):
        # Create a package-style module and import by module:attr
        pkg_dir = tmp_path / "mypkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text(
            textwrap.dedent(
                """
                from milo import CLI
                cli = CLI(name="mypkg", version="0.1")

                @cli.command("hello", description="Say hi")
                def hello(name: str) -> str:
                    \"\"\"Say hi.

                    Args:
                        name: Who to greet.
                    \"\"\"
                    return f"hi {name}"
                """
            )
        )
        monkeypatch.chdir(tmp_path)
        report = verify("mypkg:cli")
        transport_check = next(c for c in report.checks if c.name == "mcp_transport")
        assert transport_check.status == "skip"
        assert report.exit_code == 0


# ---------------------------------------------------------------------------
# Regression gate: every CLI example in examples/ must pass `milo verify`.
# `milo verify` targets the CLI/MCP protocol, so App-based TUI examples
# (which don't construct a `CLI(...)` at module scope) are out of scope.
# ---------------------------------------------------------------------------


def _example_ids() -> list[str]:
    """Return example names whose app.py constructs a top-level `CLI(...)`."""
    ids: list[str] = []
    for app_py in _EXAMPLES_DIR.glob("*/app.py"):
        text = app_py.read_text(encoding="utf-8")
        if "CLI(" in text:
            ids.append(app_py.parent.name)
    return sorted(ids)


@pytest.mark.parametrize("example_name", _example_ids())
def test_example_passes_verify(example_name):
    if example_name in _SKIP_EXAMPLES:
        pytest.skip(_SKIP_EXAMPLES[example_name])
    app_path = _EXAMPLES_DIR / example_name / "app.py"
    report = verify(str(app_path), timeout=10.0)
    if report.exit_code != 0:
        pytest.fail(
            f"Example {example_name!r} fails `milo verify`:\n\n{report.format()}"
        )


class TestMiloVerifyCommand:
    def test_milo_verify_exits_zero_on_valid_cli(self, tmp_path):
        project = scaffold("cmd_ok", tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "milo.cli", "verify", str(project / "app.py")],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "6 passed" in result.stdout

    def test_milo_verify_exits_nonzero_on_missing_file(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "-m", "milo.cli", "verify", str(tmp_path / "nope.py")],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 1
        assert "imports" in result.stdout
        assert "fail" in result.stdout or "✗" in result.stdout
