"""Tests for milo.registry v2 — health check, fingerprint, doctor."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from milo.registry import HealthResult, doctor, fingerprint, health_check


class TestHealthResult:
    def test_frozen(self) -> None:
        r = HealthResult(name="test", reachable=True, latency_ms=10.0)
        with pytest.raises(AttributeError):
            r.name = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        r = HealthResult(name="test", reachable=True, latency_ms=5.0)
        assert r.error == ""
        assert r.stale is False


class TestFingerprint:
    def test_deterministic(self) -> None:
        fp1 = fingerprint(["python", "app.py", "--mcp"], "/home/user/project")
        fp2 = fingerprint(["python", "app.py", "--mcp"], "/home/user/project")
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_different_inputs(self) -> None:
        fp1 = fingerprint(["python", "app.py"], "/home/user/project")
        fp2 = fingerprint(["python", "other.py"], "/home/user/project")
        assert fp1 != fp2


class TestHealthCheck:
    @patch("milo.registry._load")
    def test_not_registered(self, mock_load) -> None:
        mock_load.return_value = {"version": 1, "clis": {}}
        result = health_check("nonexistent")
        assert result.reachable is False
        assert "Not registered" in result.error

    @patch("milo.registry.subprocess.run")
    @patch("milo.registry._load")
    def test_reachable(self, mock_load, mock_run) -> None:
        mock_load.return_value = {
            "version": 1,
            "clis": {
                "myapp": {
                    "command": ["python", "app.py", "--mcp"],
                    "description": "Test app",
                    "version": "1.0.0",
                }
            },
        }
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}})
        mock_run.return_value.stdout = response
        mock_run.return_value.returncode = 0

        result = health_check("myapp")
        assert result.reachable is True
        assert result.latency_ms >= 0

    @patch("milo.registry.subprocess.run")
    @patch("milo.registry._load")
    def test_timeout(self, mock_load, mock_run) -> None:
        import subprocess
        mock_load.return_value = {
            "version": 1,
            "clis": {"myapp": {"command": ["python", "app.py"]}},
        }
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)

        result = health_check("myapp")
        assert result.reachable is False
        assert result.error == "Timeout"


class TestBackwardCompat:
    @patch("milo.registry._load")
    def test_v1_entry_works(self, mock_load) -> None:
        """V1 entries (without project_root/fingerprint) should still work."""
        mock_load.return_value = {
            "version": 1,
            "clis": {
                "old_app": {
                    "command": ["python", "old.py", "--mcp"],
                    "description": "Old app",
                    "version": "0.1.0",
                }
            },
        }
        # health_check should not crash on v1 entries
        with patch("milo.registry.subprocess.run") as mock_run:
            response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
            mock_run.return_value.stdout = response
            result = health_check("old_app")
            assert result.reachable is True
            assert result.stale is False  # no fingerprint to compare


class TestDoctor:
    @patch("milo.registry.list_clis")
    def test_no_clis(self, mock_list) -> None:
        mock_list.return_value = {}
        output = doctor()
        assert "No CLIs registered" in output

    @patch("milo.registry.check_all")
    @patch("milo.registry.list_clis")
    def test_with_clis(self, mock_list, mock_check) -> None:
        mock_list.return_value = {"app1": {}, "app2": {}}
        mock_check.return_value = [
            HealthResult(name="app1", reachable=True, latency_ms=15.0),
            HealthResult(name="app2", reachable=False, latency_ms=0.0, error="Timeout"),
        ]
        output = doctor()
        assert "app1: OK" in output
        assert "app2: FAIL" in output
        assert "1/2 reachable" in output
