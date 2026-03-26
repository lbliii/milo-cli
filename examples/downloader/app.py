"""Parallel downloader — Fork-per-URL saga concurrency.

Demonstrates: Fork, Call, Put, Select, Delay, ReducerResult, Quit,
tick-based spinner animation, and parallel saga execution.

    uv run python examples/downloader/app.py
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

from milo import (
    Action,
    App,
    Call,
    Delay,
    Fork,
    Key,
    Put,
    Quit,
    ReducerResult,
    Select,
    SpecialKey,
)
from milo.templates import get_env

# ---------------------------------------------------------------------------
# URLs to fetch
# ---------------------------------------------------------------------------

URLS: tuple[str, ...] = (
    "https://example.com",
    "https://httpbin.org/status/200",
    "https://httpbin.org/delay/1",
    "https://jsonplaceholder.typicode.com/posts/1",
    "https://httpbin.org/get",
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UrlState:
    """Per-URL download state."""

    url: str = ""
    status: str = "pending"  # pending | fetching | done | error
    status_code: int = 0
    content_length: int = 0
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class State:
    """Root application state."""

    urls: tuple[UrlState, ...] = ()
    phase: str = "ready"  # ready | fetching | done
    tick: int = 0
    start_time: float = 0.0
    elapsed: float = 0.0


# ---------------------------------------------------------------------------
# Side-effect: HTTP HEAD request
# ---------------------------------------------------------------------------


def fetch_url(url: str) -> dict:
    """Fetch a URL via HEAD and return status info."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return {
            "url": url,
            "status_code": resp.status,
            "content_length": int(resp.headers.get("Content-Length", 0)),
        }


# ---------------------------------------------------------------------------
# Sagas
# ---------------------------------------------------------------------------


def fetch_one_saga(url: str):
    """Saga: fetch a single URL, dispatch success or error."""

    def _saga():
        yield Put(Action("URL_FETCHING", payload=url))
        try:
            result = yield Call(fetch_url, (url,))
            yield Put(Action("URL_DONE", payload=result))
        except Exception as e:
            yield Put(Action("URL_ERROR", payload={"url": url, "error": str(e)}))

    return _saga


def fetch_all_saga():
    """Parent saga: Fork a child saga for each URL."""
    state = yield Select()
    for url_state in state.urls:
        yield Fork(fetch_one_saga(url_state.url)())
    # Poll until all URLs are resolved, then mark done
    while True:
        yield Delay(0.2)
        current = yield Select()
        all_resolved = all(
            u.status in ("done", "error") for u in current.urls
        )
        if all_resolved:
            yield Put(Action("ALL_DONE"))
            return


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


def _update_url(urls: tuple[UrlState, ...], target_url: str, **kwargs) -> tuple[UrlState, ...]:
    """Return a new tuple with one UrlState replaced."""
    return tuple(
        replace(u, **kwargs) if u.url == target_url else u
        for u in urls
    )


def reducer(state: State | None, action: Action) -> State | ReducerResult | Quit:
    if state is None:
        return State(
            urls=tuple(UrlState(url=u) for u in URLS),
        )

    match action.type:
        case "@@KEY":
            key: Key = action.payload
            # Quit on Escape or q
            if key.name == SpecialKey.ESCAPE or key.char == "q":
                return Quit(state)
            # Start fetching on Enter (only from ready state)
            if key.name == SpecialKey.ENTER and state.phase == "ready":
                return ReducerResult(
                    state=replace(
                        state,
                        phase="fetching",
                        tick=0,
                        start_time=time.time(),
                    ),
                    sagas=(fetch_all_saga,),
                )

        case "@@TICK":
            new_state = replace(state, tick=state.tick + 1)
            if state.phase == "fetching" and state.start_time > 0:
                new_state = replace(
                    new_state, elapsed=time.time() - state.start_time
                )
            return new_state

        case "URL_FETCHING":
            url = action.payload
            return replace(
                state,
                urls=_update_url(state.urls, url, status="fetching"),
            )

        case "URL_DONE":
            data = action.payload
            return replace(
                state,
                urls=_update_url(
                    state.urls,
                    data["url"],
                    status="done",
                    status_code=data["status_code"],
                    content_length=data["content_length"],
                ),
            )

        case "URL_ERROR":
            data = action.payload
            return replace(
                state,
                urls=_update_url(
                    state.urls,
                    data["url"],
                    status="error",
                    error_message=data["error"],
                ),
            )

        case "ALL_DONE":
            return replace(
                state,
                phase="done",
                elapsed=time.time() - state.start_time if state.start_time else 0.0,
            )

    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from kida import FileSystemLoader

    templates = Path(__file__).parent / "templates"
    env = get_env(loader=FileSystemLoader(str(templates)))

    app = App(
        template="downloader.txt",
        reducer=reducer,
        initial_state=State(urls=tuple(UrlState(url=u) for u in URLS)),
        tick_rate=0.1,
        env=env,
        exit_template="exit.txt",
    )
    app.run()
