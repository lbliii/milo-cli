"""Ctxdemo — context injection, logging, progress, and confirm gates.

Demonstrates: Context parameter injection, get_context(), custom global options,
verbosity levels, color flag, ctx.info/warning/error/success, ctx.progress(),
ctx.confirm(), --dry-run, --output-file.

    uv run python examples/ctxdemo/app.py greet --name Alice
    uv run python examples/ctxdemo/app.py -v greet --name Alice
    uv run python examples/ctxdemo/app.py -q greet --name Alice
    uv run python examples/ctxdemo/app.py info --format json
    uv run python examples/ctxdemo/app.py -e staging info
    uv run python examples/ctxdemo/app.py --dry-run deploy --service api
    uv run python examples/ctxdemo/app.py process --count 50
    uv run python examples/ctxdemo/app.py cleanup
"""

from __future__ import annotations

import time

from milo import CLI, Context, get_context

cli = CLI(
    name="ctxdemo",
    description="Context and global options example — verbosity, color, custom globals.",
    version="0.1.0",
)

# Register custom global options (available on every command via ctx.globals)
cli.global_option("environment", short="-e", default="local", description="Target environment")


@cli.command("greet", description="Greet a user with context-aware verbosity")
def greet(name: str, ctx: Context = None) -> str:
    """Greet someone, demonstrating verbosity levels."""
    ctx.log(f"Context: verbosity={ctx.verbosity}, color={ctx.color}", level=2)
    ctx.log(f"Environment: {ctx.globals.get('environment', 'local')}", level=1)

    if ctx.quiet:
        return name
    return f"Hello, {name}!"


@cli.command("info", description="Show execution context details")
def info(ctx: Context = None) -> dict:
    """Display the full execution context."""
    return {
        "verbosity": ctx.verbosity,
        "format": ctx.format,
        "color": ctx.color,
        "quiet": ctx.quiet,
        "verbose": ctx.verbose,
        "debug": ctx.debug,
        "dry_run": ctx.dry_run,
        "globals": dict(ctx.globals),
    }


@cli.command("deploy", description="Simulate a deployment with dry-run support")
def deploy(service: str, ctx: Context = None) -> dict:
    """Deploy a service, demonstrating --dry-run, ctx.info/success, and ctx.confirm."""
    env = ctx.globals.get("environment", "local")

    ctx.info(f"Deploying {service} to {env}")

    if ctx.dry_run:
        ctx.warning(f"Dry-run: would deploy {service} to {env}")
        return {"action": "dry-run", "service": service, "environment": env}

    if env == "production" and not ctx.confirm(f"Deploy {service} to production?"):
        ctx.warning("Aborted by user")
        return {"action": "aborted", "service": service}

    ctx.success(f"Deployed {service} to {env}")
    return {"action": "deployed", "service": service, "environment": env}


@cli.command("process", description="Process items with a progress bar")
def process(count: int = 20, ctx: Context = None) -> dict:
    """Process N items, demonstrating ctx.progress()."""
    ctx.info(f"Processing {count} items...")

    with ctx.progress(total=count, label="Processing") as p:
        for _i in range(count):
            time.sleep(0.02)  # simulate work
            p.update(1)

    ctx.success(f"Processed {count} items")
    return {"processed": count}


@cli.command("cleanup", description="Clean up with confirmation and logging levels")
def cleanup(ctx: Context = None) -> str:
    """Demonstrate all logging helpers."""
    ctx.info("Starting cleanup")
    ctx.log("Scanning for stale files...", level=1)
    ctx.log("Cache dir: /tmp/ctxdemo", level=2)

    if ctx.dry_run:
        ctx.warning("Dry-run: skipping actual deletion")
        return "dry-run"

    if not ctx.confirm("Delete 3 stale files?"):
        ctx.warning("Cleanup aborted")
        return "aborted"

    ctx.success("Cleaned up 3 stale files")
    return "done"


@cli.command("check", description="Demonstrate get_context() for library code")
def check() -> dict:
    """Show that get_context() works without explicit parameter injection."""
    ctx = get_context()
    return {
        "accessed_via": "get_context()",
        "verbosity": ctx.verbosity,
        "environment": ctx.globals.get("environment", "local"),
    }


if __name__ == "__main__":
    cli.run()
