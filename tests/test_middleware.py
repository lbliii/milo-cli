"""Tests for milo.middleware — middleware stack."""

from __future__ import annotations

import pytest

from milo.middleware import MCPCall, MiddlewareStack


class TestMCPCall:
    def test_frozen(self) -> None:
        call = MCPCall(method="tools/call", name="greet")
        with pytest.raises(AttributeError):
            call.name = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        call = MCPCall(method="tools/call", name="greet")
        assert call.arguments == {}
        assert call.metadata == {}


class TestMiddlewareStack:
    def test_empty_stack_calls_handler(self) -> None:
        stack = MiddlewareStack()
        call = MCPCall(method="tools/call", name="greet")
        result = stack.execute(None, call, lambda c: f"handled:{c.name}")
        assert result == "handled:greet"

    def test_single_middleware(self) -> None:
        stack = MiddlewareStack()
        log: list[str] = []

        @stack.use
        def mw(ctx, call, next_fn):
            log.append("before")
            result = next_fn(call)
            log.append("after")
            return result

        call = MCPCall(method="tools/call", name="greet")
        result = stack.execute(None, call, lambda c: "ok")
        assert result == "ok"
        assert log == ["before", "after"]

    def test_ordering(self) -> None:
        stack = MiddlewareStack()
        log: list[str] = []

        @stack.use
        def first(ctx, call, next_fn):
            log.append("first-before")
            result = next_fn(call)
            log.append("first-after")
            return result

        @stack.use
        def second(ctx, call, next_fn):
            log.append("second-before")
            result = next_fn(call)
            log.append("second-after")
            return result

        call = MCPCall(method="tools/call", name="greet")
        stack.execute(None, call, lambda c: "ok")
        assert log == ["first-before", "second-before", "second-after", "first-after"]

    def test_short_circuit(self) -> None:
        stack = MiddlewareStack()

        @stack.use
        def blocker(ctx, call, next_fn):
            return "blocked"

        @stack.use
        def never_called(ctx, call, next_fn):
            msg = "should not reach here"
            raise AssertionError(msg)

        call = MCPCall(method="tools/call", name="greet")
        result = stack.execute(None, call, lambda c: "ok")
        assert result == "blocked"

    def test_error_propagation(self) -> None:
        stack = MiddlewareStack()

        @stack.use
        def raiser(ctx, call, next_fn):
            msg = "middleware error"
            raise ValueError(msg)

        call = MCPCall(method="tools/call", name="greet")
        with pytest.raises(ValueError, match="middleware error"):
            stack.execute(None, call, lambda c: "ok")

    def test_middleware_receives_ctx(self) -> None:
        stack = MiddlewareStack()
        captured: list = []

        @stack.use
        def capture(ctx, call, next_fn):
            captured.append(ctx)
            return next_fn(call)

        call = MCPCall(method="tools/call", name="greet")
        stack.execute("my-ctx", call, lambda c: "ok")
        assert captured == ["my-ctx"]

    def test_middleware_can_modify_call(self) -> None:
        stack = MiddlewareStack()

        @stack.use
        def modifier(ctx, call, next_fn):
            modified = MCPCall(
                method=call.method,
                name=call.name,
                arguments={**call.arguments, "injected": True},
            )
            return next_fn(modified)

        call = MCPCall(method="tools/call", name="greet", arguments={"name": "Alice"})
        result = stack.execute(None, call, lambda c: c.arguments)
        assert result == {"name": "Alice", "injected": True}
