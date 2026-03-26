"""Pipeline orchestration with observable state through the Store/saga system."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from milo._types import Action, Call, Fork, Put

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Phase:
    """A named pipeline phase."""

    name: str
    handler: Callable[..., Any]
    description: str = ""
    depends_on: tuple[str, ...] = ()
    parallel: bool = False
    weight: int = 1


@dataclass(frozen=True, slots=True)
class PhaseStatus:
    """Runtime status of a single phase."""

    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: float = 0.0
    elapsed: float = 0.0
    error: str = ""


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


# ---------------------------------------------------------------------------
# Pipeline action types
# ---------------------------------------------------------------------------


PIPELINE_START = "@@PIPELINE_START"
PIPELINE_COMPLETE = "@@PIPELINE_COMPLETE"
PHASE_START = "@@PHASE_START"
PHASE_COMPLETE = "@@PHASE_COMPLETE"
PHASE_FAILED = "@@PHASE_FAILED"


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
    """

    def __init__(self, name: str, *phases: Phase) -> None:
        self.name = name
        self.phases = list(phases)

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
                phase_name = action.payload
                now = time.monotonic()
                new_phases = tuple(
                    replace(p, status="running", started_at=now) if p.name == phase_name else p
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
                    if new_phases[-1].status == "completed":
                        completed_weight += weight_map.get(p.name, 1)

                progress = completed_weight / total_weight if total_weight > 0 else 1.0
                return replace(
                    state,
                    phases=tuple(new_phases),
                    progress=progress,
                )

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
        """Generate a saga that executes all phases in dependency order."""
        phases = list(self.phases)
        dep_graph = {p.name: set(p.depends_on) for p in phases}
        phase_map = {p.name: p for p in phases}

        def saga():
            yield Put(Action(PIPELINE_START, time.monotonic()))

            executed: set[str] = set()
            remaining = set(dep_graph.keys())

            while remaining:
                # Find phases whose dependencies are all satisfied
                ready = [name for name in remaining if dep_graph[name].issubset(executed)]

                if not ready:
                    # Circular dependency or impossible state
                    yield Put(
                        Action(
                            PHASE_FAILED,
                            {"name": next(iter(remaining)), "error": "Unresolvable dependencies"},
                        )
                    )
                    return

                # Separate parallel and sequential phases
                parallel_ready = [n for n in ready if phase_map[n].parallel]
                sequential_ready = [n for n in ready if not phase_map[n].parallel]

                # Run parallel phases concurrently via Fork
                if parallel_ready:
                    for name in parallel_ready:
                        yield Fork(_make_phase_saga(name, phase_map[name].handler))
                    # Mark them as executed (Fork runs concurrently)
                    for name in parallel_ready:
                        remaining.discard(name)
                        executed.add(name)

                # Run sequential phases one at a time
                for name in sequential_ready:
                    yield Put(Action(PHASE_START, name))
                    try:
                        result = yield Call(phase_map[name].handler)
                        yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
                    except Exception as e:
                        yield Put(Action(PHASE_FAILED, {"name": name, "error": str(e)}))
                        return
                    remaining.discard(name)
                    executed.add(name)

            yield Put(Action(PIPELINE_COMPLETE))

        return saga

    def execution_order(self) -> list[str]:
        """Return the topological execution order of phases."""
        dep_graph = {p.name: set(p.depends_on) for p in self.phases}
        order: list[str] = []
        remaining = set(dep_graph.keys())

        while remaining:
            ready = [n for n in remaining if dep_graph[n].issubset(set(order))]
            if not ready:
                break
            order.extend(sorted(ready))
            remaining -= set(ready)

        return order


def _make_phase_saga(name: str, handler: Callable) -> Callable:
    """Create a saga for a single phase (used by Fork for parallel phases)."""

    def phase_saga():
        yield Put(Action(PHASE_START, name))
        try:
            result = yield Call(handler)
            yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
        except Exception as e:
            yield Put(Action(PHASE_FAILED, {"name": name, "error": str(e)}))

    return phase_saga
