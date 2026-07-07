"""Contract proof for the headless Context example."""

from __future__ import annotations

import runpy
from pathlib import Path

_APP_PATH = Path(__file__).parents[1] / "examples" / "ctxdemo" / "app.py"


def test_hosted_deploy_captures_output_and_uses_approval_store(capsys) -> None:
    hosted_deploy = runpy.run_path(str(_APP_PATH))["hosted_deploy"]

    approved, approved_output = hosted_deploy("api", approved=True)
    rejected, rejected_output = hosted_deploy("worker", approved=False)

    assert approved == {
        "action": "deployed",
        "service": "api",
        "environment": "production",
    }
    assert "info: Deploying api to production" in approved_output
    assert "OK: Deployed api to production" in approved_output
    assert rejected == {"action": "aborted", "service": "worker"}
    assert "warning: Aborted by user" in rejected_output
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
