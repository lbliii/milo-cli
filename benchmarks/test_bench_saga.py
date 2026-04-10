"""Saga executor benchmarks — latency, pool saturation, blocking impact."""

from __future__ import annotations

import threading

import pytest
from conftest import noop_reducer

from milo._types import Action, Call, Delay, Fork, Put, ReducerResult, Select
from milo.state import Store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _saga_done_reducer(state: dict, action: Action) -> dict | ReducerResult:
    """Reducer that tracks saga completions via a threading.Event."""
    if action.type == "@@INIT":
        return state
    if action.type == "SAGA_DONE":
        event = state.get("_done_event")
        if event is not None:
            event.set()
        return {**state, "saga_completed": state.get("saga_completed", 0) + 1}
    if action.type == "FORK_DONE":
        count = state.get("fork_completed", 0) + 1
        expected = state.get("fork_expected", 0)
        if count >= expected:
            event = state.get("_done_event")
            if event is not None:
                event.set()
        return {**state, "fork_completed": count}
    if action.type == "RUN_SAGA":
        return ReducerResult(state=state, sagas=(state["_saga_fn"],))
    if action.type == "RUN_N_SAGAS":
        saga_fn = state["_saga_fn"]
        n = action.payload.get("n", 1)
        return ReducerResult(state=state, sagas=tuple(saga_fn for _ in range(n)))
    return state


def _wait_for_done(store: Store, timeout: float = 5.0) -> None:
    """Block until the store's _done_event is set."""
    event = store.state.get("_done_event")
    if event is not None:
        event.wait(timeout=timeout)


# ---------------------------------------------------------------------------
# Saga factories
# ---------------------------------------------------------------------------


def _simple_saga():
    """1 Call + 1 Put — minimal saga."""
    result = yield Call(lambda: 42)
    yield Put(Action("SAGA_DONE", payload={"result": result}))


def _chain_saga():
    """5 sequential Call/Put pairs — measures generator stepping overhead."""
    for i in range(5):
        result = yield Call(lambda x=i: x * 2)
        yield Put(Action("step", payload={"i": i, "result": result}))
    yield Put(Action("SAGA_DONE"))


def _select_saga():
    """Select + Call + Put — reads state mid-saga."""
    state = yield Select()
    result = yield Call(lambda s: len(s) if isinstance(s, dict) else 0, (state,))
    yield Put(Action("SAGA_DONE", payload={"keys": result}))


def _fork_child():
    """Child saga dispatched by fork parent."""
    yield Call(lambda: None)
    yield Put(Action("FORK_DONE"))


def _fork_saga():
    """1 parent + 4 children via Fork."""
    for _ in range(4):
        yield Fork(_fork_child())
    yield Put(Action("step", payload={"parent": "done"}))


def _delay_saga(seconds: float):
    """Saga that sleeps — occupies a pool thread."""

    def _make():
        yield Delay(seconds)
        yield Put(Action("SAGA_DONE"))

    return _make


# ---------------------------------------------------------------------------
# 2.1: Saga dispatch latency
# ---------------------------------------------------------------------------


def test_bench_saga_simple(benchmark, store_factory) -> None:
    """End-to-end latency: dispatch → simple saga (1 Call + 1 Put) → SAGA_DONE."""

    def run():
        event = threading.Event()
        store = store_factory(
            _saga_done_reducer,
            {"_done_event": event, "_saga_fn": _simple_saga, "saga_completed": 0},
        )
        store.dispatch(Action("RUN_SAGA"))
        event.wait(timeout=5.0)

    benchmark.pedantic(run, rounds=50, warmup_rounds=5)


def test_bench_saga_chain(benchmark, store_factory) -> None:
    """End-to-end latency: 5-step chain saga (5 Call + 6 Put)."""

    def run():
        event = threading.Event()
        store = store_factory(
            _saga_done_reducer,
            {"_done_event": event, "_saga_fn": _chain_saga, "saga_completed": 0},
        )
        store.dispatch(Action("RUN_SAGA"))
        event.wait(timeout=5.0)

    benchmark.pedantic(run, rounds=50, warmup_rounds=5)


def test_bench_saga_select(benchmark, store_factory) -> None:
    """End-to-end latency: saga that reads state via Select."""

    def run():
        event = threading.Event()
        store = store_factory(
            _saga_done_reducer,
            {
                "_done_event": event,
                "_saga_fn": _select_saga,
                "saga_completed": 0,
                "data_a": 1,
                "data_b": 2,
            },
        )
        store.dispatch(Action("RUN_SAGA"))
        event.wait(timeout=5.0)

    benchmark.pedantic(run, rounds=50, warmup_rounds=5)


def test_bench_saga_fork(benchmark, store_factory) -> None:
    """End-to-end latency: 1 parent saga + 4 forked children."""

    def run():
        event = threading.Event()
        store = store_factory(
            _saga_done_reducer,
            {
                "_done_event": event,
                "_saga_fn": _fork_saga,
                "fork_completed": 0,
                "fork_expected": 4,
            },
        )
        store.dispatch(Action("RUN_SAGA"))
        event.wait(timeout=5.0)

    benchmark.pedantic(run, rounds=50, warmup_rounds=5)


# ---------------------------------------------------------------------------
# 2.2: Pool saturation
# ---------------------------------------------------------------------------


@pytest.fixture(params=[4, 8, 16, 32], ids=["sagas-4", "sagas-8", "sagas-16", "sagas-32"])
def saga_count(request: pytest.FixtureRequest) -> int:
    return request.param


def test_bench_pool_saturation(benchmark, saga_count) -> None:
    """Wall-clock time to complete N concurrent sagas (pool has 4 workers).

    Each saga does a Call(lambda: None) + Put — minimal work, measures
    pure scheduling and pool queueing overhead.
    """
    completed = threading.Event()
    lock = threading.Lock()
    remaining = [saga_count]

    def counting_reducer(state, action):
        if action.type == "@@INIT":
            return state
        if action.type == "SAGA_DONE":
            with lock:
                remaining[0] -= 1
                if remaining[0] <= 0:
                    completed.set()
            return state
        if action.type == "RUN_ALL":
            return ReducerResult(
                state=state,
                sagas=tuple(_simple_saga for _ in range(saga_count)),
            )
        return state

    def run():
        completed.clear()
        remaining[0] = saga_count
        store = Store(counting_reducer, {})
        store.dispatch(Action("RUN_ALL"))
        completed.wait(timeout=10.0)
        store.shutdown()

    benchmark.pedantic(run, rounds=20, warmup_rounds=3)


# ---------------------------------------------------------------------------
# 2.3: Blocking Call impact on concurrent dispatch
# ---------------------------------------------------------------------------


def test_bench_blocking_call_impact(benchmark) -> None:
    """Dispatch latency while a blocking saga occupies pool threads.

    Measures: how much does a 10ms-blocking saga degrade concurrent dispatch?
    Runs 3 blocking sagas (occupying 3 of 4 pool threads), then measures
    dispatch throughput on the remaining capacity.
    """
    blocker_started = threading.Event()
    blockers_done = threading.Event()
    lock = threading.Lock()
    blocker_count = [0]

    def _blocking_saga():
        yield Call(lambda: blocker_started.set())
        yield Delay(0.05)  # 50ms block — holds a pool thread
        with lock:
            blocker_count[0] += 1
            if blocker_count[0] >= 3:
                blockers_done.set()
        yield Put(Action("BLOCKER_DONE"))

    def blocking_reducer(state, action):
        if action.type == "@@INIT":
            return state
        if action.type == "START_BLOCKERS":
            return ReducerResult(
                state=state,
                sagas=(_blocking_saga, _blocking_saga, _blocking_saga),
            )
        return state

    def run():
        blocker_started.clear()
        blockers_done.clear()
        blocker_count[0] = 0

        store = Store(blocking_reducer, {"count": 0})
        # Start 3 blocking sagas (occupy 3 of 4 pool threads)
        store.dispatch(Action("START_BLOCKERS"))
        # Wait for at least one blocker to start
        blocker_started.wait(timeout=5.0)

        # Now measure dispatch throughput with pool mostly occupied
        tick = Action("tick")
        for _ in range(100):
            store.dispatch(tick)

        # Wait for blockers to finish before cleanup
        blockers_done.wait(timeout=5.0)
        store.shutdown()

    benchmark.pedantic(run, rounds=20, warmup_rounds=3)


def test_bench_saga_throughput_no_blocking(benchmark) -> None:
    """Baseline: dispatch throughput with no blocking sagas (for comparison)."""

    def run():
        store = Store(noop_reducer, 0)
        tick = Action("tick")
        for _ in range(100):
            store.dispatch(tick)
        store.shutdown()

    benchmark.pedantic(run, rounds=20, warmup_rounds=3)
