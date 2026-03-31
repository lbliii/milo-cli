"""Devtool — realistic CLI demonstrating production-grade features.

Demonstrates: doctor diagnostics, version checking, shell completions,
before/after hooks, did-you-mean suggestions, examples in help, error handling,
generate_help_all(), and invoke() for testing.

    uv run python examples/devtool/app.py doctor
    uv run python examples/devtool/app.py build --target release
    uv run python examples/devtool/app.py lint --fix
    uv run python examples/devtool/app.py --completions bash
    uv run python examples/devtool/app.py reference
"""

from __future__ import annotations

import time

from milo import CLI, Check, Context, check_version, format_doctor_report, run_doctor

cli = CLI(
    name="devtool",
    description="Example dev CLI — build, lint, doctor, and more.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Before/after hooks
# ---------------------------------------------------------------------------


_start_times: dict[str, float] = {}


@cli.before_command
def timing_start(ctx, command_name, kwargs):
    """Record the start time of every command."""
    _start_times[command_name] = time.monotonic()
    ctx.log(f"[hook] starting {command_name}", level=1)


@cli.after_command
def timing_end(ctx, command_name, result):
    """Log how long each command took (verbose only)."""
    elapsed = time.monotonic() - _start_times.pop(command_name, 0)
    ctx.log(f"[hook] {command_name} completed in {elapsed:.3f}s", level=1)


# ---------------------------------------------------------------------------
# Commands with examples in help
# ---------------------------------------------------------------------------


@cli.command(
    "build",
    description="Build the project",
    examples=(
        {"command": "devtool build", "description": "Build with defaults"},
        {"command": "devtool build --target release", "description": "Optimized release build"},
        {"command": "devtool --dry-run build", "description": "Preview what would be built"},
    ),
)
def build(target: str = "debug", ctx: Context = None) -> dict:
    """Compile the project for the given target."""
    ctx.info(f"Building for target: {target}")

    if ctx.dry_run:
        ctx.warning(f"Dry-run: would build {target}")
        return {"action": "dry-run", "target": target}

    with ctx.progress(total=5, label="Building") as p:
        for step in ("parse", "check", "codegen", "link", "package"):
            ctx.log(f"  {step}...", level=1)
            time.sleep(0.05)
            p.update(1)

    ctx.success(f"Built {target}")
    return {"action": "built", "target": target}


@cli.command(
    "lint",
    description="Lint source files",
    examples=(
        {"command": "devtool lint", "description": "Check for issues"},
        {"command": "devtool lint --fix", "description": "Auto-fix issues"},
    ),
)
def lint(fix: bool = False, ctx: Context = None) -> dict:
    """Run the linter on all source files."""
    ctx.info("Linting source files...")

    issues = [
        {"file": "src/main.py", "line": 12, "message": "unused import"},
        {"file": "src/utils.py", "line": 45, "message": "line too long"},
    ]

    if fix:
        ctx.success(f"Fixed {len(issues)} issues")
        return {"action": "fixed", "count": len(issues)}

    for issue in issues:
        ctx.warning(f"{issue['file']}:{issue['line']}: {issue['message']}")
    return {"action": "checked", "issues": issues}


# ---------------------------------------------------------------------------
# Doctor diagnostics with custom checks
# ---------------------------------------------------------------------------


def check_node():
    """Custom check: is Node.js available?"""
    import shutil

    path = shutil.which("node")
    if path:
        return Check(name="node", status="ok", message=path)
    return Check(
        name="node",
        status="warn",
        message="Not found",
        suggestion="Install Node.js for full functionality",
    )


@cli.command("doctor", description="Run diagnostic health checks")
def doctor(ctx: Context = None) -> str:
    """Check the environment for common issues."""
    report = run_doctor(
        cli,
        required_tools=("git", "python"),
        custom_checks=(check_node,),
    )
    return format_doctor_report(report, color=ctx.color)


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------


@cli.command("version", description="Show version and check for updates")
def version(ctx: Context = None) -> str:
    """Print the current version and check PyPI for updates."""
    from milo.version_check import format_version_notice

    ctx.info(f"devtool v{cli._version}")

    info = check_version("milo-cli", cli._version)
    if info and info.update_available:
        ctx.warning(format_version_notice(info, prog="devtool"))

    return cli._version


# ---------------------------------------------------------------------------
# Generate markdown reference
# ---------------------------------------------------------------------------


@cli.command("reference", description="Generate CLI reference in markdown")
def reference(ctx: Context = None) -> str:
    """Output a full markdown reference for all commands."""
    return cli.generate_help_all()


# ---------------------------------------------------------------------------
# A command that errors (demonstrates structured error handling)
# ---------------------------------------------------------------------------


@cli.command("deploy", description="Deploy (will fail without config)")
def deploy(env: str = "staging", ctx: Context = None) -> str:
    """Deploy to an environment — demonstrates error handling."""
    from milo._errors import ConfigError, ErrorCode

    raise ConfigError(
        ErrorCode.CFG_MISSING,
        f"No deployment config found for '{env}'",
        suggestion=f"Run 'devtool init --env {env}' to create one",
    )


if __name__ == "__main__":
    cli.run()
