"""Tests for _protocols.py — runtime-checkable protocol verification."""

from __future__ import annotations

from typing import Any

from milo._protocols import (
    DispatchFn,
    FieldValidator,
    GetStateFn,
    Middleware,
    Reducer,
    Saga,
)
from milo._types import Action


class TestReducerProtocol:
    def test_callable_matches(self):
        def my_reducer(state: Any, action: Action) -> Any:
            return state

        assert isinstance(my_reducer, Reducer)

    def test_lambda_matches(self):
        r = lambda s, a: s  # noqa: E731
        assert isinstance(r, Reducer)

    def test_non_callable_does_not_match(self):
        assert not isinstance(42, Reducer)
        assert not isinstance("reducer", Reducer)
        assert not isinstance(None, Reducer)

    def test_class_with_call_matches(self):
        class MyReducer:
            def __call__(self, state: Any, action: Action) -> Any:
                return state

        assert isinstance(MyReducer(), Reducer)


class TestSagaProtocol:
    def test_generator_function_matches(self):
        def my_saga(*args, **kwargs):
            yield 1

        assert isinstance(my_saga, Saga)

    def test_regular_callable_matches(self):
        def my_saga(*args, **kwargs):
            return None

        assert isinstance(my_saga, Saga)

    def test_non_callable_does_not_match(self):
        assert not isinstance([], Saga)
        assert not isinstance({}, Saga)


class TestDispatchFnProtocol:
    def test_callable_matches(self):
        def dispatch(action: Action) -> None:
            pass

        assert isinstance(dispatch, DispatchFn)

    def test_non_callable_does_not_match(self):
        assert not isinstance(42, DispatchFn)


class TestGetStateFnProtocol:
    def test_callable_matches(self):
        def get_state() -> Any:
            return {}

        assert isinstance(get_state, GetStateFn)

    def test_lambda_matches(self):
        fn = dict
        assert isinstance(fn, GetStateFn)

    def test_non_callable_does_not_match(self):
        assert not isinstance(None, GetStateFn)


class TestMiddlewareProtocol:
    def test_callable_matches(self):
        def my_middleware(dispatch: DispatchFn, get_state: GetStateFn) -> DispatchFn:
            return dispatch

        assert isinstance(my_middleware, Middleware)

    def test_non_callable_does_not_match(self):
        assert not isinstance([], Middleware)


class TestFieldValidatorProtocol:
    def test_callable_matches(self):
        def validator(value: Any) -> tuple[bool, str]:
            return (bool(value), "Required")

        assert isinstance(validator, FieldValidator)

    def test_non_callable_does_not_match(self):
        assert not isinstance("valid", FieldValidator)
        assert not isinstance(True, FieldValidator)
