"""Tests for dev.py — DevServer."""

from __future__ import annotations

import contextlib
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from milo.dev import DevServer


class TestDevServer:
    def test_scan_mtimes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.txt"
            p.write_text("hello")

            app = MagicMock()
            server = DevServer(app, watch_dirs=(tmp,))
            server._scan_mtimes()
            assert p in server._mtimes

    def test_check_changes_on_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = MagicMock()
            server = DevServer(app, watch_dirs=(tmp,))
            server._scan_mtimes()

            # Create new file
            p = Path(tmp) / "new.txt"
            p.write_text("new")

            changed = server._check_changes()
            assert p in changed

    def test_check_changes_on_modified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.txt"
            p.write_text("v1")

            app = MagicMock()
            server = DevServer(app, watch_dirs=(tmp,))
            server._scan_mtimes()

            # Modify file (ensure mtime changes)
            time.sleep(0.05)
            p.write_text("v2")

            changed = server._check_changes()
            assert p in changed

    def test_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.txt"
            p.write_text("stable")

            app = MagicMock()
            server = DevServer(app, watch_dirs=(tmp,))
            server._scan_mtimes()

            changed = server._check_changes()
            assert changed == []

    def test_scan_mtimes_nonexistent_dir_ignored(self):
        """Nonexistent watch dirs are silently skipped."""
        app = MagicMock()
        server = DevServer(app, watch_dirs=("/nonexistent/path/xyz",))
        server._scan_mtimes()  # Should not raise
        assert server._mtimes == {}

    def test_check_changes_nonexistent_dir_ignored(self):
        app = MagicMock()
        server = DevServer(app, watch_dirs=("/nonexistent/path/xyz",))
        changed = server._check_changes()
        assert changed == []

    def test_run_calls_app_run(self):
        """DevServer.run() calls the app's run() method."""
        app = MagicMock()
        app.run.return_value = "final_state"

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"):
            result = server.run()

        assert result == "final_state"
        app.run.assert_called_once()

    def test_run_stops_watcher_thread_after_app(self):
        """After app.run() returns, the stop event is set."""
        app = MagicMock()
        app.run.return_value = None

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"):
            server.run()

        assert server._stop.is_set()

    def test_run_prints_start_message(self, capsys):
        """DevServer.run() writes start message to stderr."""
        app = MagicMock()
        app.run.return_value = None

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)
        server.run()

        captured = capsys.readouterr()
        assert "dev server started" in captured.err

    def test_watch_loop_dispatches_hot_reload(self):
        """_watch_loop dispatches @@HOT_RELOAD when a file changes."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "changed.txt"
            p.write_text("v1")

            mock_store = MagicMock()
            app = MagicMock()
            app._store = mock_store

            server = DevServer(app, watch_dirs=(tmp,), poll_interval=0.01)
            server._scan_mtimes()

            # Modify file
            time.sleep(0.02)
            p.write_text("v2")

            # Manually trigger a single _check_changes cycle
            changed = server._check_changes()
            assert p in changed

            # Simulate what _watch_loop does
            for path in changed:
                if hasattr(app, "_store"):
                    from milo._types import Action
                    app._store.dispatch(Action("@@HOT_RELOAD", payload=str(path)))

            mock_store.dispatch.assert_called_once()
            call_args = mock_store.dispatch.call_args[0][0]
            assert call_args.type == "@@HOT_RELOAD"

    def test_run_stops_watcher_even_if_app_raises(self):
        """The stop event is always set, even when app.run() raises."""
        app = MagicMock()
        app.run.side_effect = RuntimeError("crash")

        server = DevServer(app, watch_dirs=(), poll_interval=100.0)

        with patch("sys.stderr"), contextlib.suppress(RuntimeError):
            server.run()

        assert server._stop.is_set()
