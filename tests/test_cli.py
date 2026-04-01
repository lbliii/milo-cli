"""Tests for cli.py — CLI entry point."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from milo.cli import _load_app, main


class TestCli:
    def test_no_args_prints_help(self, capsys):
        main([])
        captured = capsys.readouterr()
        assert "milo" in captured.out

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        from milo import __version__

        assert __version__ in captured.out

    def test_dev_missing_app(self):
        with pytest.raises(SystemExit):
            main(["dev"])

    def test_replay_missing_session(self):
        with pytest.raises(SystemExit):
            main(["replay"])


class TestLoadApp:
    def test_missing_colon_exits(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _load_app("mymodule")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "expected format" in captured.err

    def test_module_not_found_exits(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _load_app("nonexistent_module_xyz:attr")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "could not import" in captured.err

    def test_attribute_not_found_exits(self, capsys):
        # Use a real module but a fake attribute
        with pytest.raises(SystemExit) as exc_info:
            _load_app("os:nonexistent_attr_xyz")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "has no attribute" in captured.err

    def test_loads_real_attribute(self):
        # os:path is a valid module:attr
        result = _load_app("os:path")
        import os

        assert result is os.path

    def test_adds_cwd_to_sys_path(self):
        cwd = str(Path.cwd())
        # Remove cwd if already there to test it gets added
        original_path = sys.path.copy()
        if cwd in sys.path:
            sys.path.remove(cwd)
        try:
            _load_app("os:path")
            assert cwd in sys.path
        finally:
            sys.path[:] = original_path


class TestCmdReplay:
    def _make_session_file(self, tmp_dir: str) -> Path:
        """Create a minimal valid JSONL session file."""
        path = Path(tmp_dir) / "session.jsonl"
        lines = [
            json.dumps({"type": "header", "initial_state": "0", "metadata": {}}),
            json.dumps(
                {
                    "type": "action",
                    "timestamp": 1000.0,
                    "action_type": "@@INIT",
                    "action_payload": None,
                    "state_hash": "abc123",
                }
            ),
            json.dumps({"type": "footer", "final_state": "0"}),
        ]
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_replay_basic(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            session = self._make_session_file(tmp)
            # speed=0 means no sleeping
            main(["replay", str(session), "--speed", "0"])
            captured = capsys.readouterr()
            assert "Replay complete" in captured.out

    def test_replay_with_diff(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            session = self._make_session_file(tmp)
            main(["replay", str(session), "--speed", "0", "--diff"])
            captured = capsys.readouterr()
            assert "@@INIT" in captured.out

    def test_replay_assert_hashes_match(self, capsys):
        """When state hash matches, --assert should print success."""
        from milo.testing._record import state_hash as sh

        def null_reducer(state, action):
            return state

        # Compute hash for None initial state after @@INIT (which returns None)
        init_hash = sh(None)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            lines = [
                json.dumps({"type": "header", "initial_state": "None", "metadata": {}}),
                json.dumps(
                    {
                        "type": "action",
                        "timestamp": 1000.0,
                        "action_type": "@@INIT",
                        "action_payload": None,
                        "state_hash": init_hash,
                    }
                ),
                json.dumps({"type": "footer", "final_state": "None"}),
            ]
            path.write_text("\n".join(lines) + "\n")

            main(["replay", str(path), "--speed", "0", "--assert"])
            captured = capsys.readouterr()
            assert "All state hashes match" in captured.err

    def test_replay_with_reducer(self, capsys):
        """Test replay with a custom reducer loaded via module:attr."""
        with tempfile.TemporaryDirectory() as tmp:
            session = self._make_session_file(tmp)
            # Patch the replay function inside milo.testing._replay
            from unittest.mock import patch as _patch

            with _patch("milo.testing._replay.replay") as mock_replay:
                mock_replay.return_value = "done"
                main(["replay", str(session), "--speed", "0", "--reducer", "os.path:join"])
            mock_replay.assert_called_once()


class TestCmdDev:
    def test_dev_runs_app(self):
        """Test _cmd_dev calls DevServer.run with the loaded app."""
        mock_app = MagicMock()
        mock_app.run.return_value = None

        with patch("milo.cli._load_app", return_value=mock_app):
            with patch("milo.dev.DevServer.run", return_value=None) as mock_run:
                main(["dev", "mymodule:myapp", "--poll", "0.1"])
        mock_run.assert_called_once()
