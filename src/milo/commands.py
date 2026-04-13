"""CLI application with command decorator and dispatch."""

from __future__ import annotations

import argparse
import difflib
import inspect
import io
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from milo._command_defs import (
    CommandDef,
    GlobalOption,
    InvokeResult,
    LazyCommandDef,
    LazyImportError,
    PromptDef,
    ResourceDef,
    _is_context_param,
    _make_command_def,
)
from milo.help import HelpRenderer, help_formatter_with_examples
from milo.output import format_output, write_output

if TYPE_CHECKING:
    from milo.context import Context
    from milo.groups import Group
    from milo.middleware import MiddlewareStack

# Re-export for backward compatibility
__all__ = [
    "CLI",
    "CommandDef",
    "GlobalOption",
    "InvokeResult",
    "LazyCommandDef",
    "LazyImportError",
    "PromptDef",
    "ResourceDef",
]


# ---------------------------------------------------------------------------
# Resolve result types — discriminated union for command resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    """A command was found and should be dispatched."""

    command: CommandDef | LazyCommandDef
    fmt: str


@dataclass(frozen=True, slots=True)
class ResolvedGroup:
    """A group was invoked without a subcommand — show its help."""

    group: Group
    fmt: str
    prog: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedNothing:
    """No command or group matched — may offer did-you-mean."""

    attempted: str | None
    fmt: str


ResolveResult = ResolvedCommand | ResolvedGroup | ResolvedNothing


@dataclass(frozen=True, slots=True)
class CommandExecution:
    """Resolved command plus execution metadata."""

    found: CommandDef | LazyCommandDef
    command: CommandDef
    fmt: str
    confirm_msg: str


@dataclass(frozen=True, slots=True)
class BuiltinMode:
    """A built-in top-level mode that does not dispatch a registered command."""

    name: str


class _MiloArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that provides did-you-mean suggestions."""

    _cli_ref: CLI | None = None

    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        """Override to add did-you-mean for invalid subcommand choices."""
        if "invalid choice:" in message and self._cli_ref is not None:
            # Extract the invalid value
            import re

            match = re.search(r"invalid choice: '([^']+)'", message)
            if match:
                typo = match.group(1)
                suggestion = self._cli_ref.suggest_command(typo)
                if suggestion:
                    self.print_usage(sys.stderr)
                    sys.stderr.write(
                        f"{self.prog}: error: unknown command {typo!r}. "
                        f"Did you mean {suggestion!r}?\n"
                    )
                    sys.exit(2)
        super().error(message)


class CLI:
    """Command-line application with typed commands and nested groups.

    Each @command becomes a CLI subcommand, an MCP tool, and a help entry.
    Groups create nested command namespaces.

    Usage::

        cli = CLI(name="myapp", description="My tool", version="1.0.0")

        @cli.command("greet", description="Say hello")
        def greet(name: str, loud: bool = False) -> str:
            msg = f"Hello, {name}!"
            return msg.upper() if loud else msg

        site = cli.group("site", description="Site operations")

        @site.command("build", description="Build the site")
        def build(output: str = "_site") -> str:
            return f"Building to {output}"

        cli.run()

    CLI::

        myapp greet --name Alice
        myapp site build --output _site
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
        self._commands: dict[str, CommandDef | LazyCommandDef] = {}
        self._alias_map: dict[str, str] = {}
        self._groups: dict[str, Group] = {}
        self._group_alias_map: dict[str, str] = {}
        self._global_options: list[GlobalOption] = []
        self._resources: dict[str, ResourceDef] = {}
        self._prompts: dict[str, PromptDef] = {}
        self._middleware: MiddlewareStack | None = None
        self._before_command: list[Callable] = []
        self._after_command: list[Callable] = []
        self._command_version: int = 0
        """Incremented when commands are added or removed; used by MCP cache."""
        self._run_called: bool = False
        """Set to True after run() is called; used for dev warnings."""

    def global_option(
        self,
        name: str,
        *,
        short: str = "",
        option_type: type = str,
        default: Any = None,
        description: str = "",
        is_flag: bool = False,
    ) -> None:
        """Register a global option available to all commands via Context.

        Usage::

            cli.global_option("environment", short="-e", default="local",
                              description="Config environment")
        """
        # Warn if global option name shadows a command
        if name in self._commands or name.replace("_", "-") in self._commands:
            import warnings

            warnings.warn(
                f"Global option {name!r} shadows a command with the same name. "
                f"This may cause unexpected behavior.",
                UserWarning,
                stacklevel=2,
            )
        self._global_options.append(
            GlobalOption(
                name=name,
                short=short,
                option_type=option_type,
                default=default,
                description=description,
                is_flag=is_flag,
            )
        )

    def before_command(self, fn: Callable) -> Callable:
        """Register a hook that runs before every command.

        The hook receives (ctx, command_name, kwargs) and can modify kwargs.

        Usage::

            @cli.before_command
            def check_auth(ctx, command_name, kwargs):
                if not os.environ.get("API_KEY"):
                    raise SystemExit("API_KEY not set")
        """
        self._before_command.append(fn)
        return fn

    def after_command(self, fn: Callable) -> Callable:
        """Register a hook that runs after every command.

        The hook receives (ctx, command_name, result).

        Usage::

            @cli.after_command
            def log_result(ctx, command_name, result):
                ctx.log(f"{command_name} completed", level=1)
        """
        self._after_command.append(fn)
        return fn

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
        annotations: dict[str, Any] | None = None,
        display_result: bool = True,
    ) -> Callable:
        """Register a function as a CLI command.

        The function's type annotations drive:
        - argparse argument generation
        - MCP tool schema
        - help text

        Args:
            confirm: If set, prompt user with this message before executing.
            annotations: MCP tool annotations (readOnlyHint, destructiveHint,
                idempotentHint, openWorldHint).
            display_result: If False, suppress plain-format output while still
                returning data for ``--format json`` or ``--output-file``.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if self._run_called:
                import warnings

                warnings.warn(
                    f"Command {name!r} registered after cli.run() was called. "
                    f"It won't be available in this invocation.",
                    UserWarning,
                    stacklevel=2,
                )
            cmd = _make_command_def(
                name,
                func,
                description=description,
                aliases=tuple(aliases),
                tags=tuple(tags),
                hidden=hidden,
                examples=tuple(examples),
                confirm=confirm,
                annotations=annotations,
                display_result=display_result,
            )
            self._commands[name] = cmd
            for alias in aliases:
                self._alias_map[alias] = name
            self._command_version += 1

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
    ) -> LazyCommandDef:
        """Register a lazy-loaded command.

        The handler module is not imported until the command is invoked.
        This keeps CLI startup fast for large command sets.

        When providing a pre-computed *schema*, include ``"default"`` fields
        in properties for optional parameters so argparse receives the correct
        defaults without importing the handler module.
        """
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
        self._command_version += 1
        return cmd

    def resource(
        self,
        uri: str,
        *,
        name: str = "",
        description: str = "",
        mime_type: str = "text/plain",
    ) -> Callable:
        """Register a function as an MCP resource.

        Usage::

            @cli.resource("config://app", description="App config")
            def get_config() -> dict: ...
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            resource_name = name or getattr(func, "__name__", repr(func))
            res = ResourceDef(
                uri=uri,
                name=resource_name,
                description=description,
                handler=func,
                mime_type=mime_type,
            )
            self._resources[uri] = res
            return func

        return decorator

    def prompt(
        self,
        name: str,
        *,
        description: str = "",
        arguments: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    ) -> Callable:
        """Register a function as an MCP prompt.

        Usage::

            @cli.prompt("deploy-checklist", description="Pre-deploy steps")
            def checklist(environment: str) -> list[dict]: ...
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Auto-derive arguments from function signature if not provided
            args = tuple(arguments)
            if not args:
                sig = inspect.signature(func)
                derived = []
                for pname, param in sig.parameters.items():
                    arg: dict[str, Any] = {"name": pname}
                    if param.default is not inspect.Parameter.empty:
                        arg["required"] = False
                    else:
                        arg["required"] = True
                    derived.append(arg)
                args = tuple(derived)

            p = PromptDef(
                name=name,
                description=description,
                handler=func,
                arguments=args,
            )
            self._prompts[name] = p
            return func

        return decorator

    def middleware(self, fn: Callable) -> Callable:
        """Register a middleware function.

        Usage::

            @cli.middleware
            def log_calls(ctx, call, next_fn):
                result = next_fn(call)
                return result
        """
        if self._middleware is None:
            from milo.middleware import MiddlewareStack

            self._middleware = MiddlewareStack()
        self._middleware.use(fn)
        return fn

    def group(
        self,
        name: str,
        *,
        description: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
    ) -> Group:
        """Create and register a command group.

        Returns the Group for registering commands within it::

            site = cli.group("site", description="Site operations")

            @site.command("build", description="Build the site")
            def build(output: str = "_site") -> str: ...
        """
        from milo.groups import Group as GroupClass

        grp = GroupClass(name, description=description, aliases=aliases, hidden=hidden)
        self._groups[name] = grp
        for alias in aliases:
            self._group_alias_map[alias] = name
        return grp

    def add_group(self, group: Group) -> None:
        """Register an externally-created Group."""
        self._groups[group.name] = group
        for alias in group.aliases:
            self._group_alias_map[alias] = group.name

    def mount(self, prefix: str, other: CLI) -> None:
        """Mount another CLI as a command group. In-process, no subprocess.

        Usage::

            main = CLI(name="main")
            sub = CLI(name="sub")
            main.mount("sub", sub)
            # sub's commands are now at main.sub.*
        """
        from milo.groups import Group as GroupClass

        grp = GroupClass(prefix, description=other.description)

        # Mount commands
        for cmd_name, cmd in other._commands.items():
            grp._commands[cmd_name] = cmd
            if hasattr(cmd, "aliases"):
                for alias in cmd.aliases:
                    grp._alias_map[alias] = cmd_name

        # Mount sub-groups
        for gname, g in other._groups.items():
            grp._groups[gname] = g
            for alias in g.aliases:
                grp._group_alias_map[alias] = gname

        self._groups[prefix] = grp

        # Mount resources with prefix
        for uri, res in other._resources.items():
            prefixed_uri = f"{prefix}/{uri}"
            self._resources[prefixed_uri] = ResourceDef(
                uri=prefixed_uri,
                name=res.name,
                description=res.description,
                handler=res.handler,
                mime_type=res.mime_type,
            )

        # Mount prompts with prefix
        for pname, p in other._prompts.items():
            prefixed_name = f"{prefix}.{pname}"
            self._prompts[prefixed_name] = PromptDef(
                name=prefixed_name,
                description=p.description,
                handler=p.handler,
                arguments=p.arguments,
            )

    @property
    def commands(self) -> dict[str, CommandDef | LazyCommandDef]:
        """All registered top-level commands (eager and lazy)."""
        return dict(self._commands)

    @property
    def groups(self) -> dict[str, Group]:
        """All registered top-level groups."""
        return dict(self._groups)

    def get_command(self, name: str) -> CommandDef | LazyCommandDef | None:
        """Look up a command by name, alias, or dotted path.

        Dotted paths traverse groups: ``get_command("site.build")``
        resolves to the ``build`` command inside the ``site`` group.
        """
        # Dotted path: walk into groups
        if "." in name:
            return self._resolve_dotted(name)

        # Top-level command
        if name in self._commands:
            return self._commands[name]
        resolved = self._alias_map.get(name)
        if resolved:
            return self._commands.get(resolved)
        return None

    def _resolve_dotted(self, path: str) -> CommandDef | LazyCommandDef | None:
        """Resolve a dotted command path like 'site.config.show'."""
        parts = path.split(".")
        # Walk groups for all but the last part
        current_group: Group | None = None
        for part in parts[:-1]:
            if current_group is None:
                current_group = self._groups.get(part)
                if current_group is None:
                    resolved = self._group_alias_map.get(part)
                    if resolved:
                        current_group = self._groups.get(resolved)
            else:
                current_group = current_group.get_group(part)
            if current_group is None:
                return None

        # Resolve the final part as a command
        cmd_name = parts[-1]
        if current_group is None:
            return self.get_command(cmd_name)
        return current_group.get_command(cmd_name)

    def walk_commands(self):
        """Yield all commands in the tree as (dotted_path, CommandDef) tuples.

        Top-level commands have simple names. Group commands use dots::

            [("greet", greet_cmd), ("site.build", build_cmd), ...]
        """
        for cmd in self._commands.values():
            yield (cmd.name, cmd)
        for group in self._groups.values():
            yield from group.walk_commands()

    def walk_resources(self) -> list[tuple[str, ResourceDef]]:
        """Walk all registered resources."""
        return list(self._resources.items())

    def walk_prompts(self) -> list[tuple[str, PromptDef]]:
        """Walk all registered prompts."""
        return list(self._prompts.items())

    def build_parser(self) -> argparse.ArgumentParser:
        """Build argparse parser from registered commands and groups."""
        parser = _MiloArgumentParser(
            prog=self.name,
            description=self.description,
            formatter_class=HelpRenderer,
        )
        parser._cli_ref = self
        if self.version:
            parser.add_argument(
                "--version", action="version", version=f"{self.name} {self.version}"
            )
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
        parser.add_argument(
            "--mcp-install",
            action="store_true",
            help="Register this CLI in the milo gateway for AI agent discovery",
        )
        parser.add_argument(
            "--mcp-uninstall",
            action="store_true",
            help="Remove this CLI from the milo gateway",
        )
        parser.add_argument(
            "--completions",
            choices=["bash", "zsh", "fish"],
            default=None,
            metavar="SHELL",
            help="Output shell completion script (bash, zsh, fish)",
        )

        # Built-in global options
        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase verbosity (-v verbose, -vv debug)",
        )
        parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress non-error output",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            default=False,
            help="Disable color output",
        )
        parser.add_argument(
            "-n",
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would happen without making changes",
        )
        parser.add_argument(
            "-o",
            "--output-file",
            dest="_output_file",
            default="",
            metavar="FILE",
            help="Write output to FILE instead of stdout",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Overwrite output file if it exists",
        )

        # User-defined global options
        for opt in self._global_options:
            flags = [f"--{opt.name.replace('_', '-')}"]
            if opt.short:
                flags.insert(0, opt.short)
            kwargs: dict[str, Any] = {
                "dest": opt.name,
                "help": opt.description,
                "default": opt.default,
            }
            if opt.is_flag:
                kwargs["action"] = "store_true"
            else:
                kwargs["type"] = opt.option_type
            parser.add_argument(*flags, **kwargs)

        has_children = self._commands or self._groups
        if has_children:
            subparsers = parser.add_subparsers(dest="_command")
            self._add_commands_to_subparsers(subparsers, self._commands)
            self._add_groups_to_subparsers(subparsers, self._groups)

        return parser

    def _add_commands_to_subparsers(
        self,
        subparsers: argparse._SubParsersAction,
        commands: dict[str, CommandDef | LazyCommandDef],
    ) -> None:
        """Add command parsers to a subparsers action."""
        for cmd in commands.values():
            if cmd.hidden:
                continue
            fmt_class = (
                help_formatter_with_examples(tuple(cmd.examples)) if cmd.examples else HelpRenderer
            )
            sub = subparsers.add_parser(
                cmd.name,
                help=cmd.description,
                aliases=list(cmd.aliases),
                formatter_class=fmt_class,
            )
            try:
                schema = cmd.schema
            except LazyImportError as exc:
                import warnings

                warnings.warn(
                    f"Command {cmd.name!r} failed to load: {exc.cause}",
                    UserWarning,
                    stacklevel=2,
                )
                schema = {"type": "object", "properties": {}}
            self._add_arguments_from_schema(sub, schema, cmd)
            sub.add_argument(
                "--format",
                choices=["plain", "json", "table"],
                default="plain",
                help="Output format",
            )

    def _add_groups_to_subparsers(
        self,
        subparsers: argparse._SubParsersAction,
        groups: dict[str, Group],
    ) -> None:
        """Recursively add group parsers to a subparsers action."""
        for group in groups.values():
            if group.hidden:
                continue
            group_parser = subparsers.add_parser(
                group.name,
                help=group.description,
                aliases=list(group.aliases),
                formatter_class=HelpRenderer,
            )
            has_children = group._commands or group._groups
            if has_children:
                group_sub = group_parser.add_subparsers(dest=f"_command_{group.name}")
                self._add_commands_to_subparsers(group_sub, group._commands)
                self._add_groups_to_subparsers(group_sub, group._groups)

    def _add_arguments_from_schema(
        self,
        parser: argparse.ArgumentParser,
        schema: dict[str, Any],
        cmd: CommandDef | LazyCommandDef,
    ) -> None:
        """Add argparse arguments from a command's JSON schema.

        Uses the handler's signature for defaults when available (eager
        commands), or falls back to schema-only mode (lazy commands).
        """
        props = schema.get("properties", {})
        required_set = set(schema.get("required", []))

        # Try to get signature for defaults (only for eager commands)
        sig = None
        if isinstance(cmd, CommandDef):
            sig = inspect.signature(cmd.handler)

        for param_name, param_schema in props.items():
            param = sig.parameters.get(param_name) if sig else None
            kwargs: dict[str, Any] = {}

            # Determine type
            json_type = param_schema.get("type", "string")
            if json_type == "boolean":
                if param and param.default is not inspect.Parameter.empty:
                    default = param.default
                elif "default" in param_schema:
                    default = param_schema["default"]
                else:
                    default = False
                kwargs["default"] = default
                if default is True:
                    # default=True → --no-xxx flag to disable
                    flag = f"--no-{param_name.replace('_', '-')}"
                    kwargs["action"] = "store_false"
                    desc = param_schema.get("description", "")
                    hint = f"disable {param_name.replace('_', ' ')}"
                    kwargs["help"] = f"{desc} ({hint})" if desc else hint
                    parser.add_argument(flag, dest=param_name, **kwargs)
                    continue
                else:
                    kwargs["action"] = "store_true"
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

            # Enum choices from schema
            if "enum" in param_schema:
                kwargs["choices"] = param_schema["enum"]

            # Set default from signature or schema
            if param and param.default is not inspect.Parameter.empty and json_type != "boolean":
                kwargs["default"] = param.default
            elif "default" not in kwargs and "default" in param_schema:
                kwargs["default"] = param_schema["default"]

            # Required vs optional
            if param_name in required_set and json_type != "boolean":
                kwargs["required"] = True

            # Help text from schema description (extracted from docstring)
            desc = param_schema.get("description", "")
            if desc:
                kwargs["help"] = desc

            flag = f"--{param_name.replace('_', '-')}"
            parser.add_argument(flag, dest=param_name, **kwargs)

    def run(self, argv: list[str] | None = None) -> Any:
        """Parse args and dispatch to the appropriate command."""
        self._run_called = True
        parser = self.build_parser()
        self._parser = parser
        args = parser.parse_args(argv)

        builtin_mode = self._resolve_builtin_mode(args)
        if builtin_mode is not None:
            self._run_builtin_mode(args, builtin_mode)
            return None

        # Build execution context from global options
        ctx = self._build_context(args)
        execution = self._resolve_command_execution(args)
        if execution is None:
            return None

        if execution.confirm_msg and not ctx.dry_run and not ctx.confirm(execution.confirm_msg):
            sys.stderr.write("Aborted.\n")
            sys.exit(130)

        result = self._execute_command(
            execution.command,
            ctx,
            self._build_run_kwargs(args, ctx, execution.command),
        )
        result = self._consume_result(result)
        self._run_after_command_hooks(ctx, execution.command.name, result)
        suppress = not execution.command.display_result and not ctx.output_file
        if not suppress:
            force = getattr(args, "force", False)
            self._write_command_output(result, execution.fmt, ctx.output_file, force=force)

        return result

    def invoke(self, argv: list[str]) -> InvokeResult:
        """Run a command and capture output for testing.

        Stdout and stderr are captured separately. ``output`` contains
        stdout (command results), ``stderr`` contains log/error messages.

        Usage::

            result = cli.invoke(["greet", "--name", "Alice"])
            assert result.exit_code == 0
            assert "Alice" in result.output
            assert result.stderr == ""  # no warnings
        """
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_out
        sys.stderr = captured_err

        exit_code = 0
        result = None
        exception = None

        try:
            result = self.run(argv)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        except Exception as e:
            exception = e
            exit_code = 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return InvokeResult(
            output=captured_out.getvalue(),
            exit_code=exit_code,
            result=result,
            exception=exception,
            stderr=captured_err.getvalue(),
        )

    def _resolve_builtin_mode(self, args: argparse.Namespace) -> BuiltinMode | None:
        """Return the selected built-in top-level mode, if any."""
        if getattr(args, "completions", None):
            return BuiltinMode("completions")
        if getattr(args, "llms_txt", False):
            return BuiltinMode("llms_txt")
        if getattr(args, "mcp", False):
            return BuiltinMode("mcp")
        if getattr(args, "mcp_install", False):
            return BuiltinMode("mcp_install")
        if getattr(args, "mcp_uninstall", False):
            return BuiltinMode("mcp_uninstall")
        return None

    def _run_builtin_mode(self, args: argparse.Namespace, mode: BuiltinMode) -> None:
        """Execute a built-in top-level mode."""
        if mode.name == "completions":
            from milo.completions import install_completions

            sys.stdout.write(install_completions(self, args.completions))
            return
        if mode.name == "llms_txt":
            from milo.llms import generate_llms_txt

            sys.stdout.write(generate_llms_txt(self))
            return
        if mode.name == "mcp":
            from milo.mcp import run_mcp_server

            run_mcp_server(self)
            return
        if mode.name == "mcp_install":
            self._mcp_install()
            return
        if mode.name == "mcp_uninstall":
            self._mcp_uninstall()
            return
        raise AssertionError(f"Unknown builtin mode: {mode.name}")

    def _resolve_command_execution(self, args: argparse.Namespace) -> CommandExecution | None:
        """Resolve parsed args to an executable command or handle help cases."""
        result = self._resolve_command_from_args(args)

        if isinstance(result, ResolvedGroup):
            result.group.format_help(result.prog)
            return None

        if isinstance(result, ResolvedNothing):
            if result.attempted:
                suggestion = self.suggest_command(result.attempted)
                if suggestion:
                    sys.stderr.write(
                        f"Unknown command: {result.attempted!r}. Did you mean {suggestion!r}?\n"
                    )
                    return None
            self._format_root_help()
            return None

        found = result.command
        try:
            cmd = found.resolve() if isinstance(found, LazyCommandDef) else found
        except LazyImportError as exc:
            sys.stderr.write(f"error: {exc}\n")
            sys.stderr.write(f"  hint: Check that {exc.import_path!r} is installed and importable.\n")
            return None
        confirm_msg = getattr(found, "confirm", "") or getattr(cmd, "confirm", "")
        return CommandExecution(found=found, command=cmd, fmt=result.fmt, confirm_msg=confirm_msg)

    def _build_run_kwargs(
        self, args: argparse.Namespace, ctx: Context, command: CommandDef
    ) -> dict[str, Any]:
        """Build handler kwargs from parsed args, injecting the active context."""
        return self._build_handler_kwargs_from_namespace(args, ctx, command)

    def _build_handler_kwargs_from_namespace(
        self, args: argparse.Namespace, ctx: Context, command: CommandDef
    ) -> dict[str, Any]:
        """Build handler kwargs from an argparse namespace."""
        sig = inspect.signature(command.handler)
        kwargs: dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name == "ctx" or _is_context_param(param):
                kwargs[param_name] = ctx
            elif hasattr(args, param_name):
                kwargs[param_name] = getattr(args, param_name)
        return kwargs

    def _get_resolved_command(
        self, command_name: str
    ) -> tuple[CommandDef | LazyCommandDef, CommandDef]:
        """Resolve a command name to the registered definition and eager command.

        Raises :class:`LazyImportError` if a lazy command fails to import.
        """
        found = self.get_command(command_name)
        if not found:
            suggestion = self.suggest_command(command_name)
            msg = f"Unknown command: {command_name!r}"
            if suggestion:
                msg += f". Did you mean {suggestion!r}?"
            raise ValueError(msg)
        cmd = found.resolve() if isinstance(found, LazyCommandDef) else found
        return found, cmd

    def _filter_call_kwargs(self, command: CommandDef, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Filter programmatic kwargs to handler parameters, excluding context injection."""
        sig = inspect.signature(command.handler)
        return {
            k: v
            for k, v in kwargs.items()
            if k in sig.parameters and not _is_context_param(sig.parameters[k])
        }

    def _new_call_context(self) -> Context:
        """Create a default context for programmatic command calls."""
        from milo.context import Context as ContextClass

        return ContextClass()

    def _execute_command(
        self,
        command: CommandDef,
        ctx: Context,
        kwargs: dict[str, Any],
        *,
        method: str = "command",
        call_name: str | None = None,
        raise_on_error: bool = False,
    ) -> Any:
        """Execute a command with context setup, hooks, middleware, and error handling."""
        from milo.context import set_context

        set_context(ctx)
        self._run_before_command_hooks(ctx, command.name, kwargs)

        try:
            if self._middleware:
                from milo.middleware import MCPCall

                call = MCPCall(
                    method=method,
                    name=call_name or command.name,
                    arguments=kwargs,
                )
                return self._middleware.execute(ctx, call, lambda c: command.handler(**c.arguments))
            return command.handler(**kwargs)
        except SystemExit:
            raise
        except KeyboardInterrupt:
            if raise_on_error:
                raise
            sys.stderr.write("\nInterrupted.\n")
            sys.exit(130)
        except Exception as exc:
            if raise_on_error:
                raise
            from milo._errors import MiloError, format_error

            if isinstance(exc, MiloError):
                ctx.error(format_error(exc))
            else:
                ctx.error(f"{type(exc).__name__}: {exc}")
            if ctx.debug:
                import traceback

                traceback.print_exc(file=sys.stderr)
            sys.exit(1)

    def _run_before_command_hooks(
        self, ctx: Context, command_name: str, kwargs: dict[str, Any]
    ) -> None:
        """Execute before-command hooks."""
        for hook in self._before_command:
            try:
                hook(ctx, command_name, kwargs)
            except SystemExit:
                raise
            except Exception as exc:
                ctx.error(f"before_command hook failed: {type(exc).__name__}: {exc}")
                sys.exit(1)

    def _run_after_command_hooks(self, ctx: Context, command_name: str, result: Any) -> None:
        """Execute after-command hooks."""
        for hook in self._after_command:
            try:
                hook(ctx, command_name, result)
            except Exception as exc:
                ctx.error(f"after_command hook failed: {type(exc).__name__}: {exc}")

    def _consume_result(self, result: Any, *, emit_progress: bool = True) -> Any:
        """Consume generator-based command results."""
        from milo.streaming import consume_generator, is_generator_result

        if not is_generator_result(result):
            return result

        progress_list, final_value = consume_generator(result)
        if emit_progress:
            for p in progress_list:
                sys.stderr.write(f"  {p.status}\n")
        return final_value

    def _write_command_output(
        self, result: Any, fmt: str, output_file: str, *, force: bool = False
    ) -> None:
        """Write command output to stdout or a file.

        When *output_file* already exists and *force* is False, prints an
        error and exits instead of silently overwriting.
        """
        if output_file:
            if not force and os.path.exists(output_file):
                sys.stderr.write(
                    f"error: output file {output_file!r} already exists. "
                    f"Use --force to overwrite.\n"
                )
                sys.exit(1)
            formatted = format_output(result, fmt=fmt)
            with open(output_file, "w") as f:
                f.write(formatted + "\n")
            return
        write_output(result, fmt=fmt)

    def _build_context(self, args: argparse.Namespace) -> Context:
        """Build a Context from parsed global options."""
        from milo.context import Context as ContextClass

        verbose = getattr(args, "verbose", 0)
        quiet = getattr(args, "quiet", False)
        verbosity = -1 if quiet else verbose

        # Collect user global option values
        user_globals = {}
        for opt in self._global_options:
            if hasattr(args, opt.name):
                user_globals[opt.name] = getattr(args, opt.name)

        return ContextClass(
            verbosity=verbosity,
            format=getattr(args, "format", "plain"),
            color=not getattr(args, "no_color", False),
            dry_run=getattr(args, "dry_run", False),
            output_file=getattr(args, "_output_file", ""),
            globals=user_globals,
        )

    def _format_root_help(self) -> None:
        """Render root help from command/group registries and the actual parser."""
        from milo.help import HelpState
        from milo.templates import get_env

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

        # Derive options from the actual parser so new flags are never missed
        options: list[dict[str, Any]] = []
        for action in self._parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                continue
            flags = ", ".join(action.option_strings) if action.option_strings else ""
            if not flags:
                continue
            entry: dict[str, Any] = {"flags": flags, "help": action.help or ""}
            if action.metavar:
                entry["metavar"] = action.metavar
            options.append(entry)

        state = HelpState(
            prog=self.name,
            description=self.description,
            commands=commands,
            options=tuple(options),
        )
        env = get_env()
        try:
            template = env.get_template("help.kida")
            output = template.render(state=state)
        except Exception:
            # Fallback to plain text if template is missing or broken
            lines = [f"{self.name} — {self.description}", ""]
            lines.extend(f"  {cmd['name']:<20} {cmd.get('help', '')}" for cmd in commands)
            lines.extend(f"  {opt.get('flags', ''):<20} {opt.get('help', '')}" for opt in options)
            output = "\n".join(lines)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    def _resolve_command_from_args(self, args: argparse.Namespace) -> ResolveResult:
        """Walk the parsed args to find the leaf command, group, or nothing."""
        fmt = getattr(args, "format", "plain")

        cmd_name = getattr(args, "_command", None)
        if not cmd_name:
            return ResolvedNothing(attempted=None, fmt=fmt)

        # Direct command?
        cmd = self.get_command(cmd_name)
        if cmd:
            return ResolvedCommand(command=cmd, fmt=fmt)

        # Group? Walk into it.
        group = self._groups.get(cmd_name)
        if group is None:
            resolved = self._group_alias_map.get(cmd_name)
            if resolved:
                group = self._groups.get(resolved)
        if group is None:
            return ResolvedNothing(attempted=cmd_name, fmt=fmt)

        return self._resolve_group_command(group, args, fmt, prog=self.name)

    def _resolve_group_command(
        self,
        group: Group,
        args: argparse.Namespace,
        fmt: str,
        prog: str = "",
    ) -> ResolveResult:
        """Recursively resolve a command within a group from parsed args."""
        group_prog = f"{prog} {group.name}".strip()
        sub_name = getattr(args, f"_command_{group.name}", None)
        if not sub_name:
            return ResolvedGroup(group=group, fmt=fmt, prog=group_prog)

        cmd = group.get_command(sub_name)
        if cmd:
            return ResolvedCommand(command=cmd, fmt=fmt)

        sub_group = group.get_group(sub_name)
        if sub_group:
            return self._resolve_group_command(sub_group, args, fmt, prog=group_prog)

        return ResolvedNothing(attempted=sub_name, fmt=fmt)

    def call(self, command_name: str, **kwargs: Any) -> Any:
        """Programmatically call a command by name or dotted path.

        Used by MCP server and for programmatic invocation::

            cli.call("greet", name="Alice")
            cli.call("site.build", output="_site")
        """
        _found, cmd = self._get_resolved_command(command_name)
        ctx = self._new_call_context()
        result = self._execute_command(
            cmd, ctx, self._filter_call_kwargs(cmd, kwargs), raise_on_error=True
        )
        return self._consume_result(result, emit_progress=False)

    def call_raw(self, command_name: str, **kwargs: Any) -> Any:
        """Call a command without consuming generators.

        Like :meth:`call`, but returns the raw result — if the handler
        returns a generator, it is *not* consumed.  The MCP server uses
        this to stream ``Progress`` yields as notifications.
        """
        _found, cmd = self._get_resolved_command(command_name)
        ctx = self._new_call_context()
        return self._execute_command(
            cmd,
            ctx,
            self._filter_call_kwargs(cmd, kwargs),
            method="tools/call",
            call_name=command_name,
            raise_on_error=True,
        )

    def suggest_command(self, name: str) -> str | None:
        """Suggest the closest command name for typo correction."""
        all_names = [path for path, _ in self.walk_commands()]
        # Also include group names for suggestions
        all_names.extend(self._groups.keys())
        all_names.extend(self._group_alias_map.keys())
        matches = difflib.get_close_matches(name, all_names, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def generate_help_all(self) -> str:
        """Generate a full command tree reference in markdown."""
        from milo._cli_help import generate_help_all

        return generate_help_all(self)

    def _mcp_install(self) -> None:
        """Register this CLI in the milo gateway."""
        from milo.registry import install

        # Build the command to invoke this CLI with --mcp
        # Use sys.argv[0] to get the script/module that was run
        command = [sys.executable, sys.argv[0], "--mcp"]
        project_root = os.getcwd()

        install(
            name=self.name,
            command=command,
            description=self.description,
            version=self.version,
            project_root=project_root,
        )

    def _mcp_uninstall(self) -> None:
        """Remove this CLI from the milo gateway."""
        from milo.registry import uninstall

        uninstall(self.name)
