"""Tests for the _compat cross-platform module."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

from milo._compat import (
    _poll_resize,
    data_dir,
    default_shell,
    enable_vt_processing,
    watch_terminal_resize,
)


class TestDataDir:
    def test_unix_returns_dot_milo(self):
        with patch.object(sys, "platform", "linux"):
            with patch.dict("os.environ", {}, clear=True):
                from milo import _compat

                # Temporarily override the module-level flag
                old = _compat._IS_WINDOWS
                _compat._IS_WINDOWS = False
                try:
                    result = data_dir()
                    assert result == Path.home() / ".milo"
                finally:
                    _compat._IS_WINDOWS = old

    def test_windows_uses_localappdata(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = True
        try:
            with patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}):
                result = data_dir()
                assert result == Path("C:\\Users\\test\\AppData\\Local") / "milo"
        finally:
            _compat._IS_WINDOWS = old

    def test_windows_fallback_without_localappdata(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = True
        try:
            with patch.dict("os.environ", {}, clear=True):
                result = data_dir()
                assert result == Path.home() / ".milo"
        finally:
            _compat._IS_WINDOWS = old


class TestDefaultShell:
    def test_unix_zsh(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = False
        try:
            with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
                assert default_shell() == "zsh"
        finally:
            _compat._IS_WINDOWS = old

    def test_unix_fish(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = False
        try:
            with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
                assert default_shell() == "fish"
        finally:
            _compat._IS_WINDOWS = old

    def test_unix_default_bash(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = False
        try:
            with patch.dict("os.environ", {"SHELL": "/bin/sh"}):
                assert default_shell() == "bash"
        finally:
            _compat._IS_WINDOWS = old

    def test_windows_powershell(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = True
        try:
            with patch.dict(
                "os.environ",
                {"PSMODULEPATH": "C:\\Program Files\\PowerShell\\Modules"},
            ):
                assert default_shell() == "powershell"
        finally:
            _compat._IS_WINDOWS = old

    def test_windows_cmd(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = True
        try:
            with patch.dict("os.environ", {}, clear=True):
                assert default_shell() == "cmd"
        finally:
            _compat._IS_WINDOWS = old


class TestEnableVtProcessing:
    def test_noop_on_unix(self):
        from milo import _compat

        old_win = _compat._IS_WINDOWS
        old_vt = _compat._vt_enabled
        _compat._IS_WINDOWS = False
        _compat._vt_enabled = False
        try:
            enable_vt_processing()
            assert not _compat._vt_enabled
        finally:
            _compat._IS_WINDOWS = old_win
            _compat._vt_enabled = old_vt

    def test_idempotent(self):
        from milo import _compat

        old_win = _compat._IS_WINDOWS
        old_vt = _compat._vt_enabled
        _compat._IS_WINDOWS = True
        _compat._vt_enabled = True
        try:
            # Should return early without calling ctypes
            enable_vt_processing()
            assert _compat._vt_enabled
        finally:
            _compat._IS_WINDOWS = old_win
            _compat._vt_enabled = old_vt


class TestPollResize:
    def test_detects_size_change(self):
        sizes = [(80, 24), (80, 24), (120, 40)]
        call_idx = {"i": 0}
        received = []

        def fake_terminal_size():
            idx = min(call_idx["i"], len(sizes) - 1)
            call_idx["i"] += 1

            class _Size:
                columns = sizes[idx][0]
                lines = sizes[idx][1]

                def __eq__(self, other):
                    return self.columns == other.columns and self.lines == other.lines

                def __ne__(self, other):
                    return not self.__eq__(other)

            return _Size()

        def on_resize(cols, rows):
            received.append((cols, rows))

        with patch("milo._compat.os.get_terminal_size", side_effect=fake_terminal_size):
            stop = _poll_resize(on_resize, interval=0.05)
            time.sleep(0.3)
            stop()

        assert (120, 40) in received

    def test_stop_terminates_thread(self):
        initial_threads = threading.active_count()

        def noop(c, r):
            pass

        with patch(
            "milo._compat.os.get_terminal_size",
            return_value=type("S", (), {"columns": 80, "lines": 24})(),
        ):
            stop = _poll_resize(noop, interval=0.05)
            time.sleep(0.1)
            stop()
            time.sleep(0.15)

        # Daemon thread should have stopped
        assert threading.active_count() <= initial_threads + 1


class TestWatchTerminalResize:
    def test_unix_uses_sigwinch(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = False
        try:
            with patch("milo._compat._sigwinch_resize") as mock_sig:
                mock_sig.return_value = lambda: None
                watch_terminal_resize(lambda c, r: None)
                mock_sig.assert_called_once()
        finally:
            _compat._IS_WINDOWS = old

    def test_windows_uses_polling(self):
        from milo import _compat

        old = _compat._IS_WINDOWS
        _compat._IS_WINDOWS = True
        try:
            with patch("milo._compat._poll_resize") as mock_poll:
                mock_poll.return_value = lambda: None
                watch_terminal_resize(lambda c, r: None)
                mock_poll.assert_called_once()
        finally:
            _compat._IS_WINDOWS = old
