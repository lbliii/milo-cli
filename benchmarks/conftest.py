"""Shared fixtures for milo benchmark suite.

Provides reusable factories for Store, CLI, MCP, template rendering,
and schema generation benchmarks. All fixtures handle cleanup automatically.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from milo._types import Action, ReducerResult
from milo.commands import CLI
from milo.state import Store

# ---------------------------------------------------------------------------
# Reducers for benchmarking
# ---------------------------------------------------------------------------


def noop_reducer(state: Any, action: Action) -> Any:
    """Identity reducer — returns state unchanged."""
    return state


def dict_merge_reducer(state: dict, action: Action) -> dict:
    """Typical reducer — merges action payload into state."""
    if action.type == "@@INIT":
        return state
    if action.payload is not None:
        return {**state, **action.payload}
    return state


def saga_trigger_reducer(state: dict, action: Action) -> dict | ReducerResult:
    """Reducer that returns ReducerResult with saga references.

    Does NOT actually attach real sagas — use with saga fixtures separately.
    Returns ReducerResult to measure unwrapping overhead.
    """
    if action.type == "@@INIT":
        return state
    if action.type == "WITH_RESULT":
        return ReducerResult(state={**state, "touched": True})
    return state


# ---------------------------------------------------------------------------
# Store fixtures
# ---------------------------------------------------------------------------


def _make_state(size: int) -> dict:
    """Generate a dict state with *size* keys."""
    return {f"key_{i}": i for i in range(size)}


@pytest.fixture(params=[5, 50, 500], ids=["state-5", "state-50", "state-500"])
def state_size(request: pytest.FixtureRequest) -> int:
    """Parameterized state size for scaling benchmarks."""
    return request.param


@pytest.fixture
def store_factory() -> Callable[..., Store]:
    """Factory that creates a Store and tracks it for cleanup.

    Usage::

        def test_something(store_factory):
            store = store_factory(my_reducer, {"count": 0})
            ...
    """
    stores: list[Store] = []

    def factory(
        reducer: Callable = noop_reducer,
        initial_state: Any = 0,
        *,
        record: bool = False,
    ) -> Store:
        s = Store(reducer, initial_state, record=record)
        stores.append(s)
        return s

    yield factory

    for s in stores:
        s.shutdown()


# ---------------------------------------------------------------------------
# CLI fixtures
# ---------------------------------------------------------------------------


def _build_cli(num_commands: int = 5, name: str = "bench") -> CLI:
    """Build a CLI with *num_commands* registered commands."""
    cli = CLI(name=name, description=f"Benchmark CLI with {num_commands} commands")

    for i in range(num_commands):

        def _make_handler(idx: int) -> Callable:
            def handler(value: str = "default", count: int = 1) -> dict:
                return {"command": idx, "value": value, "count": count}

            handler.__name__ = f"cmd_{idx}"
            handler.__qualname__ = f"cmd_{idx}"
            handler.__doc__ = f"""Command number {idx}.

            Args:
                value: A string value to process.
                count: Number of times to repeat.
            """
            return handler

        cli.command(f"cmd-{i}", description=f"Benchmark command {i}")(_make_handler(i))

    return cli


@pytest.fixture
def cli_factory() -> Callable[..., CLI]:
    """Factory that creates a CLI with N registered commands.

    Usage::

        def test_something(cli_factory):
            cli = cli_factory(num_commands=20)
    """
    return _build_cli


@pytest.fixture
def cli_small() -> CLI:
    """CLI with 5 commands."""
    return _build_cli(5)


@pytest.fixture
def cli_medium() -> CLI:
    """CLI with 20 commands."""
    return _build_cli(20)


# ---------------------------------------------------------------------------
# MCP fixtures
# ---------------------------------------------------------------------------


def build_jsonrpc_request(method: str, params: dict | None = None, req_id: int = 1) -> str:
    """Build a JSON-RPC request string."""
    request = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        request["params"] = params
    return json.dumps(request)


def parse_jsonrpc_response(line: str) -> dict:
    """Parse a JSON-RPC response string."""
    return json.loads(line)


# ---------------------------------------------------------------------------
# Schema fixtures
# ---------------------------------------------------------------------------


def simple_func(name: str, count: int = 1) -> str:
    """A simple function.

    Args:
        name: The name.
        count: How many times.
    """
    return name * count


def complex_func(
    name: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    mode: str = "fast",
    verbose: bool = False,
    threshold: float = 0.5,
    items: list[int] | None = None,
    config: dict[str, str] | None = None,
    label: str | None = None,
    retry: int = 3,
) -> dict:
    """A complex function with many parameter types.

    Args:
        name: Primary identifier.
        tags: List of string tags.
        metadata: Arbitrary key-value metadata.
        mode: Operation mode.
        verbose: Enable verbose output.
        threshold: Numeric threshold.
        items: List of integer items.
        config: Configuration mapping.
        label: Optional label.
        retry: Number of retries.
    """
    return {"name": name}


@pytest.fixture
def schema_simple() -> Callable:
    """Simple function for schema generation benchmarks."""
    return simple_func


@pytest.fixture
def schema_complex() -> Callable:
    """Complex function for schema generation benchmarks."""
    return complex_func
