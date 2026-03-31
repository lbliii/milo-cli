"""Tests for the doctor module."""

from __future__ import annotations

import os
from unittest.mock import patch

from milo.commands import CLI


class TestDoctor:
    def test_basic_doctor(self):
        from milo.doctor import run_doctor

        cli = CLI(name="test")

        @cli.command("hello", description="Hello")
        def hello() -> str:
            return "hi"

        report = run_doctor(cli)
        assert report.ok > 0
        assert report.failures == 0

    def test_doctor_missing_env(self):
        from milo.doctor import run_doctor

        cli = CLI(name="test")
        with patch.dict(os.environ, {}, clear=True):
            report = run_doctor(cli, required_env=("NONEXISTENT_VAR_12345",))
            assert report.failures >= 1

    def test_doctor_required_tools(self):
        from milo.doctor import run_doctor

        cli = CLI(name="test")
        report = run_doctor(cli, required_tools=("python3",))
        # python3 should be found
        tool_checks = [c for c in report.checks if c.name.startswith("tool:")]
        assert any(c.status == "ok" for c in tool_checks)

    def test_doctor_missing_tools(self):
        from milo.doctor import run_doctor

        cli = CLI(name="test")
        report = run_doctor(cli, required_tools=("nonexistent_tool_xyz",))
        assert report.failures >= 1

    def test_doctor_custom_check(self):
        from milo.doctor import Check, run_doctor

        cli = CLI(name="test")

        def my_check():
            return Check(name="custom", status="ok", message="All good")

        report = run_doctor(cli, custom_checks=(my_check,))
        assert any(c.name == "custom" for c in report.checks)

    def test_format_report(self):
        from milo.doctor import format_doctor_report, run_doctor

        cli = CLI(name="test")
        report = run_doctor(cli)
        formatted = format_doctor_report(report, color=False)
        assert "passed" in formatted

    def test_doctor_config_check(self, tmp_path):
        from milo.config import ConfigSpec
        from milo.doctor import run_doctor

        cli = CLI(name="test")
        spec = ConfigSpec(sources=("nonexistent_config.toml",))
        report = run_doctor(cli, config_spec=spec)
        config_checks = [c for c in report.checks if c.name.startswith("config:")]
        assert any(c.status == "warn" for c in config_checks)
