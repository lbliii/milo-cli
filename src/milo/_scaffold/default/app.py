"""{{name}} — a milo CLI scaffolded by `milo new`.

Run modes:
    uv run python app.py greet --name Alice
    uv run python app.py --llms-txt
    uv run python app.py --mcp
"""

from __future__ import annotations

from milo import CLI

cli = CLI(name="{{name}}", description="What it does", version="0.1")


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
