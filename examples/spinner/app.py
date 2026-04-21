"""Multi-fetch spinner — Cmd, Batch, TickCmd, ViewState, message filter.

Demonstrates the Bubbletea-inspired patterns: lightweight Cmd thunks
instead of sagas, Batch for concurrent effects, TickCmd for self-sustaining
animation, ViewState for declarative terminal control, and a message
filter to block quit during loading.

    uv run python examples/spinner/app.py
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass, replace

from milo import (
    Action,
    App,
    Batch,
    Cmd,
    Key,
    Quit,
    ReducerResult,
    SpecialKey,
    TickCmd,
    ViewState,
)
from milo.live import Spinner

SPINNER = Spinner.BRAILLE

URLS = (
    "https://example.com",
    "https://httpbin.org/status/200",
    "https://httpbin.org/status/404",
)


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class State:
    status: str = "idle"  # idle | loading | done
    results: tuple[FetchResult, ...] = ()
    tick: int = 0


def make_fetch_cmd(url: str):
    """Create a Cmd that fetches a URL and returns the result."""

    def fetch():
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return Action("FETCH_DONE", payload=FetchResult(url=url, status=resp.status))
        except Exception as e:
            return Action("FETCH_DONE", payload=FetchResult(url=url, error=str(e)))

    return Cmd(fetch)


def block_quit_while_loading(state, action):
    """Message filter: ignore Ctrl+C while fetches are in-flight."""
    if action.type == "@@QUIT" and isinstance(state, State) and state.status == "loading":
        return None
    return action


def reducer(state: State | None, action: Action) -> State | ReducerResult | Quit:
    if state is None:
        return State()

    match action.type:
        case "@@KEY":
            key: Key = action.payload
            if key.name == SpecialKey.ESCAPE:
                return Quit(state, view=ViewState(cursor_visible=True))
            if key.name == SpecialKey.ENTER and state.status != "loading":
                # Batch-fetch all URLs concurrently + start ticking
                cmds = Batch(tuple(make_fetch_cmd(url) for url in URLS))
                return ReducerResult(
                    replace(state, status="loading", results=(), tick=0),
                    cmds=(cmds, TickCmd(0.08)),
                    view=ViewState(cursor_visible=False, window_title="Fetching..."),
                )

        case "@@TICK":
            if state.status == "loading":
                return ReducerResult(
                    replace(state, tick=state.tick + 1),
                    cmds=(TickCmd(0.08),),  # Keep spinning
                )

        case "FETCH_DONE":
            results = (*state.results, action.payload)
            if len(results) == len(URLS):
                # All done — stop ticking (no TickCmd returned)
                return ReducerResult(
                    replace(state, status="done", results=results),
                    view=ViewState(cursor_visible=True, window_title="Done"),
                )
            return replace(state, results=results)

        case "@@CMD_ERROR":
            return replace(state, status="done")

    return state


if __name__ == "__main__":
    app = App.from_dir(
        __file__,
        template="spinner.kida",
        reducer=reducer,
        initial_state=State(),
        exit_template="exit.kida",
        filter=block_quit_while_loading,
    )
    app.run()
