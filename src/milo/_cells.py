"""Terminal display-cell width helpers.

Python string length counts code points, but terminals lay text out in display
cells. Box drawing, CJK characters, combining marks, and ANSI escapes all make
``len(text)`` the wrong primitive for fixed-width terminal UI.
"""

from __future__ import annotations

import re
import unicodedata

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(value: object) -> str:
    """Return *value* as text with ANSI SGR/control sequences removed."""
    return _ANSI_RE.sub("", str(value))


def cell_width(value: object) -> int:
    """Return the terminal display-cell width of *value*.

    This intentionally implements the common wcwidth behavior we need without
    adding a runtime dependency: combining/control characters are zero-width,
    fullwidth/wide East Asian characters are two cells, and ambiguous-width
    symbols are treated as one cell for Western terminal defaults.
    """
    width = 0
    for ch in strip_ansi(value):
        category = unicodedata.category(ch)
        if category.startswith("C") or unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def cell_ljust(value: object, width: int, fill: str = " ") -> str:
    """Left-justify *value* to display-cell *width*."""
    text = str(value)
    return text + fill * max(0, width - cell_width(text))


def cell_rjust(value: object, width: int, fill: str = " ") -> str:
    """Right-justify *value* to display-cell *width*."""
    text = str(value)
    return fill * max(0, width - cell_width(text)) + text


def cell_truncate(value: object, width: int, marker: str = "…") -> str:
    """Truncate *value* to display-cell *width*, preserving ANSI-free text."""
    text = strip_ansi(value)
    if cell_width(text) <= width:
        return text
    if width <= 0:
        return ""
    marker_width = cell_width(marker)
    if width <= marker_width:
        return marker[:width]

    budget = width - marker_width
    out: list[str] = []
    used = 0
    for ch in text:
        ch_width = cell_width(ch)
        if used + ch_width > budget:
            break
        out.append(ch)
        used += ch_width
    return "".join(out) + marker


def cell_fit(value: object, width: int, fill: str = " ", marker: str = "…") -> str:
    """Truncate then left-pad *value* so it occupies exactly *width* cells."""
    return cell_ljust(cell_truncate(value, width, marker=marker), width, fill=fill)


def cell_fill(width: int, fill: str = " ") -> str:
    """Return *fill* repeated/truncated to exactly *width* display cells."""
    if width <= 0:
        return ""
    fill_width = cell_width(fill)
    if fill_width <= 0:
        return " " * width
    repeated = str(fill) * ((width // fill_width) + 1)
    return cell_truncate(repeated, width, marker="")


def _rule_tail(width: int, fill: str = "─", tail: str = "╌┄") -> str:
    """Return a fixed-width rule that fades instead of ending abruptly."""
    tail_width = cell_width(tail)
    if width > tail_width + 8:
        return cell_fill(width - tail_width, fill) + tail
    return cell_fill(width, fill)


def rule_line(
    value: object = "",
    width: int = 78,
    left: str = "╭",
    right: str = "╮",
    fill: str = "─",
    tail: str = "",
) -> str:
    """Return a display-cell exact horizontal rule."""
    label = str(value)
    prefix = f"{left}─ {label} " if label else left
    suffix_width = cell_width(right)
    body_width = width - suffix_width
    prefix_width = cell_width(prefix)
    if body_width <= 0:
        return cell_truncate(right, width, marker="")
    if prefix_width > body_width:
        return cell_fit(cell_truncate(prefix, body_width, marker="…"), body_width) + right
    if tail:
        return prefix + _rule_tail(body_width - prefix_width, fill=fill, tail=tail) + right
    return prefix + cell_fill(body_width - prefix_width, fill) + right


def divider_line(value: object = "", width: int = 78) -> str:
    """Return a display-cell exact closed-box divider."""
    return rule_line(value, width=width, left="├", right="┤")


def bottom_rule(value: object = "", width: int = 78) -> str:
    """Return a display-cell exact closed-box bottom rule."""
    return rule_line(value, width=width, left="╰", right="╯")


def frame_line(value: object = "", width: int = 78, left: str = "│", right: str = "│") -> str:
    """Return a display-cell exact framed content row."""
    content_width = width - cell_width(left) - cell_width(right) - 2
    if content_width <= 0:
        return cell_truncate(left + right, width, marker="")
    return f"{left} {cell_fit(value, content_width)} {right}"


def rail_line(value: object = "", width: int = 78, rail: str = "│") -> str:
    """Return a display-cell exact open-card row with one left rail."""
    content_width = width - cell_width(rail) - 1
    if content_width <= 0:
        return cell_truncate(rail, width, marker="")
    return f"{rail} {cell_fit(value, content_width)}"


def open_rule(value: object = "", width: int = 78, corner: str = "╭") -> str:
    """Return a cell-width exact open-card rule with a fading right edge."""
    return rule_line(value, width=width, left=corner, right="", tail="╌┄")


def open_rule_divider(value: object = "", width: int = 78) -> str:
    """Return a cell-width exact open-card section divider."""
    return open_rule(value, width=width, corner="├")


def open_rule_end(value: object = "", width: int = 78) -> str:
    """Return a cell-width exact open-card bottom rule."""
    return open_rule(value, width=width, corner="╰")


def cell_meter(value: int, total: int, width: int = 10, filled: str = "█", empty: str = "░") -> str:
    """Return a display-cell exact meter."""
    if width <= 0:
        return ""
    fill_cells = 0 if total <= 0 else max(0, min(width, round((value / total) * width)))
    return cell_fill(fill_cells, filled) + cell_fill(width - fill_cells, empty)
