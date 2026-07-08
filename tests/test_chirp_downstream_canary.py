"""Version pin, local fixture, CI, and documentation proof for issue #77."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT = _ROOT / "tests" / "downstream" / "chirp_canary" / "contract.json"
_RUNNER = _ROOT / "scripts" / "check_chirp_canary.py"


def _contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_CONTRACT.read_text(encoding="utf-8")))


def test_canary_pins_released_immutable_contract() -> None:
    contract = _contract()

    assert contract["versions"] == {
        "milo": "0.4.1",
        "chirp": "0.9.0",
        "chirp_tag": "v0.9.0",
        "chirp_commit": "9ada3ba4b26ed37fbfde0ef69b60c3897830d3d3",
    }
    assert list(contract["commands"]) == [
        "new",
        "run",
        "dev",
        "check",
        "diff",
        "routes",
        "security-check",
        "freeze",
        "makemigrations",
        "migrate",
        "shapes-codegen",
    ]
    assert "main" not in json.dumps(contract["versions"])


def test_current_milo_passes_the_chirp_shaped_fixture() -> None:
    env = os.environ.copy()
    env["PYTHON_GIL"] = "0"
    completed = subprocess.run(
        (sys.executable, str(_RUNNER), "--fixture-only", "--require-free-threaded"),
        cwd=_ROOT,
        env=env,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(completed.stdout)

    assert receipt["status"] == "passed"
    assert receipt["free_threaded"] is True
    assert receipt["commands"] == 11
    assert receipt["mcp_tools"] == ["check", "diff", "routes", "security-check"]
    assert receipt["versions"] == _contract()["versions"]


def test_canary_ci_and_advance_policy_use_the_same_exact_pair() -> None:
    makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (_ROOT / ".github" / "workflows" / "downstream-chirp.yml").read_text(
        encoding="utf-8"
    )
    docs = (_ROOT / "docs" / "chirp-downstream-canary.md").read_text(encoding="utf-8")

    for source in (makefile, workflow, docs):
        assert "0.4.1" in source
        assert "0.9.0" in source
    assert "--no-project --isolated --python 3.14t" in makefile
    assert "--with milo-cli==0.4.1 --with bengal-chirp==0.9.0" in makefile
    assert 'PYTHON_GIL: "0"' in workflow
    assert "schedule:" in workflow
    assert "make chirp-canary" in workflow
    assert "does not use a compatible range" in docs
    assert "do not\n   scrape an unreleased branch" in docs
