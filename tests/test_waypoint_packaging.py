"""Clean-checkout replay, documentation, and CI proof for Waypoint issue #103."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_REPLAY = _ROOT / "showcase" / "waypoint" / "replay.py"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


def test_clean_checkout_replay_shows_race_pick_and_dag_under_two_minutes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "fixture"
    started = time.monotonic()
    completed = subprocess.run(
        (sys.executable, str(_REPLAY), "--repo", str(repo)),
        cwd=_ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=120,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 120
    assert "ACT 1 — hook → CLI" in completed.stdout
    assert "race recorded: 3 parallel attempts" in completed.stdout
    assert "ACT 2 — agent → MCP" in completed.stdout
    assert "why [readOnlyHint]" in completed.stdout
    assert "pick [destructiveHint]: safe → planner.py" in completed.stdout
    assert "ACT 3 — human → TUI / MCP Apps" in completed.stdout
    assert "DAG view: plan-race" in completed.stdout
    assert "ui://waypoint/attempts" in completed.stdout
    assert "CLI for depth, MCP for reach" in completed.stdout
    assert (repo / "planner.py").read_text(encoding="utf-8") == (
        'def choose_plan() -> str:\n    return "validate every dependency before landing"\n'
    )
    refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/waypoint/")
    assert refs.splitlines() == [
        "refs/waypoint/plan-race/balanced",
        "refs/waypoint/plan-race/fast",
        "refs/waypoint/plan-race/meta",
        "refs/waypoint/plan-race/safe",
    ]


def test_waypoint_packaging_is_cross_linked_and_recording_ready() -> None:
    root_readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    examples_readme = (_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    waypoint_readme = (_ROOT / "showcase" / "waypoint" / "README.md").read_text(encoding="utf-8")
    launch_script = (_ROOT / "docs" / "launch-demo-script.md").read_text(encoding="utf-8")

    assert "[Waypoint showcase](showcase/waypoint/)" in root_readme
    assert "[Waypoint showcase](../showcase/waypoint/)" in examples_readme
    assert "complete product demonstration" in examples_readme
    assert "Git records what changed; agents need why" in waypoint_readme
    assert "uv run python showcase/waypoint/replay.py" in waypoint_readme
    assert "Hook → CLI, agent → MCP, and human → TUI/Apps" in waypoint_readme
    assert "CLI for depth, MCP for reach" in waypoint_readme
    assert "Keep Waypoint in-tree through Milo's launch" in waypoint_readme
    assert "Waypoint replay's three-attempt DAG" in launch_script


def test_make_ci_and_github_actions_verify_waypoint() -> None:
    makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "showcase-test:" in makefile
    assert "pytest tests/test_waypoint*.py" in makefile
    assert "milo verify showcase/waypoint/app.py" in makefile
    assert "$(MAKE) showcase-test" in makefile
    assert "showcase/waypoint/" in workflow
    assert "Verify Waypoint showcase" in workflow
    assert "uv run milo verify showcase/waypoint/app.py" in workflow
