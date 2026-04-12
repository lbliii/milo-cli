---
title: Pipeline Orchestration
nav_title: Pipeline
description: Declarative build pipelines with phases, dependency graphs, retry policies, output capture, and Store integration.
weight: 65
draft: false
lang: en
tags: [pipeline, phases, dependencies, build, observability]
keywords: [pipeline, phase, dependency, build, saga, orchestration, parallel, retry, output, capture]
category: usage
icon: git-branch
---

Milo's pipeline system orchestrates multi-phase workflows through the Store/saga architecture. Each phase is a function with declared dependencies, and the pipeline resolves execution order, runs parallel phases concurrently, and tracks progress through observable state.

## Defining a pipeline

```python
from milo import Pipeline, Phase

pipeline = Pipeline(
    "build",
    Phase("discover", handler=discover),
    Phase("parse", handler=parse, depends_on=("discover",)),
    Phase("render", handler=render, depends_on=("parse",), parallel=True),
    Phase("assets", handler=copy_assets, depends_on=("parse",), parallel=True),
    Phase("write", handler=write, depends_on=("render", "assets")),
)
```

Each `Phase` has:

| Field | Purpose |
|---|---|
| `name` | Unique phase identifier |
| `handler` | Callable that does the work |
| `depends_on` | Tuple of phase names that must complete first |
| `parallel` | If `True`, can run concurrently with other parallel phases |
| `weight` | Progress weight (default: 1) |
| `description` | Human-readable description |
| `policy` | `PhasePolicy` controlling failure behavior (default: stop on failure) |
| `max_logs` | Max captured log lines per phase (default: 200) |

## Dependency resolution

The pipeline resolves phases in topological order. Given the example above:

```
discover → parse → [render, assets] → write
```

`render` and `assets` both depend on `parse` and are marked `parallel=True`, so they execute concurrently via `Fork`. `write` waits for both to complete.

```python
pipeline.execution_order()
# ["discover", "parse", "assets", "render", "write"]
```

## Extending pipelines

Use the `>>` operator to append phases:

```python
pipeline = pipeline >> Phase(
    "health",
    handler=check_links,
    depends_on=("write",),
    description="Verify internal links",
)
```

This returns a new `Pipeline` — the original is unchanged.

## Store integration

The pipeline generates a reducer and saga that work with the Store for observable, testable execution.

### Generated reducer

```python
reducer = pipeline.build_reducer()
store = Store(reducer, initial_state=None)
```

The reducer handles these action types:

| Action | Effect |
|---|---|
| `@@PIPELINE_START` | Sets status to `"running"` |
| `@@PHASE_START` | Marks a phase as `"running"` |
| `@@PHASE_COMPLETE` | Marks a phase as `"completed"`, updates progress |
| `@@PHASE_FAILED` | Marks a phase as `"failed"`, sets pipeline status to `"failed"` |
| `@@PIPELINE_COMPLETE` | Sets status to `"completed"`, progress to 1.0 |

### Generated saga

```python
saga = pipeline.build_saga()
```

The saga walks the dependency graph, yielding `Put` actions for state transitions, `Call` effects for phase handlers, and `Fork` effects for parallel phases. Wire it into the Store with a `ReducerResult` or run it through the saga runner directly.

## Observable state

`PipelineState` gives you a real-time view of pipeline progress:

```python
state: PipelineState = store.get_state()
state.status        # "running" | "completed" | "failed" | "pending"
state.progress      # 0.0 to 1.0 based on phase weights
state.current_phase # name of the currently executing phase
state.elapsed       # total elapsed time
state.phases        # tuple of PhaseStatus objects
```

Each `PhaseStatus` tracks:

```python
phase.name       # "render"
phase.status     # "pending" | "running" | "completed" | "failed" | "skipped"
phase.started_at # monotonic timestamp
phase.elapsed    # seconds
phase.error      # error message if failed
```

## Failure policies

Control what happens when a phase raises an exception with `PhasePolicy`:

```python
from milo import Phase, PhasePolicy

Phase(
    "deploy",
    handler=deploy,
    policy=PhasePolicy(on_fail="retry", max_retries=3, retry_backoff="exponential"),
)
```

| Field | Default | Description |
|---|---|---|
| `on_fail` | `"stop"` | `"stop"` halts the pipeline, `"skip"` continues, `"retry"` retries |
| `max_retries` | `0` | Number of retry attempts (only when `on_fail="retry"`) |
| `retry_delay` | `1.0` | Initial delay in seconds between retries |
| `retry_backoff` | `"fixed"` | `"fixed"` or `"exponential"` (capped at 30s) |

The pipeline reducer tracks `"retrying"` as a distinct phase status alongside `"pending"`, `"running"`, `"completed"`, `"failed"`, and `"skipped"`.

## Output capture

Enable `capture_output=True` to collect stdout/stderr from each phase handler:

```python
pipeline = Pipeline("build", *phases, capture_output=True)
```

Captured output is dispatched as `@@PHASE_LOG` actions with `{"name", "line", "stream", "timestamp"}` payloads. The pipeline reducer stores logs on each `PhaseStatus`:

```python
phase = state.phases[0]
for log in phase.logs:
    print(f"[{log.stream}] {log.line}")
```

## Detail TUI

For interactive pipeline visualization, wrap the pipeline reducer with `make_detail_reducer`:

```python
from milo import App, Store
from milo.pipeline import make_detail_reducer

reducer = make_detail_reducer(pipeline.build_reducer())
app = App(template="pipeline.kida", reducer=reducer, initial_state=None)
```

The detail reducer adds keyboard navigation over `PipelineViewState`:

| Key | Action |
|---|---|
| `↑` / `↓` | Select phase |
| `Enter` | Expand/collapse phase logs |
| `g` / `G` | Scroll to top/bottom of logs |
| `f` | Toggle auto-follow |
| `q` | Quit |

## MCP timeline resource

When a pipeline is active, the `milo://pipeline/timeline` resource exposes the execution timeline as JSON. AI agents can read this to monitor pipeline progress in real time.

:::{tip}
Subscribe a listener to the Store to render a live progress display as phases complete. The weighted progress calculation gives accurate estimates even when phases have different durations.
:::
