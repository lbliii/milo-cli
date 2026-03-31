"""Store, dispatch, saga runner, combine_reducers."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from milo._errors import ErrorCode, StateError
from milo._types import (
    Action,
    Call,
    Delay,
    Fork,
    Put,
    Quit,
    ReducerResult,
    Retry,
    Select,
)


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
        self._quit = threading.Event()
        self._exit_code = 0

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
        """Core dispatch: reducer + saga scheduling + recording."""
        quit_signal = False

        with self._lock:
            try:
                result = self._reducer(self._state, action)
            except Exception as e:
                raise StateError(ErrorCode.STA_REDUCER, f"Reducer error: {e}") from e

            sagas = ()

            # Unwrap Quit — may wrap a ReducerResult or plain state
            if isinstance(result, Quit):
                quit_signal = True
                self._exit_code = result.code
                sagas = result.sagas
                result = result.state

            # Unwrap ReducerResult
            if isinstance(result, ReducerResult):
                self._state = result.state
                sagas = sagas + result.sagas
            else:
                self._state = result

            # Record
            if self._recording is not None:
                state_hash = hashlib.sha256(repr(self._state).encode()).hexdigest()[:16]
                self._recording.append(
                    {
                        "timestamp": time.time(),
                        "action_type": action.type,
                        "action_payload": action.payload,
                        "state_hash": state_hash,
                    }
                )

        # Notify listeners
        for listener in self._listeners:
            listener()

        # Schedule sagas outside the lock
        for saga_fn in sagas:
            self.run_saga(saga_fn())

        # Set quit after sagas are scheduled and listeners notified
        if quit_signal:
            self._quit.set()

    def run_saga(self, saga: Any) -> None:
        """Schedule a saga on the thread pool."""
        self._executor.submit(self._run_saga, saga)

    def _run_saga(self, saga: Any) -> None:
        """Step through a generator saga, executing effects."""
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
        except StateError:
            raise
        except Exception as e:
            raise StateError(ErrorCode.STA_SAGA, f"Saga error: {e}") from e

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
        """Shut down the thread pool."""
        self._executor.shutdown(wait=False)


def combine_reducers(**reducers: Callable) -> Callable:
    """Combine multiple reducers into one that manages a dict state.

    Each reducer manages a slice of state under its keyword name.
    Sagas from ReducerResult and Quit are collected and propagated.
    """

    def combined(state: dict | None, action: Action) -> dict | ReducerResult | Quit:
        if state is None:
            state = {}
        next_state = {}
        changed = False
        all_sagas: list[Callable] = []
        quit_signal: Quit | None = None

        for key, reducer in reducers.items():
            prev = state.get(key)
            next_val = reducer(prev, action)
            if isinstance(next_val, Quit):
                quit_signal = next_val
                next_state[key] = next_val.state
                all_sagas.extend(next_val.sagas)
                changed = True
            elif isinstance(next_val, ReducerResult):
                next_state[key] = next_val.state
                all_sagas.extend(next_val.sagas)
                changed = True
            else:
                next_state[key] = next_val
            if next_state[key] is not prev:
                changed = True

        result = next_state if changed else state

        if quit_signal is not None:
            return Quit(state=result, code=quit_signal.code, sagas=tuple(all_sagas))
        if all_sagas:
            return ReducerResult(state=result, sagas=tuple(all_sagas))
        return result

    return combined


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
    last_error: Exception | None = None
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
