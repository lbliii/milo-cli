"""Tests for dev.py — DevServer, file watching, and debouncing."""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from milo.dev import (
    _STYLE_EXTENSIONS,
    DevServer,
    _ChangeBatcher,
    _make_watcher,
    _PollingWatcher,
)

# ---------------------------------------------------------------------------
# Polling watcher
# ---------------------------------------------------------------------------


class TestPollingWatcher:
    def test_detects_new_file(self, tmp_path):
        import threading

        watch_dir = tmp_path / "content"
        watch_dir.mkdir()
        (watch_dir / "existing.txt").write_text("hello")

        detected = []

        def callback(paths):
            detected.extend(paths)

        stop = threading.Event()
        watcher = _PollingWatcher((watch_dir,), poll_interval=0.05)

        thread = threading.Thread(target=watcher.watch, args=(callback, stop), daemon=True)
        thread.start()

        time.sleep(0.1)
        (watch_dir / "new.txt").write_text("world")
        time.sleep(0.2)

        stop.set()
        thread.join(timeout=1)

        names = [p.name for p in detected]
        assert "new.txt" in names

    def test_detects_modified_file(self, tmp_path):
        import threading

        watch_dir = tmp_path / "content"
        watch_dir.mkdir()
        f = watch_dir / "page.txt"
        f.write_text("v1")

        detected = []

        def callback(paths):
            detected.extend(paths)

        stop = threading.Event()
        watcher = _PollingWatcher((watch_dir,), poll_interval=0.05)

        thread = threading.Thread(target=watcher.watch, args=(callback, stop), daemon=True)
        thread.start()

        time.sleep(0.1)
        f.write_text("v2")
        time.sleep(0.2)

        stop.set()
        thread.join(timeout=1)

        names = [p.name for p in detected]
        assert "page.txt" in names

    def test_extension_filter(self, tmp_path):
        import threading

        watch_dir = tmp_path / "assets"
        watch_dir.mkdir()

        detected = []

        def callback(paths):
            detected.extend(paths)

        stop = threading.Event()
        watcher = _PollingWatcher(
            (watch_dir,),
            extensions=frozenset({".css"}),
            poll_interval=0.05,
        )

        thread = threading.Thread(target=watcher.watch, args=(callback, stop), daemon=True)
        thread.start()

        time.sleep(0.1)
        (watch_dir / "style.css").write_text("body {}")
        (watch_dir / "script.js").write_text("alert(1)")
        time.sleep(0.2)

        stop.set()
        thread.join(timeout=1)

        names = [p.name for p in detected]
        assert "style.css" in names
        assert "script.js" not in names

    def test_nonexistent_dir_ignored(self, tmp_path):
        import threading

        detected = []
        stop = threading.Event()
        watcher = _PollingWatcher((tmp_path / "nonexistent",), poll_interval=0.05)

        thread = threading.Thread(target=watcher.watch, args=(lambda p: detected.extend(p), stop), daemon=True)
        thread.start()

        time.sleep(0.15)
        stop.set()
        thread.join(timeout=1)
        assert detected == []


# ---------------------------------------------------------------------------
# Change batcher / debounce
# ---------------------------------------------------------------------------


class TestChangeBatcher:
    def test_batches_rapid_changes(self):
        flushed = []

        batcher = _ChangeBatcher(debounce=0.1)
        batcher.set_callback(lambda paths: flushed.append(list(paths)))

        batcher.add([Path("a.txt")])
        batcher.add([Path("b.txt")])
        batcher.add([Path("c.txt")])

        time.sleep(0.3)

        assert len(flushed) == 1
        names = [p.name for p in flushed[0]]
        assert set(names) == {"a.txt", "b.txt", "c.txt"}

    def test_separate_batches_after_debounce(self):
        flushed = []

        batcher = _ChangeBatcher(debounce=0.05)
        batcher.set_callback(lambda paths: flushed.append(list(paths)))

        batcher.add([Path("first.txt")])
        time.sleep(0.15)
        batcher.add([Path("second.txt")])
        time.sleep(0.15)

        assert len(flushed) == 2


# ---------------------------------------------------------------------------
# Watcher factory
# ---------------------------------------------------------------------------


class TestMakeWatcher:
    def test_falls_back_to_polling(self, tmp_path):
        watcher = _make_watcher((tmp_path,))
        assert watcher is not None


# ---------------------------------------------------------------------------
# DevServer
# ---------------------------------------------------------------------------


class TestDevServer:
    def test_creation(self, tmp_path):
        app = MagicMock()
        dev = DevServer(app, watch_dirs=(str(tmp_path),), debounce=0.05)
        assert dev is not None

    def test_run_calls_app_run(self):
        app = MagicMock()
        app.run.return_value = "final_state"

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"):
            result = server.run()

        assert result == "final_state"
        app.run.assert_called_once()

    def test_run_stops_on_finish(self):
        app = MagicMock()
        app.run.return_value = None

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"):
            server.run()

        assert server._stop.is_set()

    def test_run_stops_even_if_app_raises(self):
        app = MagicMock()
        app.run.side_effect = RuntimeError("crash")

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"), contextlib.suppress(RuntimeError):
            server.run()

        assert server._stop.is_set()

    def test_run_prints_start_message(self, capsys):
        app = MagicMock()
        app.run.return_value = None

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)
        server.run()

        captured = capsys.readouterr()
        assert "dev server started" in captured.err

    def test_style_extensions(self):
        assert ".css" in _STYLE_EXTENSIONS
        assert ".scss" in _STYLE_EXTENSIONS

    def test_smart_reload_css(self, tmp_path):
        """CSS-only changes dispatch @@CSS_RELOAD."""
        dispatched = []

        class FakeStore:
            def dispatch(self, action):
                dispatched.append(action)

        class FakeApp:
            _store = FakeStore()

        dev = DevServer(FakeApp(), watch_dirs=(str(tmp_path),))
        dev._on_changes([Path("style.css")])
        assert dispatched[-1].type == "@@CSS_RELOAD"

    def test_smart_reload_html(self, tmp_path):
        """Non-CSS changes dispatch @@HOT_RELOAD."""
        dispatched = []

        class FakeStore:
            def dispatch(self, action):
                dispatched.append(action)

        class FakeApp:
            _store = FakeStore()

        dev = DevServer(FakeApp(), watch_dirs=(str(tmp_path),))
        dev._on_changes([Path("page.html")])
        assert dispatched[-1].type == "@@HOT_RELOAD"

    def test_smart_reload_mixed(self, tmp_path):
        """Mixed CSS + non-CSS dispatches @@HOT_RELOAD."""
        dispatched = []

        class FakeStore:
            def dispatch(self, action):
                dispatched.append(action)

        class FakeApp:
            _store = FakeStore()

        dev = DevServer(FakeApp(), watch_dirs=(str(tmp_path),))
        dev._on_changes([Path("style.css"), Path("page.html")])
        assert dispatched[-1].type == "@@HOT_RELOAD"

    def test_dispatch_payload_is_filenames(self, tmp_path):
        """Payload should be list of file paths as strings."""
        dispatched = []

        class FakeStore:
            def dispatch(self, action):
                dispatched.append(action)

        class FakeApp:
            _store = FakeStore()

        dev = DevServer(FakeApp(), watch_dirs=(str(tmp_path),))
        dev._on_changes([Path("a.txt"), Path("b.txt")])
        assert isinstance(dispatched[-1].payload, list)
        assert len(dispatched[-1].payload) == 2
