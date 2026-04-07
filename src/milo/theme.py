"""Theme system for styled CLI output.

Provides named styles that templates can reference via the ``style`` filter
or the ``theme`` global proxy::

    {{ message | style("primary") }}
    {{ theme.success }}Done!{{ theme.reset }}

CLI applications opt in by passing a theme dict to ``get_env()``::

    from milo.templates import get_env
    from milo.theme import DEFAULT_THEME, ThemeStyle

    env = get_env(theme={
        **DEFAULT_THEME,
        "brand": ThemeStyle(fg="magenta", bold=True),
    })
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_RESET = "\033[0m"

_FG_CODES: dict[str, int] = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    "bright_red": 91,
    "bright_green": 92,
    "bright_yellow": 93,
    "bright_blue": 94,
    "bright_magenta": 95,
    "bright_cyan": 96,
}

_DECO_CODES: dict[str, int] = {
    "bold": 1,
    "dim": 2,
    "italic": 3,
}


@dataclass(frozen=True, slots=True)
class ThemeStyle:
    """A named style mapping to ANSI SGR attributes."""

    fg: str | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False

    def sgr_prefix(self) -> str:
        """Return the SGR escape prefix for this style (no reset)."""
        codes: list[int] = []
        if self.fg and self.fg in _FG_CODES:
            codes.append(_FG_CODES[self.fg])
        if self.bold:
            codes.append(_DECO_CODES["bold"])
        if self.dim:
            codes.append(_DECO_CODES["dim"])
        if self.italic:
            codes.append(_DECO_CODES["italic"])
        if not codes:
            return ""
        return "\033[" + ";".join(str(c) for c in codes) + "m"


DEFAULT_THEME: dict[str, ThemeStyle] = {
    "primary": ThemeStyle(fg="cyan", bold=True),
    "secondary": ThemeStyle(fg="blue"),
    "success": ThemeStyle(fg="green"),
    "error": ThemeStyle(fg="red", bold=True),
    "warning": ThemeStyle(fg="yellow"),
    "muted": ThemeStyle(dim=True),
    "emphasis": ThemeStyle(bold=True),
}


class ThemeProxy:
    """Attribute-access proxy for use as a kida template global.

    In templates::

        {{ theme.primary }}Hello{{ theme.reset }}
        {{ theme.error }}Oops{{ theme.reset }}

    When color is disabled, all attributes return empty strings.
    """

    __slots__ = ("_color", "_theme")

    def __init__(self, theme: dict[str, ThemeStyle], *, color: bool = True) -> None:
        object.__setattr__(self, "_theme", theme)
        object.__setattr__(self, "_color", color)

    def __getattr__(self, name: str) -> str:
        if name == "reset":
            return _RESET if object.__getattribute__(self, "_color") else ""
        theme = object.__getattribute__(self, "_theme")
        if name not in theme:
            msg = f"Unknown theme style: {name!r}. Available: {', '.join(sorted(theme))}"
            raise AttributeError(msg)
        if not object.__getattribute__(self, "_color"):
            return ""
        return theme[name].sgr_prefix()


def make_style_filter(
    theme: dict[str, ThemeStyle],
    *,
    color: bool = True,
) -> Any:
    """Create a ``style`` filter closure bound to a theme.

    Usage in templates::

        {{ "Error!" | style("error") }}
        {{ count | style("primary") }}
    """

    def _filter_style(value: Any, name: str) -> str:
        if not color:
            return str(value)
        if name not in theme:
            msg = f"Unknown theme style: {name!r}. Available: {', '.join(sorted(theme))}"
            raise ValueError(msg)
        style = theme[name]
        prefix = style.sgr_prefix()
        if not prefix:
            return str(value)
        return f"{prefix}{value}{_RESET}"

    return _filter_style
