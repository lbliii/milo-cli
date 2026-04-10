"""Tests for milo._child — persistent child process."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from milo._child import ChildProcess


def _make_mock_popen(responses: list[dict]) -> MagicMock:
    """Create a mock Popen that returns JSON-RPC responses line by line."""
    mock = MagicMock()
    mock.poll.return_value = None  # process is alive
    mock.stdin = MagicMock()
    response_lines = [json.dumps(r) + "\n" for r in responses]
    mock.stdout = MagicMock()
    mock.stdout.readline = MagicMock(side_effect=response_lines)
    return mock


class TestChildProcess:
    def test_init(self) -> None:
        child = ChildProcess("test", ["python", "-m", "test"])
        assert child.name == "test"
        assert child._proc is None

    @patch("milo._child.subprocess.Popen")
    def test_ensure_alive_spawns(self, mock_popen_cls: MagicMock) -> None:
        init_response = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}
        mock_proc = _make_mock_popen([init_response])
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["python", "-m", "test"])
        child.ensure_alive()

        mock_popen_cls.assert_called_once()
        assert child._proc is mock_proc
        assert child._initialized is True

    @patch("milo._child.subprocess.Popen")
    def test_send_call(self, mock_popen_cls: MagicMock) -> None:
        init_response = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}
        call_response = {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "greet"}]}}
        mock_proc = _make_mock_popen([init_response, call_response])
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["python", "-m", "test"])
        result = child.send_call("tools/list", {})

        assert result == {"tools": [{"name": "greet"}]}

    @patch("milo._child.subprocess.Popen")
    def test_fetch_tools(self, mock_popen_cls: MagicMock) -> None:
        init_response = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}
        tools_response = {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "add"}]}}
        mock_proc = _make_mock_popen([init_response, tools_response])
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["python", "-m", "test"])
        tools = child.fetch_tools()

        assert tools == [{"name": "add"}]

    def test_is_idle_initially_false(self) -> None:
        child = ChildProcess("test", ["cmd"], idle_timeout=300.0)
        assert child.is_idle() is False

    def test_is_idle_after_timeout(self) -> None:
        child = ChildProcess("test", ["cmd"], idle_timeout=0.0)
        assert child.is_idle() is True

    @patch("milo._child.subprocess.Popen")
    def test_kill(self, mock_popen_cls: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        init_response = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_proc.stdout.readline = MagicMock(return_value=json.dumps(init_response) + "\n")
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["cmd"])
        child.ensure_alive()
        child.kill()

        mock_proc.terminate.assert_called_once()
        assert child._proc is None

    @patch("milo._child.subprocess.Popen")
    def test_auto_reconnect_on_dead_process(self, mock_popen_cls: MagicMock) -> None:
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        call_resp = {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}

        mock_proc1 = _make_mock_popen([init_resp])
        mock_proc2 = _make_mock_popen([init_resp, call_resp])

        mock_popen_cls.side_effect = [mock_proc1, mock_proc2]

        child = ChildProcess("test", ["cmd"])
        child.ensure_alive()

        # Simulate process death
        mock_proc1.poll.return_value = 1

        result = child.send_call("test", {})
        assert result == {"ok": True}
        assert mock_popen_cls.call_count == 2


class TestRequestTimeout:
    def test_default_request_timeout(self) -> None:
        child = ChildProcess("test", ["cmd"])
        assert child.request_timeout == 30.0

    def test_custom_request_timeout(self) -> None:
        child = ChildProcess("test", ["cmd"], request_timeout=10.0)
        assert child.request_timeout == 10.0

    @patch("milo._child.subprocess.Popen")
    def test_per_call_timeout_override(self, mock_popen_cls: MagicMock) -> None:
        """Per-call timeout is passed through to _read_line."""
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        call_resp = {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}
        mock_proc = _make_mock_popen([init_resp, call_resp])
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["cmd"], request_timeout=30.0)
        # Use a per-call timeout — should still work since mock responds instantly
        result = child.send_call("test", {}, timeout=5.0)
        assert result == {"ok": True}


class TestGracefulKill:
    @patch("milo._child.subprocess.Popen")
    def test_graceful_kill_sends_sigterm_first(self, mock_popen_cls: MagicMock) -> None:
        """_graceful_kill sends SIGTERM and waits before escalating."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_proc.stdout.readline = MagicMock(return_value=json.dumps(init_resp) + "\n")
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["cmd"])
        child.ensure_alive()
        child.kill()

        # SIGTERM sent via terminate()
        mock_proc.terminate.assert_called_once()
        # wait() called with grace period
        mock_proc.wait.assert_called_once_with(timeout=5)
        # kill() NOT called because wait() succeeded (no TimeoutExpired)
        mock_proc.kill.assert_not_called()
        assert child._proc is None

    @patch("milo._child.subprocess.Popen")
    def test_graceful_kill_escalates_to_sigkill(self, mock_popen_cls: MagicMock) -> None:
        """If SIGTERM grace period expires, escalate to SIGKILL."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_proc.stdout.readline = MagicMock(return_value=json.dumps(init_resp) + "\n")
        # Simulate: terminate works but wait times out
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["cmd"])
        child.ensure_alive()
        child.kill()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert child._proc is None

    @patch("milo._child.subprocess.Popen")
    def test_graceful_kill_handles_already_dead(self, mock_popen_cls: MagicMock) -> None:
        """If process already exited, _graceful_kill handles ProcessLookupError."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_proc.stdout.readline = MagicMock(return_value=json.dumps(init_resp) + "\n")
        mock_proc.terminate.side_effect = ProcessLookupError
        mock_popen_cls.return_value = mock_proc

        child = ChildProcess("test", ["cmd"])
        child.ensure_alive()
        child.kill()  # Should not raise

        assert child._proc is None

    @patch("milo._child.subprocess.Popen")
    def test_graceful_kill_on_noop_when_no_proc(self, mock_popen_cls: MagicMock) -> None:
        """_graceful_kill is a no-op when _proc is None."""
        child = ChildProcess("test", ["cmd"])
        assert child._proc is None
        child.kill()  # Should not raise
        assert child._proc is None
