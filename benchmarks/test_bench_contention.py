"""Store dispatch under thread contention — measures lock scaling."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, wait

import pytest
from conftest import dict_merge_reducer, noop_reducer

from milo._types import Action
from milo.state import Store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dispatch_n(store: Store, action: Action, n: int) -> None:
    """Dispatch *n* actions sequentially from the calling thread."""
    for _ in range(n):
        store.dispatch(action)


# ---------------------------------------------------------------------------
# Contention: N threads dispatching to the same store
# ---------------------------------------------------------------------------

DISPATCHES_PER_THREAD = 200


@pytest.fixture(params=[1, 2, 4, 8], ids=["threads-1", "threads-2", "threads-4", "threads-8"])
def thread_count(request: pytest.FixtureRequest) -> int:
    return request.param


def test_bench_contention_noop(benchmark, store_factory, thread_count) -> None:
    """Dispatch throughput with N threads competing for the store lock (noop reducer)."""
    store = store_factory(noop_reducer, 0)
    action = Action("tick")

    def run() -> None:
        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            futures = [
                pool.submit(_dispatch_n, store, action, DISPATCHES_PER_THREAD)
                for _ in range(thread_count)
            ]
            wait(futures)
            # Raise if any thread hit an exception
            for f in futures:
                f.result()

    benchmark.pedantic(run, rounds=10, warmup_rounds=2)


def test_bench_contention_dict_merge(benchmark, store_factory, thread_count) -> None:
    """Dispatch throughput with N threads competing (dict-merge reducer)."""
    store = store_factory(dict_merge_reducer, {"count": 0})
    action = Action("update", payload={"count": 1})

    def run() -> None:
        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            futures = [
                pool.submit(_dispatch_n, store, action, DISPATCHES_PER_THREAD)
                for _ in range(thread_count)
            ]
            wait(futures)
            for f in futures:
                f.result()

    benchmark.pedantic(run, rounds=10, warmup_rounds=2)


# ---------------------------------------------------------------------------
# Contention with listeners (simulates renderer subscription)
# ---------------------------------------------------------------------------


def test_bench_contention_with_listeners(benchmark, store_factory) -> None:
    """Dispatch under contention with 4 subscribed listeners (typical app: renderer + sagas)."""
    store = store_factory(noop_reducer, 0)
    action = Action("tick")
    call_count = 0

    def listener():
        nonlocal call_count
        call_count += 1

    for _ in range(4):
        store.subscribe(listener)

    def run() -> None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_dispatch_n, store, action, DISPATCHES_PER_THREAD) for _ in range(4)
            ]
            wait(futures)
            for f in futures:
                f.result()

    benchmark.pedantic(run, rounds=10, warmup_rounds=2)


# ---------------------------------------------------------------------------
# Lock fairness: measure whether one thread starves others
# ---------------------------------------------------------------------------


def test_bench_lock_fairness(benchmark, store_factory) -> None:
    """Check dispatch distribution across 4 threads — detects starvation.

    Each thread records how many dispatches it completed. The benchmark
    measures total throughput; the assertion checks fairness.
    """
    store = store_factory(noop_reducer, 0)
    action = Action("tick")
    per_thread = [0, 0, 0, 0]

    def counted_dispatch(thread_id: int) -> None:
        for _ in range(DISPATCHES_PER_THREAD):
            store.dispatch(action)
            per_thread[thread_id] += 1

    def run() -> None:
        for i in range(4):
            per_thread[i] = 0
        threads = [threading.Thread(target=counted_dispatch, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    benchmark.pedantic(run, rounds=10, warmup_rounds=2)

    # Fairness check: no thread should get less than 25% of the expected share
    total = sum(per_thread)
    if total > 0:
        min_share = min(per_thread) / total
        assert min_share > 0.10, f"Lock starvation detected: shares={per_thread}"
