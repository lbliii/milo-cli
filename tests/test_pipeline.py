"""Tests for pipeline orchestration."""

from __future__ import annotations

from milo._types import Action, Call, Put
from milo.pipeline import (
    PHASE_COMPLETE,
    PHASE_FAILED,
    PHASE_START,
    PIPELINE_COMPLETE,
    PIPELINE_START,
    Phase,
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
        state = reducer(
            state, Action(PHASE_FAILED, {"name": "discover", "error": "boom"})
        )
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
        assert effect.action.payload == "discover"

        effect = gen.send(None)  # Call discover handler
        assert isinstance(effect, Call)

        effect = gen.send("found")  # PHASE_COMPLETE discover
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_COMPLETE

        # Phase: parse
        effect = gen.send(None)  # PHASE_START parse
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_START
        assert effect.action.payload == "parse"

        effect = gen.send(None)  # Call parse handler
        assert isinstance(effect, Call)

        effect = gen.send("parsed")  # PHASE_COMPLETE parse
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_COMPLETE

        # Phase: render
        effect = gen.send(None)  # PHASE_START render
        assert isinstance(effect, Put)
        assert effect.action.type == PHASE_START
        assert effect.action.payload == "render"

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
            Phase("b", handler=lambda: (_ for _ in ()).throw(RuntimeError("fail")), depends_on=("a",)),
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

    def test_pipeline_state_defaults(self):
        ps = PipelineState()
        assert ps.status == "pending"
        assert ps.progress == 0.0
