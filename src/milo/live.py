"""Live-rendering primitives for non-event-loop use.

Re-exports from :mod:`kida.terminal`. Reach for these when you need a small
animated or streamed view *outside* a full :class:`milo.App` event loop — a
background job, a one-shot CLI command, or a script. When you need a
reducer-driven app, use :class:`milo.App` with :class:`milo.TickCmd` instead.

    from milo.live import LiveRenderer, Spinner, stream_to_terminal
"""

from __future__ import annotations

from kida.terminal import LiveRenderer, Spinner, stream_to_terminal, terminal_env

__all__ = ["LiveRenderer", "Spinner", "stream_to_terminal", "terminal_env"]
