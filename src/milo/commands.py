"""CLI application with command decorator and dispatch."""

from __future__ import annotations

import argparse
import difflib
import importlib
import inspect
import io
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from milo.help import HelpRenderer
from milo.output import format_output, write_output
from milo.schema import function_to_schema

if TYPE_CHECKING:
    from milo.context import Context
    from milo.groups import Group
    from milo.middleware import MiddlewareStack


@dataclass(frozen=True, slots=True)
class GlobalOption:
    """A CLI-wide option available to all commands via Context."""

    name: str
    short: str = ""
    option_type: type = str
    default: Any = None
    description: str = ""
    is_flag: bool = False


@dataclass(frozen=True, slots=True)
class ResourceDef:
    """A registered MCP resource."""

    uri: str
    name: str
    description: str
    handler: Callable[..., Any]
    mime_type: str = "text/plain"


@dataclass(frozen=True, slots=True)
class PromptDef:
    """A registered MCP prompt."""

    name: str
    description: str
    handler: Callable[..., Any]
    arguments: tuple[dict[str, Any], ...] = ()


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
    examples: tuple[dict[str, Any], ...] = ()
    confirm: str = ""
    """If non-empty, prompt for confirmation before running."""


class LazyCommandDef:
    """A command whose handler is imported on first use.

    Stores a dotted import path (``module:attribute``) and defers the
    actual import until the command is invoked.  This keeps CLI startup
    fast even with dozens of commands.

    If *schema* is provided upfront, MCP ``tools/list`` and llms.txt
    can be generated without importing the handler module at all.
    """

    __slots__ = (
        "_lock",
        "_resolved",
        "_schema",
        "aliases",
        "confirm",
        "description",
        "examples",
        "hidden",
        "import_path",
        "name",
        "tags",
    )

    def __init__(
        self,
        name: str,
        import_path: str,
        description: str = "",
        *,
        schema: dict[str, Any] | None = None,
        aliases: tuple[str, ...] | list[str] = (),
        tags: tuple[str, ...] | list[str] = (),
        hidden: bool = False,
        examples: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        confirm: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self.import_path = import_path
        self.aliases = tuple(aliases)
        self.tags = tuple(tags)
        self.hidden = hidden
        self.examples = tuple(examples)
        self.confirm = confirm
        self._schema = schema
        self._resolved: CommandDef | None = None
        self._lock = threading.Lock()

    @property
    def schema(self) -> dict[str, Any]:
        """Return pre-computed schema or resolve to get it."""
        if self._schema is not None:
            return self._schema
        return self.resolve().schema

    @property
    def handler(self) -> Callable[..., Any]:
        """Resolve and return the handler function."""
        return self.resolve().handler

    def resolve(self) -> CommandDef:
        """Import the handler and cache as a full CommandDef. Thread-safe."""
        if self._resolved is not None:
            return self._resolved

        with self._lock:
            # Double-check after acquiring lock
            if self._resolved is not None:
                return self._resolved

            module_path, _, attr_name = self.import_path.rpartition(":")
            if not module_path or not attr_name:
                msg = f"Invalid import_path {self.import_path!r}: expected 'module.path:attribute'"
                raise ValueError(msg)

            module = importlib.import_module(module_path)
            handler = getattr(module, attr_name)

            schema = self._schema if self._schema is not None else function_to_schema(handler)

            self._resolved = CommandDef(
                name=self.name,
                description=self.description,
                handler=handler,
                schema=schema,
                aliases=self.aliases,
                tags=self.tags,
                hidden=self.hidden,
                examples=self.examples,
                confirm=self.confirm,
            )
            return self._resolved


@dataclass(frozen=True, slots=True)
class InvokeResult:
    """Result of CLI.invoke() for testing."""

    output: str
    exit_code: int
    result: Any = None
    exception: Exception | None = None


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
    ) -> Callable:
        """Register a function as a CLI command.

        The function's type annotations drive:
        - argparse argument generation
        - MCP tool schema
        - help text

        Args:
            confirm: If set, prompt user with this message before executing.
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
                examples=tuple(examples),
                confirm=confirm,
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
    ) -> LazyCommandDef:
        """Register a lazy-loaded command.

        The handler module is not imported until the command is invoked.
        This keeps CLI startup fast for large command sets.
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
        )
        self._commands[name] = cmd
        for alias in aliases:
            self._alias_map[alias] = name
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
            resource_name = name or func.__name__
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

    def walk_commands(self) -> list[tuple[str, CommandDef | LazyCommandDef]]:
        """Walk all commands in the tree, yielding (dotted_path, CommandDef).

        Top-level commands have simple names. Group commands use dots::

            [("greet", greet_cmd), ("site.build", build_cmd), ...]
        """
        result = [(cmd.name, cmd) for cmd in self._commands.values()]
        for group in self._groups.values():
            result.extend(group.walk_commands())
        return result

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
            sub = subparsers.add_parser(
                cmd.name,
                help=cmd.description,
                aliases=list(cmd.aliases),
                formatter_class=HelpRenderer,
            )
            self._add_arguments_from_schema(sub, cmd.schema, cmd)
            sub.add_argument(
                "--format",
                choices=["plain", "json", "table"],
                default="plain",
                help="Output format (default: plain)",
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

            # Set default from signature if available
            if param and param.default is not inspect.Parameter.empty and json_type != "boolean":
                kwargs["default"] = param.default

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
        parser = self.build_parser()
        args = parser.parse_args(argv)

        # --completions mode
        if getattr(args, "completions", None):
            from milo.completions import install_completions

            sys.stdout.write(install_completions(self, args.completions))
            return None

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

        # --mcp-install mode
        if getattr(args, "mcp_install", False):
            self._mcp_install()
            return None

        # --mcp-uninstall mode
        if getattr(args, "mcp_uninstall", False):
            self._mcp_uninstall()
            return None

        # Build execution context from global options
        ctx = self._build_context(args)

        # Resolve command from args (may be nested in groups)
        found, fmt = self._resolve_command_from_args(args)
        if not found:
            # Did-you-mean suggestion for typos
            cmd_name = getattr(args, "_command", None)
            if cmd_name:
                suggestion = self.suggest_command(cmd_name)
                if suggestion:
                    sys.stderr.write(
                        f"Unknown command: {cmd_name!r}. Did you mean {suggestion!r}?\n"
                    )
                    return None
            parser.print_help()
            return None

        # Resolve lazy commands
        cmd = found.resolve() if isinstance(found, LazyCommandDef) else found

        # Confirmation prompt
        confirm_msg = getattr(found, "confirm", "") or getattr(cmd, "confirm", "")
        if confirm_msg and not ctx.dry_run and not ctx.confirm(confirm_msg):
            sys.stderr.write("Aborted.\n")
            return None

        # Extract command arguments and inject context
        sig = inspect.signature(cmd.handler)
        kwargs: dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name == "ctx" or _is_context_param(param):
                kwargs[param_name] = ctx
            elif hasattr(args, param_name):
                kwargs[param_name] = getattr(args, param_name)

        # Set context for get_context() access
        from milo.context import set_context

        set_context(ctx)

        # Before-command hooks
        for hook in self._before_command:
            hook(ctx, cmd.name, kwargs)

        # Call handler (through middleware if present)
        result = cmd.handler(**kwargs)

        # Handle streaming generators
        from milo.streaming import consume_generator, is_generator_result

        if is_generator_result(result):
            progress_list, final_value = consume_generator(result)
            for p in progress_list:
                sys.stderr.write(f"  {p.status}\n")
            result = final_value

        # After-command hooks
        for hook in self._after_command:
            hook(ctx, cmd.name, result)

        # Format and output (to file or stdout)
        output_file = ctx.output_file
        if output_file:
            formatted = format_output(result, fmt=fmt)
            with open(output_file, "w") as f:
                f.write(formatted + "\n")
        else:
            write_output(result, fmt=fmt)

        return result

    def invoke(self, argv: list[str]) -> InvokeResult:
        """Run a command and capture output for testing.

        Usage::

            result = cli.invoke(["greet", "--name", "Alice"])
            assert result.exit_code == 0
            assert "Alice" in result.output
        """
        captured = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured
        sys.stderr = captured

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
            output=captured.getvalue(),
            exit_code=exit_code,
            result=result,
            exception=exception,
        )

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

    def _resolve_command_from_args(
        self, args: argparse.Namespace
    ) -> tuple[CommandDef | LazyCommandDef | None, str]:
        """Walk the parsed args to find the leaf command."""
        fmt = getattr(args, "format", "plain")

        # Check top-level command
        cmd_name = getattr(args, "_command", None)
        if not cmd_name:
            return None, fmt

        # Is it a direct command?
        cmd = self.get_command(cmd_name)
        if cmd:
            return cmd, fmt

        # Is it a group? Walk into it.
        group = self._groups.get(cmd_name)
        if group is None:
            resolved = self._group_alias_map.get(cmd_name)
            if resolved:
                group = self._groups.get(resolved)
        if group is None:
            return None, fmt

        return self._resolve_group_command(group, args, fmt)

    def _resolve_group_command(
        self,
        group: Group,
        args: argparse.Namespace,
        fmt: str,
    ) -> tuple[CommandDef | None, str]:
        """Recursively resolve a command within a group from parsed args."""
        sub_name = getattr(args, f"_command_{group.name}", None)
        if not sub_name:
            return None, fmt

        # Check if it's a command in this group
        cmd = group.get_command(sub_name)
        if cmd:
            return cmd, fmt

        # Check if it's a nested sub-group
        sub_group = group.get_group(sub_name)
        if sub_group:
            return self._resolve_group_command(sub_group, args, fmt)

        return None, fmt

    def call(self, command_name: str, **kwargs: Any) -> Any:
        """Programmatically call a command by name or dotted path.

        Used by MCP server and for programmatic invocation::

            cli.call("greet", name="Alice")
            cli.call("site.build", output="_site")
        """
        found = self.get_command(command_name)
        if not found:
            suggestion = self.suggest_command(command_name)
            msg = f"Unknown command: {command_name!r}"
            if suggestion:
                msg += f". Did you mean {suggestion!r}?"
            raise ValueError(msg)

        # Resolve lazy commands
        cmd = found.resolve() if isinstance(found, LazyCommandDef) else found

        sig = inspect.signature(cmd.handler)
        # Filter to only valid parameters (exclude context params)
        valid = {
            k: v
            for k, v in kwargs.items()
            if k in sig.parameters and not _is_context_param(sig.parameters[k])
        }

        result = cmd.handler(**valid)

        # Handle streaming generators
        from milo.streaming import consume_generator, is_generator_result

        if is_generator_result(result):
            _, result = consume_generator(result)

        return result

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
        lines: list[str] = []
        lines.append(f"# {self.name}")
        if self.description:
            lines.append(f"\n{self.description}")
        if self.version:
            lines.append(f"\nVersion: {self.version}")
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
        for opt in self._global_options:
            flag = f"`--{opt.name.replace('_', '-')}`"
            if opt.short:
                flag = f"`{opt.short}, {flag[1:]}"
            default = f"`{opt.default}`" if opt.default is not None else ""
            lines.append(f"| {flag} | {opt.description} | {default} |")
        lines.append("")

        # Commands
        if self._commands:
            lines.append("## Commands\n")
            for cmd in self._commands.values():
                if cmd.hidden:
                    continue
                self._format_cmd_markdown(cmd, lines)

        # Groups
        for group in self._groups.values():
            if group.hidden:
                continue
            self._format_group_markdown(group, lines, depth=2)

        return "\n".join(lines)

    def _format_cmd_markdown(
        self,
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
        required = set(cmd.schema.get("required", []))
        if props:
            lines.append("| Option | Type | Required | Default |")
            lines.append("|--------|------|----------|---------|")
            for name, schema in props.items():
                ptype = schema.get("type", "string")
                req = "yes" if name in required else ""
                lines.append(f"| `--{name.replace('_', '-')}` | {ptype} | {req} | |")
            lines.append("")

    def _format_group_markdown(
        self,
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
            self._format_cmd_markdown(cmd, lines, prefix=f"{group.name} ")

        for sub in group._groups.values():
            if sub.hidden:
                continue
            self._format_group_markdown(sub, lines, depth=depth + 1)

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


def _is_context_param(param: inspect.Parameter) -> bool:
    """Check if a parameter is a Context injection point."""
    annotation = param.annotation
    if annotation is inspect.Parameter.empty:
        return False
    # Check for Context type or string annotation
    if isinstance(annotation, type):
        return annotation.__name__ == "Context"
    if isinstance(annotation, str):
        return annotation in ("Context", "milo.context.Context")
    return False
