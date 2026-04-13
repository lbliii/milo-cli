"""Tests for pipeline orchestration."""

from __future__ import annotations

from dataclasses import replace

import pytest

from milo._types import Action, Call, Key, Put, Quit, SpecialKey
from milo.pipeline import (
    PHASE_COMPLETE,
    PHASE_FAILED,
    PHASE_LOG,
    PHASE_RETRY,
    PHASE_SKIPPED,
    PHASE_START,
    PIPELINE_COMPLETE,
    PIPELINE_START,
    CycleError,
    Phase,
    PhaseLog,
    PhasePolicy,
    PhaseStatus,
    Pipeline,
    PipelineState,
    PipelineViewState,
    get_active_pipeline,
    make_detail_reducer,
    pipeline_to_timeline,
    set_active_pipeline,
)

# ---------------------------------------------------------------------------
# Phase and Pipeline creation
# ---------------------------------------------------------------------------


class TestPipelineCreation:
    def test_phase_basic(self):
        p = Phase("discover", handler=lambda: None, description="Find content")
        assert p.name == "discover"
        assert p.weight == 1

    def test_phase_with_depends(self):
        p = Phase("render", handler=lambda: None, depends_on=("parse",))
        assert p.depends_on == ("parse",)

    def test_pipeline_creation(self):
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None),
        )
        assert pipeline.name == "build"
        assert len(pipeline.phases) == 2

    def test_pipeline_rshift(self):
        p1 = Pipeline("build", Phase("a", handler=lambda: None))
        p2 = p1 >> Phase("b", handler=lambda: None)
        assert len(p2.phases) == 2
        assert p2.phases[1].name == "b"
        # Original unchanged
        assert len(p1.phases) == 1

    def test_phase_policy_validates_on_fail(self):
        with pytest.raises(ValueError, match="on_fail must be one of"):
            PhasePolicy(on_fail="stpo")

    def test_phase_policy_validates_retry_backoff(self):
        with pytest.raises(ValueError, match="retry_backoff must be one of"):
            PhasePolicy(retry_backoff="linear")

    def test_phase_policy_valid_values(self):
        for on_fail in ("stop", "skip", "retry"):
            for backoff in ("fixed", "exponential"):
                p = PhasePolicy(on_fail=on_fail, retry_backoff=backoff)
                assert p.on_fail == on_fail
                assert p.retry_backoff == backoff

    def test_pipeline_rejects_nonexistent_dependency(self):
        from milo._errors import PipelineError

        with pytest.raises(PipelineError, match="does not exist"):
            Pipeline(
                "p",
                Phase("a", handler=lambda: None),
                Phase("b", handler=lambda: None, depends_on=("typo",)),
            )

    def test_pipeline_nonexistent_dep_lists_available(self):
        from milo._errors import PipelineError

        with pytest.raises(PipelineError, match="Available phases"):
            Pipeline(
                "p",
                Phase("a", handler=lambda: None),
                Phase("b", handler=lambda: None, depends_on=("missing",)),
            )


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class TestPipelineReducer:
    def _make_pipeline(self):
        return Pipeline(
            "build",
            Phase("discover", handler=lambda: "found"),
            Phase("parse", handler=lambda: "parsed", depends_on=("discover",)),
            Phase("render", handler=lambda: "rendered", depends_on=("parse",)),
        )

    def test_init(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        assert isinstance(state, PipelineState)
        assert state.name == "build"
        assert state.status == "pending"
        assert len(state.phases) == 3
        assert all(p.status == "pending" for p in state.phases)

    def test_pipeline_start(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START, 100.0))
        assert state.status == "running"
        assert state.started_at == 100.0

    def test_phase_start(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, "discover"))
        assert state.current_phase == "discover"
        discover = next(p for p in state.phases if p.name == "discover")
        assert discover.status == "running"

    def test_phase_complete(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, "discover"))
        state = reducer(state, Action(PHASE_COMPLETE, {"name": "discover"}))
        discover = next(p for p in state.phases if p.name == "discover")
        assert discover.status == "completed"
        # 1 of 3 phases done, equal weight
        assert abs(state.progress - 1 / 3) < 0.01

    def test_phase_failed(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, "discover"))
        state = reducer(state, Action(PHASE_FAILED, {"name": "discover", "error": "boom"}))
        discover = next(p for p in state.phases if p.name == "discover")
        assert discover.status == "failed"
        assert discover.error == "boom"
        assert state.status == "failed"

    def test_pipeline_complete(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START, 100.0))
        for name in ["discover", "parse", "render"]:
            state = reducer(state, Action(PHASE_START, name))
            state = reducer(state, Action(PHASE_COMPLETE, {"name": name}))
        state = reducer(state, Action(PIPELINE_COMPLETE))
        assert state.status == "completed"
        assert state.progress == 1.0

    def test_unrelated_action_passthrough(self):
        pipeline = self._make_pipeline()
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state2 = reducer(state, Action("CUSTOM_ACTION"))
        assert state2 is state


# ---------------------------------------------------------------------------
# Saga
# ---------------------------------------------------------------------------


class TestPipelineSaga:
    def test_saga_generation(self):
        """Saga yields correct sequence of effects."""
        results = {"discover": "found", "parse": "parsed", "render": "rendered"}

        pipeline = Pipeline(
            "build",
            Phase("discover", handler=lambda: results["discover"]),
            Phase("parse", handler=lambda: results["parse"], depends_on=("discover",)),
            Phase("render", handler=lambda: results["render"], depends_on=("parse",)),
        )

        saga = pipeline.build_saga()
        gen = saga()

        # PIPELINE_START
        effect = next(gen)
        assert isinstance(effect, Put)
        assert effect.action.type == PIPELINE_START

        # Phase: discover
        effect = gen.send(None)  # PHASE_START discover
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_START
        assert effect.action.payload["name"] == "discover"

        effect = gen.send(None)  # Call discover handler
        assert isinstance(effect, Call)

        effect = gen.send("found")  # PHASE_COMPLETE discover
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_COMPLETE

        # Phase: parse
        effect = gen.send(None)  # PHASE_START parse
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_START
        assert effect.action.payload["name"] == "parse"

        effect = gen.send(None)  # Call parse handler
        assert isinstance(effect, Call)

        effect = gen.send("parsed")  # PHASE_COMPLETE parse
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_COMPLETE

        # Phase: render
        effect = gen.send(None)  # PHASE_START render
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_START
        assert effect.action.payload["name"] == "render"

        effect = gen.send(None)  # Call render handler
        assert isinstance(effect, Call)

        effect = gen.send("rendered")  # PHASE_COMPLETE render
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_COMPLETE

        # PIPELINE_COMPLETE
        effect = gen.send(None)
        assert isinstance(effect, Put)
        assert effect.action.type == PIPELINE_COMPLETE

    def test_saga_failure_stops_pipeline(self):
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: "ok"),
            Phase(
                "b", handler=lambda: (_ for _ in ()).throw(RuntimeError("fail")), depends_on=("a",)
            ),
        )

        saga = pipeline.build_saga()
        gen = saga()

        # PIPELINE_START
        next(gen)
        # PHASE_START a
        gen.send(None)
        # Call a
        gen.send(None)
        # PHASE_COMPLETE a -> send result
        gen.send("ok")

        # PHASE_START b
        gen.send(None)
        # Call b
        effect = gen.send(None)
        assert isinstance(effect, Call)

        # Simulate exception from Call
        effect = gen.throw(RuntimeError("fail"))
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_FAILED

        # Saga should stop (StopIteration)
        try:
            gen.send(None)
            stopped = False
        except StopIteration:
            stopped = True
        assert stopped


# ---------------------------------------------------------------------------
# Execution order
# ---------------------------------------------------------------------------


class TestExecutionOrder:
    def test_linear_order(self):
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",)),
            Phase("c", handler=lambda: None, depends_on=("b",)),
        )
        assert pipeline.execution_order() == ["a", "b", "c"]

    def test_parallel_phases_same_level(self):
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",), parallel=True),
            Phase("c", handler=lambda: None, depends_on=("a",), parallel=True),
            Phase("d", handler=lambda: None, depends_on=("b", "c")),
        )
        order = pipeline.execution_order()
        assert order[0] == "a"
        assert set(order[1:3]) == {"b", "c"}
        assert order[3] == "d"

    def test_no_dependencies(self):
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None),
        )
        order = pipeline.execution_order()
        assert set(order) == {"a", "b"}

    def test_fail_fast_pipeline_uses_all_for_parallel(self):
        """fail_fast=True uses All instead of Fork for parallel phases."""
        from milo._types import All

        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",), parallel=True),
            Phase("c", handler=lambda: None, depends_on=("a",), parallel=True),
            fail_fast=True,
        )
        saga = pipeline.build_saga()
        gen = saga()

        # PIPELINE_START
        next(gen)
        # PHASE_START a
        gen.send(None)
        # Call a
        gen.send(None)
        # PHASE_COMPLETE a
        gen.send("ok")

        # Next should be an All effect (not Fork) for the parallel phases
        effect = gen.send(None)
        assert isinstance(effect, All), f"Expected All, got {type(effect).__name__}"


# ---------------------------------------------------------------------------
# PhaseStatus and PipelineState
# ---------------------------------------------------------------------------


class TestDataTypes:
    def test_phase_status_defaults(self):
        ps = PhaseStatus(name="test")
        assert ps.status == "pending"
        assert ps.elapsed == 0.0
        assert ps.attempt == 1

    def test_pipeline_state_defaults(self):
        ps = PipelineState()
        assert ps.status == "pending"
        assert ps.progress == 0.0

    def test_phase_policy_defaults(self):
        pp = PhasePolicy()
        assert pp.on_fail == "stop"
        assert pp.max_retries == 0

    def test_phase_with_policy(self):
        p = Phase(
            "x",
            handler=lambda: None,
            policy=PhasePolicy(on_fail="retry", max_retries=3),
        )
        assert p.policy.on_fail == "retry"
        assert p.policy.max_retries == 3


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_self_cycle(self):
        with pytest.raises(CycleError, match=r"Circular dependency.*a.*a"):
            Pipeline("p", Phase("a", handler=lambda: None, depends_on=("a",)))

    def test_two_node_cycle(self):
        with pytest.raises(CycleError, match="Circular dependency"):
            Pipeline(
                "p",
                Phase("a", handler=lambda: None, depends_on=("b",)),
                Phase("b", handler=lambda: None, depends_on=("a",)),
            )

    def test_three_node_cycle(self):
        with pytest.raises(CycleError, match="Circular dependency"):
            Pipeline(
                "p",
                Phase("a", handler=lambda: None, depends_on=("c",)),
                Phase("b", handler=lambda: None, depends_on=("a",)),
                Phase("c", handler=lambda: None, depends_on=("b",)),
            )

    def test_no_cycle_passes(self):
        # Should not raise
        Pipeline(
            "p",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",)),
            Phase("c", handler=lambda: None, depends_on=("b",)),
        )

    def test_diamond_no_cycle(self):
        # Diamond: a -> {b, c} -> d. Not a cycle.
        Pipeline(
            "p",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",)),
            Phase("c", handler=lambda: None, depends_on=("a",)),
            Phase("d", handler=lambda: None, depends_on=("b", "c")),
        )

    def test_cycle_error_includes_path(self):
        with pytest.raises(CycleError) as exc_info:
            Pipeline(
                "p",
                Phase("a", handler=lambda: None, depends_on=("b",)),
                Phase("b", handler=lambda: None, depends_on=("a",)),
            )
        msg = str(exc_info.value)
        assert "\u2192" in msg  # arrow in path


# ---------------------------------------------------------------------------
# PhasePolicy: skip
# ---------------------------------------------------------------------------


class TestPhasePolicySkip:
    def test_skip_continues_pipeline(self):
        """on_fail='skip' marks phase as skipped, pipeline continues."""
        from milo.state import Store

        def failing():
            raise RuntimeError("boom")

        pipeline = Pipeline(
            "p",
            Phase("a", handler=failing, policy=PhasePolicy(on_fail="skip")),
            Phase("b", handler=lambda: "ok", depends_on=("a",)),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        a_status = next(p for p in state.phases if p.name == "a")
        b_status = next(p for p in state.phases if p.name == "b")
        assert a_status.status == "skipped"
        assert b_status.status == "completed"
        assert state.status == "completed"

    def test_skip_reducer_progress(self):
        """Skipped phases count toward progress."""
        pipeline = Pipeline(
            "p",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None),
            Phase("c", handler=lambda: None),
        )
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, "a"))
        state = reducer(state, Action(PHASE_SKIPPED, {"name": "a", "error": "skip"}))
        a = next(p for p in state.phases if p.name == "a")
        assert a.status == "skipped"
        assert abs(state.progress - 1 / 3) < 0.01


# ---------------------------------------------------------------------------
# PhasePolicy: retry
# ---------------------------------------------------------------------------


class TestPhasePolicyRetry:
    def test_retry_succeeds_on_second_attempt(self):
        """on_fail='retry' retries and succeeds."""
        from milo.state import Store

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "ok"

        pipeline = Pipeline(
            "p",
            Phase(
                "a",
                handler=flaky,
                policy=PhasePolicy(on_fail="retry", max_retries=3, retry_delay=0.01),
            ),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        a_status = next(p for p in state.phases if p.name == "a")
        assert a_status.status == "completed"
        assert state.status == "completed"
        assert call_count == 2

    def test_retry_exhausted(self):
        """Retries exhaust, pipeline fails."""
        from milo.state import Store

        def always_fails():
            raise RuntimeError("nope")

        pipeline = Pipeline(
            "p",
            Phase(
                "a",
                handler=always_fails,
                policy=PhasePolicy(on_fail="retry", max_retries=2, retry_delay=0.01),
            ),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        assert state.status == "failed"

    def test_retry_reducer_state(self):
        """PHASE_RETRY action sets status to 'retrying'."""
        pipeline = Pipeline("p", Phase("a", handler=lambda: None))
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, {"name": "a", "attempt": 1}))
        state = reducer(
            state,
            Action(PHASE_RETRY, {"name": "a", "attempt": 1, "error": "fail", "max_retries": 3}),
        )
        a = next(p for p in state.phases if p.name == "a")
        assert a.status == "retrying"
        assert a.attempt == 1
        assert a.error == "fail"

    def test_default_policy_is_stop(self):
        """Default PhasePolicy preserves original fail-fast behavior."""
        from milo.state import Store

        def failing():
            raise RuntimeError("boom")

        pipeline = Pipeline(
            "p",
            Phase("a", handler=failing),
            Phase("b", handler=lambda: "ok", depends_on=("a",)),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        assert state.status == "failed"
        b_status = next(p for p in state.phases if p.name == "b")
        assert b_status.status == "pending"  # Never ran


# ---------------------------------------------------------------------------
# Phase context forwarding
# ---------------------------------------------------------------------------


class TestPhaseContext:
    def test_handler_receives_context(self):
        """Phase handlers that accept 'context' get dependency results."""
        from milo.state import Store

        received_context = {}

        def producer():
            return {"data": 42}

        def consumer(context):
            received_context.update(context)
            return "consumed"

        pipeline = Pipeline(
            "p",
            Phase("produce", handler=producer),
            Phase("consume", handler=consumer, depends_on=("produce",)),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        assert received_context == {"produce": {"data": 42}}
        assert store.state.status == "completed"

    def test_handler_without_context_works(self):
        """Handlers without 'context' param still work (backward compat)."""
        from milo.state import Store

        pipeline = Pipeline(
            "p",
            Phase("a", handler=lambda: "result_a"),
            Phase("b", handler=lambda: "result_b", depends_on=("a",)),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        assert store.state.status == "completed"

    def test_skipped_dependency_passes_none(self):
        """Skipped phase passes None in context to downstream."""
        from milo.state import Store

        received_context = {}

        def failing():
            raise RuntimeError("skip me")

        def consumer(context):
            received_context.update(context)
            return "done"

        pipeline = Pipeline(
            "p",
            Phase("a", handler=failing, policy=PhasePolicy(on_fail="skip")),
            Phase("b", handler=consumer, depends_on=("a",)),
        )

        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        assert received_context == {"a": None}
        assert store.state.status == "completed"

    def test_build_context_rejects_missing_dependency(self):
        """_build_context raises PipelineError for misspelled dependency names."""
        from milo._errors import PipelineError
        from milo.pipeline import _build_context

        phase = Phase("render", handler=lambda ctx: None, depends_on=("typo",))
        with pytest.raises(PipelineError, match="typo"):
            _build_context(phase, results={"parse": "ok"})


# ---------------------------------------------------------------------------
# PhaseLog data model (Sprint 1)
# ---------------------------------------------------------------------------


class TestPhaseLog:
    def test_phase_log_defaults(self):
        log = PhaseLog(line="hello")
        assert log.line == "hello"
        assert log.stream == "stdout"
        assert log.timestamp == 0.0

    def test_phase_log_stderr(self):
        log = PhaseLog(line="warning", stream="stderr", timestamp=1.23)
        assert log.stream == "stderr"
        assert log.timestamp == 1.23

    def test_phase_status_has_empty_logs(self):
        ps = PhaseStatus(name="test")
        assert ps.logs == ()

    def test_phase_max_logs_default(self):
        p = Phase("x", handler=lambda: None)
        assert p.max_logs == 200

    def test_phase_max_logs_custom(self):
        p = Phase("x", handler=lambda: None, max_logs=50)
        assert p.max_logs == 50

    def test_phase_log_import_from_milo(self):
        from milo import PhaseLog as PhaseLogImport

        assert PhaseLogImport is PhaseLog


# ---------------------------------------------------------------------------
# PHASE_LOG reducer (Sprint 1)
# ---------------------------------------------------------------------------


class TestPhaseLogReducer:
    def _make_pipeline(self):
        return Pipeline(
            "build",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",)),
        )

    def _init_state(self, pipeline):
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, {"name": "a", "attempt": 1}))
        return reducer, state

    def test_phase_log_appends(self):
        pipeline = self._make_pipeline()
        reducer, state = self._init_state(pipeline)
        state = reducer(
            state,
            Action(PHASE_LOG, {"name": "a", "line": "hello", "stream": "stdout", "timestamp": 1.0}),
        )
        a = next(p for p in state.phases if p.name == "a")
        assert len(a.logs) == 1
        assert a.logs[0].line == "hello"
        assert a.logs[0].stream == "stdout"
        assert a.logs[0].timestamp == 1.0

    def test_phase_log_multiple(self):
        pipeline = self._make_pipeline()
        reducer, state = self._init_state(pipeline)
        for i in range(5):
            state = reducer(
                state,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}"}),
            )
        a = next(p for p in state.phases if p.name == "a")
        assert len(a.logs) == 5
        assert a.logs[0].line == "line 0"
        assert a.logs[4].line == "line 4"

    def test_phase_log_ring_buffer(self):
        """Logs are evicted when exceeding max_logs."""
        pipeline = Pipeline(
            "build",
            Phase("a", handler=lambda: None, max_logs=5),
        )
        reducer = pipeline.build_reducer()
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action(PIPELINE_START))
        state = reducer(state, Action(PHASE_START, {"name": "a", "attempt": 1}))
        for i in range(10):
            state = reducer(
                state,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}"}),
            )
        a = next(p for p in state.phases if p.name == "a")
        assert len(a.logs) == 5
        # Oldest lines evicted — should have lines 5-9
        assert a.logs[0].line == "line 5"
        assert a.logs[4].line == "line 9"

    def test_phase_log_defaults_stream(self):
        """Stream defaults to stdout when not provided."""
        pipeline = self._make_pipeline()
        reducer, state = self._init_state(pipeline)
        state = reducer(state, Action(PHASE_LOG, {"name": "a", "line": "test"}))
        a = next(p for p in state.phases if p.name == "a")
        assert a.logs[0].stream == "stdout"

    def test_phase_log_does_not_affect_other_phases(self):
        pipeline = self._make_pipeline()
        reducer, state = self._init_state(pipeline)
        state = reducer(state, Action(PHASE_LOG, {"name": "a", "line": "only a"}))
        b = next(p for p in state.phases if p.name == "b")
        assert len(b.logs) == 0

    def test_logs_preserved_across_status_change(self):
        """Logs survive phase completion."""
        pipeline = self._make_pipeline()
        reducer, state = self._init_state(pipeline)
        state = reducer(state, Action(PHASE_LOG, {"name": "a", "line": "before"}))
        state = reducer(state, Action(PHASE_COMPLETE, {"name": "a"}))
        a = next(p for p in state.phases if p.name == "a")
        assert a.status == "completed"
        assert len(a.logs) == 1
        assert a.logs[0].line == "before"


# ---------------------------------------------------------------------------
# Output capture (Sprint 2)
# ---------------------------------------------------------------------------


class TestOutputCapture:
    def test_capture_sequential_stdout(self):
        """Handler print() captured as PHASE_LOG when capture_output=True."""
        from milo.state import Store

        def chatty():
            print("hello from phase")
            return "done"

        pipeline = Pipeline("p", Phase("a", handler=chatty), capture_output=True)
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        assert state.status == "completed"
        a = next(p for p in state.phases if p.name == "a")
        assert len(a.logs) >= 1
        assert any(log.line == "hello from phase" for log in a.logs)
        assert all(log.stream == "stdout" for log in a.logs)

    def test_capture_sequential_stderr(self):
        """Handler stderr captured with stream='stderr'."""
        import sys

        from milo.state import Store

        def warns():
            print("warning!", file=sys.stderr)
            return "done"

        pipeline = Pipeline("p", Phase("a", handler=warns), capture_output=True)
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        a = next(p for p in store.state.phases if p.name == "a")
        assert any(log.stream == "stderr" and log.line == "warning!" for log in a.logs)

    def test_no_capture_by_default(self):
        """Without capture_output, no logs are captured."""
        from milo.state import Store

        def chatty():
            print("this should not be captured")
            return "done"

        pipeline = Pipeline("p", Phase("a", handler=chatty))
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        a = next(p for p in store.state.phases if p.name == "a")
        assert len(a.logs) == 0

    def test_capture_multiple_lines(self):
        """Multiple print calls produce multiple log entries."""
        from milo.state import Store

        def multi():
            for i in range(5):
                print(f"line {i}")
            return "done"

        pipeline = Pipeline("p", Phase("a", handler=multi), capture_output=True)
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        a = next(p for p in store.state.phases if p.name == "a")
        assert len(a.logs) == 5
        assert a.logs[0].line == "line 0"
        assert a.logs[4].line == "line 4"

    def test_capture_with_failure_preserves_logs(self):
        """Logs from before a failure are preserved on the failed phase."""
        from milo.state import Store

        def fails_after_output():
            print("before crash")
            raise RuntimeError("boom")

        pipeline = Pipeline("p", Phase("a", handler=fails_after_output), capture_output=True)
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        state = store.state
        assert state.status == "failed"
        a = next(p for p in state.phases if p.name == "a")
        assert a.status == "failed"
        # Logs captured before the exception are flushed to state
        assert len(a.logs) >= 1
        assert a.logs[0].line == "before crash"

    def test_capture_parallel_isolation(self):
        """Parallel phases capture independently — no cross-contamination."""
        import time

        from milo.state import Store

        def phase_a():
            for i in range(10):
                print(f"a-{i}")
            return "a-done"

        def phase_b():
            for i in range(10):
                print(f"b-{i}")
            return "b-done"

        pipeline = Pipeline(
            "p",
            Phase("root", handler=lambda: "ok"),
            Phase("a", handler=phase_a, depends_on=("root",), parallel=True),
            Phase("b", handler=phase_b, depends_on=("root",), parallel=True),
            capture_output=True,
        )
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        # Poll until pipeline completes instead of fixed sleep
        for _ in range(100):
            if store.state.status in ("completed", "failed"):
                break
            time.sleep(0.05)
        store._executor.shutdown(wait=True)

        a = next(p for p in store.state.phases if p.name == "a")
        b = next(p for p in store.state.phases if p.name == "b")
        # Each phase should only have its own lines
        a_lines = [log.line for log in a.logs]
        b_lines = [log.line for log in b.logs]
        assert all(line.startswith("a-") for line in a_lines), f"a got: {a_lines}"
        assert all(line.startswith("b-") for line in b_lines), f"b got: {b_lines}"
        assert len(a_lines) == 10
        assert len(b_lines) == 10

    def test_capture_rshift_preserves_flag(self):
        """>> operator preserves capture_output flag."""
        p1 = Pipeline("p", Phase("a", handler=lambda: None), capture_output=True)
        p2 = p1 >> Phase("b", handler=lambda: None)
        assert p2.capture_output is True

    def test_capture_ring_buffer_large_output(self):
        """Large output respects max_logs ring buffer."""
        from milo.state import Store

        def verbose():
            for i in range(300):
                print(f"line {i}")
            return "done"

        pipeline = Pipeline(
            "p",
            Phase("a", handler=verbose, max_logs=100),
            capture_output=True,
        )
        reducer = pipeline.build_reducer()
        saga_fn = pipeline.build_saga()
        store = Store(reducer, None)
        store.run_saga(saga_fn())
        store._executor.shutdown(wait=True)

        a = next(p for p in store.state.phases if p.name == "a")
        assert len(a.logs) == 100
        # Oldest evicted — should have lines 200-299
        assert a.logs[0].line == "line 200"
        assert a.logs[99].line == "line 299"


# ---------------------------------------------------------------------------
# PipelineViewState
# ---------------------------------------------------------------------------


class TestPipelineViewState:
    def test_defaults(self):
        ps = PipelineState(name="test", phases=())
        vs = PipelineViewState(pipeline=ps)
        assert vs.selected_phase == 0
        assert vs.expanded is False
        assert vs.log_scroll == 0
        assert vs.auto_follow is True
        assert vs.log_height == 10

    def test_frozen(self):
        ps = PipelineState(name="test")
        vs = PipelineViewState(pipeline=ps)
        with pytest.raises(AttributeError):
            vs.expanded = True

    def test_import_from_milo(self):
        from milo import PipelineViewState as PipelineViewStateImport

        assert PipelineViewStateImport is PipelineViewState

    def test_make_detail_reducer_import(self):
        from milo import make_detail_reducer as mdr

        assert mdr is make_detail_reducer


# ---------------------------------------------------------------------------
# Detail reducer
# ---------------------------------------------------------------------------


class TestDetailReducer:
    @pytest.fixture
    def pipeline(self):
        return Pipeline(
            "test",
            Phase("a", handler=lambda: None),
            Phase("b", handler=lambda: None, depends_on=("a",)),
            Phase("c", handler=lambda: None, depends_on=("b",)),
        )

    @pytest.fixture
    def reducer(self, pipeline):
        return make_detail_reducer(pipeline.build_reducer())

    @pytest.fixture
    def state(self, reducer):
        return reducer(None, Action("@@INIT"))

    def test_init_creates_view_state(self, state):
        assert isinstance(state, PipelineViewState)
        assert state.pipeline.name == "test"
        assert len(state.pipeline.phases) == 3
        assert state.selected_phase == 0
        assert state.expanded is False

    def test_cursor_down(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        assert s.selected_phase == 1

    def test_cursor_up(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.UP)))
        assert s.selected_phase == 0

    def test_cursor_clamps_at_top(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.UP)))
        assert s.selected_phase == 0

    def test_cursor_clamps_at_bottom(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        assert s.selected_phase == 2  # 3 phases, max index 2

    def test_enter_expands(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        assert s.expanded is True
        assert s.auto_follow is True

    def test_space_expands(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(char=" ")))
        assert s.expanded is True

    def test_escape_in_overview_quits(self, reducer, state):
        result = reducer(state, Action("@@KEY", Key(name=SpecialKey.ESCAPE)))
        assert isinstance(result, Quit)

    def test_q_quits_from_overview(self, reducer, state):
        result = reducer(state, Action("@@KEY", Key(char="q")))
        assert isinstance(result, Quit)

    def test_enter_collapses_in_detail(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        assert s.expanded is True
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        assert s.expanded is False
        assert s.log_scroll == 0

    def test_escape_collapses_in_detail(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.ESCAPE)))
        assert s.expanded is False

    def test_q_quits_from_detail(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        result = reducer(s, Action("@@KEY", Key(char="q")))
        assert isinstance(result, Quit)

    def test_scroll_down_in_detail(self, reducer, state):
        # Add some logs first
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        for i in range(20):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}", "stream": "stdout"}),
            )
        # Disable auto-follow by scrolling up
        s = replace(s, auto_follow=False, log_scroll=0)
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.DOWN)))
        assert s.log_scroll == 1
        assert s.auto_follow is False

    def test_scroll_up_in_detail(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        for i in range(20):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}", "stream": "stdout"}),
            )
        s = replace(s, auto_follow=False, log_scroll=5)
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.UP)))
        assert s.log_scroll == 4

    def test_scroll_clamps_at_zero(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        s = replace(s, auto_follow=False, log_scroll=0)
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.UP)))
        assert s.log_scroll == 0

    def test_home_jumps_to_top(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        for i in range(20):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}", "stream": "stdout"}),
            )
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.HOME)))
        assert s.log_scroll == 0
        assert s.auto_follow is False

    def test_end_jumps_to_bottom(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        for i in range(20):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}", "stream": "stdout"}),
            )
        s = replace(s, auto_follow=False, log_scroll=0)
        s = reducer(s, Action("@@KEY", Key(name=SpecialKey.END)))
        assert s.log_scroll == 10  # 20 logs - 10 height

    def test_toggle_follow(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        assert s.auto_follow is True
        s = reducer(s, Action("@@KEY", Key(char="f")))
        assert s.auto_follow is False
        s = reducer(s, Action("@@KEY", Key(char="f")))
        assert s.auto_follow is True

    def test_auto_follow_scrolls_on_log(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        for i in range(15):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "a", "line": f"line {i}", "stream": "stdout"}),
            )
        # With auto_follow=True, scroll should track the latest
        assert s.auto_follow is True
        assert s.log_scroll == 5  # 15 logs - 10 height

    def test_auto_follow_ignores_other_phase_logs(self, reducer, state):
        s = reducer(state, Action("@@KEY", Key(name=SpecialKey.ENTER)))
        # Add logs to phase "b" (selected is "a")
        for i in range(15):
            s = reducer(
                s,
                Action(PHASE_LOG, {"name": "b", "line": f"line {i}", "stream": "stdout"}),
            )
        assert s.log_scroll == 0  # Not scrolled — different phase

    def test_delegates_pipeline_actions(self, reducer, state):
        s = reducer(state, Action(PIPELINE_START))
        assert s.pipeline.status == "running"

    def test_phase_start_delegated(self, reducer, state):
        s = reducer(state, Action(PIPELINE_START))
        s = reducer(s, Action(PHASE_START, {"name": "a", "attempt": 1}))
        a = next(p for p in s.pipeline.phases if p.name == "a")
        assert a.status == "running"


# ---------------------------------------------------------------------------
# Pipeline timeline serialization
# ---------------------------------------------------------------------------


class TestPipelineTimeline:
    def test_basic_serialization(self):
        state = PipelineState(
            name="build",
            phases=(
                PhaseStatus(name="a", status="completed", elapsed=0.523, attempt=1),
                PhaseStatus(name="b", status="running", elapsed=0.0),
            ),
            status="running",
            progress=0.5,
            elapsed=1.234,
        )
        timeline = pipeline_to_timeline(state)
        assert timeline["pipeline"] == "build"
        assert timeline["status"] == "running"
        assert timeline["elapsed"] == 1.234
        assert timeline["progress"] == 0.5
        assert len(timeline["phases"]) == 2
        assert timeline["phases"][0]["name"] == "a"
        assert timeline["phases"][0]["status"] == "completed"
        assert timeline["phases"][0]["elapsed"] == 0.523
        assert timeline["phases"][0]["attempt"] == 1
        assert timeline["phases"][0]["log_count"] == 0
        assert timeline["phases"][0]["error"] is None
        assert timeline["phases"][1]["name"] == "b"

    def test_with_logs_and_error(self):
        state = PipelineState(
            name="deploy",
            phases=(
                PhaseStatus(
                    name="validate",
                    status="failed",
                    error="bad config",
                    elapsed=0.1,
                    logs=(PhaseLog(line="checking..."), PhaseLog(line="error!")),
                ),
            ),
            status="failed",
            elapsed=0.1,
        )
        timeline = pipeline_to_timeline(state)
        assert timeline["phases"][0]["log_count"] == 2
        assert timeline["phases"][0]["error"] == "bad config"

    def test_set_and_get_active_pipeline(self):
        state = PipelineState(name="test", status="running")
        set_active_pipeline(state)
        try:
            result = get_active_pipeline()
            assert result is state
        finally:
            set_active_pipeline(None)

    def test_get_active_pipeline_default_none(self):
        set_active_pipeline(None)
        assert get_active_pipeline() is None

    def test_imports_from_milo(self):
        from milo import get_active_pipeline as gap
        from milo import pipeline_to_timeline as ptt
        from milo import set_active_pipeline as sap

        assert gap is get_active_pipeline
        assert sap is set_active_pipeline
        assert ptt is pipeline_to_timeline
