"""Ctxdemo — context injection and global options.

Demonstrates: Context parameter injection, get_context(), custom global options,
verbosity levels, color flag.

    uv run python examples/ctxdemo/app.py greet --name Alice
    uv run python examples/ctxdemo/app.py -v greet --name Alice
    uv run python examples/ctxdemo/app.py -q greet --name Alice
    uv run python examples/ctxdemo/app.py info --format json
    uv run python examples/ctxdemo/app.py -e staging info
"""

from __future__ import annotations

from milo import CLI, Context, get_context

cli = CLI(
    name="ctxdemo",
    description="Context and global options example — verbosity, color, custom globals.",
    version="0.1.0",
)

# Register custom global options (available on every command via ctx.globals)
cli.global_option("environment", short="-e", default="local", description="Target environment")
cli.global_option("dry_run", is_flag=True, description="Simulate without making changes")


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
        "globals": dict(ctx.globals),
    }


@cli.command("deploy", description="Simulate a deployment with global options")
def deploy(service: str, ctx: Context = None) -> dict:
    """Deploy a service, respecting --dry-run and --environment."""
    env = ctx.globals.get("environment", "local")
    dry = ctx.globals.get("dry_run", False)

    ctx.log(f"Target environment: {env}", level=1)
    ctx.log(f"Dry run: {dry}", level=1)

    if dry:
        return {"action": "dry-run", "service": service, "environment": env}
    return {"action": "deployed", "service": service, "environment": env}


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
