"""Markdown help generation for CLI command trees."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from milo._command_defs import CommandDef, LazyCommandDef
    from milo.commands import CLI
    from milo.groups import Group


def generate_help_all(cli: CLI) -> str:
    """Generate a full command tree reference in markdown."""
    lines: list[str] = []
    lines.append(f"# {cli.name}")
    if cli.description:
        lines.append(f"\n{cli.description}")
    if cli.version:
        lines.append(f"\nVersion: {cli.version}")
    lines.append("")

    # Global options
    lines.append("## Global Options\n")
    lines.append("| Flag | Description | Default |")
    lines.append("|------|-------------|---------|")
    lines.append("| `-v, --verbose` | Increase verbosity | `0` |")
    lines.append("| `-q, --quiet` | Suppress non-error output | `false` |")
    lines.append("| `--no-color` | Disable color output | `false` |")
    lines.append("| `-n, --dry-run` | Preview without changes | `false` |")
    lines.append("| `-o, --output FILE` | Write output to file | |")
    for opt in cli._global_options:
        flag = f"`--{opt.name.replace('_', '-')}`"
        if opt.short:
            flag = f"`{opt.short}, --{opt.name.replace('_', '-')}`"
        default = f"`{opt.default}`" if opt.default is not None else ""
        lines.append(f"| {flag} | {opt.description} | {default} |")
    lines.append("")

    # Commands
    if cli._commands:
        lines.append("## Commands\n")
        for cmd in cli._commands.values():
            if cmd.hidden:
                continue
            _format_cmd_markdown(cmd, lines)

    # Groups
    for group in cli._groups.values():
        if group.hidden:
            continue
        _format_group_markdown(group, lines, depth=2)

    return "\n".join(lines)


def _format_cmd_markdown(
    cmd: CommandDef | LazyCommandDef,
    lines: list[str],
    prefix: str = "",
) -> None:
    """Format a single command as markdown."""
    full_name = f"{prefix}{cmd.name}" if prefix else cmd.name
    lines.append(f"### `{full_name}`\n")
    if cmd.description:
        lines.append(f"{cmd.description}\n")
    if cmd.aliases:
        lines.append(f"Aliases: {', '.join(f'`{a}`' for a in cmd.aliases)}\n")

    props = cmd.schema.get("properties", {})
    required: set[Any] = set(cmd.schema.get("required", []))
    if props:
        lines.append("| Option | Type | Required | Default |")
        lines.append("|--------|------|----------|---------|")
        for name, schema in props.items():
            ptype = schema.get("type", "string")
            req = "yes" if name in required else ""
            lines.append(f"| `--{name.replace('_', '-')}` | {ptype} | {req} | |")
        lines.append("")

    if cmd.examples:
        lines.append("**Examples:**\n")
        lines.append("```")
        for ex in cmd.examples:
            lines.append(f"$ {ex.get('command', '')}")
            if ex.get("description"):
                lines.append(f"# {ex['description']}")
        lines.append("```\n")


def _format_group_markdown(
    group: Group,
    lines: list[str],
    depth: int,
) -> None:
    """Format a group and its commands as markdown."""
    heading = "#" * depth
    lines.append(f"{heading} {group.name}\n")
    if group.description:
        lines.append(f"{group.description}\n")

    for cmd in group._commands.values():
        if cmd.hidden:
            continue
        _format_cmd_markdown(cmd, lines, prefix=f"{group.name} ")

    for sub in group._groups.values():
        if sub.hidden:
            continue
        _format_group_markdown(sub, lines, depth=depth + 1)
