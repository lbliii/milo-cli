"""Execution context for CLI command handlers."""

from __future__ import annotations

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
