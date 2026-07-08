# Waypoint

Git records what changed; agents need why. Waypoint is an intent journal layered
over Git that records the goal, agent, attempt, and reason behind parallel work
without moving `HEAD`, staging files, or rewriting a worktree.

This directory is intentionally under `showcase/`, not `examples/`: Waypoint is
a complete demonstration of Milo's shared CLI, MCP, and terminal-app contract.
The examples remain small, focused copy paths.

## Prove it in 60 seconds

From a clean Milo checkout with [`uv`](https://docs.astral.sh/uv/) and Git:

```bash milo-docs:run cwd=.
uv run python showcase/waypoint/replay.py
```

The replay creates a retained temporary fixture repository, then runs one race
in three acts:

1. Three simulated harness sessions edit the same file. Claude Code-compatible
   stop-hook payloads create `fast`, `safe`, and `balanced` checkpoints through
   the CLI without an explicit agent checkpoint call.
2. A real stdio MCP session asks why the line exists, reads the attempt graph,
   and picks `safe`. The transcript shows the read-only and destructive tool
   hints a shell-less host uses for approval policy.
3. The same journal becomes the human timeline and the MCP Apps attempt DAG.

The command normally completes in under ten seconds and prints the fixture
path so you can inspect it. To choose the destination yourself, pass an empty
or nonexistent directory:

```bash milo-docs:skip reason=creates-a-git-fixture-at-a-user-selected-path
uv run python showcase/waypoint/replay.py --repo /tmp/waypoint-demo
```

Then explore the retained fixture from that directory:

```bash milo-docs:skip reason=requires-the-replay-fixture-path
APP=/absolute/path/to/milo-cli/showcase/waypoint/app.py
uv run python "$APP" attempts plan-race --format table
uv run python "$APP" why planner.py:2 --format json
uv run python "$APP" log
uv run python "$APP" attempt-graph --intent-id plan-race --format json
```

## The three consumption modes

### Act 1: hook → CLI

Inside a shell-capable harness, install the
[Claude Code/Conductor hook recipe](HOOKS.md). Hooks pipe edit and stop events
to `checkpoint --auto`; agents use `why` and `attempts` through the CLI. Nothing
is registered as MCP, and the automatic write path costs no prompt context.

### Act 2: agent → MCP

In a shell-less host, register the same file as a stdio MCP server:

```bash milo-docs:skip reason=requires-a-host-specific-mcp-registration
uv run python showcase/waypoint/app.py --mcp
```

`why`, `attempts`, and `attempt-graph` advertise `readOnlyHint`, so a host can
approve inspection automatically. `pick` and `undo` advertise
`destructiveHint`, so the host can ask before changing the worktree. Types,
docstrings, and annotations on the existing functions produce those schemas;
there is no adapter layer.

### Act 3: human → TUI / MCP Apps

Run `wp log` in a terminal for the interactive timeline. Checkpoints are
grouped by intent and attempt; use `j`/`k` (or arrow keys) to navigate, Enter
to inspect why and the diffstat, and `q`/Escape to quit.

An MCP Apps-capable host links `attempt-graph` to
`ui://waypoint/attempts`. The dependency-free view renders parallel lanes,
checkpoint detail, refresh, and the destructive pick action. Hosts without
Apps support receive the same structured graph.

Hook → CLI, agent → MCP, and human → TUI/Apps all come from the same typed
functions. **CLI for depth, MCP for reach.**

## Storage and safety contract

- Intent metadata lives at `refs/waypoint/<intent>/meta`.
- Each attempt head lives at `refs/waypoint/<intent>/<attempt>`.
- A checkpoint is a commit object whose tree snapshots tracked and untracked
  worktree files and whose trailers record intent, attempt, agent, timestamp,
  task reference, and why.
- Snapshotting uses a temporary `GIT_INDEX_FILE`; `intent` and `checkpoint`
  never change `HEAD`, the real index, or working-tree files.
- Ref updates use Git compare-and-swap semantics. Concurrent writers cannot
  silently replace one another under free-threaded Python.
- Every Git subprocess captures stdout/stderr and has a ten-second timeout.
- Only `pick` and `undo` mutate files, and both leave `HEAD` and the index alone.

## Packaging decision

Keep Waypoint in-tree through Milo's launch. It is an integration showcase,
not a promised standalone product, and colocating it keeps framework changes
and the cross-surface proof atomic. Reassess after launch: graduate it to a
sibling repository consuming `milo-cli` from PyPI when it needs an independent
release cadence or gains users outside Milo development. That graduation would
be valuable second-consumer dogfood rather than a prerequisite for launch.

## Verify the showcase

```bash
make showcase-test
```

That target runs every `tests/test_waypoint*.py` contract under free-threading
and executes `milo verify showcase/waypoint/app.py`. It is part of `make ci`.
