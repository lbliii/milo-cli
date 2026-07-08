"""Contract and full-loop proof for the Waypoint showcase (issue #99)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from milo import generate_llms_txt
from milo.mcp import _CLIHandler
from milo.verify import verify

_ROOT = Path(__file__).resolve().parents[1]
_APP_PATH = _ROOT / "showcase" / "waypoint" / "app.py"
_GIT = shutil.which("git")


def _load_app() -> ModuleType:
    module_name = "_test_waypoint_app"
    spec = importlib.util.spec_from_file_location(module_name, _APP_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _git_run(repo: Path, *args: str) -> str:
    assert _GIT is not None
    completed = subprocess.run(
        (_GIT, "-C", str(repo), *args),
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    _git_run(tmp_path, "init", "-b", "main")
    _git_run(tmp_path, "config", "user.name", "Waypoint Tests")
    _git_run(tmp_path, "config", "user.email", "waypoint-tests@example.test")
    _git_run(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "story.txt").write_text("base\n", encoding="utf-8")
    _git_run(tmp_path, "add", "story.txt")
    _git_run(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)
    return _load_app(), tmp_path


def test_showcase_readmes_distinguish_demonstrations_from_copy_paths() -> None:
    showcase = (_ROOT / "showcase" / "README.md").read_text(encoding="utf-8")
    waypoint = (_ROOT / "showcase" / "waypoint" / "README.md").read_text(encoding="utf-8")
    assert "complete demonstrations" in showcase
    assert "small, focused copy paths" in showcase
    assert "showcase/`, not `examples/`" in waypoint
    assert "Git records what" in waypoint


@pytest.mark.parametrize(
    "value",
    ["", "-intent", "intent-", "Intent", "has/slash", "has space", "a" * 65],
)
def test_waypoint_ids_reject_values_unsafe_for_the_ref_contract(value: str) -> None:
    module = _load_app()
    with pytest.raises(ValueError, match="lowercase letters, digits, or hyphens"):
        module.validate_id(value, field="intent id")


def test_waypoint_ref_is_deterministic_namespaced_and_reserves_metadata() -> None:
    module = _load_app()
    assert module.waypoint_ref("launch-milo", "agent-2") == ("refs/waypoint/launch-milo/agent-2")
    with pytest.raises(ValueError, match="reserved"):
        module.waypoint_ref("launch-milo", "meta")


def test_intent_metadata_round_trips_through_commit_trailers() -> None:
    module = _load_app()
    intent = module.Intent(
        id="launch-milo",
        title="Launch Milo",
        agent="codex",
        created_at=datetime(2026, 7, 8, 16, 25, tzinfo=UTC),
        task_ref="milo-cli#99",
    )
    message = intent.commit_message()
    assert message.startswith("waypoint-intent: Launch Milo\n\n")
    assert "Waypoint-Type: intent" in message
    assert module.parse_intent_message(message) == intent


def test_checkpoint_metadata_round_trips_through_commit_trailers() -> None:
    module = _load_app()
    metadata = module.CheckpointMetadata(
        intent_id="launch-milo",
        attempt_id="agent-2",
        agent="codex",
        why="preserve the shared schema contract",
        created_at=datetime(2026, 7, 8, 16, 30, tzinfo=UTC),
        task_ref="milo-cli#99",
    )
    message = metadata.commit_message()
    assert message.startswith("waypoint: preserve the shared schema contract\n\n")
    assert "Waypoint-Intent: launch-milo" in message
    assert "Waypoint-Timestamp: 2026-07-08T16:30:00Z" in message
    assert "Waypoint-Type: checkpoint" in message
    assert module.parse_checkpoint_message(message) == metadata


@pytest.mark.parametrize(
    ("message", "repair"),
    [
        ("ordinary commit", "must start"),
        ("waypoint: why\n\nWaypoint-Agent: codex", "missing Waypoint trailer"),
        (
            "waypoint: why\n\n"
            "Waypoint-Agent: codex\n"
            "Waypoint-Agent: claude\n"
            "Waypoint-Attempt: first\n"
            "Waypoint-Intent: demo\n"
            "Waypoint-Timestamp: 2026-07-08T16:30:00Z\n"
            "Waypoint-Type: checkpoint",
            "duplicate Waypoint trailer",
        ),
    ],
)
def test_checkpoint_parser_rejects_unrepairable_metadata(message: str, repair: str) -> None:
    module = _load_app()
    with pytest.raises(ValueError, match=repair):
        module.parse_checkpoint_message(message)


def test_intent_and_checkpoint_leave_head_index_and_worktree_untouched(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    head_before = _git_run(repo, "rev-parse", "HEAD").strip()
    index_before = _git_run(repo, "write-tree").strip()

    declared = module.create_intent(
        "Launch Waypoint", intent_id="launch-waypoint", agent="codex", task_ref="milo#99"
    )
    assert declared["id"] == "launch-waypoint"
    assert _git_run(repo, "rev-parse", "HEAD").strip() == head_before
    assert _git_run(repo, "write-tree").strip() == index_before
    assert (repo / "story.txt").read_text(encoding="utf-8") == "base\n"

    (repo / "story.txt").write_text("first attempt\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("captured too\n", encoding="utf-8")
    status_before = _git_run(repo, "status", "--porcelain=v1")
    checkpoint = module.create_checkpoint(
        "launch-waypoint", "capture the first approach", attempt_id="alpha", agent="codex"
    )

    assert _git_run(repo, "rev-parse", "HEAD").strip() == head_before
    assert _git_run(repo, "write-tree").strip() == index_before
    assert _git_run(repo, "status", "--porcelain=v1") == status_before
    assert (repo / "story.txt").read_text(encoding="utf-8") == "first attempt\n"
    assert (repo / "untracked.txt").read_text(encoding="utf-8") == "captured too\n"
    tree_files = _git_run(repo, "ls-tree", "-r", "--name-only", checkpoint["checkpoint"])
    assert tree_files.splitlines() == ["story.txt", "untracked.txt"]
    assert (
        _git_run(repo, "show-ref", "--hash", checkpoint["ref"]).strip() == checkpoint["checkpoint"]
    )


def test_full_loop_three_checkpoints_two_attempts_pick_undo_and_why(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    head = _git_run(repo, "rev-parse", "HEAD").strip()
    index = _git_run(repo, "write-tree").strip()
    module.create_intent("Choose an implementation", intent_id="choose", agent="lead")

    story = repo / "story.txt"
    story.write_text("alpha one\n", encoding="utf-8")
    alpha_one = module.create_checkpoint(
        "choose", "start the alpha design", attempt_id="alpha", agent="agent-a"
    )
    story.write_text("alpha one\nalpha two\n", encoding="utf-8")
    alpha_two = module.create_checkpoint(
        "choose", "finish the alpha design", attempt_id="alpha", agent="agent-a"
    )

    story.write_text("beta design\n", encoding="utf-8")
    beta = module.create_checkpoint(
        "choose", "try the beta design", attempt_id="beta", agent="agent-b"
    )

    attempts = module.list_attempts("choose")
    assert [(item["attempt"], item["checkpoints"]) for item in attempts] == [
        ("alpha", 2),
        ("beta", 1),
    ]
    why = module.explain_why("story.txt:1")
    assert why["checkpoint"] == beta["checkpoint"]
    assert why["why"] == "try the beta design"

    with pytest.raises(module.WaypointError, match="conflicts"):
        module.pick_attempt("choose/alpha")
    picked = module.pick_attempt("choose/alpha", force=True)
    assert picked["paths"] == ["story.txt"]
    assert story.read_text(encoding="utf-8") == "alpha one\nalpha two\n"

    undone = module.undo_checkpoint(alpha_two["checkpoint"][:12])
    assert undone["checkpoint"] == alpha_two["checkpoint"]
    assert story.read_text(encoding="utf-8") == "alpha one\n"
    assert alpha_one["checkpoint"] != alpha_two["checkpoint"]
    assert _git_run(repo, "rev-parse", "HEAD").strip() == head
    assert _git_run(repo, "write-tree").strip() == index


def test_non_force_pick_applies_clean_delta_and_preserves_unrelated_changes(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    module.create_intent("Clean pick", intent_id="clean-pick", agent="lead")
    story = repo / "story.txt"
    story.write_text("winning change\n", encoding="utf-8")
    module.create_checkpoint(
        "clean-pick", "make the winning change", attempt_id="winner", agent="agent-a"
    )
    story.write_text("base\n", encoding="utf-8")
    unrelated = repo / "notes.txt"
    unrelated.write_text("keep me\n", encoding="utf-8")

    result = module.pick_attempt("winner")
    assert result["force"] is False
    assert story.read_text(encoding="utf-8") == "winning change\n"
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"


def test_force_pick_reproduces_added_and_deleted_paths_without_staging(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    removed = repo / "removed.txt"
    removed.write_text("remove this\n", encoding="utf-8")
    _git_run(repo, "add", "removed.txt")
    _git_run(repo, "commit", "-m", "add removal fixture")
    index = _git_run(repo, "write-tree").strip()
    module.create_intent("Replace a file", intent_id="replace-file", agent="lead")

    removed.unlink()
    added = repo / "added.txt"
    added.write_text("new file\n", encoding="utf-8")
    module.create_checkpoint(
        "replace-file", "replace the fixture", attempt_id="replacement", agent="agent-a"
    )

    _git_run(repo, "restore", "--worktree", "--", "removed.txt")
    added.unlink()
    result = module.pick_attempt("replacement", force=True)
    assert result["paths"] == ["added.txt", "removed.txt"]
    assert added.read_text(encoding="utf-8") == "new file\n"
    assert not removed.exists()
    assert _git_run(repo, "write-tree").strip() == index


def test_ref_compare_and_swap_refuses_a_stale_writer(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, _ = git_repo
    first = module.create_intent("First", intent_id="first", agent="lead")
    second = module.create_intent("Second", intent_id="second", agent="lead")
    repo = module.GitRepository.discover()
    ref = "refs/waypoint/first/meta"

    with pytest.raises(module.WaypointError, match="changed concurrently"):
        repo.update_ref(ref, second["commit"], None)
    assert repo.ref_oid(ref) == first["commit"]


def test_checkpoint_and_why_fail_with_actionable_repairs(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, _ = git_repo
    module.create_intent("No empty checkpoints", intent_id="no-empty", agent="lead")
    with pytest.raises(module.WaypointError, match="No worktree changes"):
        module.create_checkpoint("no-empty", "nothing changed", agent="lead")
    with pytest.raises(ValueError, match="inside the Git repository"):
        module.explain_why("../outside.txt")


def test_cli_llms_and_mcp_share_the_waypoint_contract(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    cli = module.cli
    about_result = cli.invoke(["about", "--format", "json"])
    assert about_result.exit_code == 0
    assert about_result.result["ref_namespace"] == "refs/waypoint"
    assert "pick/undo" in about_result.result["write_boundary"]

    declared = cli.invoke(
        [
            "intent",
            "Exercise every surface",
            "--intent-id",
            "surface-proof",
            "--agent",
            "codex",
            "--format",
            "json",
        ]
    )
    assert declared.exit_code == 0
    assert declared.result["id"] == "surface-proof"

    (repo / "story.txt").write_text("surface change\n", encoding="utf-8")
    handler = _CLIHandler(cli)
    called: dict[str, Any] = handler.call_tool(
        {
            "name": "checkpoint",
            "arguments": {
                "intent_id": "surface-proof",
                "why": "prove MCP dispatch",
                "attempt_id": "mcp",
                "agent": "codex",
            },
        }
    )
    assert called["structuredContent"]["attempt"] == "mcp"

    (repo / "story.txt").write_text("CLI alias change\n", encoding="utf-8")
    cli_checkpoint = cli.invoke(
        [
            "checkpoint",
            "--intent",
            "surface-proof",
            "--why",
            "prove the documented intent alias",
            "--attempt-id",
            "cli",
            "--agent",
            "codex",
            "--format",
            "json",
        ]
    )
    assert cli_checkpoint.exit_code == 0
    assert cli_checkpoint.result["attempt"] == "cli"

    tools = {item["name"]: item for item in handler.list_tools({})["tools"]}
    assert tools["pick"]["annotations"] == {"destructiveHint": True}
    assert tools["why"]["annotations"] == {"readOnlyHint": True}
    assert tools["checkpoint"]["inputSchema"]["properties"]["intent_id"]["pattern"] == (
        "^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
    )

    llms = generate_llms_txt(cli)
    for command in ("intent", "intents", "checkpoint", "attempts", "pick", "undo", "why"):
        assert f"**{command}**" in llms


def test_showcase_passes_milo_verify() -> None:
    report = verify(str(_APP_PATH), timeout=10.0)
    assert report.exit_code == 0, report.format()
