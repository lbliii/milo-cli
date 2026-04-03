"""Micro-benchmarks for hot paths (Store dispatch)."""

from __future__ import annotations

import pytest

from milo._types import Action
from milo.state import Store


def _noop_reducer(state: int, action: Action) -> int:
    if action.type == "@@INIT":
        return state
    return state


@pytest.fixture
def store() -> Store:
    s = Store(_noop_reducer, 0)
    yield s
    s.shutdown()


def test_bench_store_dispatch(benchmark, store: Store) -> None:
    tick = Action("tick")

    def run() -> None:
        store.dispatch(tick)

    benchmark(run)
