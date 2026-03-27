"""Structured error hierarchy with format_compact() for terminal display."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(Enum):
    # Input errors
    INP_RAW_MODE = "M-INP-001"
    INP_ESCAPE_PARSE = "M-INP-002"
    INP_READ = "M-INP-003"

    # State errors
    STA_REDUCER = "M-STA-001"
    STA_DISPATCH = "M-STA-002"
    STA_SAGA = "M-STA-003"
    STA_COMBINE = "M-STA-004"

    # App errors
    APP_LIFECYCLE = "M-APP-001"
    APP_RENDER = "M-APP-002"
    APP_TEMPLATE = "M-APP-003"

    # Form errors
    FRM_VALIDATION = "M-FRM-001"
    FRM_FIELD = "M-FRM-002"
    FRM_SUBMIT = "M-FRM-003"

    # Flow errors
    FLW_TRANSITION = "M-FLW-001"
    FLW_SCREEN = "M-FLW-002"
    FLW_DUPLICATE = "M-FLW-003"

    # Dev errors
    DEV_WATCH = "M-DEV-001"
    DEV_RELOAD = "M-DEV-002"

    # Config errors
    CFG_PARSE = "M-CFG-001"
    CFG_MERGE = "M-CFG-002"
    CFG_VALIDATE = "M-CFG-003"
    CFG_MISSING = "M-CFG-004"

    # Pipeline errors
    PIP_PHASE = "M-PIP-001"
    PIP_TIMEOUT = "M-PIP-002"
    PIP_DEPENDENCY = "M-PIP-003"

    # Plugin errors
    PLG_LOAD = "M-PLG-001"
    PLG_HOOK = "M-PLG-002"

    # Command errors
    CMD_NOT_FOUND = "M-CMD-001"
    CMD_AMBIGUOUS = "M-CMD-002"


class MiloError(Exception):
    """Base error for all milo errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        suggestion: str = "",
        context: dict[str, Any] | None = None,
        docs_url: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.context = context or {}
        self.docs_url = docs_url
        super().__init__(f"[{code.value}] {message}")

    def format_compact(self) -> str:
        """Format error for terminal display, consistent with kida's format_compact()."""
        parts = [f"{self.code.value}: {self.message}"]
        if self.suggestion:
            parts.append(f"  hint: {self.suggestion}")
        if self.docs_url:
            parts.append(f"  docs: {self.docs_url}")
        return "\n".join(parts)


class InputError(MiloError):
    """Input-related errors (raw mode, escape parsing)."""


class StateError(MiloError):
    """State-related errors (reducer, dispatch, saga)."""


class FormError(MiloError):
    """Form-related errors (validation, field)."""


class AppError(MiloError):
    """App lifecycle errors."""


class FlowError(MiloError):
    """Flow errors (transitions, screens)."""


class DevError(MiloError):
    """Dev server errors (watch, reload)."""


class ConfigError(MiloError):
    """Configuration errors (parse, merge, validate)."""


class PipelineError(MiloError):
    """Pipeline orchestration errors (phase, timeout, dependency)."""


class PluginError(MiloError):
    """Plugin system errors (load, hook)."""


def format_error(error: Exception) -> str:
    """Format any error for terminal display.

    Uses format_compact() for kida TemplateErrors and MiloErrors.
    Falls back to str() for other exceptions.
    """
    if hasattr(error, "format_compact"):
        return error.format_compact()
    return f"{type(error).__name__}: {error}"


def format_render_error(
    error: Exception,
    *,
    template_name: str = "",
    env: Any = None,
) -> str:
    """Format a render error with optional error template rendering.

    Tries to render through the built-in error.txt template.
    Falls back to format_error() if template rendering fails.
    """
    compact = format_error(error)

    # Try to render through error template
    if env is not None:
        try:
            tmpl = env.get_template("error.kida")
            return tmpl.render(
                error=compact,
                code=_get_error_code(error),
                template_name=template_name,
                message=str(error),
                hint=_get_hint(error),
                docs_url=_get_docs_url(error),
            )
        except Exception:
            pass

    return compact


def _get_error_code(error: Exception) -> str:
    """Extract error code string from any error."""
    if isinstance(error, MiloError):
        return error.code.value
    if hasattr(error, "code") and error.code is not None:
        return str(error.code.value) if hasattr(error.code, "value") else str(error.code)
    return ""


def _get_hint(error: Exception) -> str:
    """Extract hint/suggestion from an error."""
    if hasattr(error, "suggestion") and error.suggestion:
        return str(error.suggestion)
    return ""


def _get_docs_url(error: Exception) -> str:
    """Extract docs URL from an error."""
    if hasattr(error, "docs_url") and error.docs_url:
        return str(error.docs_url)
    if hasattr(error, "code") and hasattr(error.code, "docs_url"):
        return str(error.code.docs_url)
    return ""
