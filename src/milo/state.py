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
    ReducerResult,
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
        with self._lock:
            try:
                result = self._reducer(self._state, action)
            except Exception as e:
                raise StateError(ErrorCode.STA_REDUCER, f"Reducer error: {e}") from e

            sagas = ()
            if isinstance(result, ReducerResult):
                self._state = result.state
                sagas = result.sagas
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
    def recording(self) -> list[dict] | None:
        """Get session recording if enabled."""
        return self._recording

    def shutdown(self) -> None:
        """Shut down the thread pool."""
        self._executor.shutdown(wait=False)


def combine_reducers(**reducers: Callable) -> Callable:
    """Combine multiple reducers into one that manages a dict state.

    Each reducer manages a slice of state under its keyword name.
    """

    def combined(state: dict | None, action: Action) -> dict:
        if state is None:
            state = {}
        next_state = {}
        changed = False
        for key, reducer in reducers.items():
            prev = state.get(key)
            next_val = reducer(prev, action)
            if isinstance(next_val, ReducerResult):
                next_state[key] = next_val.state
                changed = True
            else:
                next_state[key] = next_val
            if next_state[key] is not prev:
                changed = True
        return next_state if changed else state

    return combined
