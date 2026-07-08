"""Same deploy capability composed from Typer and FastMCP."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer
from fastmcp import FastMCP

app = typer.Typer(help="Deploy services")
mcp = FastMCP("deployer")


@app.callback()
def main() -> None:
    """Deploy services from a human-facing CLI."""


@mcp.tool
def deploy(
    environment: str,
    service: str,
    version: str = "latest",
) -> dict[str, str]:
    """Deploy one service version to an environment.

    Args:
        environment: Target environment.
        service: Service to deploy.
        version: Version tag to deploy.
    """
    return {
        "status": "deployed",
        "environment": environment,
        "service": service,
        "version": version,
    }


@app.command("deploy")
def deploy_cli(
    environment: Annotated[str, typer.Option(help="Target environment.")],
    service: Annotated[str, typer.Option(help="Service to deploy.")],
    version: Annotated[str, typer.Option(help="Version tag to deploy.")] = "latest",
) -> None:
    """Deploy one service version to an environment."""
    typer.echo(json.dumps(deploy(environment, service, version), sort_keys=True))


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        sys.argv.remove("--mcp")
        mcp.run()
    else:
        app()
