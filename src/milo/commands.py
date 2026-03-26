"""CLI application with command decorator and dispatch."""

from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from milo.output import write_output
from milo.schema import function_to_schema


@dataclass(frozen=True, slots=True)
class CommandDef:
    """A registered CLI command."""

    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any]
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    hidden: bool = False


class CLI:
    """Command-line application with typed commands.

    Each @command becomes a CLI subcommand, an MCP tool, and a help entry.

    Usage::

        cli = CLI(name="myapp", description="My tool", version="1.0.0")

        @cli.command("greet", description="Say hello")
        def greet(name: str, loud: bool = False) -> str:
            msg = f"Hello, {name}!"
            return msg.upper() if loud else msg

        cli.run()

    CLI::

        myapp greet --name Alice
        myapp greet --name Alice --loud
        myapp greet --name Alice --format json
        myapp --help
        myapp --llms-txt
        myapp --mcp
    """

    def __init__(
        self,
        *,
        name: str = "",
        description: str = "",
        version: str = "",
    ) -> None:
        self.name = name or "app"
        self.description = description
        self.version = version
        self._commands: dict[str, CommandDef] = {}
        self._alias_map: dict[str, str] = {}

    def command(
        self,
        name: str,
        *,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        tags: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
    ) -> Callable:
        """Register a function as a CLI command.

        The function's type annotations drive:
        - argparse argument generation
        - MCP tool schema
        - help text
        """

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

    @property
    def commands(self) -> dict[str, CommandDef]:
        """All registered commands."""
        return dict(self._commands)

    def get_command(self, name: str) -> CommandDef | None:
        """Look up a command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        resolved = self._alias_map.get(name)
        if resolved:
            return self._commands.get(resolved)
        return None

    def build_parser(self) -> argparse.ArgumentParser:
        """Build argparse parser from registered commands."""
        parser = argparse.ArgumentParser(
            prog=self.name,
            description=self.description,
        )
        if self.version:
            parser.add_argument("--version", action="version", version=f"%(prog)s {self.version}")
        parser.add_argument(
            "--llms-txt",
            action="store_true",
            help="Output llms.txt for AI agent discovery",
        )
        parser.add_argument(
            "--mcp",
            action="store_true",
            help="Run as MCP server (JSON-RPC on stdin/stdout)",
        )

        if self._commands:
            subparsers = parser.add_subparsers(dest="_command")
            for cmd in self._commands.values():
                if cmd.hidden:
                    continue
                sub = subparsers.add_parser(
                    cmd.name,
                    help=cmd.description,
                    aliases=list(cmd.aliases),
                )
                self._add_arguments(sub, cmd)
                sub.add_argument(
                    "--format",
                    choices=["plain", "json", "table"],
                    default="plain",
                    help="Output format (default: plain)",
                )

        return parser

    def _add_arguments(self, parser: argparse.ArgumentParser, cmd: CommandDef) -> None:
        """Add argparse arguments from a command's schema."""
        props = cmd.schema.get("properties", {})
        required = set(cmd.schema.get("required", []))

        sig = inspect.signature(cmd.handler)

        for param_name, param_schema in props.items():
            param = sig.parameters.get(param_name)
            kwargs: dict[str, Any] = {}

            # Determine type
            json_type = param_schema.get("type", "string")
            if json_type == "boolean":
                default = (
                    param.default
                    if param and param.default is not inspect.Parameter.empty
                    else False
                )
                kwargs["action"] = "store_true"
                kwargs["default"] = default
            elif json_type == "integer":
                kwargs["type"] = int
            elif json_type == "number":
                kwargs["type"] = float
            elif json_type == "array":
                kwargs["nargs"] = "*"
                item_type = param_schema.get("items", {}).get("type", "string")
                if item_type == "integer":
                    kwargs["type"] = int
                elif item_type == "number":
                    kwargs["type"] = float
            else:
                kwargs["type"] = str

            # Set default
            if param and param.default is not inspect.Parameter.empty and json_type != "boolean":
                kwargs["default"] = param.default

            # Required vs optional
            if param_name in required and json_type != "boolean":
                kwargs["required"] = True

            flag = f"--{param_name.replace('_', '-')}"
            parser.add_argument(flag, dest=param_name, **kwargs)

    def run(self, argv: list[str] | None = None) -> Any:
        """Parse args and dispatch to the appropriate command."""
        parser = self.build_parser()
        args = parser.parse_args(argv)

        # --llms-txt mode
        if getattr(args, "llms_txt", False):
            from milo.llms import generate_llms_txt

            sys.stdout.write(generate_llms_txt(self))
            return None

        # --mcp mode
        if getattr(args, "mcp", False):
            from milo.mcp import run_mcp_server

            run_mcp_server(self)
            return None

        # Dispatch to command
        cmd_name = getattr(args, "_command", None)
        if not cmd_name:
            parser.print_help()
            return None

        cmd = self.get_command(cmd_name)
        if not cmd:
            parser.print_help()
            return None

        # Extract command arguments
        sig = inspect.signature(cmd.handler)
        kwargs = {}
        for param_name in sig.parameters:
            if hasattr(args, param_name):
                kwargs[param_name] = getattr(args, param_name)

        # Call handler
        result = cmd.handler(**kwargs)

        # Format and output
        fmt = getattr(args, "format", "plain")
        write_output(result, fmt=fmt)

        return result

    def call(self, command_name: str, **kwargs: Any) -> Any:
        """Programmatically call a command by name. Used by MCP server."""
        cmd = self.get_command(command_name)
        if not cmd:
            raise ValueError(f"Unknown command: {command_name!r}")

        sig = inspect.signature(cmd.handler)
        # Filter to only valid parameters
        valid = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return cmd.handler(**valid)
