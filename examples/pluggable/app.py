"""Pluggable — plugin system with hooks, listeners, and manual invocation.

Demonstrates: HookRegistry, define/on/invoke, freeze, introspection.

    uv run python examples/pluggable/app.py build
    uv run python examples/pluggable/app.py hooks
    uv run python examples/pluggable/app.py build --format json
"""

from __future__ import annotations

import sys
import time

from milo import CLI, Action, HookRegistry

# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------

hooks = HookRegistry()

# Define hook points
hooks.define("before_build", description="Fires before the build starts")
hooks.define("after_phase", description="Fires after each build phase completes")
hooks.define("build_complete", description="Fires when the full build finishes")


# ---------------------------------------------------------------------------
# Plugin: timing
# ---------------------------------------------------------------------------

build_start_time: float = 0.0


@hooks.on("before_build")
def timing_start(**kwargs):
    """Record build start time."""
    global build_start_time
    build_start_time = time.monotonic()
    return {"plugin": "timing", "event": "start"}


@hooks.on("build_complete")
def timing_end(**kwargs):
    """Report build duration."""
    elapsed = time.monotonic() - build_start_time
    return {"plugin": "timing", "elapsed": round(elapsed, 3)}


# ---------------------------------------------------------------------------
# Plugin: logger
# ---------------------------------------------------------------------------


@hooks.on("before_build")
def log_start(**kwargs):
    """Log build start."""
    sys.stderr.write("[logger] Build starting...\n")
    return {"plugin": "logger", "event": "start"}


@hooks.on("after_phase")
def log_phase(phase_name, **kwargs):
    """Log phase completions."""
    sys.stderr.write(f"[logger] Phase complete: {phase_name}\n")
    return {"plugin": "logger", "phase": phase_name}


@hooks.on("build_complete")
def log_end(**kwargs):
    """Log build completion."""
    sys.stderr.write("[logger] Build complete!\n")
    return {"plugin": "logger", "event": "end"}


# Freeze after all plugins are registered
hooks.freeze()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

cli = CLI(
    name="pluggable",
    description="Plugin system example — hooks, listeners, and extensibility.",
    version="0.1.0",
)


@cli.command("hooks", description="List all defined hooks")
def list_hooks() -> list[dict]:
    """List all registered hooks and their listener counts."""
    return [
        {"hook": name, "listeners": len(hooks.listeners(name))}
        for name in hooks.hook_names()
    ]


@cli.command("build", description="Run a build with plugins active")
def build() -> dict:
    """Run a simulated build with hook-based plugins."""
    # Fire before_build hook
    before_results = hooks.invoke("before_build")

    # Simulate phases
    phases = ["discover", "parse", "render", "write"]
    phase_results = {}
    for phase in phases:
        time.sleep(0.02)
        phase_results[phase] = "ok"
        # Fire after_phase hook for each completed phase
        hooks.invoke("after_phase", phase_name=phase)

    # Fire build_complete hook
    complete_results = hooks.invoke("build_complete")

    return {
        "status": "done",
        "phases": phase_results,
        "plugin_results": {
            "before_build": before_results,
            "build_complete": complete_results,
        },
    }


if __name__ == "__main__":
    cli.run()
