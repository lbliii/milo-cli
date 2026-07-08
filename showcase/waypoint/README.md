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

## Human timeline

Run `wp log` in a terminal to open the interactive timeline. Checkpoints are
grouped by intent and attempt; use `j`/`k` (or arrow keys) to navigate, Enter
to expand the selected checkpoint's why and diffstat, and `q`/Escape to quit.

In CI or a non-interactive shell, plain output becomes a compact text timeline.
Every list command supports `--format plain|table|json`; MCP and programmatic
calls always receive the same structured records. Interactive terminals ask
before `pick` or `undo`, while non-interactive and MCP dispatch rely on the
existing destructive tool annotations instead of reading stdin.

## MCP Apps attempt graph

`attempt-graph` returns the complete intent → attempt → checkpoint graph as
structured JSON in every host. Clients that negotiate MCP Apps also receive
the linked `ui://waypoint/attempts` view: parallel attempt lanes, checkpoint
inspection, refresh, and a pick action that converges the selected winner.

The HTML is dependency-free and uses no external assets. It discovers the
host- or gateway-rewritten tool identity during `ui/initialize`, so refresh,
inspect, and pick calls remain valid behind a Milo gateway. Hosts without Apps
support keep the same read-only tool and structured fallback without seeing a
UI resource.

## Verify the showcase

```bash
uv run milo verify showcase/waypoint/app.py
PYTHON_GIL=0 uv run pytest tests/test_waypoint_showcase.py -q
```
