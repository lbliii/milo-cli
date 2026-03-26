"""Structured error hierarchy."""

from __future__ import annotations

from enum import Enum


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


class MiloError(Exception):
    """Base error for all milo errors."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"[{code.value}] {message}")


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
