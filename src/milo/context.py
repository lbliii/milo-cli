"""Execution context for CLI command handlers."""

from __future__ import annotations

import os
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Context:
    """Execution context available to all command handlers.

    Handlers opt in by adding a ``ctx: Context`` parameter::

        @cli.command("build", description="Build the site")
        def build(output: str = "_site", ctx: Context = None) -> str:
            ctx.log("Starting build...", level=1)  # verbose only
            return f"Built to {output}"

    The context is injected automatically by the CLI dispatcher and
    excluded from argparse and MCP schemas.
    """

    verbosity: int = 0
    """Verbosity level: -1=quiet, 0=normal, 1=verbose, 2=debug."""

    format: str = "plain"
    """Output format: plain, json, table."""

    color: bool = True
    """Whether color output is enabled."""

    dry_run: bool = False
    """Whether --dry-run was passed (no side effects)."""

    output_file: str = ""
    """Path to redirect output to (from --output)."""

    globals: dict[str, Any] = field(default_factory=dict)
    """Values from user-defined global options."""

    def log(self, message: str, *, level: int = 0) -> None:
        """Print a message if verbosity is at or above *level*.

        level 0 = normal (always shown unless quiet)
        level 1 = verbose (shown with --verbose)
        level 2 = debug (shown with -vv)
        """
        if self.verbosity >= level:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()

    def info(self, message: str) -> None:
        """Print an informational message (level 0)."""
        if self.verbosity >= 0:
            prefix = "\033[34minfo:\033[0m " if self.color else "info: "
            sys.stderr.write(prefix + message + "\n")
            sys.stderr.flush()

    def success(self, message: str) -> None:
        """Print a success message (level 0)."""
        if self.verbosity >= 0:
            prefix = "\033[32m\u2713\033[0m " if self.color else "OK: "
            sys.stderr.write(prefix + message + "\n")
            sys.stderr.flush()

    def warning(self, message: str) -> None:
        """Print a warning message (always shown, even in quiet mode)."""
        prefix = "\033[33mwarning:\033[0m " if self.color else "warning: "
        sys.stderr.write(prefix + message + "\n")
        sys.stderr.flush()

    def error(self, message: str) -> None:
        """Print an error message (always shown)."""
        prefix = "\033[31merror:\033[0m " if self.color else "error: "
        sys.stderr.write(prefix + message + "\n")
        sys.stderr.flush()

    def confirm(self, message: str, *, default: bool = False) -> bool:
        """Prompt for yes/no confirmation. Returns default in non-interactive mode.

        In dry-run mode, always returns False.
        """
        if self.dry_run:
            self.info(f"[dry-run] Would ask: {message}")
            return False

        if not sys.stdin.isatty():
            return default

        suffix = " [Y/n] " if default else " [y/N] "
        try:
            sys.stderr.write(message + suffix)
            sys.stderr.flush()
            answer = input().strip().lower()
        except EOFError, KeyboardInterrupt:
            sys.stderr.write("\n")
            return default

        if not answer:
            return default
        return answer in ("y", "yes")

    def progress(self, total: int = 0, *, label: str = "") -> CLIProgress:
        """Create an inline progress indicator for CLI commands.

        Usage::

            with ctx.progress(total=100, label="Downloading") as p:
                for i in range(100):
                    do_work()
                    p.update(1)
        """
        return CLIProgress(total=total, label=label, color=self.color, quiet=self.quiet)

    @property
    def quiet(self) -> bool:
        """True when --quiet was passed."""
        return self.verbosity < 0

    @property
    def verbose(self) -> bool:
        """True when --verbose was passed."""
        return self.verbosity >= 1

    @property
    def debug(self) -> bool:
        """True when -vv (or higher) was passed."""
        return self.verbosity >= 2

    @property
    def is_ci(self) -> bool:
        """True when running in CI (CI env var is set)."""
        return bool(os.environ.get("CI"))

    @property
    def is_interactive(self) -> bool:
        """True when stdin is a TTY."""
        return sys.stdin.isatty()


class CLIProgress:
    """Inline progress bar for CLI commands."""

    def __init__(
        self,
        *,
        total: int = 0,
        label: str = "",
        color: bool = True,
        quiet: bool = False,
    ) -> None:
        self._total = total
        self._label = label
        self._color = color
        self._quiet = quiet
        self._current = 0

    def __enter__(self) -> CLIProgress:
        if not self._quiet:
            self._render()
        return self

    def __exit__(self, *exc: object) -> None:
        if not self._quiet:
            sys.stderr.write("\n")
            sys.stderr.flush()

    def update(self, n: int = 1) -> None:
        """Advance progress by n steps."""
        self._current += n
        if not self._quiet:
            self._render()

    def set(self, n: int) -> None:
        """Set progress to an absolute value."""
        self._current = n
        if not self._quiet:
            self._render()

    def _render(self) -> None:
        parts: list[str] = ["\r"]
        if self._label:
            parts.append(f"{self._label} ")

        if self._total > 0:
            pct = min(100, int(self._current / self._total * 100))
            filled = pct // 2
            bar = "\u2588" * filled + "\u2591" * (50 - filled)
            parts.append(f"[{bar}] {pct}% ({self._current}/{self._total})")
        else:
            parts.append(f"{self._current} items")

        sys.stderr.write("".join(parts))
        sys.stderr.flush()


_current_context: ContextVar[Context | None] = ContextVar("milo_context", default=None)


def get_context() -> Context:
    """Get the current execution context.

    Returns a default Context if none has been set.
    """
    ctx = _current_context.get()
    if ctx is None:
        return Context()
    return ctx


def set_context(ctx: Context) -> None:
    """Set the current execution context."""
    _current_context.set(ctx)
