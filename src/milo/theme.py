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
    "bright_black": 90,
    "bright_red": 91,
    "bright_green": 92,
    "bright_yellow": 93,
    "bright_blue": 94,
    "bright_magenta": 95,
    "bright_cyan": 96,
    "bright_white": 97,
}

_BG_CODES: dict[str, int] = {
    "black": 40,
    "red": 41,
    "green": 42,
    "yellow": 43,
    "blue": 44,
    "magenta": 45,
    "cyan": 46,
    "white": 47,
    "bright_black": 100,
    "bright_red": 101,
    "bright_green": 102,
    "bright_yellow": 103,
    "bright_blue": 104,
    "bright_magenta": 105,
    "bright_cyan": 106,
    "bright_white": 107,
}

_DECO_CODES: dict[str, int] = {
    "bold": 1,
    "dim": 2,
    "italic": 3,
}


def _parse_hex(color: str) -> tuple[int, int, int]:
    """Parse ``#rrggbb`` into an (r, g, b) tuple."""
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_codes(color: str | int, *, ground: str) -> str:
    """Return the SGR parameter string for a foreground or background color.

    Args:
        color: Named color, 256-color index (int), or ``#rrggbb`` hex string.
        ground: ``"fg"`` or ``"bg"``.

    Returns:
        SGR parameter fragment (e.g. ``"31"`` or ``"38;5;33"`` or ``"38;2;255;102;0"``).
        Empty string if the named color is unknown.
    """
    named_map = _FG_CODES if ground == "fg" else _BG_CODES
    base = 38 if ground == "fg" else 48

    if isinstance(color, int):
        # 256-color: \033[38;5;Nm or \033[48;5;Nm
        return f"{base};5;{color}"

    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        # Truecolor: \033[38;2;r;g;bm or \033[48;2;r;g;bm
        r, g, b = _parse_hex(color)
        return f"{base};2;{r};{g};{b}"

    if isinstance(color, str) and color in named_map:
        return str(named_map[color])

    return ""


@dataclass(frozen=True, slots=True)
class ThemeStyle:
    """A named style mapping to ANSI SGR attributes.

    The ``fg`` and ``bg`` fields accept three formats:

    - **Named color** (str): ``"red"``, ``"bright_cyan"`` — basic 16-color ANSI.
    - **256-color index** (int): ``33`` — extended 256-color palette.
    - **Truecolor hex** (str): ``"#ff6600"`` — 24-bit RGB color.
    """

    fg: str | int | None = None
    bg: str | int | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False

    def sgr_prefix(self) -> str:
        """Return the SGR escape prefix for this style (no reset)."""
        codes: list[str] = []
        if self.fg is not None:
            codes.append(_color_codes(self.fg, ground="fg"))
        if self.bg is not None:
            codes.append(_color_codes(self.bg, ground="bg"))
        if self.bold:
            codes.append(str(_DECO_CODES["bold"]))
        if self.dim:
            codes.append(str(_DECO_CODES["dim"]))
        if self.italic:
            codes.append(str(_DECO_CODES["italic"]))
        # Filter empty strings (unknown named colors)
        codes = [c for c in codes if c]
        if not codes:
            return ""
        return "\033[" + ";".join(codes) + "m"


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
