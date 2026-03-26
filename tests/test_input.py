"""Tests for input module — escape sequences, key parsing, platform, reader."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from milo._types import Key, SpecialKey
from milo.input._sequences import CTRL_CHARS, ESCAPE_SEQUENCES


class TestEscapeSequences:
    def test_arrow_keys(self):
        assert ESCAPE_SEQUENCES["\x1b[A"] == Key(name=SpecialKey.UP)
        assert ESCAPE_SEQUENCES["\x1b[B"] == Key(name=SpecialKey.DOWN)
        assert ESCAPE_SEQUENCES["\x1b[C"] == Key(name=SpecialKey.RIGHT)
        assert ESCAPE_SEQUENCES["\x1b[D"] == Key(name=SpecialKey.LEFT)

    def test_function_keys(self):
        assert ESCAPE_SEQUENCES["\x1bOP"] == Key(name=SpecialKey.F1)
        assert ESCAPE_SEQUENCES["\x1bOQ"] == Key(name=SpecialKey.F2)

    def test_special_keys(self):
        assert ESCAPE_SEQUENCES["\r"] == Key(name=SpecialKey.ENTER)
        assert ESCAPE_SEQUENCES["\t"] == Key(name=SpecialKey.TAB)
        assert ESCAPE_SEQUENCES["\x7f"] == Key(name=SpecialKey.BACKSPACE)

    def test_modifier_keys(self):
        assert ESCAPE_SEQUENCES["\x1b[1;2A"] == Key(name=SpecialKey.UP, shift=True)
        assert ESCAPE_SEQUENCES["\x1b[1;3A"] == Key(name=SpecialKey.UP, alt=True)
        assert ESCAPE_SEQUENCES["\x1b[1;5A"] == Key(name=SpecialKey.UP, ctrl=True)

    def test_nav_keys(self):
        assert ESCAPE_SEQUENCES["\x1b[H"] == Key(name=SpecialKey.HOME)
        assert ESCAPE_SEQUENCES["\x1b[F"] == Key(name=SpecialKey.END)
        assert ESCAPE_SEQUENCES["\x1b[5~"] == Key(name=SpecialKey.PAGE_UP)
        assert ESCAPE_SEQUENCES["\x1b[6~"] == Key(name=SpecialKey.PAGE_DOWN)


class TestCtrlChars:
    def test_ctrl_a(self):
        assert CTRL_CHARS[1] == "a"

    def test_ctrl_c(self):
        assert CTRL_CHARS[3] == "c"

    def test_ctrl_z(self):
        assert CTRL_CHARS[26] == "z"

    def test_range(self):
        assert len(CTRL_CHARS) == 26


# ---------------------------------------------------------------------------
# Platform tests
# ---------------------------------------------------------------------------

class TestIsTty:
    def test_is_tty_true(self):
        from milo.input._platform import is_tty

        with patch("os.isatty", return_value=True):
            assert is_tty(1) is True

    def test_is_tty_false(self):
        from milo.input._platform import is_tty

        with patch("os.isatty", return_value=False):
            assert is_tty(1) is False

    def test_is_tty_no_fd_uses_stdin(self):
        from milo.input._platform import is_tty

        # Patch sys.stdin.fileno to return a fake fd and os.isatty to return True
        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0
        with patch("sys.stdin", mock_stdin), patch("os.isatty", return_value=True):
            result = is_tty()
        assert result is True

    def test_is_tty_stdin_no_fileno(self):
        """If stdin doesn't have fileno (e.g. StringIO), returns False."""
        from milo.input._platform import is_tty

        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = AttributeError("no fileno")
        with patch("sys.stdin", mock_stdin):
            result = is_tty()
        assert result is False

    def test_is_tty_stdin_fileno_raises_value_error(self):
        from milo.input._platform import is_tty

        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = ValueError("closed file")
        with patch("sys.stdin", mock_stdin):
            result = is_tty()
        assert result is False


class TestReadChar:
    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_char_unix(self):
        from milo.input._platform import read_char

        with patch("os.read", return_value=b"a"):
            result = read_char(0)
        assert result == "a"

    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_char_with_fd(self):
        from milo.input._platform import read_char

        with patch("os.read", return_value=b"z"):
            result = read_char(5)
        assert result == "z"

    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_char_uses_stdin_when_no_fd(self):
        from milo.input._platform import read_char

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 99
        with patch("sys.stdin", mock_stdin), patch("os.read", return_value=b"x"):
            result = read_char()
        assert result == "x"


class TestReadAvailable:
    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_available_no_data(self):
        from milo.input._platform import read_available

        with patch("select.select", return_value=([], [], [])):
            result = read_available(0)
        assert result == ""

    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_available_some_data(self):
        from milo.input._platform import read_available

        # First two calls return data ready, third returns empty (stops loop)
        select_returns = [([0], [], []), ([0], [], []), ([], [], [])]
        select_iter = iter(select_returns)

        def fake_select(rlist, wlist, xlist, timeout):
            return next(select_iter)

        os_read_returns = iter([b"[", b"A"])

        with patch("select.select", side_effect=fake_select):
            with patch("os.read", side_effect=os_read_returns):
                result = read_available(0)
        assert result == "[A"

    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_read_available_uses_stdin_when_no_fd(self):
        from milo.input._platform import read_available

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 99
        with patch("sys.stdin", mock_stdin):
            with patch("select.select", return_value=([], [], [])):
                result = read_available()
        assert result == ""


class TestRawMode:
    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_raw_mode_restores_settings(self):
        from milo.input._platform import raw_mode

        old_settings = object()

        with patch("termios.tcgetattr", return_value=old_settings), patch("tty.setraw"):
            with patch("termios.tcsetattr") as mock_restore:
                with raw_mode(0):
                    pass
        mock_restore.assert_called_once()

    @pytest.mark.skipif(sys.platform == "win32", reason="unix only")
    def test_raw_mode_restores_on_exception(self):
        from milo.input._platform import raw_mode

        old_settings = object()

        with patch("termios.tcgetattr", return_value=old_settings), patch("tty.setraw"):
            with patch("termios.tcsetattr") as mock_restore:
                try:
                    with raw_mode(0):
                        raise ValueError("test error")
                except ValueError:
                    pass
        mock_restore.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_raw_mode_win32_is_noop(self):
        from milo.input._platform import raw_mode

        with raw_mode(0):
            pass  # Should not raise


# ---------------------------------------------------------------------------
# KeyReader tests
# ---------------------------------------------------------------------------

class TestKeyReader:
    def test_enter_raises_if_not_tty(self):
        from milo._errors import InputError
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=False):
            reader = KeyReader(fd=0)
            with pytest.raises(InputError):
                reader.__enter__()

    def test_read_key_regular_char(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", return_value="h"):
                    reader = KeyReader(fd=0)
                    reader.__enter__()
                    key = reader.read_key()
                    assert key.char == "h"

    def test_read_key_escape_sequence(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", return_value="\x1b"):
                    with patch("milo.input._reader.read_available", return_value="[A"):
                        reader = KeyReader(fd=0)
                        reader.__enter__()
                        key = reader.read_key()
                        assert key.name == SpecialKey.UP

    def test_read_key_escape_alone(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", return_value="\x1b"):
                    with patch("milo.input._reader.read_available", return_value=""):
                        reader = KeyReader(fd=0)
                        reader.__enter__()
                        key = reader.read_key()
                        assert key.name == SpecialKey.ESCAPE

    def test_read_key_alt_char(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                # Alt+x: escape followed by a single printable char
                with patch("milo.input._reader.read_char", return_value="\x1b"):
                    with patch("milo.input._reader.read_available", return_value="x"):
                        reader = KeyReader(fd=0)
                        reader.__enter__()
                        key = reader.read_key()
                        assert key.char == "x"
                        assert key.alt is True

    def test_read_key_ctrl_char(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", return_value="\x01"):  # Ctrl+A
                    reader = KeyReader(fd=0)
                    reader.__enter__()
                    key = reader.read_key()
                    assert key.ctrl is True
                    assert key.char == "a"

    def test_read_key_enter(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", return_value="\r"):
                    reader = KeyReader(fd=0)
                    reader.__enter__()
                    key = reader.read_key()
                    assert key.name == SpecialKey.ENTER

    def test_read_key_oserror_raises_input_error(self):
        from milo._errors import InputError
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                with patch("milo.input._reader.read_char", side_effect=OSError("bad fd")):
                    reader = KeyReader(fd=0)
                    reader.__enter__()
                    with pytest.raises(InputError):
                        reader.read_key()

    def test_closed_reader_raises_stop_iteration(self):
        from milo.input._reader import KeyReader

        reader = KeyReader(fd=0)
        reader._closed = True
        with pytest.raises(StopIteration):
            next(reader)

    def test_exit_sets_closed(self):
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                reader = KeyReader(fd=0)
                reader.__enter__()
                reader.__exit__(None, None, None)
                assert reader._closed is True

    def test_iter_returns_self(self):
        from milo.input._reader import KeyReader

        reader = KeyReader(fd=0)
        assert iter(reader) is reader

    def test_unknown_escape_sequence_returns_escape(self):
        """Unknown multi-byte escape sequence should return ESCAPE key."""
        from milo.input._reader import KeyReader

        with patch("milo.input._reader.is_tty", return_value=True):
            with patch("milo.input._reader.raw_mode") as mock_raw:
                mock_raw.return_value.__enter__ = MagicMock(return_value=None)
                mock_raw.return_value.__exit__ = MagicMock(return_value=False)

                # Unknown multi-byte sequence: \x1b followed by non-printable multi-char
                with patch("milo.input._reader.read_char", return_value="\x1b"):
                    with patch("milo.input._reader.read_available", return_value="\x00\x01"):
                        reader = KeyReader(fd=0)
                        reader.__enter__()
                        key = reader.read_key()
                        assert key.name == SpecialKey.ESCAPE
