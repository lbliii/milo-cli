"""File picker — scrollable directory browser with saga-driven I/O.

Demonstrates: scroll viewport, saga for directory reads, frozen tuples,
derived scroll offset, ReducerResult, quit_on combinator, App.from_dir.

    uv run python examples/filepicker/app.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from milo import Action, App, Call, Key, Put, Quit, ReducerResult, SpecialKey

VIEWPORT_HEIGHT = 15


# ---------------------------------------------------------------------------
# Entry dataclass — one per file/directory in the listing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entry:
    name: str
    is_dir: bool = False
    size: int = 0


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class State:
    cwd: str = ""
    entries: tuple[Entry, ...] = ()
    cursor: int = 0
    scroll_offset: int = 0
    selected: str = ""  # non-empty when a file is chosen
    cancelled: bool = False
    loading: bool = True
    error: str = ""


# ---------------------------------------------------------------------------
# Saga — read directory listing
# ---------------------------------------------------------------------------


def read_directory(path: str) -> list[dict]:
    """Read directory contents. Returns list of dicts for each entry."""
    p = Path(path)
    dirs: list[dict] = []
    files: list[dict] = []
    try:
        for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
            try:
                if child.is_dir():
                    dirs.append({"name": child.name, "is_dir": True, "size": 0})
                else:
                    size = child.stat().st_size
                    files.append({"name": child.name, "is_dir": False, "size": size})
            except PermissionError:
                files.append({"name": child.name, "is_dir": False, "size": 0})
    except PermissionError:
        return []
    # Directories first, then files
    return dirs + files


def load_dir_saga():
    """Saga: read cwd from state, list directory, dispatch result."""
    from milo import Select

    state = yield Select()
    cwd = state.cwd
    try:
        result = yield Call(read_directory, (cwd,))
        yield Put(Action("DIR_LOADED", payload=result))
    except Exception as e:
        yield Put(Action("DIR_ERROR", payload=str(e)))


# ---------------------------------------------------------------------------
# Scroll offset derivation
# ---------------------------------------------------------------------------


def derive_scroll_offset(cursor: int, current_offset: int, total: int) -> int:
    """Compute scroll offset so the cursor stays within the viewport."""
    if total <= VIEWPORT_HEIGHT:
        return 0
    # If cursor moved below visible area, scroll down
    if cursor >= current_offset + VIEWPORT_HEIGHT:
        return cursor - VIEWPORT_HEIGHT + 1
    # If cursor moved above visible area, scroll up
    if cursor < current_offset:
        return cursor
    return current_offset


# ---------------------------------------------------------------------------
# Format helpers exposed to template via state
# ---------------------------------------------------------------------------


def format_size(size: int) -> str:
    """Human-readable file size."""
    if size == 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            if unit == "B":
                return f"{size} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


# ---------------------------------------------------------------------------
# Reducer
#
# Note: This reducer handles quit and cursor navigation manually
# because quit sets cancelled=True on state and scroll_offset must
# be derived alongside each cursor move.
# ---------------------------------------------------------------------------


def reducer(state: State | None, action: Action) -> State | ReducerResult | Quit:
    if state is None:
        # Initial state triggers directory load
        cwd = os.getcwd()
        return ReducerResult(
            state=State(cwd=cwd, loading=True),
            sagas=(load_dir_saga,),
        )

    match action.type:
        case "@@KEY":
            key: Key = action.payload

            # Quit
            if key.name == SpecialKey.ESCAPE or key.char == "q":
                return Quit(replace(state, cancelled=True))

            # Navigation
            if key.name == SpecialKey.UP:
                new_cursor = max(0, state.cursor - 1)
                new_offset = derive_scroll_offset(
                    new_cursor, state.scroll_offset, len(state.entries)
                )
                return replace(
                    state, cursor=new_cursor, scroll_offset=new_offset
                )

            if key.name == SpecialKey.DOWN:
                new_cursor = min(len(state.entries) - 1, state.cursor + 1)
                new_offset = derive_scroll_offset(
                    new_cursor, state.scroll_offset, len(state.entries)
                )
                return replace(
                    state, cursor=new_cursor, scroll_offset=new_offset
                )

            # Enter — open directory or select file
            if key.name == SpecialKey.ENTER and state.entries:
                entry = state.entries[state.cursor]
                if entry.is_dir:
                    new_cwd = str(Path(state.cwd) / entry.name)
                    return ReducerResult(
                        state=replace(
                            state,
                            cwd=new_cwd,
                            entries=(),
                            cursor=0,
                            scroll_offset=0,
                            loading=True,
                            error="",
                        ),
                        sagas=(load_dir_saga,),
                    )
                else:
                    selected = str(Path(state.cwd) / entry.name)
                    return Quit(replace(state, selected=selected))

            # Backspace — go up one directory
            if key.name == SpecialKey.BACKSPACE:
                parent = str(Path(state.cwd).parent)
                if parent != state.cwd:
                    return ReducerResult(
                        state=replace(
                            state,
                            cwd=parent,
                            entries=(),
                            cursor=0,
                            scroll_offset=0,
                            loading=True,
                            error="",
                        ),
                        sagas=(load_dir_saga,),
                    )

        case "DIR_LOADED":
            raw: list[dict] = action.payload
            entries = tuple(
                Entry(name=e["name"], is_dir=e["is_dir"], size=e["size"]) for e in raw
            )
            return replace(state, entries=entries, loading=False, error="")

        case "DIR_ERROR":
            return replace(
                state, entries=(), loading=False, error=str(action.payload)
            )

    return state


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App.from_dir(
        __file__,
        template="filepicker.kida",
        reducer=reducer,
        initial_state=State(),
        exit_template="exit.kida",
    )

    # Add format_size as a global so the template can use it
    app._env.globals["format_size"] = format_size
    app._env.globals["viewport_height"] = VIEWPORT_HEIGHT

    app.run()
