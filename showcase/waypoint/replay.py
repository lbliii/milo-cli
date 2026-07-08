"""Replay Waypoint's three-agent race through CLI, MCP, and human surfaces."""

# This executable's stdout is the recording-ready demo transcript.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

APP_PATH = Path(__file__).with_name("app.py").resolve()
BASELINE = """def choose_plan() -> str:
    return "baseline"
"""
ATTEMPTS = (
    (
        "fast",
        "agent-fast",
        """def choose_plan() -> str:
    return "ship the first valid plan"
""",
        "favor the shortest path to a valid plan",
    ),
    (
        "safe",
        "agent-safe",
        """def choose_plan() -> str:
    return "validate every dependency before landing"
""",
        "validate dependencies before selecting the plan",
    ),
    (
        "balanced",
        "agent-balanced",
        """def choose_plan() -> str:
    return "score speed and safety together"
""",
        "balance delivery speed with dependency safety",
    ),
)


class ReplayError(RuntimeError):
    """Raised when the deterministic demo cannot complete."""


def _run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReplayError(f"{' '.join(command)} failed: {detail}")
    return completed


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ReplayError("Git is required to run the Waypoint replay")
    return _run((git, "-C", str(repo), *args), cwd=repo).stdout


def _wp(
    repo: Path,
    *args: str,
    input_value: dict[str, Any] | None = None,
    extra_env: dict[str, str] | None = None,
) -> Any:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    input_text = None if input_value is None else f"{json.dumps(input_value)}\n"
    completed = _run(
        (sys.executable, str(APP_PATH), *args),
        cwd=repo,
        input_text=input_text,
        env=env,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ReplayError(f"Waypoint returned invalid JSON: {completed.stdout!r}") from error


def _rpc(repo: Path, *requests: dict[str, Any]) -> list[dict[str, Any]]:
    payload = "".join(f"{json.dumps(request)}\n" for request in requests)
    completed = _run(
        (sys.executable, str(APP_PATH), "--mcp"),
        cwd=repo,
        input_text=payload,
        env=os.environ.copy(),
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _response(messages: list[dict[str, Any]], request_id: int) -> dict[str, Any]:
    try:
        return next(message for message in messages if message.get("id") == request_id)
    except StopIteration as error:
        raise ReplayError(f"MCP response {request_id} was not returned") from error


def _structured(messages: list[dict[str, Any]], request_id: int) -> Any:
    response = _response(messages, request_id)
    if "error" in response:
        raise ReplayError(f"MCP request {request_id} failed: {response['error']}")
    result = response.get("result", {})
    if result.get("isError"):
        raise ReplayError(f"MCP tool request {request_id} failed: {result}")
    return result.get("structuredContent")


def _prepare_repo(repo: Path) -> None:
    if repo.exists() and any(repo.iterdir()):
        raise ReplayError(f"Replay destination must be empty: {repo}")
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Waypoint Replay")
    _git(repo, "config", "user.email", "waypoint-replay@example.test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "planner.py").write_text(BASELINE, encoding="utf-8")
    _git(repo, "add", "planner.py")
    _git(repo, "commit", "-m", "baseline")


def _act_one(repo: Path) -> list[dict[str, Any]]:
    print("\nACT 1 — hook → CLI (three agents race; no MCP registration)")
    _wp(
        repo,
        "intent",
        "Choose the plan that should land",
        "--intent-id",
        "plan-race",
        "--agent",
        "demo-lead",
        "--task-ref",
        "milo-cli#103",
        "--format",
        "json",
    )
    planner = repo / "planner.py"
    for attempt, agent, source, why in ATTEMPTS:
        planner.write_text(source, encoding="utf-8")
        checkpoint = _wp(
            repo,
            "checkpoint",
            "--auto",
            "--format",
            "json",
            input_value={
                "session_id": f"session-{attempt}",
                "agent_id": agent,
                "hook_event_name": "Stop",
                "last_assistant_message": why,
            },
            extra_env={
                "WAYPOINT_INTENT": "plan-race",
                "WAYPOINT_ATTEMPT": attempt,
                "WAYPOINT_TASK": "Choose the plan that should land",
                "WAYPOINT_TASK_REF": "milo-cli#103",
            },
        )
        print(f"  {attempt:<8} {checkpoint['checkpoint'][:12]}  {checkpoint['why']}")

    attempts = _wp(repo, "attempts", "plan-race", "--format", "json")
    print(f"  race recorded: {len(attempts)} parallel attempts")
    return attempts


def _act_two(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    print("\nACT 2 — agent → MCP (shell-less host)")
    (repo / "planner.py").write_text(BASELINE, encoding="utf-8")
    messages = _rpc(
        repo,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "capabilities": {
                    "extensions": {
                        "io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}
                    }
                }
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "why", "arguments": {"target": "planner.py:2"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "attempt-graph",
                "arguments": {"intent_id": "plan-race"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "pick", "arguments": {"attempt": "plan-race/safe"}},
        },
    )
    tools = _response(messages, 2)["result"]["tools"]
    annotations = {tool["name"]: tool.get("annotations", {}) for tool in tools}
    why = _structured(messages, 3)
    graph = _structured(messages, 4)
    picked = _structured(messages, 5)
    print(f"  why [readOnlyHint]: {why['why']}")
    print(f"  graph [readOnlyHint]: {len(graph['attempts'])} lanes at ui://waypoint/attempts")
    print(f"  pick [destructiveHint]: {picked['attempt']} → {', '.join(picked['paths'])}")
    if not annotations["why"].get("readOnlyHint"):
        raise ReplayError("why must advertise readOnlyHint")
    if not annotations["attempt-graph"].get("readOnlyHint"):
        raise ReplayError("attempt-graph must advertise readOnlyHint")
    if not annotations["pick"].get("destructiveHint"):
        raise ReplayError("pick must advertise destructiveHint")
    return graph, picked


def _act_three(repo: Path, graph: dict[str, Any]) -> None:
    print("\nACT 3 — human → TUI / MCP Apps")
    timeline = _wp(repo, "log", "--format", "json")
    lanes = " → ".join(item["attempt"] for item in graph["attempts"])
    print(f"  timeline: {len(timeline)} journal events; run `wp log` in a terminal")
    print(f"  DAG view: plan-race → [{lanes}] → picked safe")
    print("  Apps resource: ui://waypoint/attempts")


def replay(repo: Path) -> None:
    """Create and replay the deterministic three-act Waypoint fixture."""
    started = time.monotonic()
    _prepare_repo(repo)
    attempts = _act_one(repo)
    graph, picked = _act_two(repo)
    _act_three(repo, graph)
    if len(attempts) != 3 or picked.get("status") != "picked":
        raise ReplayError("Replay did not record three attempts and pick a winner")
    elapsed = time.monotonic() - started
    print("\nCLI for depth, MCP for reach — one typed function set, zero adapters.")
    print(f"Replay complete in {elapsed:.2f}s. Fixture: {repo}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        help="Empty destination for the fixture (default: a retained temporary directory).",
    )
    args = parser.parse_args()
    destination = (
        args.repo.resolve()
        if args.repo is not None
        else Path(tempfile.mkdtemp(prefix="waypoint-replay-")).resolve()
    )
    try:
        replay(destination)
    except (OSError, ReplayError, subprocess.SubprocessError) as error:
        print(f"Waypoint replay failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
