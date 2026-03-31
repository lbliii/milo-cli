"""Shell completion generation for bash, zsh, and fish."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from milo.commands import CLI


def generate_bash_completion(cli: CLI) -> str:
    """Generate bash completion script."""
    prog = cli.name
    commands = _collect_completions(cli)

    cmd_names = " ".join(commands.keys())
    subcmd_cases = []
    for cmd, info in commands.items():
        flags = " ".join(info["flags"])
        subcmd_cases.append(f'        {cmd}) COMPREPLY=($(compgen -W "{flags}" -- "$cur")) ;;')

    subcmd_block = "\n".join(subcmd_cases)

    return f'''# bash completion for {prog}
# Add to ~/.bashrc: eval "$({prog} --completions bash)"
_{prog}_completions() {{
    local cur prev words cword
    _init_completion || return

    local commands="{cmd_names}"

    if [[ ${{cword}} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "${{commands}}" -- "$cur"))
        return
    fi

    case "${{words[1]}}" in
{subcmd_block}
    esac
}}
complete -F _{prog}_completions {prog}
'''


def generate_zsh_completion(cli: CLI) -> str:
    """Generate zsh completion script."""
    prog = cli.name
    commands = _collect_completions(cli)

    subcmd_lines = []
    for cmd, info in commands.items():
        desc = info.get("description", "").replace("'", "'\\''")
        subcmd_lines.append(f"        '{cmd}:{desc}'")
    subcmd_block = "\n".join(subcmd_lines)

    flag_cases = []
    for cmd, info in commands.items():
        flags = [f"            '{flag}[{info.get('description', '')}]'" for flag in info["flags"]]
        if flags:
            flag_block = "\n".join(flags)
            flag_cases.append(
                f"        {cmd})\n            _arguments \\\n{flag_block}\n            ;;"
            )

    flag_case_block = "\n".join(flag_cases)

    return f"""#compdef {prog}
# Add to ~/.zshrc: eval "$({prog} --completions zsh)"
_{prog}() {{
    local -a commands
    commands=(
{subcmd_block}
    )

    _arguments -C \\
        '1:command:->cmds' \\
        '*::arg:->args'

    case "$state" in
    cmds)
        _describe -t commands 'commands' commands
        ;;
    args)
        case ${{words[1]}} in
{flag_case_block}
        esac
        ;;
    esac
}}
_{prog}
"""


def generate_fish_completion(cli: CLI) -> str:
    """Generate fish completion script."""
    prog = cli.name
    commands = _collect_completions(cli)

    lines = [
        f"# fish completion for {prog}",
        f"# Add to fish config: {prog} --completions fish | source",
    ]

    for cmd, info in commands.items():
        desc = info.get("description", "").replace("'", "\\'")
        lines.append(f"complete -c {prog} -n '__fish_use_subcommand' -a '{cmd}' -d '{desc}'")
        for flag in info["flags"]:
            flag_name = flag.lstrip("-")
            if flag.startswith("--"):
                lines.append(
                    f"complete -c {prog} -n '__fish_seen_subcommand_from {cmd}' -l '{flag_name}'"
                )
            elif flag.startswith("-"):
                lines.append(
                    f"complete -c {prog} -n '__fish_seen_subcommand_from {cmd}' -s '{flag_name}'"
                )

    return "\n".join(lines) + "\n"


def _collect_completions(cli: CLI) -> dict[str, dict[str, Any]]:
    """Collect command names, flags, and descriptions for completions."""
    result: dict[str, dict[str, Any]] = {}

    for path, cmd in cli.walk_commands():
        props = cmd.schema.get("properties", {})
        flags = [f"--{name.replace('_', '-')}" for name in props]
        flags.extend(["--format", "--help"])

        # Include dynamic completion callbacks if registered
        completers: dict[str, Any] = {}
        if hasattr(cmd, "_completers"):
            completers = cmd._completers  # type: ignore[assignment]

        result[path] = {
            "description": cmd.description,
            "flags": flags,
            "completers": completers,
        }

    return result


def install_completions(cli: CLI, shell: str = "") -> str:
    """Generate completion script for the specified shell.

    If shell is empty, auto-detects from $SHELL.
    """
    if not shell:
        shell_path = os.environ.get("SHELL", "")
        if "zsh" in shell_path:
            shell = "zsh"
        elif "fish" in shell_path:
            shell = "fish"
        else:
            shell = "bash"

    generators = {
        "bash": generate_bash_completion,
        "zsh": generate_zsh_completion,
        "fish": generate_fish_completion,
    }

    gen = generators.get(shell)
    if gen is None:
        supported = ", ".join(sorted(generators))
        return f"Unsupported shell: {shell!r}. Supported: {supported}"

    return gen(cli)
