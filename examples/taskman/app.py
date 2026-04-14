"""Taskman — AI-native CLI example using milo's CLI class.

Demonstrates: @command decorator, @resource decorator, typed parameters, aliases,
tags, hidden commands, --format json|table|plain, --llms-txt, --mcp.

    uv run python examples/taskman/app.py list
    uv run python examples/taskman/app.py add --title "Buy milk" --priority high
    uv run python examples/taskman/app.py list --format json
    uv run python examples/taskman/app.py --llms-txt
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | uv run python examples/taskman/app.py --mcp
"""

from __future__ import annotations

import json
from pathlib import Path

from milo import CLI

# In-memory store (a real app would use a file or database)
_STORE_FILE = Path(__file__).parent / ".tasks.json"


def _load_tasks() -> list[dict]:
    if _STORE_FILE.exists():
        return json.loads(_STORE_FILE.read_text())
    return []


def _save_tasks(tasks: list[dict]) -> None:
    _STORE_FILE.write_text(json.dumps(tasks, indent=2))


def _next_id(tasks: list[dict]) -> int:
    return max((t["id"] for t in tasks), default=0) + 1


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

cli = CLI(
    name="taskman",
    description="A simple task manager — milo AI-native CLI example.",
    version="0.1.0",
)


@cli.command("add", description="Add a new task", aliases=("a",), tags=("tasks",))
def add(title: str, priority: str = "medium") -> dict:
    """Add a task with a title and optional priority (low/medium/high)."""
    tasks = _load_tasks()
    task = {
        "id": _next_id(tasks),
        "title": title,
        "priority": priority,
        "done": False,
    }
    tasks.append(task)
    _save_tasks(tasks)
    return task


@cli.command("list", description="List all tasks", aliases=("ls",), tags=("tasks",))
def list_tasks(priority: str | None = None, done: bool = False) -> list[dict]:
    """List tasks, optionally filtered by priority or completion status."""
    tasks = _load_tasks()
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if done:
        tasks = [t for t in tasks if t["done"]]
    return tasks


@cli.command("done", description="Mark a task as complete", aliases=("d",), tags=("tasks",))
def mark_done(id: int) -> dict:
    """Mark the task with the given ID as done."""
    tasks = _load_tasks()
    for task in tasks:
        if task["id"] == id:
            task["done"] = True
            _save_tasks(tasks)
            return task
    return {"error": f"Task {id} not found"}


@cli.command("remove", description="Remove a task", aliases=("rm",), tags=("tasks",))
def remove(id: int) -> dict:
    """Remove the task with the given ID."""
    tasks = _load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if t["id"] != id]
    _save_tasks(tasks)
    if len(tasks) < before:
        return {"removed": id}
    return {"error": f"Task {id} not found"}


@cli.command("stats", description="Show task statistics", tags=("info",))
def stats() -> dict:
    """Show counts of total, done, and pending tasks by priority."""
    tasks = _load_tasks()
    total = len(tasks)
    done = sum(1 for t in tasks if t["done"])
    by_priority = {}
    for t in tasks:
        p = t["priority"]
        by_priority.setdefault(p, {"total": 0, "done": 0})
        by_priority[p]["total"] += 1
        if t["done"]:
            by_priority[p]["done"] += 1
    return {
        "total": total,
        "done": done,
        "pending": total - done,
        "by_priority": by_priority,
    }


@cli.command("clear", description="Remove all completed tasks", tags=("tasks",))
def clear() -> dict:
    """Remove all tasks marked as done."""
    tasks = _load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if not t["done"]]
    _save_tasks(tasks)
    return {"cleared": before - len(tasks), "remaining": len(tasks)}


@cli.command("_debug", description="Dump raw task store", hidden=True)
def debug() -> dict:
    """Internal: dump the raw JSON store for debugging."""
    return {"file": str(_STORE_FILE), "tasks": _load_tasks()}


# ---------------------------------------------------------------------------
# MCP resources — expose task data to AI agents
# ---------------------------------------------------------------------------


@cli.resource("tasks://all", description="All tasks as JSON")
def all_tasks() -> list[dict]:
    """Return every task in the store."""
    return _load_tasks()


@cli.resource("tasks://pending", description="Pending (incomplete) tasks")
def pending_tasks() -> list[dict]:
    """Return only tasks that are not yet done."""
    return [t for t in _load_tasks() if not t["done"]]


if __name__ == "__main__":
    cli.run()
