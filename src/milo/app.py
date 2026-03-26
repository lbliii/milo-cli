"""App event loop and LiveRenderer integration."""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from milo._errors import AppError, ErrorCode
from milo._types import Action, AppStatus, RenderTarget
from milo.flow import Flow, FlowState
from milo.input._platform import is_tty
from milo.input._reader import KeyReader
from milo.state import Store


class App:
    """Main application event loop.

    Integrates the Store, KeyReader, and kida LiveRenderer
    into a unified event loop.
    """

    def __init__(
        self,
        *,
        template: str | Any = "",
        reducer: Callable | None = None,
        initial_state: Any = None,
        middleware: tuple[Callable, ...] = (),
        tick_rate: float = 0.0,
        transient: bool = False,
        target: RenderTarget = RenderTarget.TERMINAL,
        record: bool | str | Path = False,
        env: Any = None,
        flow: Flow | None = None,
    ) -> None:
        self._target = target
        self._tick_rate = tick_rate
        self._transient = transient
        self._env = env
        self._flow = flow
        self._template_name = template
        self._status = AppStatus.IDLE

        # Flow mode: build reducer from flow
        if flow is not None:
            self._reducer = flow.build_reducer()
            self._initial_state = None
            self._template_map = flow.template_map
        else:
            if reducer is None:
                raise AppError(ErrorCode.APP_LIFECYCLE, "Either reducer or flow is required")
            self._reducer = reducer
            self._initial_state = initial_state
            self._template_map = None

        self._middleware = middleware
        self._record = record

    @classmethod
    def from_flow(cls, flow: Flow, **kwargs: Any) -> App:
        """Create App from a declarative Flow."""
        return cls(flow=flow, **kwargs)

    def run(self) -> Any:
        """Run the event loop. Returns final state."""
        store = Store(
            self._reducer,
            self._initial_state,
            self._middleware,
            record=self._record,
        )

        if self._target == RenderTarget.HTML or not is_tty():
            # Single render pass, no input
            self._render_once(store.state)
            return store.state

        self._status = AppStatus.RUNNING

        # Set up signal handler for resize
        original_sigwinch = None
        if hasattr(signal, "SIGWINCH"):
            def _on_resize(signum: int, frame: Any) -> None:
                try:
                    cols, rows = os.get_terminal_size()
                    store.dispatch(Action("@@RESIZE", payload=(cols, rows)))
                except OSError:
                    pass

            original_sigwinch = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, _on_resize)

        # Set up tick timer
        tick_thread = None
        if self._tick_rate > 0:
            import threading

            stop_tick = threading.Event()

            def _tick_loop() -> None:
                while not stop_tick.is_set():
                    stop_tick.wait(self._tick_rate)
                    if not stop_tick.is_set() and self._status == AppStatus.RUNNING:
                        store.dispatch(Action("@@TICK"))

            tick_thread = threading.Thread(target=_tick_loop, daemon=True)
            tick_thread.start()

        env = self._get_env()
        renderer = None

        try:
            # Try to use kida LiveRenderer for flicker-free rendering
            try:
                from kida import LiveRenderer

                renderer = LiveRenderer(env)  # type: ignore[call-non-callable]
            except ImportError:
                pass

            # Subscribe to state changes for re-rendering
            def _on_state_change() -> None:
                self._render_state(store.state, env, renderer)

            unsubscribe = store.subscribe(_on_state_change)

            # Initial render
            self._render_state(store.state, env, renderer)

            # Input loop
            try:
                with KeyReader() as keys:
                    for key in keys:
                        if self._status != AppStatus.RUNNING:
                            break

                        # Ctrl+C or Escape quits
                        if key.ctrl and key.char == "c":
                            store.dispatch(Action("@@QUIT"))
                            break

                        store.dispatch(Action("@@KEY", payload=key))

                        # Check if the app should stop
                        state = store.state
                        if self._should_quit(state):
                            store.dispatch(Action("@@QUIT"))
                            break
            except Exception:
                pass

            self._status = AppStatus.STOPPED
            unsubscribe()

        finally:
            if tick_thread is not None:
                stop_tick.set()
            if renderer is not None:
                with contextlib.suppress(Exception):
                    renderer.stop()
            if original_sigwinch is not None:
                signal.signal(signal.SIGWINCH, original_sigwinch)
            store.shutdown()

        # Final render if transient, clear screen
        if self._transient and renderer:
            with contextlib.suppress(Exception):
                renderer.clear()

        return store.state

    def _should_quit(self, state: Any) -> bool:
        """Check if state signals the app should quit."""
        if hasattr(state, "submitted") and state.submitted:
            return True
        return bool(isinstance(state, dict) and state.get("quit"))

    def _get_env(self) -> Any:
        """Get or create the kida Environment."""
        if self._env is not None:
            return self._env
        from milo.templates import get_env

        return get_env()

    def _get_template_name(self, state: Any) -> str:
        """Get the template name for the current state."""
        if self._template_map and isinstance(state, FlowState):
            return self._template_map.get(state.current_screen, self._template_name)
        return self._template_name

    def _render_state(self, state: Any, env: Any, renderer: Any) -> None:
        """Render current state through the template."""
        try:
            template_name = self._get_template_name(state)
            template = env.get_template(template_name)

            # For flow state, pass the current screen's state
            render_state = state
            if isinstance(state, FlowState):
                render_state = state.screen_states.get(state.current_screen, state)

            output = template.render(state=render_state)

            if renderer is not None:
                renderer.update(output)
            else:
                sys.stdout.write("\033[2J\033[H" + output)
                sys.stdout.flush()
        except Exception:
            pass

    def _render_once(self, state: Any) -> None:
        """Single render pass (non-TTY or HTML mode)."""
        try:
            env = self._get_env()
            template_name = self._get_template_name(state)
            template = env.get_template(template_name)

            render_state = state
            if isinstance(state, FlowState):
                render_state = state.screen_states.get(state.current_screen, state)

            output = template.render(state=render_state)
            sys.stdout.write(output + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def run(*, template: str, reducer: Callable, initial_state: Any, **kwargs: Any) -> Any:
    """Shorthand: App(...).run()"""
    return App(template=template, reducer=reducer, initial_state=initial_state, **kwargs).run()


def render_html(
    state: Any,
    template: str | Any,
    *,
    title: str = "",
    css: str = "",
    env: Any = None,
) -> str:
    """One-shot HTML render of state through template."""
    if env is None:
        from milo.templates import get_env

        env = get_env(autoescape=True)

    tmpl = env.get_template(template) if isinstance(template, str) else template

    body = tmpl.render(state=state)

    default_css = """
body { background: #1e1e1e; color: #d4d4d4; font-family: monospace; padding: 2em; }
.dim { opacity: 0.6; }
strong { font-weight: bold; }
"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css or default_css}</style>
</head>
<body>
<pre>{body}</pre>
</body>
</html>"""
