"""Lazyapp — lazy-loaded commands for fast CLI startup.

Demonstrates: cli.lazy_command(), deferred imports, pre-computed schemas.

    uv run python examples/lazyapp/app.py status
    uv run python examples/lazyapp/app.py deploy --target staging
    uv run python examples/lazyapp/app.py --llms-txt
"""

from __future__ import annotations

import sys
from pathlib import Path

from milo import CLI

# Ensure the examples directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

cli = CLI(
    name="lazyapp",
    description="Lazy loading example — deferred imports for fast startup.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Eager command — loaded immediately
# ---------------------------------------------------------------------------


@cli.command("status", description="Show deployment status")
def status() -> dict:
    """Show the current deployment status (always available, fast import)."""
    return {"environment": "production", "version": "2.1.0", "healthy": True}


# ---------------------------------------------------------------------------
# Lazy commands — handlers imported only when invoked
# ---------------------------------------------------------------------------

# The handler module is NOT imported until `deploy` is actually called.
# This keeps `lazyapp status` fast even if deploy_handlers has heavy imports.
cli.lazy_command(
    "deploy",
    "lazyapp.deploy_handlers:deploy",
    description="Deploy to an environment",
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False},
        },
        "required": ["target"],
    },
)

cli.lazy_command(
    "rollback",
    "lazyapp.deploy_handlers:rollback",
    description="Rollback the last deployment",
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "steps": {"type": "integer", "default": 1},
        },
        "required": ["target"],
    },
)

cli.lazy_command(
    "logs",
    "lazyapp.deploy_handlers:show_logs",
    description="Show deployment logs",
    aliases=("log",),
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string", "default": "production"},
            "lines": {"type": "integer", "default": 20},
        },
    },
)


if __name__ == "__main__":
    cli.run()
