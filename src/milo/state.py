"""Store, dispatch, saga runner, combine_reducers."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from milo._errors import ErrorCode, StateError
from milo._types import (
    Action,
    Batch,
    Call,
    Cmd,
    Delay,
    Fork,
    Put,
    Quit,
    ReducerResult,
    Retry,
    Select,
    Sequence,
    TickCmd,
    ViewState,
)

_logger = logging.getLogger("milo.state")


class Store:
    """Centralized state container with saga support.

    Thread-safety: reads are lock-free (frozen state).
    Dispatch serializes through a lock.
    Sagas run on a ThreadPoolExecutor.
    """

    def __init__(
        self,
        reducer: Callable,
        initial_state: Any,
        middleware: tuple[Callable, ...] = (),
        *,
        record: bool | str | Path = False,
    ) -> None:
        self._reducer = reducer
        self._state = initial_state
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._recording: list[dict] | None = [] if record else None
        self._record_path = record if isinstance(record, (str, Path)) else None
        self._prev_hash: str = "0" * 16  # Merkle chain seed
        self._quit = threading.Event()
        self._exit_code = 0
        self._view_state = None

        # Build middleware chain
        self._dispatch_fn = self._base_dispatch
        for mw in reversed(middleware):
            self._dispatch_fn = mw(self._dispatch_fn, self._get_state)

        # Initialize
        self.dispatch(Action("@@INIT"))

    def _get_state(self) -> Any:
        return self._state

    @property
    def state(self) -> Any:
        return self._state

    def dispatch(self, action: Action) -> None:
        """Dispatch action through middleware -> reducer."""
        self._dispatch_fn(action)

    def _base_dispatch(self, action: Action) -> None:
        """Core dispatch: reducer + saga scheduling + cmd execution + recording."""
        quit_signal = False

        with self._lock:
            try:
                result = self._reducer(self._state, action)
            except Exception as e:
                raise StateError(ErrorCode.STA_REDUCER, f"Reducer error: {e}") from e

            sagas = ()
            cmds: tuple = ()
            view = None

            # Unwrap Quit — may wrap a ReducerResult or plain state
            if isinstance(result, Quit):
                quit_signal = True
                self._exit_code = result.code
                sagas = result.sagas
                cmds = result.cmds
                view = result.view
                result = result.state

            # Unwrap ReducerResult
            if isinstance(result, ReducerResult):
                self._state = result.state
                sagas = sagas + result.sagas
                cmds = cmds + result.cmds
                if result.view is not None:
                    view = result.view
            else:
                self._state = result

            # Record (Merkle chain: hash action + previous hash — O(1) per dispatch)
            if self._recording is not None:
                chain_input = f"{self._prev_hash}:{action.type}:{action.payload}"
                state_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]
                self._prev_hash = state_hash
                self._recording.append(
                    {
                        "timestamp": time.time(),
                        "action_type": action.type,
                        "action_payload": action.payload,
                        "state_hash": state_hash,
                    }
                )

        # Store latest view state for renderer to pick up
        if view is not None:
            self._view_state = view

        # Notify listeners
        for listener in self._listeners:
            listener()

        # Schedule sagas outside the lock
        for saga_fn in sagas:
            self.run_saga(saga_fn())

        # Execute commands outside the lock
        for cmd in cmds:
            self._exec_cmd(cmd)

        # Set quit after sagas are scheduled and listeners notified
        if quit_signal:
            self._quit.set()

    @property
    def view_state(self) -> Any:
        """Latest ViewState from a reducer, or None."""
        return self._view_state

    def run_saga(self, saga: Any) -> None:
        """Schedule a saga on the thread pool."""
        self._executor.submit(self._run_saga, saga)

    def _run_saga(self, saga: Any) -> None:
        """Step through a generator saga, executing effects.

        Catches unhandled exceptions and dispatches @@SAGA_ERROR so the
        reducer can react gracefully.  The error is never swallowed silently.
        """
        try:
            effect = next(saga)
            while True:
                match effect:
                    case Call(fn, args, kwargs):
                        result = fn(*args, **kwargs)
                        effect = saga.send(result)
                    case Put(action):
                        self.dispatch(action)
                        effect = next(saga)
                    case Select(selector):
                        state = self._state
                        if selector:
                            state = selector(state)
                        effect = saga.send(state)
                    case Fork(child_saga):
                        self._executor.submit(self._run_saga, child_saga)
                        effect = next(saga)
                    case Delay(seconds):
                        time.sleep(seconds)
                        effect = next(saga)
                    case Retry(fn, r_args, r_kwargs, max_attempts, backoff, base_delay, max_delay):
                        result = _execute_retry(
                            fn, r_args, r_kwargs, max_attempts, backoff, base_delay, max_delay
                        )
                        effect = saga.send(result)
                    case _:
                        raise StateError(
                            ErrorCode.STA_SAGA,
                            f"Unknown effect type: {type(effect).__name__}",
                        )
        except StopIteration:
            pass
        except Exception as e:
            # Dispatch error to the store so reducers can handle it
            try:
                self.dispatch(
                    Action(
                        "@@SAGA_ERROR",
                        payload={"error": str(e), "type": type(e).__name__},
                    )
                )
            except Exception:
                _logger.debug("Failed to dispatch @@SAGA_ERROR", exc_info=True)

    def _exec_cmd(self, cmd: Any) -> None:
        """Execute a Cmd, Batch, Sequence, or TickCmd."""
        match cmd:
            case Cmd(fn):
                self._executor.submit(self._run_cmd, fn)
            case Batch(cmds):
                for c in cmds:
                    self._exec_cmd(c)
            case Sequence(cmds):
                self._executor.submit(self._run_sequence, cmds)
            case TickCmd(interval):
                self._executor.submit(self._run_tick, interval)

    def _run_cmd(self, fn: Any) -> None:
        """Run a single Cmd thunk and dispatch its result."""
        try:
            result = fn()
            if result is not None:
                self.dispatch(result)
        except Exception as e:
            try:
                self.dispatch(
                    Action(
                        "@@CMD_ERROR",
                        payload={"error": str(e), "type": type(e).__name__},
                    )
                )
            except Exception:
                _logger.debug("Failed to dispatch @@CMD_ERROR", exc_info=True)

    def _run_sequence(self, cmds: tuple) -> None:
        """Run commands serially, dispatching each result before the next."""
        for cmd in cmds:
            match cmd:
                case Cmd(fn):
                    self._run_cmd(fn)
                case Batch(batch_cmds):
                    # For nested Batch inside Sequence, run concurrently and wait
                    import concurrent.futures

                    futures = []
                    for c in batch_cmds:
                        if isinstance(c, Cmd):
                            futures.append(self._executor.submit(self._run_cmd, c.fn))
                        else:
                            self._exec_cmd(c)
                    concurrent.futures.wait(futures, timeout=60)
                case Sequence(seq_cmds):
                    self._run_sequence(seq_cmds)
                case TickCmd(interval):
                    self._run_tick(interval)

    def _run_tick(self, interval: float) -> None:
        """Schedule a single @@TICK after *interval* seconds."""
        time.sleep(interval)
        if not self._quit.is_set():
            self.dispatch(Action("@@TICK"))

    def subscribe(self, listener: Callable) -> Callable[[], None]:
        """Register state-change listener. Returns unsubscribe callable."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            self._listeners.remove(listener)

        return unsubscribe

    @property
    def quit_requested(self) -> bool:
        """True if a reducer returned Quit."""
        return self._quit.is_set()

    @property
    def exit_code(self) -> int:
        """Exit code from the Quit signal (default 0)."""
        return self._exit_code

    @property
    def recording(self) -> list[dict] | None:
        """Get session recording if enabled."""
        return self._recording

    def shutdown(self) -> None:
        """Shut down the thread pool, waiting for pending work."""
        self._executor.shutdown(wait=True)


def combine_reducers(**reducers: Callable) -> Callable:
    """Combine multiple reducers into one that manages a dict state.

    Each reducer manages a slice of state under its keyword name.
    Sagas, cmds, and view state from ReducerResult and Quit are collected
    and propagated.
    """

    def combined(state: dict | None, action: Action) -> dict | ReducerResult | Quit:
        if state is None:
            state = {}
        next_state = {}
        changed = False
        all_sagas: list[Callable] = []
        all_cmds: list = []
        last_view = None
        quit_signal: Quit | None = None

        for key, reducer in reducers.items():
            prev = state.get(key)
            next_val = reducer(prev, action)
            if isinstance(next_val, Quit):
                quit_signal = next_val
                next_state[key] = next_val.state
                all_sagas.extend(next_val.sagas)
                all_cmds.extend(next_val.cmds)
                if next_val.view is not None:
                    last_view = _merge_view(last_view, next_val.view)
                changed = True
            elif isinstance(next_val, ReducerResult):
                next_state[key] = next_val.state
                all_sagas.extend(next_val.sagas)
                all_cmds.extend(next_val.cmds)
                if next_val.view is not None:
                    last_view = _merge_view(last_view, next_val.view)
                changed = True
            else:
                next_state[key] = next_val
            if next_state[key] is not prev:
                changed = True

        result = next_state if changed else state

        if quit_signal is not None:
            return Quit(
                state=result,
                code=quit_signal.code,
                sagas=tuple(all_sagas),
                cmds=tuple(all_cmds),
                view=last_view,
            )
        if all_sagas or all_cmds or last_view is not None:
            return ReducerResult(
                state=result,
                sagas=tuple(all_sagas),
                cmds=tuple(all_cmds),
                view=last_view,
            )
        return result

    return combined


def _merge_view(prev: ViewState | None, new: ViewState) -> ViewState:
    """Merge two ViewStates: explicitly-set fields in *new* override *prev*."""
    if prev is None:
        return new
    return ViewState(
        alt_screen=new.alt_screen if new.alt_screen is not None else prev.alt_screen,
        cursor_visible=new.cursor_visible
        if new.cursor_visible is not None
        else prev.cursor_visible,
        window_title=new.window_title if new.window_title is not None else prev.window_title,
        mouse_mode=new.mouse_mode if new.mouse_mode is not None else prev.mouse_mode,
    )


def _execute_retry(
    fn: Any,
    args: tuple,
    kwargs: dict,
    max_attempts: int,
    backoff: str,
    base_delay: float,
    max_delay: float,
) -> Any:
    """Execute a function with retry and backoff."""
    last_error: Exception = RuntimeError("no attempts made")
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                if backoff == "exponential":
                    delay = min(base_delay * (2**attempt), max_delay)
                elif backoff == "linear":
                    delay = min(base_delay * (attempt + 1), max_delay)
                else:  # fixed
                    delay = base_delay
                time.sleep(delay)
    raise last_error  # type: ignore[misc]
