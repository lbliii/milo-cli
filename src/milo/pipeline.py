"""Pipeline orchestration with observable state through the Store/saga system."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from milo._errors import ErrorCode, PipelineError
from milo._types import Action, Call, Delay, Fork, Put

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhasePolicy:
    """Failure policy for a pipeline phase.

    Controls what happens when a phase's handler raises an exception.
    Default behavior (``on_fail="stop"``) matches the original fail-fast semantics.
    """

    on_fail: str = "stop"  # "stop" | "skip" | "retry"
    max_retries: int = 0
    retry_delay: float = 1.0
    retry_backoff: str = "fixed"  # "fixed" | "exponential"


@dataclass(frozen=True, slots=True)
class Phase:
    """A named pipeline phase."""

    name: str
    handler: Callable[..., Any]
    description: str = ""
    depends_on: tuple[str, ...] = ()
    parallel: bool = False
    weight: int = 1
    policy: PhasePolicy = PhasePolicy()


@dataclass(frozen=True, slots=True)
class PhaseStatus:
    """Runtime status of a single phase."""

    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped, retrying
    started_at: float = 0.0
    elapsed: float = 0.0
    error: str = ""
    attempt: int = 1


@dataclass(frozen=True, slots=True)
class PipelineState:
    """Observable state for a running pipeline."""

    name: str = ""
    phases: tuple[PhaseStatus, ...] = ()
    current_phase: str = ""
    started_at: float = 0.0
    elapsed: float = 0.0
    progress: float = 0.0
    status: str = "pending"  # pending, running, completed, failed


class CycleError(PipelineError):
    """Raised when a pipeline dependency graph contains a cycle."""


# ---------------------------------------------------------------------------
# Pipeline action types
# ---------------------------------------------------------------------------


PIPELINE_START = "@@PIPELINE_START"
PIPELINE_COMPLETE = "@@PIPELINE_COMPLETE"
PHASE_START = "@@PHASE_START"
PHASE_COMPLETE = "@@PHASE_COMPLETE"
PHASE_FAILED = "@@PHASE_FAILED"
PHASE_SKIPPED = "@@PHASE_SKIPPED"
PHASE_RETRY = "@@PHASE_RETRY"


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class Pipeline:
    """Declarative build pipeline that executes through the Store.

    Usage::

        pipeline = Pipeline(
            "build",
            Phase("discover", handler=discover),
            Phase("parse", handler=parse, depends_on=("discover",)),
            Phase("render", handler=render, depends_on=("parse",), parallel=True),
            Phase("assets", handler=assets, depends_on=("parse",), parallel=True),
            Phase("write", handler=write, depends_on=("render", "assets")),
        )

        # Extend with >>
        pipeline = pipeline >> Phase("health", handler=check)

    The pipeline generates a saga and reducer that work with the Store
    for observable, testable execution.

    Raises :class:`CycleError` at construction if the dependency graph
    contains a cycle.
    """

    def __init__(self, name: str, *phases: Phase) -> None:
        self.name = name
        self.phases = list(phases)
        _validate_dependencies(self.phases)

    def __rshift__(self, phase: Phase) -> Pipeline:
        """Extend the pipeline: ``pipeline >> Phase(...)``."""
        new = Pipeline(self.name, *self.phases, phase)
        return new

    def build_reducer(self) -> Callable:
        """Generate a reducer that handles pipeline state transitions."""
        name = self.name
        phase_names = tuple(p.name for p in self.phases)
        total_weight = sum(p.weight for p in self.phases)
        weight_map = {p.name: p.weight for p in self.phases}

        def reducer(state: PipelineState | None, action: Action) -> PipelineState:
            if action.type == "@@INIT":
                return PipelineState(
                    name=name,
                    phases=tuple(PhaseStatus(name=n) for n in phase_names),
                    status="pending",
                )

            if state is None:
                return PipelineState(name=name)

            if action.type == PIPELINE_START:
                return replace(
                    state,
                    status="running",
                    started_at=action.payload or time.monotonic(),
                )

            if action.type == PHASE_START:
                payload = action.payload
                phase_name = payload["name"] if isinstance(payload, dict) else payload
                attempt = payload.get("attempt", 1) if isinstance(payload, dict) else 1
                now = time.monotonic()
                new_phases = tuple(
                    replace(p, status="running", started_at=now, attempt=attempt)
                    if p.name == phase_name
                    else p
                    for p in state.phases
                )
                return replace(state, phases=new_phases, current_phase=phase_name)

            if action.type == PHASE_COMPLETE:
                phase_name = (
                    action.payload.get("name", "")
                    if isinstance(action.payload, dict)
                    else action.payload
                )
                now = time.monotonic()
                new_phases = []
                completed_weight = 0
                for p in state.phases:
                    if p.name == phase_name:
                        new_phases.append(
                            replace(p, status="completed", elapsed=now - p.started_at)
                        )
                    else:
                        new_phases.append(p)
                    if new_phases[-1].status in ("completed", "skipped"):
                        completed_weight += weight_map.get(p.name, 1)

                progress = completed_weight / total_weight if total_weight > 0 else 1.0
                return replace(
                    state,
                    phases=tuple(new_phases),
                    progress=progress,
                )

            if action.type == PHASE_SKIPPED:
                payload = (
                    action.payload if isinstance(action.payload, dict) else {"name": action.payload}
                )
                phase_name = payload.get("name", "")
                error = payload.get("error", "")
                now = time.monotonic()
                new_phases = []
                completed_weight = 0
                for p in state.phases:
                    if p.name == phase_name:
                        new_phases.append(
                            replace(
                                p,
                                status="skipped",
                                error=error,
                                elapsed=now - p.started_at if p.started_at else 0.0,
                            )
                        )
                    else:
                        new_phases.append(p)
                    if new_phases[-1].status in ("completed", "skipped"):
                        completed_weight += weight_map.get(p.name, 1)

                progress = completed_weight / total_weight if total_weight > 0 else 1.0
                return replace(state, phases=tuple(new_phases), progress=progress)

            if action.type == PHASE_RETRY:
                payload = action.payload if isinstance(action.payload, dict) else {}
                phase_name = payload.get("name", "")
                error = payload.get("error", "")
                attempt = payload.get("attempt", 1)
                new_phases = tuple(
                    replace(p, status="retrying", error=error, attempt=attempt)
                    if p.name == phase_name
                    else p
                    for p in state.phases
                )
                return replace(state, phases=new_phases)

            if action.type == PHASE_FAILED:
                payload = (
                    action.payload if isinstance(action.payload, dict) else {"name": action.payload}
                )
                phase_name = payload.get("name", "")
                error = payload.get("error", "")
                now = time.monotonic()
                new_phases = tuple(
                    replace(p, status="failed", error=error, elapsed=now - p.started_at)
                    if p.name == phase_name
                    else p
                    for p in state.phases
                )
                return replace(
                    state,
                    phases=new_phases,
                    status="failed",
                    current_phase=phase_name,
                )

            if action.type == PIPELINE_COMPLETE:
                now = time.monotonic()
                return replace(
                    state,
                    status="completed",
                    progress=1.0,
                    elapsed=now - state.started_at if state.started_at else 0.0,
                    current_phase="",
                )

            return state

        return reducer

    def build_saga(self) -> Callable:
        """Generate a saga that executes all phases in dependency order.

        Phase handlers that accept a ``context`` parameter receive a dict
        mapping dependency names to their results.
        """
        phases = list(self.phases)
        dep_graph = {p.name: set(p.depends_on) for p in phases}
        phase_map = {p.name: p for p in phases}

        def saga():
            yield Put(Action(PIPELINE_START, time.monotonic()))

            executed: set[str] = set()
            remaining = set(dep_graph.keys())
            results: dict[str, Any] = {}

            while remaining:
                ready = [name for name in remaining if dep_graph[name].issubset(executed)]

                if not ready:
                    yield Put(
                        Action(
                            PHASE_FAILED,
                            {"name": next(iter(remaining)), "error": "Unresolvable dependencies"},
                        )
                    )
                    return

                parallel_ready = [n for n in ready if phase_map[n].parallel]
                sequential_ready = [n for n in ready if not phase_map[n].parallel]

                if parallel_ready:
                    for name in parallel_ready:
                        phase = phase_map[name]
                        ctx = _build_context(phase, results)
                        yield Fork(
                            _make_phase_saga(name, phase.handler, phase.policy, ctx, results)
                        )
                    for name in parallel_ready:
                        remaining.discard(name)
                        executed.add(name)

                for name in sequential_ready:
                    phase = phase_map[name]
                    ctx = _build_context(phase, results)
                    failed = yield from _run_phase_inline(name, phase, ctx, results)
                    if failed:
                        return
                    remaining.discard(name)
                    executed.add(name)

            yield Put(Action(PIPELINE_COMPLETE))

        return saga

    def execution_order(self) -> list[str]:
        """Return the topological execution order of phases."""
        dep_graph = {p.name: set(p.depends_on) for p in self.phases}
        order: list[str] = []
        seen: set[str] = set()
        remaining = set(dep_graph.keys())

        while remaining:
            ready = [n for n in remaining if dep_graph[n].issubset(seen)]
            if not ready:
                break
            order.extend(sorted(ready))
            seen.update(ready)
            remaining.difference_update(ready)

        return order


# ---------------------------------------------------------------------------
# Dependency validation
# ---------------------------------------------------------------------------


def _validate_dependencies(phases: list[Phase]) -> None:
    """Validate the dependency graph upfront. Raises CycleError if a cycle exists."""
    names = {p.name for p in phases}
    dep_graph = {p.name: set(p.depends_on) for p in phases}

    # DFS-based cycle detection
    _white, _gray, _black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(names, _white)
    parent: dict[str, str | None] = dict.fromkeys(names, None)

    def dfs(node: str) -> list[str] | None:
        color[node] = _gray
        for dep in dep_graph.get(node, ()):
            if dep not in names:
                continue  # dependency on non-existent phase — ignored at validation
            if color[dep] == _gray:
                # Back edge found — reconstruct cycle path
                cycle = [dep, node]
                cur = node
                while cur != dep:
                    cur = parent[cur]  # type: ignore[assignment]
                    if cur is None or cur == dep:
                        break
                    cycle.append(cur)
                cycle.append(dep)
                cycle.reverse()
                return cycle
            if color[dep] == _white:
                parent[dep] = node
                result = dfs(dep)
                if result is not None:
                    return result
        color[node] = _black
        return None

    for name in names:
        if color[name] == _white:
            cycle = dfs(name)
            if cycle is not None:
                path_str = " \u2192 ".join(cycle)
                raise CycleError(
                    ErrorCode.PIP_DEPENDENCY,
                    f"Circular dependency: {path_str}",
                )


# ---------------------------------------------------------------------------
# Phase execution helpers
# ---------------------------------------------------------------------------


def _handler_wants_context(handler: Callable) -> bool:
    """Return True if the handler has a ``context`` parameter."""
    try:
        sig = inspect.signature(handler)
        return "context" in sig.parameters
    except ValueError, TypeError:
        return False


def _build_context(phase: Phase, results: dict[str, Any]) -> dict[str, Any]:
    """Build the context dict for a phase from its dependency results."""
    return {dep: results.get(dep) for dep in phase.depends_on}


def _call_handler(handler: Callable, context: dict[str, Any]) -> Any:
    """Call a handler, passing context if it accepts one."""
    if _handler_wants_context(handler):
        return handler(context=context)
    return handler()


def _retry_delay_for(policy: PhasePolicy, attempt: int) -> float:
    """Calculate retry delay for the given attempt number."""
    if policy.retry_backoff == "exponential":
        return min(policy.retry_delay * (2 ** (attempt - 1)), 30.0)
    return policy.retry_delay


def _run_phase_inline(
    name: str,
    phase: Phase,
    context: dict[str, Any],
    results: dict[str, Any],
) -> Any:
    """Run a sequential phase inline in the main saga. Returns True if pipeline should stop."""
    policy = phase.policy
    max_attempts = policy.max_retries + 1 if policy.on_fail == "retry" else 1

    for attempt in range(1, max_attempts + 1):
        yield Put(Action(PHASE_START, {"name": name, "attempt": attempt}))
        try:
            result = yield Call(lambda: _call_handler(phase.handler, context))
            yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
            results[name] = result
            return False  # success — don't stop
        except Exception as e:
            if policy.on_fail == "retry" and attempt < max_attempts:
                yield Put(
                    Action(
                        PHASE_RETRY,
                        {
                            "name": name,
                            "attempt": attempt,
                            "error": str(e),
                            "max_retries": policy.max_retries,
                        },
                    )
                )
                yield Delay(_retry_delay_for(policy, attempt))
            elif policy.on_fail == "skip":
                yield Put(Action(PHASE_SKIPPED, {"name": name, "error": str(e)}))
                results[name] = None
                return False  # skipped — don't stop
            else:
                yield Put(Action(PHASE_FAILED, {"name": name, "error": str(e)}))
                return True  # stop pipeline

    # Retries exhausted
    yield Put(Action(PHASE_FAILED, {"name": name, "error": "retries exhausted"}))
    return True


def _make_phase_saga(
    name: str,
    handler: Callable,
    policy: PhasePolicy,
    context: dict[str, Any],
    results: dict[str, Any],
) -> Callable:
    """Create a saga for a single phase (used by Fork for parallel phases)."""

    def phase_saga():
        max_attempts = policy.max_retries + 1 if policy.on_fail == "retry" else 1

        for attempt in range(1, max_attempts + 1):
            yield Put(Action(PHASE_START, {"name": name, "attempt": attempt}))
            try:
                result = yield Call(lambda: _call_handler(handler, context))
                yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
                results[name] = result
                return
            except Exception as e:
                if policy.on_fail == "retry" and attempt < max_attempts:
                    yield Put(
                        Action(
                            PHASE_RETRY,
                            {
                                "name": name,
                                "attempt": attempt,
                                "error": str(e),
                                "max_retries": policy.max_retries,
                            },
                        )
                    )
                    yield Delay(_retry_delay_for(policy, attempt))
                elif policy.on_fail == "skip":
                    yield Put(Action(PHASE_SKIPPED, {"name": name, "error": str(e)}))
                    results[name] = None
                    return
                else:
                    yield Put(Action(PHASE_FAILED, {"name": name, "error": str(e)}))
                    return

        yield Put(Action(PHASE_FAILED, {"name": name, "error": "retries exhausted"}))

    return phase_saga
