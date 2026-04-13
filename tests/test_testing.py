"""Tests for the testing module itself."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from milo._types import Action, Call, Put
from milo.testing._record import (
    ActionRecord,
    SessionRecording,
    load_recording,
    save_recording,
    state_hash,
)
from milo.testing._replay import replay
from milo.testing._snapshot import assert_renders, assert_saga, assert_state, strip_ansi


class TestStripAnsi:
    def test_basic(self):
        assert strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_no_ansi(self):
        assert strip_ansi("plain text") == "plain text"

    def test_complex(self):
        assert strip_ansi("\x1b[1;32mbold green\x1b[0m") == "bold green"


class TestAssertState:
    def test_passes(self):
        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "inc":
                return state + 1
            return state

        assert_state(reducer, 0, [Action("inc"), Action("inc")], 2)

    def test_fails(self):
        def reducer(state, action):
            return state or 0

        with pytest.raises(AssertionError):
            assert_state(reducer, 0, [Action("inc")], 1)


class TestAssertSaga:
    def test_passes(self):
        def my_saga():
            result = yield Call(fn=len)
            yield Put(Action("done", payload=result))

        gen = my_saga()
        assert_saga(
            gen,
            [
                (Call(fn=len), 5),
                (Put(Action("done", payload=5)), None),
            ],
        )

    def test_fails(self):
        def my_saga():
            yield Put(Action("a"))

        gen = my_saga()
        with pytest.raises(AssertionError):
            assert_saga(gen, [(Put(Action("b")), None)])


class TestStateHash:
    def test_deterministic(self):
        assert state_hash(42) == state_hash(42)

    def test_different(self):
        assert state_hash(42) != state_hash(43)

    def test_length(self):
        assert len(state_hash("test")) == 16


class TestRecording:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"

            records = [
                {
                    "timestamp": 1000.0,
                    "action_type": "@@INIT",
                    "action_payload": None,
                    "state_hash": "abc123",
                },
                {
                    "timestamp": 1001.0,
                    "action_type": "increment",
                    "action_payload": None,
                    "state_hash": "def456",
                },
            ]

            save_recording(path, 0, records, 1, metadata={"version": "0.1.0"})
            loaded = load_recording(path)

            assert len(loaded.records) == 2
            assert loaded.records[0].action.type == "@@INIT"
            assert loaded.records[1].action.type == "increment"
            assert loaded.metadata == {"version": "0.1.0"}

    def test_load_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("")
            with pytest.raises(ValueError, match="Empty or invalid recording file"):
                load_recording(path)

    def test_load_single_line_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.jsonl"
            path.write_text('{"type": "header"}\n')
            with pytest.raises(ValueError, match="at least a header and footer"):
                load_recording(path)


# ---------------------------------------------------------------------------
# assert_renders tests
# ---------------------------------------------------------------------------


class TestAssertRenders:
    def _make_env(self, template_str: str):
        from unittest.mock import MagicMock

        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string(template_str)
        env = MagicMock()
        env.get_template.return_value = tmpl
        return env, tmpl

    def test_returns_rendered_string_no_snapshot(self):
        env, tmpl = self._make_env("hello {{ state }}")
        result = assert_renders("world", tmpl, env=env)
        assert result == "hello world"

    def test_strips_ansi_by_default(self):
        env, tmpl = self._make_env("\x1b[31mred\x1b[0m {{ state }}")
        result = assert_renders("text", tmpl, env=env)
        assert "\x1b" not in result
        assert "red text" in result

    def test_keeps_ansi_when_color_true(self):
        env, tmpl = self._make_env("\x1b[31mred\x1b[0m")
        result = assert_renders("x", tmpl, color=True, env=env)
        assert "\x1b[31m" in result

    def test_creates_snapshot_file_if_not_exists(self):
        env, tmpl = self._make_env("output={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.txt"
            assert_renders("42", tmpl, snapshot=snap, env=env)
            assert snap.exists()
            assert snap.read_text() == "output=42"

    def test_passes_when_snapshot_matches(self):
        env, tmpl = self._make_env("x={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.txt"
            snap.write_text("x=hello")
            # Should not raise
            result = assert_renders("hello", tmpl, snapshot=snap, env=env)
            assert result == "x=hello"

    def test_fails_when_snapshot_mismatch(self):
        env, tmpl = self._make_env("x={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.txt"
            snap.write_text("x=old")
            with pytest.raises(AssertionError, match="Snapshot mismatch"):
                assert_renders("new", tmpl, snapshot=snap, env=env)

    def test_update_overwrites_snapshot(self):
        env, tmpl = self._make_env("x={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.txt"
            snap.write_text("x=old")
            assert_renders("new", tmpl, snapshot=snap, update=True, env=env)
            assert snap.read_text() == "x=new"

    def test_env_var_triggers_update(self):
        env, tmpl = self._make_env("x={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.txt"
            snap.write_text("x=old")
            with patch.dict(os.environ, {"MILO_UPDATE_SNAPSHOTS": "1"}):
                assert_renders("new", tmpl, snapshot=snap, env=env)
            assert snap.read_text() == "x=new"

    def test_creates_parent_dirs_for_snapshot(self):
        env, tmpl = self._make_env("v={{ state }}")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "nested" / "deep" / "snap.txt"
            assert_renders("val", tmpl, snapshot=snap, env=env)
            assert snap.exists()

    def test_with_string_template_uses_env(self):
        env, tmpl = self._make_env("t={{ state }}")
        env.get_template.return_value = tmpl
        result = assert_renders("5", "t.kida", env=env)
        env.get_template.assert_called_with("t.kida")
        assert result == "t=5"

    def test_no_env_creates_default(self):
        """When env=None, assert_renders fetches one from milo.templates."""
        # Use the built-in milo templates — help.txt exists
        # We'll pass a template object to avoid needing template name resolution
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("result={{ state }}")
        result = assert_renders("ok", tmpl)
        assert result == "result=ok"


# ---------------------------------------------------------------------------
# replay() tests
# ---------------------------------------------------------------------------


class TestReplay:
    def _make_recording(self, records_dicts=None):
        """Create a SessionRecording with the given action records."""
        records_dicts = records_dicts or []
        records = tuple(
            ActionRecord(
                timestamp=d["timestamp"],
                action=Action(d["action_type"], d.get("action_payload")),
                state_hash=d["state_hash"],
            )
            for d in records_dicts
        )
        return SessionRecording(
            initial_state=None,
            records=records,
            final_state=None,
            metadata={},
        )

    def test_empty_recording(self):
        recording = self._make_recording()

        def reducer(state, action):
            return state or 0

        result = replay(recording, reducer)
        assert result == 0

    def test_applies_actions(self):
        from milo.testing._record import state_hash as sh

        records = [
            {
                "timestamp": 1000.0,
                "action_type": "inc",
                "action_payload": None,
                "state_hash": sh(1),
            },
            {
                "timestamp": 1001.0,
                "action_type": "inc",
                "action_payload": None,
                "state_hash": sh(2),
            },
        ]
        recording = self._make_recording(records)

        def reducer(state, action):
            if state is None:
                return 0
            if action.type == "inc":
                return state + 1
            return state

        result = replay(recording, reducer, speed=0)
        assert result == 2

    def test_on_state_callback(self):
        from milo.testing._record import state_hash as sh

        records = [
            {
                "timestamp": 1000.0,
                "action_type": "@@INIT",
                "action_payload": None,
                "state_hash": sh(0),
            },
        ]
        recording = self._make_recording(records)

        calls = []

        def reducer(state, action):
            return 0

        def on_state(state, action):
            calls.append((state, action.type))

        replay(recording, reducer, speed=0, on_state=on_state)
        assert len(calls) == 1
        assert calls[0][1] == "@@INIT"

    def test_assert_hashes_passes(self):
        from milo.testing._record import state_hash as sh

        def reducer(state, action):
            return 42

        records = [
            {
                "timestamp": 1000.0,
                "action_type": "@@INIT",
                "action_payload": None,
                "state_hash": sh(42),
            },
        ]
        recording = self._make_recording(records)
        # Should not raise
        replay(recording, reducer, speed=0, assert_hashes=True)

    def test_assert_hashes_fails(self):
        from milo.testing._record import state_hash as sh

        def reducer(state, action):
            return 99  # produces hash for 99

        records = [
            {
                "timestamp": 1000.0,
                "action_type": "@@INIT",
                "action_payload": None,
                "state_hash": sh(0),
            },
        ]
        recording = self._make_recording(records)

        with pytest.raises(AssertionError, match="State hash mismatch"):
            replay(recording, reducer, speed=0, assert_hashes=True)

    def test_load_from_path(self, tmp_path):
        """replay() can load a recording from a file path."""
        import json

        from milo.testing._record import state_hash as sh

        path = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "header", "initial_state": "0", "metadata": {}}),
            json.dumps(
                {
                    "type": "action",
                    "timestamp": 1000.0,
                    "action_type": "@@INIT",
                    "action_payload": None,
                    "state_hash": sh(None),
                }
            ),
            json.dumps({"type": "footer", "final_state": "0"}),
        ]
        path.write_text("\n".join(lines) + "\n")

        def reducer(state, action):
            return state

        result = replay(str(path), reducer, speed=0)
        assert result is None

    def test_reducer_result_object(self):
        """ReducerResult wrapper is handled correctly."""
        from milo._types import ReducerResult
        from milo.testing._record import state_hash as sh

        def reducer(state, action):
            return ReducerResult(state=42)

        records = [
            {
                "timestamp": 1000.0,
                "action_type": "@@INIT",
                "action_payload": None,
                "state_hash": sh(42),
            },
        ]
        recording = self._make_recording(records)
        result = replay(recording, reducer, speed=0)
        assert result == 42
