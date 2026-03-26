"""Plugin system with hook registry and Store middleware integration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from milo._errors import ErrorCode, PluginError
from milo._types import Action


class HookRegistry:
    """Registry of named hooks that plugins can subscribe to.

    Usage::

        hooks = HookRegistry()
        hooks.define("before_build")
        hooks.define("after_phase", required_args=("phase_name",))

        @hooks.on("before_build")
        def my_plugin(config):
            print("Building with", config)

        # Invoke all listeners
        hooks.invoke("before_build", config=my_config)

        # Freeze after setup (optional but recommended)
        hooks.freeze()

        # Use as Store middleware
        store = Store(reducer, state, middleware=(hooks.as_middleware(),))
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable]] = {}
        self._action_map: dict[str, str] = {}  # action_type -> hook_name
        self._frozen = False
        self._lock = threading.Lock()

    def define(
        self,
        name: str,
        *,
        action_type: str = "",
        description: str = "",
    ) -> None:
        """Define a named hook point.

        Args:
            name: Hook name (e.g., "before_build", "after_phase").
            action_type: If set, this hook fires automatically when
                the Store dispatches an action of this type.
            description: Human-readable description for docs/introspection.
        """
        if self._frozen:
            raise PluginError(
                ErrorCode.PLG_HOOK,
                f"Cannot define hook '{name}' — registry is frozen",
            )
        with self._lock:
            if name not in self._hooks:
                self._hooks[name] = []
            if action_type:
                self._action_map[action_type] = name

    def on(self, hook_name: str) -> Callable:
        """Decorator to register a listener on a hook.

        Usage::

            @hooks.on("before_build")
            def my_listener(config): ...
        """

        def decorator(fn: Callable) -> Callable:
            self.register(hook_name, fn)
            return fn

        return decorator

    def register(self, hook_name: str, fn: Callable) -> None:
        """Register a listener function on a hook."""
        if self._frozen:
            raise PluginError(
                ErrorCode.PLG_HOOK,
                f"Cannot register on hook '{hook_name}' — registry is frozen",
            )
        with self._lock:
            if hook_name not in self._hooks:
                raise PluginError(
                    ErrorCode.PLG_HOOK,
                    f"Unknown hook '{hook_name}'",
                    suggestion=f"Define it first with hooks.define('{hook_name}')",
                )
            self._hooks[hook_name].append(fn)

    def invoke(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke all listeners registered on a hook.

        Returns a list of return values from each listener.
        Listeners are called in registration order.
        """
        with self._lock:
            listeners = list(self._hooks.get(hook_name, []))

        results = []
        for fn in listeners:
            try:
                results.append(fn(**kwargs))
            except Exception as e:
                raise PluginError(
                    ErrorCode.PLG_HOOK,
                    f"Hook '{hook_name}' listener {fn.__name__!r} raised: {e}",
                ) from e
        return results

    def freeze(self) -> None:
        """Freeze the registry — no more defines or registrations."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def hook_names(self) -> tuple[str, ...]:
        """Return all defined hook names."""
        return tuple(self._hooks.keys())

    def listeners(self, hook_name: str) -> tuple[Callable, ...]:
        """Return all listeners for a hook."""
        return tuple(self._hooks.get(hook_name, []))

    def as_middleware(self) -> Callable:
        """Return a Store middleware that fires hooks on matching actions.

        The middleware intercepts actions whose type matches an
        ``action_type`` registered via ``define()``, invokes the
        corresponding hook, and then passes the action through.

        Usage::

            store = Store(reducer, state, middleware=(hooks.as_middleware(),))
        """
        action_map = self._action_map
        registry = self

        def middleware(store_api: Any) -> Callable:
            def wrapper(next_dispatch: Callable) -> Callable:
                def dispatch(action: Action) -> Any:
                    # Fire hook before reducer processes the action
                    hook_name = action_map.get(action.type)
                    if hook_name:
                        registry.invoke(
                            hook_name,
                            action=action,
                            get_state=store_api.get_state
                            if hasattr(store_api, "get_state")
                            else lambda: None,
                        )
                    return next_dispatch(action)

                return dispatch

            return wrapper

        return middleware
