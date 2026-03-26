"""Protocols — stdlib/typing only, no internal imports."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from milo._types import Action, ReducerResult


@runtime_checkable
class Reducer(Protocol):
    def __call__(self, state: Any, action: Action) -> Any | ReducerResult: ...


@runtime_checkable
class Saga(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class DispatchFn(Protocol):
    def __call__(self, action: Action) -> None: ...


@runtime_checkable
class Middleware(Protocol):
    def __call__(self, dispatch: DispatchFn, get_state: GetStateFn) -> DispatchFn: ...


@runtime_checkable
class GetStateFn(Protocol):
    def __call__(self) -> Any: ...


@runtime_checkable
class FieldValidator(Protocol):
    def __call__(self, value: Any) -> tuple[bool, str]: ...
