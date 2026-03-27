"""Buildpipe — pipeline orchestration with phases, dependencies, and progress.

Demonstrates: Pipeline, Phase, build_reducer, build_saga, execution_order, >> operator.

    uv run python examples/buildpipe/app.py build
    uv run python examples/buildpipe/app.py order
    uv run python examples/buildpipe/app.py build --format json
"""

from __future__ import annotations

import time

from milo import CLI, Action, Phase, Pipeline, PipelineState


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
    Phase("render", handler=render, depends_on=("parse",), parallel=True, description="Render HTML"),
    Phase("assets", handler=copy_assets, depends_on=("parse",), parallel=True, description="Copy assets"),
    Phase("write", handler=write_output, depends_on=("render", "assets"), description="Write files"),
)

# Extend with >> operator
pipeline = pipeline >> Phase("health", handler=check_links, depends_on=("write",), description="Check links")


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


if __name__ == "__main__":
    cli.run()
