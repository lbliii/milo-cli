"""Reducer complexity scaling — measures cost of different reducer patterns."""

from __future__ import annotations

from conftest import dict_merge_reducer, noop_reducer

from milo._types import Action, Batch, Cmd, ReducerResult, Sequence
from milo.state import combine_reducers

# ---------------------------------------------------------------------------
# Reducers of increasing complexity
# ---------------------------------------------------------------------------


def cmd_reducer(state: dict, action: Action) -> dict | ReducerResult:
    """Reducer that returns a Cmd (lightweight one-shot effect)."""
    if action.type == "@@INIT":
        return state
    if action.type == "WITH_CMD":

        def _noop_cmd():
            return None

        return ReducerResult(state={**state, "cmd": True}, cmds=(Cmd(_noop_cmd),))
    return state


def batch_reducer(state: dict, action: Action) -> dict | ReducerResult:
    """Reducer that returns a Batch of 4 Cmds."""
    if action.type == "@@INIT":
        return state
    if action.type == "WITH_BATCH":

        def _noop_cmd():
            return None

        cmds = tuple(Cmd(_noop_cmd) for _ in range(4))
        return ReducerResult(state={**state, "batch": True}, cmds=(Batch(cmds),))
    return state


def sequence_reducer(state: dict, action: Action) -> dict | ReducerResult:
    """Reducer that returns a Sequence of 4 Cmds."""
    if action.type == "@@INIT":
        return state
    if action.type == "WITH_SEQ":

        def _noop_cmd():
            return None

        cmds = tuple(Cmd(_noop_cmd) for _ in range(4))
        return ReducerResult(state={**state, "seq": True}, cmds=(Sequence(cmds),))
    return state


# ---------------------------------------------------------------------------
# Baseline: reducer dispatch cost by complexity tier
# ---------------------------------------------------------------------------


def test_bench_reducer_noop(benchmark, store_factory) -> None:
    """Floor: identity reducer, no state change."""
    store = store_factory(noop_reducer, 0)
    benchmark(store.dispatch, Action("tick"))


def test_bench_reducer_dict_merge(benchmark, store_factory) -> None:
    """Tier 1: dict spread ({**state, ...})."""
    store = store_factory(dict_merge_reducer, {"count": 0})
    benchmark(store.dispatch, Action("update", payload={"count": 1}))


def test_bench_reducer_result_only(benchmark, store_factory) -> None:
    """Tier 2: ReducerResult unwrapping (no actual sagas/cmds)."""

    def reducer(state, action):
        if action.type == "@@INIT":
            return state
        return ReducerResult(state={**state, "x": 1})

    store = store_factory(reducer, {"x": 0})
    benchmark(store.dispatch, Action("go"))


def test_bench_reducer_with_cmd(benchmark, store_factory) -> None:
    """Tier 3: ReducerResult + Cmd scheduling."""
    store = store_factory(cmd_reducer, {"cmd": False})
    benchmark(store.dispatch, Action("WITH_CMD"))


def test_bench_reducer_with_batch(benchmark, store_factory) -> None:
    """Tier 4: ReducerResult + Batch of 4 Cmds."""
    store = store_factory(batch_reducer, {"batch": False})
    benchmark(store.dispatch, Action("WITH_BATCH"))


def test_bench_reducer_with_sequence(benchmark, store_factory) -> None:
    """Tier 5: ReducerResult + Sequence of 4 Cmds."""
    store = store_factory(sequence_reducer, {"seq": False})
    benchmark(store.dispatch, Action("WITH_SEQ"))


# ---------------------------------------------------------------------------
# combine_reducers overhead
# ---------------------------------------------------------------------------


def test_bench_combine_reducers_2_slices(benchmark, store_factory) -> None:
    """Combined reducer with 2 slices."""
    combined = combine_reducers(a=noop_reducer, b=noop_reducer)
    store = store_factory(combined, {"a": 0, "b": 0})
    benchmark(store.dispatch, Action("tick"))


def test_bench_combine_reducers_5_slices(benchmark, store_factory) -> None:
    """Combined reducer with 5 slices."""
    combined = combine_reducers(
        a=noop_reducer, b=noop_reducer, c=noop_reducer, d=noop_reducer, e=noop_reducer
    )
    store = store_factory(combined, {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0})
    benchmark(store.dispatch, Action("tick"))


def test_bench_combine_reducers_10_slices(benchmark, store_factory) -> None:
    """Combined reducer with 10 slices — measures iteration overhead."""
    slices = {f"s{i}": noop_reducer for i in range(10)}
    combined = combine_reducers(**slices)
    initial = {f"s{i}": 0 for i in range(10)}
    store = store_factory(combined, initial)
    benchmark(store.dispatch, Action("tick"))


# ---------------------------------------------------------------------------
# Listener notification overhead
# ---------------------------------------------------------------------------


def test_bench_dispatch_0_listeners(benchmark, store_factory) -> None:
    """Dispatch with no listeners (baseline)."""
    store = store_factory(noop_reducer, 0)
    benchmark(store.dispatch, Action("tick"))


def test_bench_dispatch_4_listeners(benchmark, store_factory) -> None:
    """Dispatch with 4 listeners (typical: renderer + debug + 2 plugins)."""
    store = store_factory(noop_reducer, 0)
    for _ in range(4):
        store.subscribe(lambda: None)
    benchmark(store.dispatch, Action("tick"))


def test_bench_dispatch_16_listeners(benchmark, store_factory) -> None:
    """Dispatch with 16 listeners (stress test for plugin-heavy apps)."""
    store = store_factory(noop_reducer, 0)
    for _ in range(16):
        store.subscribe(lambda: None)
    benchmark(store.dispatch, Action("tick"))
