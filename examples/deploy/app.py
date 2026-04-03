"""Deploy — flagship dual-mode example for milo.

Demonstrates the core milo idea: one command that works as both an
interactive terminal app (when run by a human) and a structured MCP tool
(when called by an AI agent).

Human usage (interactive confirmation flow):

    uv run python examples/deploy/app.py deploy --environment production --service api

AI usage (structured JSON via MCP):

    echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"deploy","arguments":{"environment":"staging","service":"api"}}}' \
      | uv run python examples/deploy/app.py --mcp

Discovery:

    uv run python examples/deploy/app.py --llms-txt
    uv run python examples/deploy/app.py --mcp  # then send initialize + tools/list
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Annotated

from milo import (
    CLI,
    Action,
    App,
    Context,
    Gt,
    MaxLen,
    MinLen,
    Quit,
    SpecialKey,
)
from milo.streaming import Progress

# ---------------------------------------------------------------------------
# Interactive confirmation state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfirmState:
    environment: str = ""
    service: str = ""
    version: str = ""
    confirmed: bool = False


def confirm_reducer(state: ConfirmState | None, action: Action) -> ConfirmState | Quit:
    if state is None:
        return ConfirmState()
    if action.type == "@@KEY":
        key = action.payload
        if key.name == SpecialKey.ENTER:
            return Quit(state=replace(state, confirmed=True))
        if key.name == SpecialKey.ESCAPE or (key.char == "q"):
            return Quit(state=replace(state, confirmed=False), code=1)
    return state


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

cli = CLI(
    name="deployer",
    description="Deploy services to environments. Works as both a human CLI and an AI tool.",
    version="0.2.0",
)


@cli.command(
    "deploy",
    description="Deploy a service to an environment",
    annotations={"destructiveHint": True},
)
def deploy(
    environment: Annotated[str, MinLen(1), MaxLen(50)],
    service: Annotated[str, MinLen(1)],
    version: str = "latest",
    ctx: Context = None,
) -> dict:
    """Deploy a service to the specified environment.

    Args:
        environment: Target environment (dev, staging, production).
        service: Service name to deploy.
        version: Version tag to deploy (default: latest).
    """
    # Interactive mode: show confirmation UI
    if ctx and ctx.is_interactive:
        initial = ConfirmState(
            environment=environment,
            service=service,
            version=version,
        )
        final = ctx.run_app(
            reducer=confirm_reducer,
            template="confirm.kida",
            initial_state=initial,
        )
        if not final.confirmed:
            return {"status": "cancelled", "environment": environment, "service": service}

    # Simulate deployment with progress
    yield Progress(status=f"Preparing {service}", step=0, total=3)
    time.sleep(0.3)

    yield Progress(status=f"Deploying {service} to {environment}", step=1, total=3)
    time.sleep(0.5)

    yield Progress(status="Verifying health checks", step=2, total=3)
    time.sleep(0.2)

    return {
        "status": "deployed",
        "environment": environment,
        "service": service,
        "version": version,
    }


@cli.command(
    "status",
    description="Check deployment status",
    annotations={"readOnlyHint": True},
)
def status(
    environment: Annotated[str, MinLen(1)],
    service: Annotated[str, MinLen(1)],
) -> dict:
    """Check the current deployment status of a service.

    Args:
        environment: Target environment to check.
        service: Service name to check.
    """
    # Simulated status
    return {
        "environment": environment,
        "service": service,
        "version": "latest",
        "status": "healthy",
        "uptime": "2h 15m",
        "replicas": 3,
    }


@cli.command(
    "rollback",
    description="Rollback to previous version",
    annotations={"destructiveHint": True, "idempotentHint": True},
)
def rollback(
    environment: Annotated[str, MinLen(1)],
    service: Annotated[str, MinLen(1)],
    target_version: str = "previous",
    ctx: Context = None,
) -> dict:
    """Rollback a service to a previous version.

    Args:
        environment: Target environment.
        service: Service name to rollback.
        target_version: Version to rollback to (default: previous).
    """
    if ctx and ctx.is_interactive and not ctx.confirm(
        f"Rollback {service} in {environment} to {target_version}?"
    ):
        return {"status": "cancelled"}

    yield Progress(status=f"Rolling back {service}", step=0, total=2)
    time.sleep(0.3)
    yield Progress(status="Verifying rollback", step=1, total=2)
    time.sleep(0.2)

    return {
        "status": "rolled_back",
        "environment": environment,
        "service": service,
        "version": target_version,
    }


@cli.command(
    "environments",
    description="List available environments",
    annotations={"readOnlyHint": True},
)
def environments() -> list[dict]:
    """List all available deployment environments."""
    return [
        {"name": "dev", "status": "active", "region": "us-east-1"},
        {"name": "staging", "status": "active", "region": "us-east-1"},
        {"name": "production", "status": "active", "region": "us-east-1,eu-west-1"},
    ]


@cli.resource("deploy://environments", description="Available deployment environments")
def env_resource() -> list[dict]:
    return environments()


@cli.prompt("deploy-checklist", description="Pre-deployment verification checklist")
def deploy_checklist(environment: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    f"Before deploying to {environment}, verify:\n"
                    f"1. All tests pass on the target branch\n"
                    f"2. Database migrations are ready\n"
                    f"3. Feature flags are configured for {environment}\n"
                    f"4. Monitoring dashboards are set up\n"
                    f"5. Rollback plan is documented"
                ),
            },
        }
    ]


if __name__ == "__main__":
    cli.run()
