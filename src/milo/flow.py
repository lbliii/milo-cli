"""Declarative screen state machine with >> operator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from milo._errors import ErrorCode, FlowError
from milo._types import Action, Quit, ReducerResult, Transition


def _default_transition(from_name: str, to_name: str) -> Transition:
    return Transition(from_screen=from_name, to_screen=to_name, on_action="@@NAVIGATE")


@dataclass(frozen=True, slots=True)
class FlowScreen:
    """A screen in a flow with its template and reducer."""

    name: str
    template: str
    reducer: Callable

    def __rshift__(self, other: FlowScreen) -> Flow:
        """screen_a >> screen_b creates a Flow."""
        return Flow(
            screens=(self, other),
            transitions=(_default_transition(self.name, other.name),),
        )


@dataclass(frozen=True, slots=True)
class FlowState:
    """Runtime state for a flow."""

    current_screen: str
    screen_states: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Flow:
    """Declarative multi-screen state machine."""

    screens: tuple[FlowScreen, ...]
    transitions: tuple[Transition, ...]

    def __rshift__(self, other: FlowScreen) -> Flow:
        """flow >> screen_c extends the flow."""
        last = self.screens[-1]
        return Flow(
            screens=(*self.screens, other),
            transitions=(*self.transitions, _default_transition(last.name, other.name)),
        )

    @classmethod
    def from_screens(cls, *screens: FlowScreen) -> Flow:
        """Create a flow from an ordered sequence of screens."""
        if len(screens) < 2:
            raise FlowError(ErrorCode.FLW_SCREEN, "Flow requires at least 2 screens")
        transitions = tuple(
            _default_transition(screens[i].name, screens[i + 1].name)
            for i in range(len(screens) - 1)
        )
        return cls(screens=screens, transitions=transitions)

    def with_transition(self, from_screen: str, to_screen: str, *, on: str) -> Flow:
        """Add a custom transition."""
        # Validate screen names
        names = {s.name for s in self.screens}
        if from_screen not in names:
            raise FlowError(ErrorCode.FLW_SCREEN, f"Unknown screen: {from_screen}")
        if to_screen not in names:
            raise FlowError(ErrorCode.FLW_SCREEN, f"Unknown screen: {to_screen}")
        return Flow(
            screens=self.screens,
            transitions=(*self.transitions, Transition(from_screen, to_screen, on)),
        )

    def build_reducer(self) -> Callable:
        """Build a combined reducer that routes actions to the current screen's reducer."""
        screen_map = {s.name: s for s in self.screens}
        transition_map: dict[tuple[str, str], str] = {}
        for t in self.transitions:
            transition_map[(t.from_screen, t.on_action)] = t.to_screen

        def flow_reducer(
            state: FlowState | None, action: Action
        ) -> FlowState | ReducerResult | Quit:
            if state is None:
                first = self.screens[0]
                initial_states = {s.name: s.reducer(None, Action("@@INIT")) for s in self.screens}
                return FlowState(
                    current_screen=first.name,
                    screen_states=initial_states,
                )

            current = state.current_screen

            # Check for transitions
            target = transition_map.get((current, action.type))
            if target is None and action.type == "@@NAVIGATE" and action.payload:
                target = action.payload if action.payload in screen_map else None

            if target is not None and target in screen_map:
                return FlowState(
                    current_screen=target,
                    screen_states=state.screen_states,
                )

            # Route action to current screen's reducer
            screen = screen_map.get(current)
            if screen is None:
                raise FlowError(ErrorCode.FLW_SCREEN, f"Unknown screen: {current}")

            result = screen.reducer(state.screen_states.get(current), action)

            # Unwrap Quit/ReducerResult to propagate sagas
            sagas = ()
            quit_signal: Quit | None = None
            if isinstance(result, Quit):
                quit_signal = result
                new_screen_state = result.state
                sagas = result.sagas
            elif isinstance(result, ReducerResult):
                new_screen_state = result.state
                sagas = result.sagas
            else:
                new_screen_state = result

            new_states = {**state.screen_states, current: new_screen_state}
            flow_state = FlowState(
                current_screen=current,
                screen_states=new_states,
            )

            if quit_signal is not None:
                return Quit(state=flow_state, code=quit_signal.code, sagas=sagas)
            if sagas:
                return ReducerResult(state=flow_state, sagas=sagas)
            return flow_state

        return flow_reducer

    @property
    def template_map(self) -> dict[str, str]:
        """Map screen names to template names."""
        return {s.name: s.template for s in self.screens}
