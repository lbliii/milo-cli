"""Command definition types and helpers."""

from __future__ import annotations

import importlib
import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from milo.mcp_apps import MCPAppToolMeta

CommandSurface = Literal["cli", "mcp", "llms"]
_VALID_COMMAND_SURFACES = frozenset({"cli", "mcp", "llms"})


def _normalize_surfaces(
    surfaces: tuple[CommandSurface, ...] | list[CommandSurface],
) -> tuple[CommandSurface, ...]:
    """Validate and de-duplicate command discovery surfaces."""
    normalized = tuple(dict.fromkeys(surfaces))
    invalid = set(normalized) - _VALID_COMMAND_SURFACES
    if invalid:
        msg = f"Unknown command surface(s): {', '.join(sorted(invalid))}"
        raise ValueError(msg)
    return normalized


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
class RootOptionSpec:
    """Parser-independent metadata for a CLI-wide root option."""

    flags: tuple[str, ...]
    dest: str
    description: str = ""
    action: Literal["help", "version_report", "store", "store_true", "count"] = "store"
    default: Any = None
    option_type: type | None = None
    choices: tuple[str, ...] = ()
    metavar: str = ""


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
    surfaces: tuple[CommandSurface, ...] = ("cli", "mcp", "llms")
    examples: tuple[dict[str, Any], ...] = ()
    confirm: str = ""
    """If non-empty, prompt for confirmation before running."""
    annotations: dict[str, Any] = field(default_factory=dict)
    """MCP tool annotations (readOnlyHint, destructiveHint, etc.)."""
    display_result: bool = True
    """If False, suppress plain-format output (return value still available for --format json)."""
    terminal_renderer: Callable[[Any, Any], str] | None = None
    """Optional plain-terminal renderer; protocol and programmatic calls keep structured values."""
    ui: MCPAppToolMeta | None = None
    """Optional stable MCP Apps metadata linking this tool to a UI resource."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "surfaces", _normalize_surfaces(self.surfaces))


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
        "annotations",
        "confirm",
        "description",
        "display_result",
        "examples",
        "hidden",
        "import_path",
        "name",
        "surfaces",
        "tags",
        "terminal_renderer",
        "ui",
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
        surfaces: tuple[CommandSurface, ...] | list[CommandSurface] = ("cli", "mcp", "llms"),
        examples: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        confirm: str = "",
        annotations: dict[str, Any] | None = None,
        display_result: bool = True,
        terminal_renderer: Callable[[Any, Any], str] | None = None,
        ui: MCPAppToolMeta | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.import_path = import_path
        self.aliases = tuple(aliases)
        self.tags = tuple(tags)
        self.hidden = hidden
        self.surfaces = _normalize_surfaces(surfaces)
        self.examples = tuple(examples)
        self.confirm = confirm
        self.annotations = annotations or {}
        self.display_result = display_result
        self.terminal_renderer = terminal_renderer
        self.ui = ui
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
        """Import the handler and cache as a full CommandDef. Thread-safe.

        Raises :class:`LazyImportError` if the module or attribute cannot
        be imported, wrapping the original exception with a clear message.
        """
        if self._resolved is not None:
            return self._resolved

        with self._lock:
            # Double-check after acquiring lock
            if self._resolved is not None:
                return self._resolved

            module_path, _, attr_name = self.import_path.rpartition(":")
            if not module_path or not attr_name:
                msg = f"Invalid import_path {self.import_path!r}: expected 'module.path:attribute'"
                raise LazyImportError(self.name, self.import_path, ValueError(msg))

            try:
                module = importlib.import_module(module_path)
                handler = getattr(module, attr_name)
            except Exception as exc:
                raise LazyImportError(self.name, self.import_path, exc) from exc

            from milo.schema import function_to_schema

            schema = self._schema if self._schema is not None else function_to_schema(handler)

            self._resolved = CommandDef(
                name=self.name,
                description=self.description,
                handler=handler,
                schema=schema,
                aliases=self.aliases,
                tags=self.tags,
                hidden=self.hidden,
                surfaces=self.surfaces,
                examples=self.examples,
                confirm=self.confirm,
                annotations=self.annotations,
                ui=self.ui,
                display_result=self.display_result,
                terminal_renderer=self.terminal_renderer,
            )
            return self._resolved


@dataclass(frozen=True, slots=True)
class InvokeResult:
    """Result of CLI.invoke() for testing."""

    output: str
    exit_code: int
    result: Any = None
    exception: Exception | None = None
    stderr: str = ""


class LazyImportError(Exception):
    """Raised when a lazy command's import fails.

    Wraps the original exception with the command name and import path
    so callers can provide actionable error messages.
    """

    def __init__(self, command_name: str, import_path: str, cause: Exception) -> None:
        self.command_name = command_name
        self.import_path = import_path
        self.cause = cause
        super().__init__(f"Command {command_name!r} failed to import from {import_path!r}: {cause}")


def _make_command_def(
    name: str,
    func: Callable,
    *,
    description: str = "",
    aliases: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    hidden: bool = False,
    surfaces: tuple[CommandSurface, ...] = ("cli", "mcp", "llms"),
    examples: tuple[dict[str, Any], ...] = (),
    confirm: str = "",
    annotations: dict[str, Any] | None = None,
    display_result: bool = True,
    terminal_renderer: Callable[[Any, Any], str] | None = None,
    ui: MCPAppToolMeta | None = None,
) -> CommandDef:
    """Build a CommandDef from a function and decorator kwargs."""
    from milo.schema import function_to_schema

    schema = function_to_schema(func)
    desc = description or func.__doc__ or ""
    if "\n" in desc:
        desc = desc.strip().split("\n")[0].strip()
    return CommandDef(
        name=name,
        description=desc,
        handler=func,
        schema=schema,
        aliases=aliases,
        tags=tags,
        hidden=hidden,
        surfaces=_normalize_surfaces(surfaces),
        examples=examples,
        confirm=confirm,
        annotations=annotations or {},
        display_result=display_result,
        terminal_renderer=terminal_renderer,
        ui=ui,
    )


def _is_context_param(param: inspect.Parameter) -> bool:
    """Check if a parameter is a Context injection point."""
    from milo.context import Context as _MiloContext

    annotation = param.annotation
    if annotation is inspect.Parameter.empty:
        return False
    # Check for exact type identity or subclass of milo.context.Context
    if isinstance(annotation, type):
        return issubclass(annotation, _MiloContext)
    if isinstance(annotation, str):
        return annotation in ("Context", "milo.context.Context")
    return False
