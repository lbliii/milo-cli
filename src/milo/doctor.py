"""Built-in diagnostic command for CLI health checks."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from milo.commands import CLI
    from milo.config import ConfigSpec


@dataclass(frozen=True, slots=True)
class Check:
    """A single diagnostic check."""

    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Aggregated diagnostic report."""

    checks: tuple[Check, ...] = ()
    ok: int = 0
    warnings: int = 0
    failures: int = 0


def run_doctor(
    cli: CLI,
    *,
    config_spec: ConfigSpec | None = None,
    required_env: tuple[str, ...] = (),
    required_tools: tuple[str, ...] = (),
    custom_checks: tuple[Any, ...] = (),
) -> DoctorReport:
    """Run all diagnostic checks and return a report.

    Args:
        cli: The CLI instance to diagnose.
        config_spec: If provided, check that config files exist.
        required_env: Environment variables that must be set.
        required_tools: External binaries that must be on PATH.
        custom_checks: Callables that return Check instances.
    """
    checks: list[Check] = []

    # Python version
    py = sys.version_info
    checks.append(Check(
        name="python",
        status="ok",
        message=f"Python {py.major}.{py.minor}.{py.micro}",
    ))

    # milo version
    try:
        import milo
        checks.append(Check(
            name="milo",
            status="ok",
            message=f"milo {milo.__version__}",
        ))
    except Exception:
        checks.append(Check(
            name="milo",
            status="fail",
            message="Cannot import milo",
        ))

    # Config files
    if config_spec:
        for pattern in config_spec.sources:
            import glob as globmod
            from pathlib import Path

            matched = globmod.glob(str(Path.cwd() / pattern))
            if matched:
                checks.append(Check(
                    name=f"config:{pattern}",
                    status="ok",
                    message=f"Found {len(matched)} file(s)",
                ))
            else:
                checks.append(Check(
                    name=f"config:{pattern}",
                    status="warn",
                    message=f"No files match '{pattern}'",
                    suggestion=f"Create a config file matching '{pattern}'",
                ))

    # Required env vars
    for var in required_env:
        if os.environ.get(var):
            checks.append(Check(
                name=f"env:{var}",
                status="ok",
                message="Set",
            ))
        else:
            checks.append(Check(
                name=f"env:{var}",
                status="fail",
                message="Not set",
                suggestion=f"export {var}=<value>",
            ))

    # Required tools
    for tool in required_tools:
        path = shutil.which(tool)
        if path:
            checks.append(Check(
                name=f"tool:{tool}",
                status="ok",
                message=path,
            ))
        else:
            checks.append(Check(
                name=f"tool:{tool}",
                status="fail",
                message="Not found on PATH",
                suggestion=f"Install {tool} or add it to PATH",
            ))

    # Commands registered
    cmd_count = len(list(cli.walk_commands()))
    checks.append(Check(
        name="commands",
        status="ok",
        message=f"{cmd_count} command(s) registered",
    ))

    # Custom checks
    for check_fn in custom_checks:
        try:
            result = check_fn()
            if isinstance(result, Check):
                checks.append(result)
        except Exception as e:
            checks.append(Check(
                name=getattr(check_fn, "__name__", "custom"),
                status="fail",
                message=str(e),
            ))

    ok = sum(1 for c in checks if c.status == "ok")
    warnings = sum(1 for c in checks if c.status == "warn")
    failures = sum(1 for c in checks if c.status == "fail")

    return DoctorReport(
        checks=tuple(checks),
        ok=ok,
        warnings=warnings,
        failures=failures,
    )


def format_doctor_report(report: DoctorReport, *, color: bool = True) -> str:
    """Format a doctor report for terminal display."""
    lines: list[str] = []

    icons = {
        "ok": "\u2713" if color else "OK",
        "warn": "!" if color else "WARN",
        "fail": "\u2717" if color else "FAIL",
    }

    for check in report.checks:
        icon = icons.get(check.status, "?")
        line = f"  {icon} {check.name}: {check.message}"
        lines.append(line)
        if check.suggestion:
            lines.append(f"    hint: {check.suggestion}")

    lines.append("")
    lines.append(
        f"{report.ok} passed, {report.warnings} warnings, {report.failures} failures"
    )

    return "\n".join(lines)
