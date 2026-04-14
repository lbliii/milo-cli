"""Hot-reload dev server with smart file watching."""

from __future__ import annotations

import contextlib
import sys
import threading
from pathlib import Path
from typing import Any

from milo._types import Action

# ---------------------------------------------------------------------------
# File watcher abstraction
# ---------------------------------------------------------------------------

_STYLE_EXTENSIONS = frozenset({".css", ".scss", ".sass", ".less"})


class _FileWatcher:
    """Base watcher interface."""

    def __init__(
        self,
        dirs: tuple[Path, ...],
        *,
        extensions: frozenset[str] | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self._dirs = dirs
        self._extensions = extensions
        self._poll_interval = poll_interval

    def watch(self, callback: Any, stop_event: threading.Event) -> None:
        raise NotImplementedError


class _PollingWatcher(_FileWatcher):
    """Polling-based watcher (stdlib only, no dependencies)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._mtimes: dict[Path, float] = {}

    def watch(self, callback: Any, stop_event: threading.Event) -> None:
        self._scan_mtimes()
        while not stop_event.is_set():
            stop_event.wait(self._poll_interval)
            if stop_event.is_set():
                break
            changed = self._check_changes()
            if changed:
                callback(changed)

    def _scan_mtimes(self) -> None:
        for d in self._dirs:
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if p.is_file() and self._matches(p):
                    with contextlib.suppress(OSError):
                        self._mtimes[p] = p.stat().st_mtime

    def _check_changes(self) -> list[Path]:
        changed: list[Path] = []
        for d in self._dirs:
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if not p.is_file() or not self._matches(p):
                    continue
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue  # silent: file may vanish between is_file and stat
                if p in self._mtimes:
                    if mtime > self._mtimes[p]:
                        changed.append(p)
                        self._mtimes[p] = mtime
                else:
                    self._mtimes[p] = mtime
                    changed.append(p)
        return changed

    def _matches(self, path: Path) -> bool:
        if self._extensions is None:
            return True
        return path.suffix in self._extensions


class _WatchfilesWatcher(_FileWatcher):
    """Rust-based watcher using the ``watchfiles`` package."""

    def watch(self, callback: Any, stop_event: threading.Event) -> None:
        import watchfiles  # type: ignore[import-untyped,unresolved-import]

        for changes in watchfiles.watch(
            *self._dirs,
            stop_event=stop_event,
            poll_delay_ms=int(self._poll_interval * 1000),
        ):
            changed = [
                Path(path)
                for _change_type, path in changes
                if self._extensions is None or Path(path).suffix in self._extensions
            ]
            if changed:
                callback(changed)


def _make_watcher(
    dirs: tuple[Path, ...],
    *,
    extensions: frozenset[str] | None = None,
    poll_interval: float = 0.5,
) -> _FileWatcher:
    """Try watchfiles first, fall back to polling."""
    try:
        import watchfiles  # type: ignore[import-untyped,unresolved-import]  # noqa: F401

        return _WatchfilesWatcher(dirs, extensions=extensions, poll_interval=poll_interval)
    except ImportError:
        return _PollingWatcher(dirs, extensions=extensions, poll_interval=poll_interval)


# ---------------------------------------------------------------------------
# Change batching / debounce
# ---------------------------------------------------------------------------


class _ChangeBatcher:
    """Collects file changes and flushes them after a debounce window."""

    def __init__(self, debounce: float = 0.1) -> None:
        self._debounce = debounce
        self._pending: list[Path] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._flush_callback: Any = None

    def set_callback(self, callback: Any) -> None:
        self._flush_callback = callback

    def add(self, paths: list[Path]) -> None:
        with self._lock:
            self._pending.extend(paths)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = list(self._pending)
            self._pending.clear()
            self._timer = None
        if paths and self._flush_callback:
            self._flush_callback(paths)


# ---------------------------------------------------------------------------
# DevServer
# ---------------------------------------------------------------------------


class DevServer:
    """Watches templates and content, re-renders on change.

    Tries ``watchfiles`` (Rust-based) for performance, falls back to
    stdlib polling.  Dispatches smart reload actions:

    - ``@@CSS_RELOAD`` for style-only changes
    - ``@@HOT_RELOAD`` for everything else

    Usage::

        dev = DevServer(
            app,
            watch_dirs=("templates", "content", "static"),
            debounce=0.15,
        )
        dev.run()
    """

    def __init__(
        self,
        app: Any,
        *,
        watch_dirs: tuple[str | Path, ...] = (),
        extensions: frozenset[str] | None = None,
        poll_interval: float = 0.5,
        debounce: float = 0.1,
    ) -> None:
        self._app = app
        self._watch_dirs = tuple(Path(d) for d in watch_dirs)
        self._extensions = extensions
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._batcher = _ChangeBatcher(debounce=debounce)
        self._batcher.set_callback(self._on_changes)

    def run(self) -> Any:
        """Run app with hot-reload enabled."""
        watcher = _make_watcher(
            self._watch_dirs,
            extensions=self._extensions,
            poll_interval=self._poll_interval,
        )

        thread = threading.Thread(
            target=watcher.watch,
            args=(self._batcher.add, self._stop),
            daemon=True,
        )
        thread.start()

        sys.stderr.write("[milo] dev server started, watching for changes\n")

        try:
            return self._app.run()
        finally:
            self._stop.set()

    def _on_changes(self, paths: list[Path]) -> None:
        """Dispatch appropriate reload action for changed files."""
        style_only = all(p.suffix in _STYLE_EXTENSIONS for p in paths)
        action_type = "@@CSS_RELOAD" if style_only else "@@HOT_RELOAD"

        for path in paths:
            sys.stderr.write(f"[milo] changed: {path.name}\n")

        try:
            if hasattr(self._app, "_store"):
                filenames = [str(p) for p in paths]
                self._app._store.dispatch(Action(action_type, payload=filenames))
        except Exception as e:
            sys.stderr.write(f"[milo] reload error: {e}\n")
