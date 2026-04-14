"""Buildpipe — pipeline orchestration with phases, dependencies, and progress.

Demonstrates: Pipeline, Phase, PhasePolicy, build_reducer, build_saga,
execution_order, >> operator, and interactive TUI visualization via App + Store + saga.

    uv run python examples/buildpipe/app.py build
    uv run python examples/buildpipe/app.py run        # interactive TUI
    uv run python examples/buildpipe/app.py order
    uv run python examples/buildpipe/app.py build --format json
"""

from __future__ import annotations

import time

from milo import (
    CLI,
    Action,
    App,
    Key,
    Phase,
    PhasePolicy,
    Pipeline,
    PipelineState,
    Quit,
    ReducerResult,
    SpecialKey,
)

# ---------------------------------------------------------------------------
# Phase handlers — each does real (simulated) work
# ---------------------------------------------------------------------------


def discover() -> dict:
    """Scan the content directory for source files."""
    time.sleep(0.05)
    return {"files": ["index.md", "about.md", "blog/hello.md"]}


def parse() -> dict:
    """Parse markdown files into an AST."""
    time.sleep(0.05)
    return {"parsed": 3}


def render() -> dict:
    """Render AST to HTML."""
    time.sleep(0.05)
    return {"rendered": 3}


def copy_assets() -> dict:
    """Copy static assets to the output directory."""
    time.sleep(0.05)
    return {"copied": ["style.css", "logo.png"]}


def write_output() -> dict:
    """Write final HTML files to disk."""
    time.sleep(0.05)
    return {"written": 3}


def check_links() -> dict:
    """Verify all internal links resolve."""
    time.sleep(0.05)
    return {"checked": 12, "broken": 0}


# ---------------------------------------------------------------------------
# Pipeline definition
# ---------------------------------------------------------------------------

pipeline = Pipeline(
    "site-build",
    Phase("discover", handler=discover, description="Scan content directory"),
    Phase("parse", handler=parse, depends_on=("discover",), description="Parse markdown"),
    Phase(
        "render",
        handler=render,
        depends_on=("parse",),
        parallel=True,
        description="Render HTML",
        policy=PhasePolicy(on_fail="retry", max_retries=2, retry_delay=0.5, retry_backoff="exponential"),
    ),
    Phase("assets", handler=copy_assets, depends_on=("parse",), parallel=True, description="Copy assets"),
    Phase("write", handler=write_output, depends_on=("render", "assets"), description="Write files"),
)

# Extend with >> operator — link checking is non-critical, so skip on failure
pipeline = pipeline >> Phase(
    "health",
    handler=check_links,
    depends_on=("write",),
    description="Check links",
    policy=PhasePolicy(on_fail="skip"),
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

cli = CLI(
    name="buildpipe",
    description="Pipeline orchestration example — phases, dependencies, and progress.",
    version="0.1.0",
)


@cli.command("order", description="Show execution order")
def show_order() -> list[str]:
    """Display the topological execution order of pipeline phases."""
    return pipeline.execution_order()


@cli.command("build", description="Run the build pipeline")
def build() -> dict:
    """Execute the full build pipeline through the Store/saga system."""
    from milo import Store

    reducer = pipeline.build_reducer()
    store = Store(reducer, initial_state=None)

    # Run through the pipeline actions manually for demonstration
    store.dispatch(Action("@@PIPELINE_START", time.monotonic()))

    results = {}
    for phase_name in pipeline.execution_order():
        phase = next(p for p in pipeline.phases if p.name == phase_name)

        store.dispatch(Action("@@PHASE_START", phase_name))
        try:
            result = phase.handler()
            results[phase_name] = result
            store.dispatch(Action("@@PHASE_COMPLETE", {"name": phase_name, "result": result}))
        except Exception as e:
            store.dispatch(Action("@@PHASE_FAILED", {"name": phase_name, "error": str(e)}))
            break

    store.dispatch(Action("@@PIPELINE_COMPLETE"))

    state: PipelineState = store.state
    return {
        "pipeline": state.name,
        "status": state.status,
        "progress": state.progress,
        "phases": {p.name: p.status for p in state.phases},
        "results": results,
    }


@cli.command("phases", description="List all pipeline phases")
def list_phases() -> list[dict]:
    """List pipeline phases with their dependencies and properties."""
    return [
        {
            "name": p.name,
            "description": p.description,
            "depends_on": list(p.depends_on),
            "parallel": p.parallel,
            "weight": p.weight,
        }
        for p in pipeline.phases
    ]


# ---------------------------------------------------------------------------
# Interactive TUI — live pipeline visualization
# ---------------------------------------------------------------------------


def _make_tui_reducer(pipeline_reducer, pipeline_saga):
    """Wrap the pipeline reducer with keyboard handling and saga scheduling."""

    def reducer(state: PipelineState | None, action: Action) -> PipelineState | Quit | ReducerResult:
        if action.type == "@@INIT":
            init_state = pipeline_reducer(state, action)
            # Schedule the pipeline saga on init
            return ReducerResult(state=init_state, sagas=(pipeline_saga,))

        if action.type == "@@KEY":
            key: Key = action.payload
            if key.char == "q" or key.name == SpecialKey.ESCAPE:
                return Quit(state=state)

        # Auto-quit when pipeline completes or fails
        new_state = pipeline_reducer(state, action)
        if action.type == "@@PIPELINE_COMPLETE" or action.type == "@@PHASE_FAILED":
            return Quit(state=new_state, code=0 if action.type == "@@PIPELINE_COMPLETE" else 1)

        return new_state

    return reducer


@cli.command("run", description="Run the pipeline with interactive TUI")
def run_interactive() -> str:
    """Launch the build pipeline with a live-updating terminal UI."""
    pipeline_reducer = pipeline.build_reducer()
    pipeline_saga = pipeline.build_saga()

    tui_reducer = _make_tui_reducer(pipeline_reducer, pipeline_saga)

    app = App.from_dir(
        __file__,
        template="pipeline.kida",
        reducer=tui_reducer,
        initial_state=None,
        tick_rate=0.05,
        exit_template="exit.kida",
    )
    final_state = app.run()
    return f"Pipeline {final_state.status}: {final_state.name}"


if __name__ == "__main__":
    cli.run()
