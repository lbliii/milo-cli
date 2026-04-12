"""Nestable command groups for hierarchical CLI structures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GroupDef:
    """Frozen snapshot of a command group."""

    name: str
    description: str
    commands: dict[str, Any] = field(default_factory=dict)  # str -> CommandDef
    groups: dict[str, GroupDef] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    hidden: bool = False


class Group:
    """A nestable command namespace.

    Usage::

        site = cli.group("site", description="Site operations")

        @site.command("build", description="Build the site")
        def build(output: str = "_site") -> str: ...

        config = site.group("config", description="Config management")

        @config.command("show", description="Show merged config")
        def show() -> dict: ...

    CLI::

        myapp site build --output _site
        myapp site config show
    """

    def __init__(
        self,
        name: str,
        *,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.aliases = tuple(aliases)
        self.hidden = hidden
        self._commands: dict[str, Any] = {}  # str -> CommandDef
        self._alias_map: dict[str, str] = {}
        self._groups: dict[str, Group] = {}
        self._group_alias_map: dict[str, str] = {}

    def command(
        self,
        name: str,
        *,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        tags: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
        examples: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        confirm: str = "",
        display_result: bool = True,
    ) -> Callable:
        """Register a function as a command within this group."""
        from milo.commands import _make_command_def

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            cmd = _make_command_def(
                name,
                func,
                description=description,
                aliases=tuple(aliases),
                tags=tuple(tags),
                hidden=hidden,
                examples=tuple(examples),
                confirm=confirm,
                display_result=display_result,
            )
            self._commands[name] = cmd
            for alias in aliases:
                self._alias_map[alias] = name

            return func

        return decorator

    def lazy_command(
        self,
        name: str,
        import_path: str,
        *,
        description: str = "",
        schema: dict[str, Any] | None = None,
        aliases: tuple[str, ...] | list[str] = (),
        tags: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
        examples: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        confirm: str = "",
        annotations: dict[str, Any] | None = None,
        display_result: bool = True,
    ) -> Any:
        """Register a lazy-loaded command within this group.

        The handler module is not imported until the command is invoked.
        """
        from milo.commands import LazyCommandDef

        cmd = LazyCommandDef(
            name=name,
            import_path=import_path,
            description=description,
            schema=schema,
            aliases=aliases,
            tags=tags,
            hidden=hidden,
            examples=examples,
            confirm=confirm,
            annotations=annotations,
            display_result=display_result,
        )
        self._commands[name] = cmd
        for alias in aliases:
            self._alias_map[alias] = name
        return cmd

    def group(
        self,
        name: str,
        *,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
    ) -> Group:
        """Create and register a sub-group. Returns it for chaining."""
        sub = Group(name, description=description, aliases=aliases, hidden=hidden)
        self._groups[name] = sub
        for alias in aliases:
            self._group_alias_map[alias] = name
        return sub

    def add_group(self, group: Group) -> None:
        """Add an existing Group as a sub-group."""
        self._groups[group.name] = group
        for alias in group.aliases:
            self._group_alias_map[alias] = group.name

    @property
    def commands(self) -> dict[str, Any]:
        """All registered commands in this group."""
        return dict(self._commands)

    @property
    def groups(self) -> dict[str, Group]:
        """All registered sub-groups."""
        return dict(self._groups)

    def get_command(self, name: str) -> Any | None:
        """Look up a command by name or alias within this group."""
        if name in self._commands:
            return self._commands[name]
        resolved = self._alias_map.get(name)
        if resolved:
            return self._commands.get(resolved)
        return None

    def get_group(self, name: str) -> Group | None:
        """Look up a sub-group by name or alias."""
        if name in self._groups:
            return self._groups[name]
        resolved = self._group_alias_map.get(name)
        if resolved:
            return self._groups.get(resolved)
        return None

    def to_def(self) -> GroupDef:
        """Freeze into immutable GroupDef tree."""
        return GroupDef(
            name=self.name,
            description=self.description,
            commands=dict(self._commands),
            groups={n: g.to_def() for n, g in self._groups.items()},
            aliases=self.aliases,
            hidden=self.hidden,
        )

    def format_help(self, prog_prefix: str = "") -> str:
        """Render help from this group's command/group registries.

        Writes rendered help to stdout and returns the output string.
        """
        import sys

        from milo.help import HelpState
        from milo.templates import get_env

        prog = f"{prog_prefix} {self.name}".strip() if prog_prefix else self.name
        commands = tuple(
            [
                {"name": cmd.name, "help": getattr(cmd, "description", "")}
                for cmd in self._commands.values()
                if not getattr(cmd, "hidden", False)
            ]
            + [
                {"name": g.name, "help": g.description}
                for g in self._groups.values()
                if not g.hidden
            ]
        )

        state = HelpState(prog=prog, description=self.description, commands=commands)
        env = get_env()
        template = env.get_template("help.kida")
        output = template.render(state=state)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()
        return output

    def walk_commands(self, prefix: str = ""):
        """Yield (dotted_path, CommandDef) for all commands in this tree."""
        path_prefix = f"{prefix}{self.name}." if prefix else f"{self.name}."
        for cmd in self._commands.values():
            yield (f"{path_prefix}{cmd.name}", cmd)
        for group in self._groups.values():
            yield from group.walk_commands(path_prefix)
