"""llms.txt generation from CLI command definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from milo.commands import CLI


def generate_llms_txt(cli: CLI) -> str:
    """Generate llms.txt content from a CLI's registered commands.

    Follows the llms.txt specification (https://llmstxt.org/).
    Output is a curated Markdown document that helps AI agents
    discover what the CLI can do.
    """
    lines: list[str] = []

    # Title
    lines.append(f"# {cli.name}")
    lines.append("")

    # Description
    if cli.description:
        lines.append(f"> {cli.description}")
        lines.append("")

    # Version
    if cli.version:
        lines.append(f"Version: {cli.version}")
        lines.append("")

    # Group commands by tag
    tagged: dict[str, list] = {}
    untagged: list = []

    for cmd in cli.commands.values():
        if cmd.hidden:
            continue
        if cmd.tags:
            for tag in cmd.tags:
                tagged.setdefault(tag, []).append(cmd)
        else:
            untagged.append(cmd)

    # Untagged commands
    if untagged:
        lines.append("## Commands")
        lines.append("")
        lines.extend(_format_command(cmd) for cmd in untagged)
        lines.append("")

    # Tagged groups
    for tag, cmds in sorted(tagged.items()):
        title = tag.replace("-", " ").replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(_format_command(cmd) for cmd in cmds)
        lines.append("")

    return "\n".join(lines)


def _format_command(cmd) -> str:
    """Format a single command as an llms.txt entry."""
    parts = [f"- **{cmd.name}**"]

    if cmd.aliases:
        parts.append(f" ({', '.join(cmd.aliases)})")

    parts.append(f": {cmd.description}" if cmd.description else "")

    # Parameter summary
    props = cmd.schema.get("properties", {})
    required = set(cmd.schema.get("required", []))
    if props:
        params = []
        for name, schema in props.items():
            param_type = schema.get("type", "string")
            if name in required:
                params.append(f"`--{name}` ({param_type}, required)")
            else:
                params.append(f"`--{name}` ({param_type})")
        parts.append("\n  Parameters: " + ", ".join(params))

    return "".join(parts)
