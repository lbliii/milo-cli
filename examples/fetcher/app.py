"""URL fetcher — sagas for async side effects.

Demonstrates: sagas (Call, Put, Select), ReducerResult, tick-based loading animation.

    uv run python examples/fetcher/app.py
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

from milo import Action, App, Call, Key, Put, ReducerResult, SpecialKey
from milo.templates import get_env


@dataclass(frozen=True, slots=True)
class State:
    url: str = ""
    status: str = "idle"  # idle | loading | done | error
    status_code: int = 0
    content_length: int = 0
    error_message: str = ""
    quit: bool = False
    tick: int = 0


def fetch_url(url: str) -> dict:
    """Fetch a URL and return status info."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {
            "status_code": resp.status,
            "content_length": int(resp.headers.get("Content-Length", 0)),
        }


def fetch_saga():
    """Saga: read URL from state, fetch it, dispatch result."""
    state = yield from _select_state()
    url = state.url
    if not url:
        yield Put(Action("FETCH_ERROR", payload="No URL entered"))
        return
    try:
        result = yield Call(fetch_url, (url,))
        yield Put(Action("FETCH_SUCCESS", payload=result))
    except Exception as e:
        yield Put(Action("FETCH_ERROR", payload=str(e)))


def _select_state():
    from milo import Select

    return (yield Select())


def reducer(state: State | None, action: Action) -> State | ReducerResult:
    if state is None:
        return State()

    match action.type:
        case "@@KEY":
            key: Key = action.payload
            if key.name == SpecialKey.ESCAPE:
                return replace(state, quit=True)
            if key.name == SpecialKey.ENTER and state.status != "loading":
                return ReducerResult(
                    state=replace(state, status="loading", tick=0),
                    sagas=(fetch_saga,),
                )
            if key.name == SpecialKey.BACKSPACE:
                return replace(state, url=state.url[:-1])
            if key.char and key.char.isprintable() and not key.ctrl:
                return replace(state, url=state.url + key.char)
        case "@@TICK":
            if state.status == "loading":
                return replace(state, tick=state.tick + 1)
        case "FETCH_SUCCESS":
            return replace(
                state,
                status="done",
                status_code=action.payload["status_code"],
                content_length=action.payload["content_length"],
            )
        case "FETCH_ERROR":
            return replace(state, status="error", error_message=str(action.payload))

    return state


if __name__ == "__main__":
    from kida import FileSystemLoader

    templates = Path(__file__).parent / "templates"
    env = get_env(loader=FileSystemLoader(str(templates)))

    app = App(
        template="fetcher.txt",
        reducer=reducer,
        initial_state=State(url="https://example.com"),
        tick_rate=0.15,
        env=env,
    )
    final = app.run()
    if final.status == "done":
        print(f"Fetched {final.url}: {final.status_code} ({final.content_length} bytes)")
