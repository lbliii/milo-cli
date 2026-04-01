"""llms.txt generation from CLI command definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from milo.commands import CLI, CommandDef, LazyCommandDef
    from milo.groups import Group


def generate_llms_txt(cli: CLI) -> str:
    """Generate llms.txt content from a CLI's registered commands.

    Follows the llms.txt specification (https://llmstxt.org/).
    Output is a curated Markdown document that helps AI agents
    discover what the CLI can do. Groups produce nested headings.
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
    tagged: dict[str, list[CommandDef | LazyCommandDef]] = {}
    untagged: list[CommandDef | LazyCommandDef] = []

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

    # Command groups
    for group in cli.groups.values():
        if group.hidden:
            continue
        _format_group(group, lines, depth=2)

    # Resources section
    resources = cli.walk_resources()
    if resources:
        lines.append("## Resources")
        lines.append("")
        for _uri, res in resources:
            lines.append(f"- **{res.uri}** ({res.mime_type}): {res.description}")
        lines.append("")

    # Prompts section
    prompts = cli.walk_prompts()
    if prompts:
        lines.append("## Prompts")
        lines.append("")
        for _name, p in prompts:
            args_str = ""
            if p.arguments:
                arg_names = [a.get("name", "?") for a in p.arguments]
                args_str = f" ({', '.join(arg_names)})"
            lines.append(f"- **{p.name}**{args_str}: {p.description}")
        lines.append("")

    # Workflows section (heuristic relationship detection)
    workflows = _detect_workflows(cli)
    if workflows:
        lines.append("## Workflows")
        lines.append("")
        lines.extend(f"- {desc}" for desc in workflows)
        lines.append("")

    return "\n".join(lines)


def _format_group(group: Group, lines: list[str], depth: int) -> None:
    """Format a command group as a section with nested headings."""
    heading = "#" * depth
    title = group.description or group.name.replace("-", " ").replace("_", " ").title()
    lines.append(f"{heading} {title}")
    lines.append("")

    for cmd in group.commands.values():
        if cmd.hidden:
            continue
        lines.append(_format_command(cmd))
    if group.commands:
        lines.append("")

    for sub_group in group.groups.values():
        if sub_group.hidden:
            continue
        _format_group(sub_group, lines, depth=depth + 1)


def _format_command(cmd: CommandDef) -> str:
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

    # Examples
    examples = getattr(cmd, "examples", ())
    if examples:
        parts.append("\n  Examples:")
        for ex in examples:
            args_str = " ".join(f"--{k} {v}" for k, v in ex.items())
            parts.append(f"\n    `{cmd.name} {args_str}`")

    return "".join(parts)


def _detect_workflows(cli: CLI) -> list[str]:
    """Heuristically detect command workflows via output→input parameter overlap."""
    commands = [
        (name, cmd) for name, cmd in cli.walk_commands() if not cmd.hidden
    ]
    # Pre-compute property sets once — O(N) instead of O(N²)
    prop_sets = {
        name: set(cmd.schema.get("properties", {}).keys())
        for name, cmd in commands
    }
    workflows: list[str] = []
    names = list(prop_sets.keys())

    for i, name_a in enumerate(names):
        props_a = prop_sets[name_a]
        if not props_a:
            continue
        for name_b in names[i + 1 :]:
            props_b = prop_sets[name_b]
            overlap = props_a & props_b
            if overlap:
                workflows.append(f"`{name_a}` → `{name_b}` (shared: {', '.join(sorted(overlap))})")

    return workflows
