"""Pipeline orchestration with observable state through the Store/saga system."""

from __future__ import annotations

import contextvars
import inspect
import io
import sys
import threading as _threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from milo._errors import ErrorCode, PipelineError
from milo._types import Action, All, Call, Delay, Key, Put, Quit, SpecialKey

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


_VALID_ON_FAIL = frozenset({"stop", "skip", "retry"})
_VALID_BACKOFF = frozenset({"fixed", "exponential"})


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

    def __post_init__(self) -> None:
        if self.on_fail not in _VALID_ON_FAIL:
            raise ValueError(
                f"PhasePolicy.on_fail must be one of {sorted(_VALID_ON_FAIL)}, got {self.on_fail!r}"
            )
        if self.retry_backoff not in _VALID_BACKOFF:
            raise ValueError(
                f"PhasePolicy.retry_backoff must be one of {sorted(_VALID_BACKOFF)}, "
                f"got {self.retry_backoff!r}"
            )


@dataclass(frozen=True, slots=True)
class PhaseLog:
    """A single captured output line from a phase handler."""

    line: str
    stream: str = "stdout"  # "stdout" | "stderr"
    timestamp: float = 0.0  # time.monotonic()


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
    max_logs: int = 200


@dataclass(frozen=True, slots=True)
class PhaseStatus:
    """Runtime status of a single phase."""

    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped, retrying
    started_at: float = 0.0
    elapsed: float = 0.0
    error: str = ""
    attempt: int = 1
    logs: tuple[PhaseLog, ...] = ()


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


@dataclass(frozen=True, slots=True)
class PipelineViewState:
    """UI state for the pipeline detail TUI (wraps PipelineState).

    This is a view-layer wrapper — the pipeline reducer remains pure.
    The TUI reducer wraps it and handles @@KEY actions for navigation.
    """

    pipeline: PipelineState
    selected_phase: int = 0
    expanded: bool = False
    log_scroll: int = 0
    auto_follow: bool = True
    log_height: int = 10


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
PHASE_LOG = "@@PHASE_LOG"


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

    def __init__(
        self,
        name: str,
        *phases: Phase,
        capture_output: bool = False,
        fail_fast: bool = False,
    ) -> None:
        self.name = name
        self.phases = list(phases)
        self.capture_output = capture_output
        self.fail_fast = fail_fast
        _validate_dependencies(self.phases)

    def __rshift__(self, phase: Phase) -> Pipeline:
        """Extend the pipeline: ``pipeline >> Phase(...)``."""
        new = Pipeline(
            self.name,
            *self.phases,
            phase,
            capture_output=self.capture_output,
            fail_fast=self.fail_fast,
        )
        return new

    def build_reducer(self) -> Callable:
        """Generate a reducer that handles pipeline state transitions."""
        name = self.name
        phase_names = tuple(p.name for p in self.phases)
        total_weight = sum(p.weight for p in self.phases)
        weight_map = {p.name: p.weight for p in self.phases}
        max_logs_map = {p.name: p.max_logs for p in self.phases}

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

            if action.type == PHASE_LOG:
                payload = action.payload
                phase_name = payload["name"]
                entry = PhaseLog(
                    line=payload["line"],
                    stream=payload.get("stream", "stdout"),
                    timestamp=payload.get("timestamp", 0.0),
                )
                max_logs = max_logs_map.get(phase_name, 200)
                new_phases = tuple(
                    replace(p, logs=(*p.logs, entry)[-max_logs:]) if p.name == phase_name else p
                    for p in state.phases
                )
                return replace(state, phases=new_phases)

            return state

        return reducer

    def build_saga(self) -> Callable:
        """Generate a saga that executes all phases in dependency order.

        Phase handlers that accept a ``context`` parameter receive a dict
        mapping dependency names to their results.

        When ``capture_output=True``, handler stdout/stderr is captured and
        dispatched as ``@@PHASE_LOG`` actions.
        """
        phases = list(self.phases)
        dep_graph = {p.name: set(p.depends_on) for p in phases}
        phase_map = {p.name: p for p in phases}
        capture = self.capture_output
        use_fail_fast = self.fail_fast

        def saga():
            yield Put(Action(PIPELINE_START, time.monotonic()))

            executed: set[str] = set()
            remaining = set(dep_graph.keys())
            results: dict[str, Any] = {}

            while remaining:
                ready = [name for name in remaining if dep_graph[name].issubset(executed)]

                if not ready:
                    # Identify which dependencies are blocking
                    blocked = next(iter(remaining))
                    unmet = dep_graph[blocked] - executed
                    yield Put(
                        Action(
                            PHASE_FAILED,
                            {
                                "name": blocked,
                                "error": (
                                    f"Unresolvable dependencies: phase {blocked!r} "
                                    f"is waiting on {sorted(unmet)} which "
                                    f"{'has' if len(unmet) == 1 else 'have'} "
                                    f"not completed"
                                ),
                            },
                        )
                    )
                    return

                parallel_ready = [n for n in ready if phase_map[n].parallel]
                sequential_ready = [n for n in ready if not phase_map[n].parallel]

                if parallel_ready:
                    parallel_sagas = []
                    for name in parallel_ready:
                        phase = phase_map[name]
                        ctx = _build_context(phase, results)
                        parallel_sagas.append(
                            _make_phase_saga(
                                name,
                                phase.handler,
                                phase.policy,
                                ctx,
                                results,
                                capture,
                                fail_fast=use_fail_fast,
                            )()  # call to produce generator — All expects generators
                        )
                    # Always use All to wait for parallel phases before
                    # marking them as executed (avoids race where downstream
                    # phases start before results are available).
                    yield All(sagas=tuple(parallel_sagas))
                    for name in parallel_ready:
                        remaining.discard(name)
                        executed.add(name)
                    # If fail_fast, stop pipeline when any parallel phase failed
                    if use_fail_fast:
                        failed_phases = [n for n in parallel_ready if n not in results]
                        if failed_phases:
                            return

                for name in sequential_ready:
                    phase = phase_map[name]
                    ctx = _build_context(phase, results)
                    failed = yield from _run_phase_inline(name, phase, ctx, results, capture)
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
# Timeline serialization (for MCP resource)
# ---------------------------------------------------------------------------

# Module-level holder for the most recent PipelineState, written by a Store
# listener and read by the milo://pipeline/timeline MCP resource.
# Uses a plain variable + lock (not ContextVar) for cross-thread visibility.
_active_pipeline_lock = _threading.Lock()
_active_pipeline_state: PipelineState | None = None


def set_active_pipeline(state: PipelineState | None) -> None:
    """Publish a PipelineState for the milo://pipeline/timeline resource.

    Call this from a Store listener to keep the resource up to date::

        store.subscribe(lambda: set_active_pipeline(store.state))
    """
    global _active_pipeline_state
    with _active_pipeline_lock:
        _active_pipeline_state = state


def get_active_pipeline() -> PipelineState | None:
    """Return the most recently published PipelineState, or None."""
    with _active_pipeline_lock:
        return _active_pipeline_state


def pipeline_to_timeline(state: PipelineState) -> dict[str, Any]:
    """Serialize a PipelineState to a timeline dict for MCP.

    Returns structured JSON matching the milo://pipeline/timeline schema::

        {
            "pipeline": "build",
            "status": "completed",
            "elapsed": 2.34,
            "progress": 1.0,
            "phases": [
                {"name": "discover", "status": "completed", "elapsed": 0.52, "attempt": 1, "log_count": 42},
                ...
            ]
        }
    """
    return {
        "pipeline": state.name,
        "status": state.status,
        "elapsed": round(state.elapsed, 3),
        "progress": round(state.progress, 3),
        "phases": [
            {
                "name": p.name,
                "status": p.status,
                "elapsed": round(p.elapsed, 3),
                "attempt": p.attempt,
                "error": p.error or None,
                "log_count": len(p.logs),
            }
            for p in state.phases
        ],
    }


# ---------------------------------------------------------------------------
# Detail TUI reducer
# ---------------------------------------------------------------------------


def make_detail_reducer(
    pipeline_reducer: Callable,
) -> Callable[[PipelineViewState, Action], PipelineViewState | Quit]:
    """Create a wrapping reducer for the interactive pipeline detail view.

    Handles @@KEY actions for cursor navigation, expansion/collapse,
    log scrolling, and auto-follow. Delegates all other actions to
    the inner pipeline reducer.

    Usage::

        reducer = make_detail_reducer(pipeline.build_reducer())
    """

    def detail_reducer(state: PipelineViewState | None, action: Action) -> PipelineViewState | Quit:
        if action.type == "@@INIT":
            inner = pipeline_reducer(None, action)
            return PipelineViewState(pipeline=inner)

        if state is None:
            return PipelineViewState(pipeline=PipelineState())

        num_phases = len(state.pipeline.phases)
        selected = min(state.selected_phase, max(0, num_phases - 1))
        if selected != state.selected_phase:
            state = replace(state, selected_phase=selected)

        if action.type == "@@KEY":
            key: Key = action.payload
            if num_phases == 0:
                # No phases — only quit is meaningful
                if key.char == "q" or key.name == SpecialKey.ESCAPE:
                    return Quit(state=state)
                return state
            if state.expanded:
                # Detail mode — scroll logs, collapse, toggle follow
                phase = state.pipeline.phases[state.selected_phase]
                if key.name == SpecialKey.UP:
                    return replace(
                        state,
                        log_scroll=max(0, state.log_scroll - 1),
                        auto_follow=False,
                    )
                if key.name == SpecialKey.DOWN:
                    max_scroll = max(0, len(phase.logs) - state.log_height)
                    return replace(
                        state,
                        log_scroll=min(max_scroll, state.log_scroll + 1),
                        auto_follow=False,
                    )
                if key.name in (SpecialKey.ENTER, SpecialKey.ESCAPE):
                    return replace(state, expanded=False, log_scroll=0)
                if key.name == SpecialKey.HOME:
                    return replace(state, log_scroll=0, auto_follow=False)
                if key.name == SpecialKey.END:
                    max_scroll = max(0, len(phase.logs) - state.log_height)
                    return replace(state, log_scroll=max_scroll, auto_follow=False)
                if key.char == "f":
                    new_follow = not state.auto_follow
                    if new_follow:
                        max_scroll = max(0, len(phase.logs) - state.log_height)
                        return replace(state, auto_follow=True, log_scroll=max_scroll)
                    return replace(state, auto_follow=False)
                if key.char == " ":
                    return replace(state, expanded=False, log_scroll=0)
            else:
                # Overview mode — move cursor, expand, quit
                if key.name == SpecialKey.UP:
                    return replace(
                        state,
                        selected_phase=max(0, state.selected_phase - 1),
                    )
                if key.name == SpecialKey.DOWN:
                    return replace(
                        state,
                        selected_phase=min(num_phases - 1, state.selected_phase + 1),
                    )
                if key.name == SpecialKey.ENTER or key.char == " ":
                    return replace(state, expanded=True, log_scroll=0, auto_follow=True)
                if key.name == SpecialKey.ESCAPE:
                    return Quit(state=state)

            # q quits from either mode
            if key.char == "q":
                return Quit(state=state)

            return state

        # Delegate all other actions to the inner pipeline reducer
        new_pipeline = pipeline_reducer(state.pipeline, action)
        new_state = replace(state, pipeline=new_pipeline)

        # Auto-follow: scroll to bottom when new logs arrive on selected phase
        if state.auto_follow and action.type == PHASE_LOG:
            payload = action.payload
            if state.selected_phase < len(new_state.pipeline.phases):
                selected = new_state.pipeline.phases[new_state.selected_phase]
                if payload.get("name") == selected.name:
                    max_scroll = max(0, len(selected.logs) - new_state.log_height)
                    new_state = replace(new_state, log_scroll=max_scroll)

        return new_state

    return detail_reducer


# ---------------------------------------------------------------------------
# Dependency validation
# ---------------------------------------------------------------------------


def _validate_dependencies(phases: list[Phase]) -> None:
    """Validate the dependency graph upfront. Raises CycleError if a cycle exists."""
    names = {p.name for p in phases}
    dep_graph = {p.name: set(p.depends_on) for p in phases}

    # Check for references to non-existent phases
    for phase in phases:
        missing = [dep for dep in phase.depends_on if dep not in names]
        if missing:
            raise PipelineError(
                ErrorCode.PIP_DEPENDENCY,
                f"Phase {phase.name!r} depends on {missing} which "
                f"{'does' if len(missing) == 1 else 'do'} not exist. "
                f"Available phases: {sorted(names)}",
            )

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
# Output capture (opt-in via capture_output=True)
# ---------------------------------------------------------------------------

_phase_buffer: contextvars.ContextVar[list[tuple[str, str, float]] | None] = contextvars.ContextVar(
    "_milo_phase_buffer", default=None
)

# Ref-counted proxy management — proxy stays installed while any phase captures.
_proxy_lock = _threading.Lock()
_proxy_refcount = 0
_original_stdout: Any = None
_original_stderr: Any = None


class _CaptureProxy(io.TextIOBase):
    """Proxy that routes writes to a per-phase buffer when capture is active.

    When ``_phase_buffer`` contextvar holds a list, writes are buffered there.
    Otherwise writes pass through to the original stream.  Thread-safe because
    contextvars are per-thread.
    """

    def __init__(self, original: Any, stream_name: str = "stdout") -> None:
        self._original = original
        self._stream_name = stream_name

    def write(self, s: str) -> int:
        buf = _phase_buffer.get(None)
        if buf is not None:
            for line in s.splitlines(keepends=True):
                stripped = line.rstrip("\n")
                if stripped:
                    buf.append((stripped, self._stream_name, time.monotonic()))
        else:
            self._original.write(s)
        return len(s)

    def flush(self) -> None:
        self._original.flush()

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", "utf-8")

    def fileno(self) -> int:
        return self._original.fileno()

    def isatty(self) -> bool:
        return self._original.isatty()

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def _acquire_proxy() -> None:
    """Install capture proxies on sys.stdout/stderr (ref-counted)."""
    global _proxy_refcount, _original_stdout, _original_stderr
    with _proxy_lock:
        _proxy_refcount += 1
        if _proxy_refcount == 1:
            _original_stdout = sys.stdout
            _original_stderr = sys.stderr
            sys.stdout = _CaptureProxy(_original_stdout, "stdout")
            sys.stderr = _CaptureProxy(_original_stderr, "stderr")


def _release_proxy() -> None:
    """Remove capture proxies when last consumer is done (ref-counted)."""
    global _proxy_refcount, _original_stdout, _original_stderr
    with _proxy_lock:
        _proxy_refcount -= 1
        if _proxy_refcount == 0 and _original_stdout is not None:
            sys.stdout = _original_stdout
            sys.stderr = _original_stderr
            _original_stdout = None
            _original_stderr = None


def _call_handler_captured(
    handler: Callable, context: dict[str, Any]
) -> tuple[Any, list[tuple[str, str, float]]]:
    """Call a handler with stdout/stderr capture. Returns (result, log_entries).

    On exception, the captured logs are attached to the exception as
    ``__captured_logs__`` so the caller can flush them before emitting
    PHASE_FAILED / PHASE_RETRY / PHASE_SKIPPED.
    """
    buf: list[tuple[str, str, float]] = []
    token = _phase_buffer.set(buf)
    _acquire_proxy()
    try:
        return _call_handler(handler, context), buf
    except BaseException as exc:
        exc.__captured_logs__ = list(buf)  # type: ignore[attr-defined]
        raise
    finally:
        _phase_buffer.reset(token)
        _release_proxy()


def _flush_logs(name: str, logs: list[tuple[str, str, float]]) -> Any:
    """Yield Put(PHASE_LOG) for each captured line."""
    for line, stream, ts in logs:
        yield Put(
            Action(PHASE_LOG, {"name": name, "line": line, "stream": stream, "timestamp": ts})
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
    missing = [dep for dep in phase.depends_on if dep not in results]
    if missing:
        raise PipelineError(
            ErrorCode.PIP_PHASE,
            f"Phase {phase.name!r} depends on {missing} but "
            f"{'that phase does' if len(missing) == 1 else 'those phases do'} "
            f"not exist in results. Check depends_on for typos.",
        )
    return {dep: results[dep] for dep in phase.depends_on}


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
    capture: bool = False,
) -> Any:
    """Run a sequential phase inline in the main saga. Returns True if pipeline should stop."""
    policy = phase.policy
    max_attempts = policy.max_retries + 1 if policy.on_fail == "retry" else 1

    for attempt in range(1, max_attempts + 1):
        yield Put(Action(PHASE_START, {"name": name, "attempt": attempt}))
        try:
            if capture:
                result, logs = yield Call(lambda: _call_handler_captured(phase.handler, context))
                yield from _flush_logs(name, logs)
            else:
                result = yield Call(lambda: _call_handler(phase.handler, context))
            yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
            results[name] = result
            return False  # success — don't stop
        except Exception as e:
            # Flush any logs captured before the exception
            if capture:
                yield from _flush_logs(name, getattr(e, "__captured_logs__", []))
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
    capture: bool = False,
    *,
    fail_fast: bool = False,
) -> Callable:
    """Create a saga for a single phase (used by All for parallel phases).

    When *fail_fast* is True and the phase fails with ``on_fail="stop"``
    (the default), the saga re-raises after dispatching ``PHASE_FAILED``
    so that ``All`` can cancel sibling sagas.
    """

    def phase_saga():
        max_attempts = policy.max_retries + 1 if policy.on_fail == "retry" else 1

        for attempt in range(1, max_attempts + 1):
            yield Put(Action(PHASE_START, {"name": name, "attempt": attempt}))
            try:
                if capture:
                    result, logs = yield Call(lambda: _call_handler_captured(handler, context))
                    yield from _flush_logs(name, logs)
                else:
                    result = yield Call(lambda: _call_handler(handler, context))
                yield Put(Action(PHASE_COMPLETE, {"name": name, "result": result}))
                results[name] = result
                return
            except Exception as e:
                # Flush any logs captured before the exception
                if capture:
                    yield from _flush_logs(name, getattr(e, "__captured_logs__", []))
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
                    if fail_fast:
                        raise  # propagate so All cancels siblings
                    return

        yield Put(Action(PHASE_FAILED, {"name": name, "error": "retries exhausted"}))
        if fail_fast:
            raise PipelineError(
                ErrorCode.PIP_PHASE,
                f"Phase {name!r} failed after {max_attempts} attempt(s)",
            )

    return phase_saga
