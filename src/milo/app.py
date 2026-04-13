"""App event loop and terminal rendering."""

from __future__ import annotations

import contextlib
import shutil
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from milo._compat import enable_vt_processing, watch_terminal_resize
from milo._errors import AppError, ErrorCode, format_render_error
from milo._types import Action, AppStatus, RenderTarget, ViewState
from milo.flow import Flow, FlowState
from milo.input._platform import is_tty
from milo.input._reader import KeyReader
from milo.state import Store


class _TerminalRenderer:
    """In-place terminal renderer using alternate screen buffer.

    Uses cursor-home redraws with line clearing to avoid flicker
    and prevent frame stacking.  Supports declarative ViewState for
    controlling terminal features (alt screen, cursor, mouse, title).
    """

    def __init__(self) -> None:
        self._prev_lines = 0
        self._started = False
        self._view_state = ViewState(alt_screen=False, cursor_visible=True)

    def start(self) -> None:
        """Enter alternate screen buffer and hide cursor."""
        enable_vt_processing()
        sys.stdout.write("\033[?1049h")  # Enter alternate screen
        sys.stdout.write("\033[?25l")  # Hide cursor
        sys.stdout.flush()
        self._started = True
        self._view_state = ViewState(alt_screen=True, cursor_visible=False)

    def apply_view_state(self, view: ViewState) -> None:
        """Diff *view* against current state and apply only the changes."""
        if not self._started:
            return
        prev = self._view_state
        buf = []

        if view.alt_screen is not None and view.alt_screen != prev.alt_screen:
            buf.append("\033[?1049h" if view.alt_screen else "\033[?1049l")

        if view.cursor_visible is not None and view.cursor_visible != prev.cursor_visible:
            buf.append("\033[?25h" if view.cursor_visible else "\033[?25l")

        if view.mouse_mode is not None and view.mouse_mode != prev.mouse_mode:
            buf.append("\033[?1003h" if view.mouse_mode else "\033[?1003l")

        if view.window_title is not None and view.window_title != prev.window_title:
            buf.append(f"\033]2;{view.window_title}\033\\")

        if buf:
            sys.stdout.write("".join(buf))
            sys.stdout.flush()

        # Merge: only overwrite fields that were explicitly set (not None)
        self._view_state = ViewState(
            alt_screen=view.alt_screen if view.alt_screen is not None else prev.alt_screen,
            cursor_visible=(
                view.cursor_visible if view.cursor_visible is not None else prev.cursor_visible
            ),
            mouse_mode=view.mouse_mode if view.mouse_mode is not None else prev.mouse_mode,
            window_title=(
                view.window_title if view.window_title is not None else prev.window_title
            ),
        )

    def update(self, output: str) -> None:
        """Redraw the screen with new output."""
        if not self._started:
            return
        cols = shutil.get_terminal_size().columns
        lines = output.split("\n")

        # Move cursor to home position
        sys.stdout.write("\033[H")

        # Write each line, clearing to end of line
        for line in lines:
            # Truncate to terminal width to avoid wrapping artifacts
            sys.stdout.write(line[:cols])
            sys.stdout.write("\033[K\n")  # Clear to end of line

        # Clear any leftover lines from previous frame
        if self._prev_lines > len(lines):
            for _ in range(self._prev_lines - len(lines)):
                sys.stdout.write("\033[K\n")

        self._prev_lines = len(lines)
        sys.stdout.flush()

    def stop(self) -> None:
        """Show cursor and leave alternate screen buffer.

        Each step is individually guarded so a failure in one does
        not prevent the remaining cleanup from running.
        """
        if not self._started:
            return
        self._started = False
        try:
            # Disable mouse mode if it was enabled
            if self._view_state.mouse_mode:
                sys.stdout.write("\033[?1003l")
            sys.stdout.write("\033[?25h")  # Show cursor
            sys.stdout.write("\033[?1049l")  # Leave alternate screen
            sys.stdout.flush()
        except Exception:  # noqa: S110
            pass  # Best-effort terminal restoration


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
        exit_template: str = "",
        msg_filter: Callable | None = None,
    ) -> None:
        self._target = target
        self._tick_rate = tick_rate
        self._transient = transient
        self._env = env
        self._flow = flow
        self._template_name = template
        self._exit_template = exit_template
        self._status = AppStatus.IDLE
        self._stop = threading.Event()
        self._msg_filter = msg_filter

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
    def from_dir(
        cls,
        caller_file: str,
        *,
        template: str | Any = "",
        reducer: Callable | None = None,
        initial_state: Any = None,
        flow: Flow | None = None,
        templates_dir: str = "templates",
        **kwargs: Any,
    ) -> App:
        """Create an App that auto-discovers templates relative to *caller_file*.

        Looks for a ``templates/`` directory next to the given file path
        and creates a kida environment with that directory as the loader
        root.  Pass ``__file__`` from the calling module.

        Usage::

            app = App.from_dir(
                __file__,
                template="counter.kida",
                reducer=reducer,
                initial_state=State(),
            )
            app.run()
        """
        from kida import FileSystemLoader

        from milo.templates import get_env

        base = Path(caller_file).resolve().parent
        tpl_path = base / templates_dir
        if not tpl_path.is_dir():
            raise AppError(
                ErrorCode.APP_LIFECYCLE,
                f"Templates directory not found: {tpl_path}",
            )

        if "env" in kwargs:
            raise AppError(
                ErrorCode.APP_LIFECYCLE,
                "App.from_dir derives its own template environment and does not "
                "accept an 'env' argument. Remove the 'env' parameter or construct "
                "the App directly if you need a custom environment.",
            )

        env = get_env(loader=FileSystemLoader(str(tpl_path)))

        if flow is not None:
            return cls(flow=flow, env=env, **kwargs)
        return cls(
            template=template,
            reducer=reducer,
            initial_state=initial_state,
            env=env,
            **kwargs,
        )

    @classmethod
    def from_flow(cls, flow: Flow, **kwargs: Any) -> App:
        """Create App from a declarative Flow."""
        return cls(flow=flow, **kwargs)

    @classmethod
    def render(cls, template: str, state: Any = None, *, env: Any = None) -> str:
        """One-shot render of a template with state. Returns the rendered string."""
        if env is None:
            from milo.templates import get_env

            env = get_env()
        try:
            tmpl = env.get_template(template)
        except Exception as e:
            raise AppError(
                ErrorCode.APP_RENDER,
                f"Template not found: {template!r}",
                suggestion="Ensure the template file exists and the kida environment is configured correctly.",
            ) from e
        return tmpl.render(state=state)

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
            if self._exit_template:
                env = self._get_env()
                try:
                    self._render_exit(store.state, env)
                except Exception as e:
                    msg = format_render_error(e, template_name=self._exit_template, env=env)
                    sys.stderr.write(f"[milo] {msg}\n")
            return store.state

        self._status = AppStatus.RUNNING
        self._stop.clear()

        # Set up cross-platform resize monitoring
        def _on_resize(cols: int, rows: int) -> None:
            store.dispatch(Action("@@RESIZE", payload=(cols, rows)))

        stop_resize = watch_terminal_resize(_on_resize)

        # Set up tick timer
        tick_thread = None
        if self._tick_rate > 0:
            stop_tick = threading.Event()

            def _tick_loop() -> None:
                while not stop_tick.is_set():
                    stop_tick.wait(self._tick_rate)
                    if not stop_tick.is_set() and not self._stop.is_set():
                        store.dispatch(Action("@@TICK"))

            tick_thread = threading.Thread(target=_tick_loop, daemon=True)
            tick_thread.start()

        env = self._get_env()
        renderer = _TerminalRenderer()
        quit_dispatched = False

        try:
            renderer.start()

            # Subscribe to state changes for re-rendering
            def _on_state_change() -> None:
                # Apply ViewState if the reducer set one
                view = store.view_state
                if view is not None:
                    renderer.apply_view_state(view)
                self._render_state(store.state, env, renderer)

            unsubscribe = store.subscribe(_on_state_change)

            # Initial render
            self._render_state(store.state, env, renderer)

            # Input loop
            with KeyReader() as keys:
                for key in keys:
                    if self._stop.is_set() or store.quit_requested:
                        break

                    # Ctrl+C: first dispatches @@QUIT, second force-exits
                    if key.ctrl and key.char == "c":
                        if quit_dispatched:
                            break
                        action = Action("@@QUIT")
                        if self._msg_filter:
                            action = self._msg_filter(store.state, action)
                        if action is None:
                            continue
                        quit_dispatched = True
                        store.dispatch(action)
                        if store.quit_requested:
                            break
                        continue

                    action = Action("@@KEY", payload=key)

                    # Apply message filter
                    if self._msg_filter:
                        action = self._msg_filter(store.state, action)
                        if action is None:
                            continue

                    store.dispatch(action)

                    if store.quit_requested:
                        break

            self._status = AppStatus.STOPPED
            self._stop.set()
            unsubscribe()

        finally:
            # Each cleanup step is individually guarded so a failure in one
            # does not prevent the rest from running.
            if tick_thread is not None:
                with contextlib.suppress(Exception):
                    stop_tick.set()
            with contextlib.suppress(Exception):
                renderer.stop()
            with contextlib.suppress(Exception):
                stop_resize()
            with contextlib.suppress(Exception):
                store.shutdown()

        final_state = store.state

        # Render exit template if provided
        if self._exit_template:
            try:
                self._render_exit(final_state, env)
            except Exception as e:
                msg = format_render_error(e, template_name=self._exit_template, env=env)
                sys.stderr.write(f"[milo] {msg}\n")

        return final_state

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

    def _render_state(self, state: Any, env: Any, renderer: _TerminalRenderer) -> None:
        """Render current state through the template."""
        try:
            template_name = self._get_template_name(state)
            template = env.get_template(template_name)

            # For flow state, pass the current screen's state
            render_state = state
            if isinstance(state, FlowState):
                render_state = state.screen_states.get(state.current_screen, state)

            output = template.render(state=render_state)
            renderer.update(output)
        except Exception as e:
            template_name = self._get_template_name(state)
            msg = format_render_error(e, template_name=template_name, env=env)
            sys.stderr.write(f"[milo] {msg}\n")

    def _render_exit(self, state: Any, env: Any) -> None:
        """Render the exit template once to stdout."""
        try:
            template = env.get_template(self._exit_template)
        except Exception as e:
            raise AppError(
                ErrorCode.APP_RENDER,
                f"Exit template not found: {self._exit_template!r}",
                suggestion="Ensure the exit template file exists and the kida environment is configured correctly.",
            ) from e
        render_state = state
        if isinstance(state, FlowState):
            # For flows, pass all screen states so exit template can reference any data
            render_state = state.screen_states
        output = template.render(state=render_state)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

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
        except Exception as e:
            template_name = self._get_template_name(state)
            msg = format_render_error(e, template_name=template_name)
            sys.stderr.write(f"[milo] {msg}\n")


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
