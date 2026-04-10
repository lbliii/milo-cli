"""Store, dispatch, saga runner, combine_reducers."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from milo._errors import ErrorCode, StateError
from milo._types import (
    Action,
    All,
    Batch,
    Call,
    Cmd,
    Debounce,
    Delay,
    Fork,
    Put,
    Quit,
    Race,
    ReducerResult,
    Retry,
    Select,
    Sequence,
    Take,
    TakeEvery,
    TakeLatest,
    TickCmd,
    Timeout,
    TryCall,
    ViewState,
)

_logger = logging.getLogger("milo.state")


# ---------------------------------------------------------------------------
# EffectResult — return type for effect handlers
# ---------------------------------------------------------------------------

_SEND = "send"
_NEXT = "next"
_THROW = "throw"
_CONTINUE = "continue"  # Re-check cancellation at top of loop


class EffectResult:
    """What an effect handler returns to tell the saga runner how to advance the generator."""

    __slots__ = ("action", "error", "value")

    def __init__(self, action: str, value: Any = None, error: Exception | None = None) -> None:
        self.action = action
        self.value = value
        self.error = error

    @classmethod
    def send(cls, value: Any) -> EffectResult:
        """Resume the saga with ``saga.send(value)``."""
        return cls(_SEND, value=value)

    @classmethod
    def next(cls) -> EffectResult:
        """Advance the saga with ``next(saga)``."""
        return cls(_NEXT)

    @classmethod
    def throw(cls, error: Exception) -> EffectResult:
        """Throw an exception into the saga with ``saga.throw(error)``."""
        return cls(_THROW, error=error)

    @classmethod
    def cont(cls) -> EffectResult:
        """Loop back to the cancellation check at the top of the runner."""
        return cls(_CONTINUE)


# ---------------------------------------------------------------------------
# Effect handlers — standalone functions, one per effect type
# ---------------------------------------------------------------------------


def _handle_call(effect: Call, _context: SagaContext, _store: Store) -> EffectResult:
    try:
        result = effect.fn(*effect.args, **effect.kwargs)
    except Exception as e:
        return EffectResult.throw(e)
    return EffectResult.send(result)


def _handle_put(effect: Put, _context: SagaContext, store: Store) -> EffectResult:
    store.dispatch(effect.action)
    return EffectResult.next()


def _handle_select(effect: Select, _context: SagaContext, store: Store) -> EffectResult:
    state = store._state
    if effect.selector:
        state = effect.selector(state)
    return EffectResult.send(state)


def _handle_fork(effect: Fork, context: SagaContext, store: Store) -> EffectResult:
    child_ctx = context.child() if effect.attached else context.detached_child()
    store._tracked_submit(store._run_saga, effect.saga, child_ctx)
    return EffectResult.send(child_ctx.cancel)


def _handle_delay(effect: Delay, context: SagaContext, _store: Store) -> EffectResult:
    context.cancel.wait(timeout=effect.seconds)
    if context.is_cancelled:
        return EffectResult.cont()
    return EffectResult.next()


def _handle_retry(effect: Retry, _context: SagaContext, _store: Store) -> EffectResult:
    result = _execute_retry(
        effect.fn, effect.args, effect.kwargs,
        effect.max_attempts, effect.backoff, effect.base_delay, effect.max_delay,
    )
    return EffectResult.send(result)


def _handle_timeout(effect: Timeout, _context: SagaContext, store: Store) -> EffectResult:
    try:
        result = store._execute_timeout(effect.effect, effect.seconds)
    except TimeoutError as e:
        return EffectResult.throw(e)
    return EffectResult.send(result)


def _handle_trycall(effect: TryCall, _context: SagaContext, _store: Store) -> EffectResult:
    try:
        result = effect.fn(*effect.args, **effect.kwargs)
        return EffectResult.send((result, None))
    except Exception as e:
        return EffectResult.send((None, e))


def _handle_race(effect: Race, context: SagaContext, store: Store) -> EffectResult:
    if not effect.sagas:
        raise StateError(ErrorCode.STA_SAGA, "Race requires at least one saga")
    try:
        result = store._execute_race(effect.sagas, context)
    except Exception as e:
        return EffectResult.throw(e)
    return EffectResult.send(result)


def _handle_all(effect: All, context: SagaContext, store: Store) -> EffectResult:
    if not effect.sagas:
        return EffectResult.send(())
    try:
        results = store._execute_all(effect.sagas, context)
    except Exception as e:
        return EffectResult.throw(e)
    return EffectResult.send(results)


def _handle_take(effect: Take, context: SagaContext, store: Store) -> EffectResult:
    waiter_event = threading.Event()
    result_box: list = []
    with store._lock:
        store._action_waiters.setdefault(effect.action_type, []).append(
            (waiter_event, result_box)
        )
    wait_interval = 0.1
    deadline = None if effect.timeout is None else time.monotonic() + effect.timeout
    while not waiter_event.is_set():
        if context.is_cancelled:
            break
        if deadline is None:
            current_timeout = wait_interval
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            current_timeout = min(wait_interval, remaining)
        waiter_event.wait(timeout=current_timeout)

    if context.is_cancelled:
        _cleanup_take_waiter(store, effect.action_type, waiter_event)
        return EffectResult.cont()

    if result_box:
        return EffectResult.send(result_box[0])

    # Timeout expired
    _cleanup_take_waiter(store, effect.action_type, waiter_event)
    return EffectResult.throw(
        TimeoutError(f"Take('{effect.action_type}') timed out after {effect.timeout}s")
    )


def _handle_debounce(
    effect: Debounce, context: SagaContext, store: Store, pending: list,
) -> EffectResult:
    # Cancel any pending debounce timer from a previous yield
    if pending:
        old_timer, old_ctx = pending[0]
        old_timer.cancel()
        old_ctx.cancel.set()
        pending.clear()
    child_ctx = context.child()

    def _debounce_fire(s=effect.saga, cc=child_ctx, st=store):
        if not cc.is_cancelled:
            st._tracked_submit(st._run_saga, s(), cc)

    timer = threading.Timer(effect.seconds, _debounce_fire)
    timer.daemon = True
    timer.start()
    pending.append((timer, child_ctx))
    return EffectResult.next()


def _handle_take_every(effect: TakeEvery, context: SagaContext, store: Store) -> EffectResult:
    """Block until cancelled, forking a new saga for every matching action."""
    while not context.is_cancelled:
        # Wait for the next matching action
        waiter_event = threading.Event()
        result_box: list = []
        with store._lock:
            store._action_waiters.setdefault(effect.action_type, []).append(
                (waiter_event, result_box)
            )
        # Poll with short intervals for cancellation
        while not waiter_event.is_set():
            if context.is_cancelled:
                _cleanup_take_waiter(store, effect.action_type, waiter_event)
                return EffectResult.cont()
            waiter_event.wait(timeout=0.1)
        if result_box:
            action = result_box[0]
            child_ctx = context.child()
            store._tracked_submit(store._run_saga, effect.saga(action), child_ctx)
    return EffectResult.cont()


def _handle_take_latest(effect: TakeLatest, context: SagaContext, store: Store) -> EffectResult:
    """Block until cancelled, forking a saga for the latest matching action only."""
    prev_ctx: SagaContext | None = None
    while not context.is_cancelled:
        waiter_event = threading.Event()
        result_box: list = []
        with store._lock:
            store._action_waiters.setdefault(effect.action_type, []).append(
                (waiter_event, result_box)
            )
        while not waiter_event.is_set():
            if context.is_cancelled:
                _cleanup_take_waiter(store, effect.action_type, waiter_event)
                if prev_ctx is not None:
                    prev_ctx.cancel_tree()
                return EffectResult.cont()
            waiter_event.wait(timeout=0.1)
        if result_box:
            action = result_box[0]
            # Cancel previous fork before starting new one
            if prev_ctx is not None:
                prev_ctx.cancel_tree()
            child_ctx = context.child()
            prev_ctx = child_ctx
            store._tracked_submit(store._run_saga, effect.saga(action), child_ctx)
    if prev_ctx is not None:
        prev_ctx.cancel_tree()
    return EffectResult.cont()


def _cleanup_take_waiter(
    store: Store, action_type: str, waiter_event: threading.Event,
) -> None:
    """Remove an unconsumed Take waiter from the store."""
    with store._lock:
        entries = store._action_waiters.get(action_type, [])
        for i, (ev, _) in enumerate(entries):
            if ev is waiter_event:
                entries.pop(i)
                break
        if not entries and action_type in store._action_waiters:
            del store._action_waiters[action_type]


# Default handler registry — maps effect type to handler function
_DEFAULT_HANDLERS: dict[type, Callable] = {
    Call: _handle_call,
    Put: _handle_put,
    Select: _handle_select,
    Fork: _handle_fork,
    Delay: _handle_delay,
    Retry: _handle_retry,
    Timeout: _handle_timeout,
    TryCall: _handle_trycall,
    Race: _handle_race,
    All: _handle_all,
    Take: _handle_take,
    TakeEvery: _handle_take_every,
    TakeLatest: _handle_take_latest,
    # Debounce handled specially (needs pending_debounce state)
}


# ---------------------------------------------------------------------------
# SagaContext — runtime identity + cancellation scope for sagas
# ---------------------------------------------------------------------------


class SagaContext:
    """Runtime context for a running saga — threading identity + cancellation scope.

    Provides structured cancellation: when a parent context is cancelled,
    all child contexts are cancelled transitively via :meth:`cancel_tree`.

    This is mutable runtime state (not Store state), so it uses a regular
    class with ``__slots__`` rather than a frozen dataclass.
    """

    __slots__ = ("_lock", "cancel", "children", "parent", "saga_id")

    def __init__(
        self,
        saga_id: str | None = None,
        cancel: threading.Event | None = None,
        parent: SagaContext | None = None,
    ) -> None:
        self.saga_id: str = saga_id or uuid.uuid4().hex[:12]
        self.cancel: threading.Event = cancel or threading.Event()
        self.parent: SagaContext | None = parent
        self.children: list[SagaContext] = []
        self._lock: threading.Lock = threading.Lock()
        if parent is not None:
            parent._add_child(self)

    def _add_child(self, child: SagaContext) -> None:
        with self._lock:
            self.children.append(child)

    def cancel_tree(self) -> None:
        """Cancel this context and all descendants transitively."""
        self.cancel.set()
        with self._lock:
            for child in self.children:
                child.cancel_tree()

    @property
    def is_cancelled(self) -> bool:
        """True if this context's cancel event has been set."""
        return self.cancel.is_set()

    def child(self, saga_id: str | None = None) -> SagaContext:
        """Create a child context that inherits this cancel scope."""
        return SagaContext(saga_id=saga_id, parent=self)

    def detached_child(self, saga_id: str | None = None) -> SagaContext:
        """Create a child with its own independent cancel scope."""
        return SagaContext(saga_id=saga_id)


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
        max_workers: int = 4,
        on_pool_pressure: Callable[[int, int], None] | None = None,
        pool_pressure_threshold: float = 0.8,
    ) -> None:
        self._reducer = reducer
        self._state = initial_state
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._on_pool_pressure = on_pool_pressure
        self._pool_pressure_threshold = pool_pressure_threshold
        self._active_tasks = 0
        self._tasks_lock = threading.Lock()
        self._recording: list[dict] | None = [] if record else None
        self._record_path = record if isinstance(record, (str, Path)) else None
        self._prev_hash: str = "0" * 16  # Merkle chain seed
        self._quit = threading.Event()
        self._exit_code = 0
        self._view_state = None
        # Take effect: waiters keyed by action_type
        # Each entry: list of (Event, result_box_list) tuples
        self._action_waiters: dict[str, list[tuple[threading.Event, list]]] = {}

        # Build middleware chain
        self._dispatch_fn = self._base_dispatch
        for mw in reversed(middleware):
            self._dispatch_fn = mw(self._dispatch_fn, self._get_state)

        # Initialize
        self.dispatch(Action("@@INIT"))

    def _get_state(self) -> Any:
        return self._state

    def _tracked_submit(self, fn, *args):
        """Submit work to the pool, tracking active tasks for pressure detection."""
        with self._tasks_lock:
            self._active_tasks += 1
            active = self._active_tasks
        if (
            self._on_pool_pressure is not None
            and active >= self._max_workers * self._pool_pressure_threshold
        ):
            try:
                self._on_pool_pressure(active, self._max_workers)
            except Exception:
                _logger.debug("on_pool_pressure callback failed", exc_info=True)

        def _wrapper():
            try:
                fn(*args)
            finally:
                with self._tasks_lock:
                    self._active_tasks -= 1

        return self._executor.submit(_wrapper)

    @property
    def state(self) -> Any:
        return self._state

    @property
    def pool_active(self) -> int:
        """Number of currently active tasks in the thread pool."""
        return self._active_tasks

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

            # Notify Take waiters (inside lock to avoid missed actions)
            waiters = self._action_waiters.pop(action.type, None)
            if waiters:
                for event, result_box in waiters:
                    result_box.append(action)
                    event.set()

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

    def run_saga(
        self,
        saga: Any,
        cancel: threading.Event | None = None,
        context: SagaContext | None = None,
    ) -> SagaContext:
        """Schedule a saga on the thread pool.

        Args:
            saga: Generator saga to execute.
            cancel: Optional cancellation event (legacy). Prefer *context*.
            context: Optional :class:`SagaContext` for structured cancellation.
                If neither *cancel* nor *context* is provided, a fresh context
                is created automatically.

        Returns:
            The :class:`SagaContext` assigned to this saga (useful for
            cancellation and debugging).
        """
        if context is None:
            ctx_cancel = cancel or threading.Event()
            context = SagaContext(cancel=ctx_cancel)
        self._tracked_submit(self._run_saga, saga, context)
        return context

    def _run_saga(self, saga: Any, context: SagaContext | None = None) -> None:
        """Step through a generator saga, executing effects via handler registry.

        Catches unhandled exceptions and dispatches @@SAGA_ERROR so the
        reducer can react gracefully.  The error is never swallowed silently.
        """
        if context is None:
            context = SagaContext()
        pending_debounce: list = []  # [(timer, child_ctx)] — at most one entry
        try:
            effect = next(saga)
            while True:
                if context.is_cancelled:
                    try:
                        self.dispatch(
                            Action(
                                "@@SAGA_CANCELLED",
                                payload={"saga_id": context.saga_id},
                            )
                        )
                    except Exception:
                        _logger.debug("Failed to dispatch @@SAGA_CANCELLED", exc_info=True)
                    return

                # Debounce needs per-saga state, so it's dispatched separately
                if isinstance(effect, Debounce):
                    result = _handle_debounce(effect, context, self, pending_debounce)
                else:
                    handler = _DEFAULT_HANDLERS.get(type(effect))
                    if handler is None:
                        raise StateError(
                            ErrorCode.STA_SAGA,
                            f"Unknown effect type: {type(effect).__name__}",
                        )
                    result = handler(effect, context, self)

                match result.action:
                    case "send":
                        effect = saga.send(result.value)
                    case "next":
                        effect = next(saga)
                    case "throw":
                        effect = saga.throw(result.error)
                    case "continue":
                        continue
        except StopIteration:
            pass
        except Exception as e:
            try:
                self.dispatch(
                    Action(
                        "@@SAGA_ERROR",
                        payload={
                            "error": str(e),
                            "type": type(e).__name__,
                            "saga_id": context.saga_id,
                        },
                    )
                )
            except Exception:
                _logger.debug("Failed to dispatch @@SAGA_ERROR", exc_info=True)
        finally:
            if pending_debounce:
                old_timer, old_ctx = pending_debounce[0]
                old_timer.cancel()
                old_ctx.cancel.set()

    def _execute_timeout(self, effect: Call | Retry, seconds: float) -> Any:
        """Execute a blocking effect with a timeout deadline.

        Uses a dedicated thread (not the shared pool) to avoid deadlock
        when the saga itself is already running on the pool.
        """
        result_box: list[Any] = []
        error_box: list[Exception] = []

        def run() -> None:
            try:
                result_box.append(self._execute_effect(effect))
            except Exception as e:
                error_box.append(e)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=seconds)
        if worker.is_alive():
            raise TimeoutError(f"Effect timed out after {seconds}s")
        if error_box:
            raise error_box[0]
        return result_box[0]

    @staticmethod
    def _execute_effect(effect: Call | Retry) -> Any:
        """Execute a single blocking effect and return its result."""
        match effect:
            case Call(fn, args, kwargs):
                return fn(*args, **kwargs)
            case Retry(fn, args, kwargs, max_attempts, backoff, base_delay, max_delay):
                return _execute_retry(
                    fn, args, kwargs, max_attempts, backoff, base_delay, max_delay
                )
            case _:
                raise StateError(
                    ErrorCode.STA_SAGA,
                    f"Cannot execute effect type: {type(effect).__name__}",
                )

    def _run_saga_capturing(
        self,
        saga: Any,
        context: SagaContext,
        result_box: list,
        error_box: list,
        done: threading.Event,
    ) -> None:
        """Step through a saga via ``_run_saga``, capturing the return value.

        Wraps *saga* in a thin ``yield from`` generator so that
        ``_run_saga`` handles **all** effect types (including nested
        Race/All/Take/Debounce).  On success the return value is
        appended to *result_box*; on error the exception goes into
        *error_box*.  *done* is set in all cases.
        """

        def _wrapper():
            try:
                result = yield from saga
                result_box.append(result)
            except Exception as e:
                error_box.append(e)

        self._run_saga(_wrapper(), context)
        done.set()

    def _execute_race(self, child_sagas: tuple, parent_context: SagaContext) -> Any:
        """Run sagas concurrently, return the first result. Cancel losers."""
        condition = threading.Condition()
        child_contexts: list[SagaContext] = []
        child_dones: list[threading.Event] = []
        child_results: list[list] = []
        child_errors: list[list] = []

        for child_saga in child_sagas:
            child_ctx = parent_context.child()
            child_done = threading.Event()
            result_box: list[Any] = []
            error_box: list[Exception] = []
            child_contexts.append(child_ctx)
            child_dones.append(child_done)
            child_results.append(result_box)
            child_errors.append(error_box)

            def _notify_wrapper(
                saga=child_saga,
                ctx=child_ctx,
                rb=result_box,
                eb=error_box,
                done=child_done,
            ):
                self._run_saga_capturing(saga, ctx, rb, eb, done)
                with condition:
                    condition.notify_all()

            self._executor.submit(_notify_wrapper)

        # Wait for first completion or parent cancellation
        with condition:
            while True:
                if parent_context.is_cancelled:
                    for cc in child_contexts:
                        cc.cancel_tree()
                    raise StateError(ErrorCode.STA_SAGA, "Race cancelled")
                for i, done in enumerate(child_dones):
                    if done.is_set():
                        # Cancel all others
                        for cc in child_contexts:
                            cc.cancel_tree()
                        if child_results[i]:
                            return child_results[i][0]
                        if child_errors[i]:
                            raise child_errors[i][0]
                # All done — re-check results (a child may have finished
                # between the per-child is_set() check and here).
                if all(d.is_set() for d in child_dones):
                    for i2 in range(len(child_dones)):
                        if child_results[i2]:
                            for cc in child_contexts:
                                cc.cancel_tree()
                            return child_results[i2][0]
                        if child_errors[i2]:
                            raise child_errors[i2][0]
                    return None
                condition.wait(timeout=0.05)

    def _execute_all(self, child_sagas: tuple, parent_context: SagaContext) -> tuple:
        """Run sagas concurrently, wait for all. Fail-fast on first error."""
        condition = threading.Condition()
        child_contexts: list[SagaContext] = []
        child_dones: list[threading.Event] = []
        child_results: list[list] = []
        child_errors: list[list] = []

        for child_saga in child_sagas:
            child_ctx = parent_context.child()
            child_done = threading.Event()
            result_box: list[Any] = []
            error_box: list[Exception] = []
            child_contexts.append(child_ctx)
            child_dones.append(child_done)
            child_results.append(result_box)
            child_errors.append(error_box)

            def _notify_wrapper(
                saga=child_saga,
                ctx=child_ctx,
                rb=result_box,
                eb=error_box,
                done=child_done,
            ):
                self._run_saga_capturing(saga, ctx, rb, eb, done)
                with condition:
                    condition.notify_all()

            self._executor.submit(_notify_wrapper)

        # Wait for all to complete or first failure
        with condition:
            while True:
                if parent_context.is_cancelled:
                    for cc in child_contexts:
                        cc.cancel_tree()
                    raise StateError(ErrorCode.STA_SAGA, "All cancelled")
                # Check for errors (fail-fast)
                for i, done in enumerate(child_dones):
                    if done.is_set() and child_errors[i]:
                        for cc in child_contexts:
                            cc.cancel_tree()
                        raise child_errors[i][0]
                # Check if all done
                if all(d.is_set() for d in child_dones):
                    return tuple(rb[0] if rb else None for rb in child_results)
                condition.wait(timeout=0.05)

    def _exec_cmd(self, cmd: Any) -> None:
        """Execute a Cmd, Batch, Sequence, or TickCmd."""
        match cmd:
            case Cmd(fn):
                self._tracked_submit(self._run_cmd, fn)
            case Batch(cmds):
                for c in cmds:
                    self._exec_cmd(c)
            case Sequence(cmds):
                self._tracked_submit(self._run_sequence, cmds)
            case TickCmd(interval):
                self._tracked_submit(self._run_tick, interval)

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
                            futures.append(self._tracked_submit(self._run_cmd, c.fn))
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
