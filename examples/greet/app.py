"""greet — a minimal milo CLI that ships as CLI, MCP tool, and llms.txt.

The simplest possible template for agents: one typed function, three protocols.

Run modes:
    uv run python examples/greet/app.py greet --name Alice
    uv run python examples/greet/app.py --llms-txt
    uv run python examples/greet/app.py --mcp
"""

from __future__ import annotations

from milo import CLI

cli = CLI(name="greet", description="Say hello to someone", version="1.0")


@cli.command("greet", description="Return a greeting")
def greet(name: str, loud: bool = False) -> str:
    """Greet someone by name.

    Args:
        name: The person to greet.
        loud: If true, SHOUT.
    """
    message = f"Hello, {name}!"
    return message.upper() if loud else message


if __name__ == "__main__":
    cli.run()
