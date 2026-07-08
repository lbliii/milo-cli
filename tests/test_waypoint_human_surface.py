"""Human dual-mode proof for the Waypoint showcase (issue #101)."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from milo import Action, Context, Key, Quit, SpecialKey
from milo.mcp import _CLIHandler

_ROOT = Path(__file__).resolve().parents[1]
_APP_PATH = _ROOT / "showcase" / "waypoint" / "app.py"
_GIT = shutil.which("git")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _load_app() -> ModuleType:
    module_name = "_test_waypoint_human_app"
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
def journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path, dict]:
    _git_run(tmp_path, "init", "-b", "main")
    _git_run(tmp_path, "config", "user.name", "Waypoint Human Tests")
    _git_run(tmp_path, "config", "user.email", "waypoint-human@example.test")
    _git_run(tmp_path, "config", "commit.gpgsign", "false")
    story = tmp_path / "story.txt"
    story.write_text("base\n", encoding="utf-8")
    _git_run(tmp_path, "add", "story.txt")
    _git_run(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)
    module = _load_app()
    module.create_intent("Human timeline", intent_id="human", agent="lead")
    story.write_text("first line\n", encoding="utf-8")
    first = module.create_checkpoint(
        "human", "shape the first attempt", attempt_id="alpha", agent="agent-a"
    )
    story.write_text("first line\nsecond line\n", encoding="utf-8")
    module.create_checkpoint(
        "human", "finish the first attempt", attempt_id="alpha", agent="agent-a"
    )
    story.write_text("competing line\n", encoding="utf-8")
    module.create_checkpoint(
        "human", "try a competing approach", attempt_id="beta", agent="agent-b"
    )
    return module, tmp_path, first


def test_timeline_reducer_navigates_expands_and_quits() -> None:
    module = _load_app()
    rows = (
        module.TimelineRow("one / a", True, "1111111", "now", "a", "why one", "1 +"),
        module.TimelineRow("one / a", False, "2222222", "later", "a", "why two", "2 +"),
    )
    state = module.TimelineState(rows=rows)

    state = module.timeline_reducer(state, Action("@@KEY", Key(char="j")))
    assert state.selected == 1
    state = module.timeline_reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
    assert state.expanded is True
    state = module.timeline_reducer(state, Action("@@KEY", Key(name=SpecialKey.UP)))
    assert state.selected == 0
    assert state.expanded is False
    state = module.timeline_reducer(state, Action("@@KEY", Key(char="k")))
    assert state.selected == 0
    quit_result = module.timeline_reducer(state, Action("@@KEY", Key(char="q")))
    assert isinstance(quit_result, Quit)
    assert quit_result.state == state


def test_timeline_template_renders_group_selection_and_expanded_detail(
    journal: tuple[ModuleType, Path, dict],
) -> None:
    module, _, _ = journal
    rows = module._timeline_rows(module.GitRepository.discover())
    assert [row.group for row in rows] == ["human / alpha", "human / alpha", "human / beta"]
    state = module.TimelineState(rows=rows, selected=1, expanded=True)
    rendered = module._timeline_env().get_template("timeline.kida").render(state=state)
    plain = _ANSI.sub("", rendered)
    assert "Waypoint timeline" in plain
    assert "human / alpha" in plain
    assert "human / beta" in plain
    assert "finish the first attempt" in plain
    assert "story.txt" in plain
    assert "j/k" in plain
    assert "q/esc" in plain


def test_log_launches_tui_only_for_interactive_plain_context(
    journal: tuple[ModuleType, Path, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _ = journal
    calls: list[dict] = []

    def fake_run_app(self: Context, **kwargs):
        calls.append(kwargs)
        return kwargs["initial_state"]

    monkeypatch.setattr(Context, "run_app", fake_run_app)
    interactive = Context(interactive=True, format="plain", color=False)
    result = module.cli.call("log", ctx=interactive, limit=10)
    assert len(result) == 4
    assert len(calls) == 1
    assert calls[0]["reducer"] is module.timeline_reducer
    assert calls[0]["template"] == "timeline.kida"
    assert len(calls[0]["initial_state"].rows) == 3

    structured = module.cli.call("log", ctx=Context(interactive=True, format="json"), limit=10)
    assert structured == result
    assert len(calls) == 1

    mcp = _CLIHandler(module.cli).call_tool({"name": "log", "arguments": {"limit": 10}})
    assert mcp["structuredContent"] == result
    assert len(calls) == 1


@pytest.mark.parametrize("command", ["intents", "attempts", "log"])
def test_list_commands_support_plain_table_and_json(
    journal: tuple[ModuleType, Path, dict], command: str
) -> None:
    module, _, _ = journal
    args = [command]
    if command == "attempts":
        args.append("human")

    plain = module.cli.invoke([*args, "--format", "plain"])
    table = module.cli.invoke([*args, "--format", "table"])
    json_result = module.cli.invoke([*args, "--format", "json"])
    assert plain.exit_code == table.exit_code == json_result.exit_code == 0
    assert plain.output.strip()
    assert table.output.strip()
    assert json.loads(json_result.output) == json_result.result
    if command == "intents":
        assert "INTENTS" in plain.output
        assert "id" in table.output
        assert "title" in table.output
    elif command == "attempts":
        assert "ATTEMPTS" in plain.output
        assert "attempt" in table.output
        assert "checkpoint" in table.output
    else:
        assert "WAYPOINT TIMELINE" in plain.output
        assert "type" in table.output
        assert "created_at" in table.output


def test_pick_and_undo_confirm_only_for_interactive_context(
    journal: tuple[ModuleType, Path, dict],
) -> None:
    module, repo, _first = journal
    story = repo / "story.txt"
    before = story.read_text(encoding="utf-8")
    prompts: list[str] = []

    denied = Context(
        interactive=True,
        confirm_strategy=lambda message, *, default=False: prompts.append(message) or False,
    )
    cancelled = module.cli.call("pick", ctx=denied, attempt="human/alpha", force=True)
    assert cancelled["status"] == "cancelled"
    assert story.read_text(encoding="utf-8") == before
    assert prompts == ["Pick human/alpha and update the working tree?"]

    def unexpected_prompt(_message: str, *, default: bool = False) -> bool:
        raise AssertionError("non-interactive dispatch must not prompt")

    picked = module.cli.call(
        "pick",
        ctx=Context(interactive=False, confirm_strategy=unexpected_prompt),
        attempt="human/alpha",
        force=True,
    )
    assert picked["status"] == "picked"
    assert story.read_text(encoding="utf-8") == "first line\nsecond line\n"

    alpha_latest = next(
        item for item in module.list_attempts("human") if item["attempt"] == "alpha"
    )["checkpoint"]

    cancelled_undo = module.cli.call(
        "undo",
        ctx=denied,
        checkpoint=alpha_latest,
    )
    assert cancelled_undo["status"] == "cancelled"
    assert len(prompts) == 2

    undone = module.cli.call(
        "undo",
        ctx=Context(interactive=False, confirm_strategy=unexpected_prompt),
        checkpoint=alpha_latest,
    )
    assert undone["status"] == "undone"
    assert story.read_text(encoding="utf-8") == "first line\n"


def test_context_stays_out_of_agent_schemas(journal: tuple[ModuleType, Path, dict]) -> None:
    module, _, _ = journal
    tools = {item["name"]: item for item in _CLIHandler(module.cli).list_tools({})["tools"]}
    for name in ("log", "pick", "undo"):
        assert "ctx" not in tools[name]["inputSchema"]["properties"]
