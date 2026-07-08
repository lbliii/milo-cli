"""Same deploy capability projected to CLI, MCP, and llms.txt by Milo."""

from __future__ import annotations

from milo import CLI

cli = CLI(name="deployer", description="Deploy services")


@cli.command("deploy", description="Deploy a service")
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


if __name__ == "__main__":
    cli.run()
