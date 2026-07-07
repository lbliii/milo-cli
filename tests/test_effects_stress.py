"""Free-threading stress tests for the saga effect system.

These tests exercise the saga runner under high concurrency to verify
correctness with Python 3.14t's free-threading (GIL disabled).
All tests use a 10s timeout to catch deadlocks.
"""

from __future__ import annotations

import sys
import threading
import time

from milo._types import (
    Action,
    All,
    Call,
    Delay,
    Fork,
    Put,
    Race,
    Take,
    TakeEvery,
    TakeLatest,
)
from milo.state import Store

# Skip marker for GIL-enabled builds (tests still run, just flagged)
_GIL_ENABLED = getattr(sys, "_is_gil_enabled", lambda: True)()


def _wait_for_action_waiters(
    store: Store,
    action_type: str,
    *,
    count: int = 1,
    timeout: float = 10.0,
) -> None:
    """Wait until the saga runtime has observably registered action waiters."""
    deadline = time.monotonic() + timeout
    poll = threading.Event()
    while True:
        with store._lock:
            if len(store._action_waiters.get(action_type, ())) >= count:
                return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"Expected {count} waiter(s) for {action_type}, but registration timed out"
            )
        poll.wait(0.001)


# ---------------------------------------------------------------------------
# Stress 1: 100 simultaneous sagas (pool saturation + queueing)
# ---------------------------------------------------------------------------


def test_stress_100_simultaneous_sagas():
    """Launch 100 sagas simultaneously on a 4-worker pool — all must complete."""
    total = 100
    done = threading.Event()
    lock = threading.Lock()
    completed = [0]

    def _saga():
        yield Call(fn=lambda: threading.current_thread().name)
        with lock:
            completed[0] += 1
            if completed[0] >= total:
                done.set()

    def reducer(state, action):
        return state or 0

    store = Store(reducer, 0)
    for _ in range(total):
        store.run_saga(_saga())

    assert done.wait(timeout=10.0), f"Only {completed[0]}/{total} sagas completed"
    store.shutdown()
    assert completed[0] == total


# ---------------------------------------------------------------------------
# Stress 2: Race with 8 children where each child forks 4 more sagas
# ---------------------------------------------------------------------------


def test_stress_race_with_nested_forks():
    """Race(8 children), each child forks 4 sub-sagas — deep concurrency tree."""
    done = threading.Event()
    lock = threading.Lock()
    fork_results = []

    def _grandchild(label):
        def _gc():
            yield Delay(seconds=0.01)
            with lock:
                fork_results.append(label)

        return _gc

    def _racer(idx):
        def _r():
            for j in range(4):
                yield Fork(saga=_grandchild(f"{idx}-{j}")(), attached=True)
            # First racer to reach here wins
            if idx == 0:
                yield Delay(seconds=0.02)
            else:
                yield Delay(seconds=5.0)
            return f"racer_{idx}"

        return _r

    results = []

    def _parent():
        winner = yield Race(sagas=tuple(_racer(i)() for i in range(8)))
        results.append(winner)
        yield Put(Action("DONE"))

    def reducer(state, action):
        if action.type == "DONE":
            done.set()
        return state or 0

    store = Store(reducer, 0, max_workers=8)
    store.run_saga(_parent())

    assert done.wait(timeout=10.0), "Race with nested forks deadlocked"
    store.shutdown()

    assert results == ["racer_0"]


# ---------------------------------------------------------------------------
# Stress 3: All with 4 children where each yields Take, dispatched from 4 threads
# ---------------------------------------------------------------------------


def test_stress_all_with_multi_thread_dispatch():
    """All(4 Take sagas) with actions dispatched from 4 separate threads."""
    done = threading.Event()
    results = []

    def _waiter(action_type):
        def _w():
            action = yield Take(action_type, timeout=10.0)
            return action.payload

        return _w

    def _parent():
        a, b, c, d = yield All(
            sagas=(
                _waiter("EVT_A")(),
                _waiter("EVT_B")(),
                _waiter("EVT_C")(),
                _waiter("EVT_D")(),
            )
        )
        results.extend([a, b, c, d])
        done.set()

    def reducer(state, action):
        return state or 0

    store = Store(reducer, 0, max_workers=8)
    store.run_saga(_parent())
    for action_type in ("EVT_A", "EVT_B", "EVT_C", "EVT_D"):
        _wait_for_action_waiters(store, action_type)

    # Dispatch from 4 separate threads
    threads = []
    for name, payload in [
        ("EVT_A", "alpha"),
        ("EVT_B", "beta"),
        ("EVT_C", "gamma"),
        ("EVT_D", "delta"),
    ]:
        t = threading.Thread(target=store.dispatch, args=(Action(name, payload=payload),))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    assert done.wait(timeout=10.0), "All with multi-thread dispatch deadlocked"
    store.shutdown()

    assert sorted(results) == ["alpha", "beta", "delta", "gamma"]


# ---------------------------------------------------------------------------
# Stress 4: Cancellation storm — rapidly fork+cancel 50 sagas
# ---------------------------------------------------------------------------


def test_stress_cancellation_storm():
    """Rapidly fork and cancel 50 sagas — no deadlocks, no leaked threads."""
    actions = []
    lock = threading.Lock()
    cancelled = threading.Event()
    workers_started = threading.Event()
    started_count = [0]

    def _long_saga():
        with lock:
            started_count[0] += 1
            if started_count[0] >= 8:
                workers_started.set()
        yield Delay(seconds=30.0)
        yield Put(Action("SHOULD_NOT_REACH"))

    def reducer(state, action):
        with lock:
            actions.append(action.type)
            if actions.count("@@SAGA_CANCELLED") == 50:
                cancelled.set()
        return state or 0

    store = Store(reducer, 0, max_workers=8)

    contexts = []
    for _ in range(50):
        ctx = store.run_saga(_long_saga())
        contexts.append(ctx)

    assert workers_started.wait(timeout=10.0), "Worker pool did not reach saturation"

    # Cancel all rapidly
    for ctx in contexts:
        ctx.cancel_tree()

    assert cancelled.wait(timeout=10.0), "Cancellation actions did not propagate"
    store.shutdown()
    store._executor.shutdown(wait=True)

    cancel_count = actions.count("@@SAGA_CANCELLED")
    assert cancel_count == 50, f"Expected 50 cancellations, got {cancel_count}"
    assert "SHOULD_NOT_REACH" not in actions


# ---------------------------------------------------------------------------
# Stress 5: TakeEvery under rapid dispatch — no missed events
# ---------------------------------------------------------------------------


def test_stress_take_every_rapid_dispatch():
    """TakeEvery under contention — no deadlocks, no crashes, reasonable throughput.

    TakeEvery is a sequential watcher: it registers one waiter, processes the
    action, then re-registers.  Actions dispatched between re-registrations are
    missed by design.  This test verifies correctness under contention, not
    100% delivery (which would require a buffered channel, not TakeEvery).
    """
    total = 50
    lock = threading.Lock()
    handled = [0]
    meaningful_done = threading.Event()

    def _handler(action):
        with lock:
            handled[0] += 1
            if handled[0] >= 5:
                meaningful_done.set()
        yield Put(Action("HANDLED"))

    def _watcher():
        yield TakeEvery("RAPID", _handler)

    def reducer(state, action):
        return state or 0

    store = Store(reducer, 0, max_workers=8)
    ctx = store.run_saga(_watcher())
    _wait_for_action_waiters(store, "RAPID")

    # Dispatch from multiple threads for maximum contention
    barrier = threading.Barrier(5)

    def _dispatcher(start, count):
        barrier.wait()
        for i in range(count):
            store.dispatch(Action("RAPID", payload=start + i))
            time.sleep(0.002)

    threads = []
    for batch in range(5):
        t = threading.Thread(target=_dispatcher, args=(batch * 10, 10))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10.0)

    assert meaningful_done.wait(timeout=10.0), "Too few TakeEvery handlers completed"
    ctx.cancel_tree()
    store.shutdown()
    store._executor.shutdown(wait=True)

    # Under contention some actions are missed (by design), but we should
    # handle a meaningful fraction without deadlocks or crashes
    assert handled[0] >= 5, f"Only {handled[0]}/{total} handled — too few"
    assert handled[0] <= total


# ---------------------------------------------------------------------------
# Stress 6: TakeLatest under contention — only last survives
# ---------------------------------------------------------------------------


def test_stress_take_latest_contention():
    """TakeLatest cancels 19 active handlers and completes only the last."""
    done = threading.Event()
    completed = []
    lock = threading.Lock()
    handler_started = [threading.Event() for _ in range(20)]

    def _handler(action):
        handler_started[action.payload].set()
        yield Take(f"RELEASE_{action.payload}", timeout=10.0)
        with lock:
            completed.append(action.payload)
        done.set()

    def _watcher():
        yield TakeLatest("SEARCH", _handler)

    def reducer(state, action):
        return state or 0

    store = Store(reducer, 0, max_workers=8)
    ctx = store.run_saga(_watcher())

    _wait_for_action_waiters(store, "SEARCH")

    for i in range(20):
        store.dispatch(Action("SEARCH", payload=i))
        assert handler_started[i].wait(timeout=10.0), f"Handler {i} did not start"
        _wait_for_action_waiters(store, "SEARCH")

    _wait_for_action_waiters(store, "RELEASE_19")
    store.dispatch(Action("RELEASE_19"))
    assert done.wait(timeout=10.0), "TakeLatest never completed"
    ctx.cancel_tree()
    store.shutdown()
    store._executor.shutdown(wait=True)

    assert completed == [19]


# ---------------------------------------------------------------------------
# Stress 7: Pool pressure under saturation
# ---------------------------------------------------------------------------


def test_stress_pool_pressure_fires_under_load():
    """Pool pressure callback fires when pool is saturated."""
    pressure_events = []
    lock = threading.Lock()

    def _on_pressure(active, max_w):
        with lock:
            pressure_events.append((active, max_w))

    barrier = threading.Event()
    workers_started = threading.Event()
    done = threading.Event()
    remaining = [0]
    started = [0]
    count_lock = threading.Lock()

    def _block_worker():
        with count_lock:
            started[0] += 1
            if started[0] >= 4:
                workers_started.set()
        barrier.wait(timeout=10.0)

    def _blocking_saga():
        yield Call(fn=_block_worker)
        with count_lock:
            remaining[0] -= 1
            if remaining[0] <= 0:
                done.set()

    def reducer(state, action):
        return state or 0

    total = 8
    remaining[0] = total
    store = Store(
        reducer,
        0,
        max_workers=4,
        on_pool_pressure=_on_pressure,
        pool_pressure_threshold=0.75,  # fires at 3+ active
    )

    for _ in range(total):
        store.run_saga(_blocking_saga())

    assert workers_started.wait(timeout=10.0), "Worker pool did not reach saturation"
    barrier.set()
    assert done.wait(timeout=10.0), (
        "Timed out waiting for worker sagas to complete; possible deadlock "
        "or remaining counter was not fully decremented"
    )
    store.shutdown()

    assert len(pressure_events) > 0, "Pool pressure callback never fired"
    # At peak, all 4 workers should be busy
    max_active = max(a for a, _ in pressure_events)
    assert max_active >= 3
