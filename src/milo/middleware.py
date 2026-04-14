"""Middleware stack for MCP and CLI call interception."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Type aliases
type MiddlewareFn = Callable[..., Any]
type NextFn = Callable[[MCPCall], Any]


@dataclass(frozen=True, slots=True)
class MCPCall:
    """Represents an interceptable MCP or CLI call."""

    method: str  # "tools/call", "resources/read", etc.
    name: str  # tool/resource/prompt name
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class MiddlewareStack:
    """Ordered middleware pipeline for intercepting calls.

    Middleware signature: ``def mw(ctx, call: MCPCall, next_fn: NextFn) -> Any``

    Usage::

        stack = MiddlewareStack()

        @stack.use
        def log_calls(ctx, call, next_fn):
            print(f"Calling {call.name}")
            result = next_fn(call)
            print(f"Done {call.name}")
            return result

        result = stack.execute(ctx, call, handler)
    """

    def __init__(self) -> None:
        self._middlewares: list[MiddlewareFn] = []

    def use(self, fn: MiddlewareFn) -> MiddlewareFn:
        """Register a middleware function. Can be used as a decorator."""
        self._middlewares.append(fn)
        return fn

    def execute(self, ctx: Any, call: MCPCall, handler: Callable[..., Any]) -> Any:
        """Execute the middleware chain, ending with the handler."""
        if not self._middlewares:
            return handler(call)

        def build_next(index: int) -> NextFn:
            if index >= len(self._middlewares):
                return handler
            mw = self._middlewares[index]

            def next_fn(c: MCPCall) -> Any:
                return mw(ctx, c, build_next(index + 1))

            return next_fn

        first = self._middlewares[0]
        return first(ctx, call, build_next(1))
