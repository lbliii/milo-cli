"""Command definition types and helpers."""

from __future__ import annotations

import importlib
import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


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
    annotations: dict[str, Any] = field(default_factory=dict)
    """MCP tool annotations (readOnlyHint, destructiveHint, etc.)."""
    display_result: bool = True
    """If False, suppress plain-format output (return value still available for --format json)."""


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
        annotations: dict[str, Any] | None = None,
        display_result: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.import_path = import_path
        self.aliases = tuple(aliases)
        self.tags = tuple(tags)
        self.hidden = hidden
        self.examples = tuple(examples)
        self.confirm = confirm
        self.annotations = annotations or {}
        self.display_result = display_result
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
                examples=self.examples,
                confirm=self.confirm,
                annotations=self.annotations,
                display_result=self.display_result,
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


def _make_command_def(
    name: str,
    func: Callable,
    *,
    description: str = "",
    aliases: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    hidden: bool = False,
    examples: tuple[dict[str, Any], ...] = (),
    confirm: str = "",
    annotations: dict[str, Any] | None = None,
    display_result: bool = True,
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
        examples=examples,
        confirm=confirm,
        annotations=annotations or {},
        display_result=display_result,
    )


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
