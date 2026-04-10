"""Built-in templates and template environment factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_TEMPLATE_DIR = Path(__file__).parent
_default_env: Any = None


def get_env(*, theme: dict | None = None, **kwargs: Any) -> Any:
    """Create a kida Environment with the built-in template loader.

    Returns a kida Environment with a chained loader:
    user templates -> milo built-in templates -> kida components.

    Args:
        theme: Optional dict of ``{name: ThemeStyle}`` overrides.
            When *autoescape* is ``"terminal"`` (the default), a ``style``
            filter and ``theme`` global are registered automatically.
            Pass a custom dict to override the default palette.
        **kwargs: Forwarded to ``kida.Environment``.
    """
    global _default_env

    # Return cached singleton when called with default args
    if theme is None and not kwargs and _default_env is not None:
        return _default_env

    from kida import Environment, FileSystemLoader

    loaders = []

    # User-provided loader
    if "loader" in kwargs:
        user_loader = kwargs.pop("loader")
        if user_loader is not None:
            loaders.append(user_loader)

    # Built-in milo templates
    loaders.append(FileSystemLoader(str(_TEMPLATE_DIR)))

    if len(loaders) == 1:
        loader = loaders[0]
    else:
        from kida import ChoiceLoader

        loader = ChoiceLoader(loaders)

    kwargs.setdefault("autoescape", "terminal")
    env = Environment(loader=loader, **kwargs)

    # Register theme system when in terminal mode
    if kwargs.get("autoescape", "terminal") == "terminal":
        from milo.theme import DEFAULT_THEME, ThemeProxy, make_style_filter

        resolved_theme = theme if theme is not None else DEFAULT_THEME

        # Use kida's terminal_color capability flag
        color = env.terminal_color is True

        env.globals["theme"] = ThemeProxy(resolved_theme, color=color)
        env._filters["style"] = make_style_filter(resolved_theme, color=color)

    # Cache as default singleton when called with default args
    if theme is None and not kwargs:
        _default_env = env

    return env
