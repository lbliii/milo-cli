"""URL fetcher — sagas for async side effects.

Demonstrates: sagas (Call, Put, Select, Retry), ReducerResult, Quit, tick-based loading.

    uv run python examples/fetcher/app.py
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass, replace

from milo import Action, App, Key, Put, Quit, ReducerResult, Retry, SpecialKey


@dataclass(frozen=True, slots=True)
class State:
    url: str = ""
    status: str = "idle"  # idle | loading | done | error
    status_code: int = 0
    content_length: int = 0
    error_message: str = ""
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
    """Saga: read URL from state, fetch it, dispatch result.

    Uses Retry to automatically retry on transient network errors
    with exponential backoff (up to 3 attempts).
    """
    from milo import Select

    state = yield Select()
    url = state.url
    if not url:
        yield Put(Action("FETCH_ERROR", payload="No URL entered"))
        return
    try:
        result = yield Retry(
            fetch_url,
            args=(url,),
            max_attempts=3,
            backoff="exponential",
            base_delay=0.5,
        )
        yield Put(Action("FETCH_SUCCESS", payload=result))
    except Exception as e:
        yield Put(Action("FETCH_ERROR", payload=str(e)))


def reducer(state: State | None, action: Action) -> State | ReducerResult | Quit:
    if state is None:
        return State()

    match action.type:
        case "@@KEY":
            key: Key = action.payload
            if key.name == SpecialKey.ESCAPE:
                return Quit(state)
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
    app = App.from_dir(
        __file__,
        template="fetcher.kida",
        reducer=reducer,
        initial_state=State(url="https://example.com"),
        tick_rate=0.15,
        exit_template="exit.kida",
    )
    app.run()
