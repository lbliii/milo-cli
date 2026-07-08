"""Agent-surface proof for the Waypoint showcase (issue #100)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from milo import generate_llms_txt
from milo.mcp import _CLIHandler
from milo.streaming import consume_generator

_ROOT = Path(__file__).resolve().parents[1]
_APP_PATH = _ROOT / "showcase" / "waypoint" / "app.py"
_HOOKS_PATH = _ROOT / "showcase" / "waypoint" / "HOOKS.md"
_GIT = shutil.which("git")


def _load_app() -> ModuleType:
    module_name = "_test_waypoint_agent_app"
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
    _git_run(tmp_path, "config", "user.name", "Waypoint Agent Tests")
    _git_run(tmp_path, "config", "user.email", "waypoint-agent@example.test")
    _git_run(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "story.txt").write_text("base\n", encoding="utf-8")
    _git_run(tmp_path, "add", "story.txt")
    _git_run(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)
    return _load_app(), tmp_path


def _rpc(
    repo: Path,
    *requests: dict[str, Any],
    extra_env: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    payload = "".join(f"{json.dumps(request)}\n" for request in requests)
    completed = subprocess.run(
        (sys.executable, str(_APP_PATH), "--mcp"),
        cwd=repo,
        env=env,
        input=payload,
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    return messages, completed.stderr


def _response(messages: list[dict[str, Any]], request_id: int) -> dict[str, Any]:
    return next(message for message in messages if message.get("id") == request_id)


def test_auto_checkpoint_infers_identity_intent_and_why_from_hook_payload(
    git_repo: tuple[ModuleType, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, repo = git_repo
    (repo / "story.txt").write_text("automatic edit\n", encoding="utf-8")
    payload = {
        "session_id": "session-42",
        "agent_id": "worker-7",
        "task_id": "issue-100",
        "task_description": "Build the Waypoint agent surface",
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "story.txt"},
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    checkpoint = module.create_checkpoint(auto=True)
    assert checkpoint["status"] == "checkpointed"
    assert checkpoint["intent"] == "issue-100"
    assert checkpoint["attempt"] == "worker-7"
    assert checkpoint["agent"] == "worker-7"
    assert checkpoint["why"].startswith("Edit:")
    assert module.list_intents()[0]["title"] == "Build the Waypoint agent surface"

    metadata = module.parse_checkpoint_message(
        module.GitRepository.discover().commit_message(checkpoint["checkpoint"])
    )
    assert metadata.agent == "worker-7"
    assert metadata.task_ref == "issue-100"

    stop_payload = {
        **payload,
        "hook_event_name": "Stop",
        "last_assistant_message": "Finished the agent surface.",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stop_payload)))
    skipped = module.create_checkpoint(auto=True)
    assert skipped == {
        "status": "skipped",
        "intent": "issue-100",
        "attempt": "worker-7",
        "reason": "no worktree changes since the previous checkpoint",
    }


def test_agent_override_wins_over_environment_and_payload(
    git_repo: tuple[ModuleType, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, repo = git_repo
    monkeypatch.setenv("WAYPOINT_AGENT", "environment-agent")
    (repo / "story.txt").write_text("override edit\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"session_id": "payload-agent", "intent_id": "override"})),
    )
    result = module.create_checkpoint(
        intent_id="override",
        why="prove the override",
        agent="explicit-agent",
        auto=True,
    )
    assert result["agent"] == "explicit-agent"
    assert result["attempt"] == "explicit-agent"


def test_resources_log_and_annotations_share_the_journal_contract(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    module.create_intent("Expose resources", intent_id="resources", agent="agent-a")
    (repo / "story.txt").write_text("resource edit\n", encoding="utf-8")
    checkpoint = module.create_checkpoint(
        "resources", "expose the journal", attempt_id="first", agent="agent-a"
    )

    handler = _CLIHandler(module.cli)
    tools = {item["name"]: item for item in handler.list_tools({})["tools"]}
    assert set(tools) == {
        "about",
        "intent",
        "intents",
        "checkpoint",
        "attempts",
        "log",
        "pick",
        "undo",
        "why",
    }
    destructive = {
        name for name, tool in tools.items() if tool.get("annotations", {}).get("destructiveHint")
    }
    readonly = {
        name for name, tool in tools.items() if tool.get("annotations", {}).get("readOnlyHint")
    }
    assert destructive == {"pick", "undo"}
    assert readonly == {"about", "intents", "attempts", "log", "why"}

    resources = {item["uri"]: item for item in handler.list_resources({})["resources"]}
    expected = {
        "waypoint://intents",
        "waypoint://attempts/resources",
        "waypoint://journal",
    }
    assert expected <= resources.keys()
    for uri in expected:
        assert resources[uri]["mimeType"] == "application/json"

    intents = json.loads(
        handler.read_resource({"uri": "waypoint://intents"})["contents"][0]["text"]
    )
    attempts = json.loads(
        handler.read_resource({"uri": "waypoint://attempts/resources"})["contents"][0]["text"]
    )
    journal = json.loads(
        handler.read_resource({"uri": "waypoint://journal"})["contents"][0]["text"]
    )
    assert intents[0]["id"] == "resources"
    assert attempts[0]["checkpoint"] == checkpoint["checkpoint"]
    assert [event["type"] for event in journal] == ["intent", "checkpoint"]
    assert module.journal_log() == journal


def test_pick_and_undo_stream_progress_before_structured_results(
    git_repo: tuple[ModuleType, Path],
) -> None:
    module, repo = git_repo
    module.create_intent("Stream changes", intent_id="stream", agent="agent-a")
    (repo / "story.txt").write_text("streamed edit\n", encoding="utf-8")
    checkpoint = module.create_checkpoint(
        "stream", "stream the mutation", attempt_id="winner", agent="agent-a"
    )
    (repo / "story.txt").write_text("base\n", encoding="utf-8")

    pick_progress, picked = consume_generator(module.cli.call_raw("pick", attempt="winner"))
    assert [item.status for item in pick_progress] == [
        "Inspecting stream/winner",
        "Applying 1 checkpoint(s)",
    ]
    assert picked["status"] == "picked"

    undo_progress, undone = consume_generator(
        module.cli.call_raw("undo", checkpoint=checkpoint["checkpoint"][:12])
    )
    assert [item.step for item in undo_progress] == [0, 1]
    assert undone["status"] == "undone"
    assert (repo / "story.txt").read_text(encoding="utf-8") == "base\n"


def test_llms_txt_tells_the_checkpoint_compare_pick_story() -> None:
    module = _load_app()
    llms = generate_llms_txt(module.cli)
    checkpoint = llms.index("**checkpoint**")
    attempts = llms.index("**attempts**")
    pick = llms.index("**pick**")
    why = llms.index("**why**")
    assert checkpoint < attempts < pick < why
    assert "Snapshot the worktree with intent metadata" in llms
    assert "Apply a winning attempt to the working tree" in llms


def test_real_jsonrpc_agent_loop_lists_calls_resources_and_progress(tmp_path: Path) -> None:
    _git_run(tmp_path, "init", "-b", "main")
    _git_run(tmp_path, "config", "user.name", "Waypoint RPC Tests")
    _git_run(tmp_path, "config", "user.email", "waypoint-rpc@example.test")
    _git_run(tmp_path, "config", "commit.gpgsign", "false")
    story = tmp_path / "story.txt"
    story.write_text("base\n", encoding="utf-8")
    _git_run(tmp_path, "add", "story.txt")
    _git_run(tmp_path, "commit", "-m", "baseline")

    first, stderr = _rpc(
        tmp_path,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "intent",
                "arguments": {
                    "title": "RPC intent",
                    "intent_id": "rpc-intent",
                    "agent": "rpc-agent",
                },
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}},
    )
    assert "MCP server ready" in stderr
    tool_names = {tool["name"] for tool in _response(first, 2)["result"]["tools"]}
    assert tool_names == {
        "about",
        "intent",
        "intents",
        "checkpoint",
        "attempts",
        "log",
        "pick",
        "undo",
        "why",
    }
    assert _response(first, 3)["result"]["structuredContent"]["id"] == "rpc-intent"
    listed_resources = {item["uri"] for item in _response(first, 4)["result"]["resources"]}
    assert "waypoint://attempts/rpc-intent" in listed_resources

    story.write_text("first rpc edit\n", encoding="utf-8")
    first_checkpoint, _ = _rpc(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "checkpoint",
                "arguments": {
                    "intent_id": "rpc-intent",
                    "why": "first RPC checkpoint",
                    "attempt_id": "rpc-agent",
                    "agent": "rpc-agent",
                },
            },
        },
    )
    assert _response(first_checkpoint, 5)["result"]["structuredContent"]["status"] == (
        "checkpointed"
    )

    story.write_text("first rpc edit\nsecond rpc edit\n", encoding="utf-8")
    second_checkpoint, _ = _rpc(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "checkpoint",
                "arguments": {
                    "intent_id": "rpc-intent",
                    "why": "second RPC checkpoint",
                    "attempt_id": "rpc-agent",
                    "agent": "rpc-agent",
                },
            },
        },
    )
    second_content = _response(second_checkpoint, 6)["result"]["structuredContent"]
    assert second_content["why"] == "second RPC checkpoint"
    second_oid = second_content["checkpoint"]

    story.write_text("base\n", encoding="utf-8")
    final, _ = _rpc(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "attempts", "arguments": {"intent_id": "rpc-intent"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "pick", "arguments": {"attempt": "rpc-agent"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "resources/read",
            "params": {"uri": "waypoint://attempts/rpc-intent"},
        },
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "resources/read",
            "params": {"uri": "waypoint://journal"},
        },
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "_debug", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "about", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "intents", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {"name": "log", "arguments": {"limit": 10}},
        },
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {"name": "why", "arguments": {"target": "story.txt:1"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {"name": "undo", "arguments": {"checkpoint": second_oid}},
        },
    )
    assert _response(final, 7)["result"]["structuredContent"][0]["checkpoints"] == 2
    assert _response(final, 8)["result"]["structuredContent"]["status"] == "picked"
    progress = [message for message in final if message.get("method") == "notifications/progress"]
    assert [message["params"]["progress"] for message in progress] == [0, 1, 0, 1]
    assert (
        json.loads(_response(final, 9)["result"]["contents"][0]["text"])[0]["attempt"]
        == "rpc-agent"
    )
    assert len(json.loads(_response(final, 10)["result"]["contents"][0]["text"])) == 3
    hidden = _response(final, 11)["result"]
    assert hidden["isError"] is True
    assert hidden["errorData"]["reason"] == "unknown_tool"
    assert _response(final, 12)["result"]["structuredContent"]["name"] == "Waypoint"
    assert _response(final, 13)["result"]["structuredContent"][0]["id"] == "rpc-intent"
    assert len(_response(final, 14)["result"]["structuredContent"]) == 3
    assert _response(final, 15)["result"]["structuredContent"]["why"] == ("first RPC checkpoint")
    assert _response(final, 16)["result"]["structuredContent"]["status"] == "undone"
    assert story.read_text(encoding="utf-8") == "first rpc edit\n"


def test_hook_recipe_tracks_current_payload_fields_and_zero_explicit_calls() -> None:
    text = _HOOKS_PATH.read_text(encoding="utf-8")
    assert "https://code.claude.com/docs/en/hooks" in text
    assert "https://www.conductor.build/docs/reference/harnesses" in text
    assert '"PostToolUse"' in text
    assert '"Stop"' in text
    assert "session_id" in text
    assert "last_assistant_message" in text
    assert "checkpoint --auto" in text
    assert "WAYPOINT_INTENT" in text
