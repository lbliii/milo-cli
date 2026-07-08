# Waypoint

Waypoint is a showcase application for an agent-native intent journal layered
over Git. Git records what changed; Waypoint records why it changed, which
agent made the change, and which parallel attempt produced it.

This directory is intentionally under `showcase/`, not `examples/`: Waypoint
is a full demonstration of Milo's CLI and MCP contract. The examples remain
small copy paths.

## Try the core loop

Run these commands inside a Git repository with an initial commit:

```bash
APP=/path/to/milo-cli/showcase/waypoint/app.py

uv run python "$APP" intent "Improve the parser" \
  --intent-id improve-parser --agent codex

# Edit files, then record why this attempt exists.
uv run python "$APP" checkpoint \
  --intent improve-parser \
  --attempt-id no-cache \
  --agent codex \
  --why "remove the stale parser cache"

uv run python "$APP" attempts improve-parser --format table
uv run python "$APP" why src/parser.py:42 --format json
uv run python "$APP" pick improve-parser/no-cache
```

For zero-touch journaling from an agent harness, use
[`checkpoint --auto`](HOOKS.md). It consumes Claude Code-compatible hook JSON
from stdin, infers the session identity and intent, and safely skips clean
turns.

`pick` refuses a patch that conflicts with the current working tree. Review
local changes first, or use `--force` to overwrite only paths changed by the
selected attempt. Reverse one checkpoint's delta with its printed id:

```bash
uv run python "$APP" undo 0123456789ab
```

## Storage and safety contract

- Intent metadata lives at `refs/waypoint/<intent>/meta`.
- Each attempt head lives at `refs/waypoint/<intent>/<attempt>`.
- A checkpoint is a commit object whose tree snapshots tracked and untracked
  worktree files and whose trailers record intent, attempt, agent, timestamp,
  task reference, and why.
- Snapshotting uses a temporary `GIT_INDEX_FILE`; `intent` and `checkpoint`
  never change HEAD, the real index, or working-tree files.
- Ref updates use Git compare-and-swap semantics. Concurrent writers cannot
  silently replace one another under free-threaded Python.
- Every Git subprocess captures stdout/stderr and has a ten-second timeout.
- Only `pick` and `undo` mutate files, and both leave HEAD and the index alone.

## Agent resources

The same journal is readable without shell access:

- `waypoint://intents` — declared intents.
- `waypoint://attempts/<intent>` — competing attempts for one intent.
- `waypoint://journal` — immutable intent/checkpoint events in append order.

`pick` and `undo` stream progress and are the only tools marked destructive.
`intents`, `attempts`, `log`, and `why` are marked read-only so an MCP host can
apply the appropriate approval policy.

## Verify the showcase

```bash
uv run milo verify showcase/waypoint/app.py
PYTHON_GIL=0 uv run pytest tests/test_waypoint_showcase.py -q
```
