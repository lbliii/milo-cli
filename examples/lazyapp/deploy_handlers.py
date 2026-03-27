"""Deploy handlers — imported lazily by lazyapp.

These handlers simulate heavy imports (cloud SDKs, etc.) that you
don't want to pay for on every CLI invocation.
"""

from __future__ import annotations


def deploy(target: str, dry_run: bool = False) -> dict:
    """Deploy to the specified environment."""
    action = "Would deploy" if dry_run else "Deploying"
    return {
        "action": action,
        "target": target,
        "dry_run": dry_run,
        "version": "2.2.0",
    }


def rollback(target: str, steps: int = 1) -> dict:
    """Rollback the last N deployments."""
    return {
        "action": "Rolling back",
        "target": target,
        "steps": steps,
        "rolled_back_to": "2.1.0",
    }


def show_logs(target: str = "production", lines: int = 20) -> list[str]:
    """Show recent deployment logs."""
    return [
        f"[{target}] 12:01 Deployed v2.2.0",
        f"[{target}] 12:00 Health check passed",
        f"[{target}] 11:59 Container started",
        f"[{target}] 11:58 Image pulled",
    ]
