"""Store dispatch benchmarks — throughput, state sizes, recording overhead."""

from __future__ import annotations

from conftest import dict_merge_reducer, noop_reducer, saga_trigger_reducer

from milo._types import Action

# ---------------------------------------------------------------------------
# Baseline: single-threaded dispatch throughput
# ---------------------------------------------------------------------------


def test_bench_dispatch_noop(benchmark, store_factory) -> None:
    """Raw dispatch cost with identity reducer (floor measurement)."""
    store = store_factory(noop_reducer, 0)
    tick = Action("tick")
    benchmark(store.dispatch, tick)


def test_bench_dispatch_dict_merge(benchmark, store_factory) -> None:
    """Dispatch with dict-merge reducer (typical app pattern)."""
    store = store_factory(dict_merge_reducer, {"count": 0})
    action = Action("update", payload={"count": 1})
    benchmark(store.dispatch, action)


def test_bench_dispatch_reducer_result(benchmark, store_factory) -> None:
    """Dispatch with ReducerResult unwrapping (measures unwrap overhead)."""
    store = store_factory(saga_trigger_reducer, {"touched": False})
    action = Action("WITH_RESULT")
    benchmark(store.dispatch, action)


# ---------------------------------------------------------------------------
# State size scaling
# ---------------------------------------------------------------------------


def test_bench_dispatch_by_state_size(benchmark, store_factory, state_size) -> None:
    """Dispatch cost as state dict grows (5, 50, 500 keys)."""
    initial = {f"key_{i}": i for i in range(state_size)}
    store = store_factory(dict_merge_reducer, initial)
    action = Action("update", payload={"key_0": 999})
    benchmark(store.dispatch, action)


# ---------------------------------------------------------------------------
# Recording overhead
# ---------------------------------------------------------------------------


def test_bench_dispatch_with_recording(benchmark, store_factory) -> None:
    """Dispatch with session recording enabled (SHA256 hash per action)."""
    store = store_factory(noop_reducer, 0, record=True)
    tick = Action("tick")
    benchmark(store.dispatch, tick)


def test_bench_dispatch_recording_large_state(benchmark, store_factory) -> None:
    """Recording overhead scales with state size (repr + SHA256)."""
    initial = {f"key_{i}": f"value_{i}" * 10 for i in range(200)}
    store = store_factory(dict_merge_reducer, initial, record=True)
    action = Action("update", payload={"key_0": "changed"})
    benchmark(store.dispatch, action)
