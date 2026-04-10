"""Tests for pipeline orchestration."""

from __future__ import annotations

import pytest

from milo._types import Action, Call, Put
from milo.pipeline import (
    PHASE_COMPLETE,
    PHASE_FAILED,
    PHASE_RETRY,
    PHASE_SKIPPED,
    PHASE_START,
    PIPELINE_COMPLETE,
    PIPELINE_START,
    CycleError,
    Phase,
    PhasePolicy,
    PhaseStatus,
    Pipeline,
    PipelineState,
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
