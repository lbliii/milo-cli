"""Executable governance and CI baseline for issue #109."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_governance_front_doors_exist_and_name_executable_checks() -> None:
    contributing = (_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    security = (_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    planning = (_ROOT / "plan" / "README.md").read_text(encoding="utf-8")
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")

    for command in ("make lint", "make ty", "make test-cov", "make docs-test"):
        assert command in contributing
    assert "mailto:" in security
    assert "milo-cli security report" in security
    assert "MCP annotations" in security
    assert "GitHub issues are Milo's canonical roadmap" in planning
    assert "[CONTRIBUTING.md](CONTRIBUTING.md)" in readme
    assert "[SECURITY.md](SECURITY.md)" in readme


def test_test_taxonomy_reduces_the_flat_suite_and_names_boundaries() -> None:
    flat_tests = list((_ROOT / "tests").glob("test_*.py"))
    layout = (_ROOT / "tests" / "README.md").read_text(encoding="utf-8")

    assert len(flat_tests) <= 66
    for directory in ("unit", "integration", "docs", "downstream"):
        assert (_ROOT / "tests" / directory).is_dir()
        assert f"`{directory}/`" in layout
    assert (_ROOT / "tests" / "unit" / "test_schema_properties.py").is_file()
    assert (_ROOT / "tests" / "unit" / "test_reducer_properties.py").is_file()


def test_ci_has_gil_on_control_and_gil_off_free_threaded_lanes() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    reference = (_ROOT / ".github" / "workflows" / "README.md").read_text(encoding="utf-8")

    assert 'python-version: "3.14"' in workflow
    assert 'python-version: "3.14t"' in workflow
    assert 'python-gil: "1"' in workflow
    assert 'python-gil: "0"' in workflow
    assert "EXPECTED_GIL" in workflow
    assert "--cov-fail-under=80" in reference
    assert "sys._is_gil_enabled()" in reference
    assert "benchmark" in reference.lower()
