"""Drift gate: every examples/*/ dir must be referenced in the README index.

When you add a new example, add a row to the "Examples Index" section in
README.md. This test fails CI otherwise — keeps the index honest.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_README = _REPO_ROOT / "README.md"
_EXAMPLES_DIR = _REPO_ROOT / "examples"


def _example_dirs() -> list[str]:
    return sorted(p.parent.name for p in _EXAMPLES_DIR.glob("*/app.py"))


def test_every_example_is_referenced_in_readme():
    readme = _README.read_text(encoding="utf-8")
    missing = [name for name in _example_dirs() if f"examples/{name}" not in readme]
    assert not missing, (
        f"README.md is missing rows for {len(missing)} example(s): {missing}. "
        f"Add them to the 'Examples Index' section."
    )
