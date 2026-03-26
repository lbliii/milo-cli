"""Hot-reload dev server."""

from __future__ import annotations

import contextlib
import sys
import threading
from pathlib import Path
from typing import Any

from milo._types import Action


class DevServer:
    """Watches templates and re-renders on change.

    Uses filesystem polling (no watchdog dependency).
    Dispatches @@HOT_RELOAD action on template change.
    """

    def __init__(
        self,
        app: Any,
        *,
        watch_dirs: tuple[str | Path, ...] = (),
        poll_interval: float = 0.5,
    ) -> None:
        self._app = app
        self._watch_dirs = tuple(Path(d) for d in watch_dirs)
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._mtimes: dict[Path, float] = {}

    def run(self) -> Any:
        """Run app with hot-reload enabled."""
        # Initialize mtime cache
        self._scan_mtimes()

        # Start watcher thread
        watcher = threading.Thread(target=self._watch_loop, daemon=True)
        watcher.start()

        sys.stderr.write("[milo] dev server started, watching for template changes\n")

        try:
            return self._app.run()
        finally:
            self._stop.set()

    def _watch_loop(self) -> None:
        """Poll for file changes."""
        while not self._stop.is_set():
            self._stop.wait(self._poll_interval)
            if self._stop.is_set():
                break

            changed = self._check_changes()
            for path in changed:
                sys.stderr.write(f"[milo] reloaded {path.name}\n")
                try:
                    # Dispatch hot reload through the app's store
                    if hasattr(self._app, "_store"):
                        self._app._store.dispatch(Action("@@HOT_RELOAD", payload=str(path)))
                except Exception as e:
                    sys.stderr.write(f"[milo] reload error: {e}\n")

    def _scan_mtimes(self) -> None:
        """Build initial mtime cache."""
        for d in self._watch_dirs:
            if not d.exists():
                continue
            for p in d.rglob("*.txt"):
                with contextlib.suppress(OSError):
                    self._mtimes[p] = p.stat().st_mtime

    def _check_changes(self) -> list[Path]:
        """Check for mtime changes. Returns list of changed paths."""
        changed: list[Path] = []
        for d in self._watch_dirs:
            if not d.exists():
                continue
            for p in d.rglob("*.txt"):
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if p in self._mtimes:
                    if mtime > self._mtimes[p]:
                        changed.append(p)
                        self._mtimes[p] = mtime
                else:
                    self._mtimes[p] = mtime
                    changed.append(p)
        return changed
