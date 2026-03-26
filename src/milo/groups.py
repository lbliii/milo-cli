"""Nestable command groups for hierarchical CLI structures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from milo.schema import function_to_schema


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
    ) -> Callable:
        """Register a function as a command within this group."""
        from milo.commands import CommandDef

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            schema = function_to_schema(func)
            desc = description or func.__doc__ or ""
            if "\n" in desc:
                desc = desc.strip().split("\n")[0].strip()

            cmd = CommandDef(
                name=name,
                description=desc,
                handler=func,
                schema=schema,
                aliases=tuple(aliases),
                tags=tuple(tags),
                hidden=hidden,
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

    def walk_commands(self, prefix: str = "") -> list[tuple[str, Any]]:
        """Yield (dotted_path, CommandDef) for all commands in this tree."""
        path_prefix = f"{prefix}{self.name}." if prefix else f"{self.name}."
        result = [(f"{path_prefix}{cmd.name}", cmd) for cmd in self._commands.values()]
        for group in self._groups.values():
            result.extend(group.walk_commands(path_prefix))
        return result
