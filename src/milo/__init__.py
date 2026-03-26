"""Milo — Template-driven CLI applications for free-threaded Python."""

from __future__ import annotations


def __getattr__(name: str):
    """Lazy imports for public API."""
    _imports = {
        # Types
        "Action": "_types",
        "Key": "_types",
        "SpecialKey": "_types",
        "AppStatus": "_types",
        "RenderTarget": "_types",
        "FieldType": "_types",
        "FieldSpec": "_types",
        "FieldState": "_types",
        "FormState": "_types",
        "Screen": "_types",
        "Transition": "_types",
        "ReducerResult": "_types",
        "Quit": "_types",
        "Call": "_types",
        "Put": "_types",
        "Select": "_types",
        "Fork": "_types",
        "Delay": "_types",
        "BUILTIN_ACTIONS": "_types",
        # Errors
        "MiloError": "_errors",
        "InputError": "_errors",
        "StateError": "_errors",
        "FormError": "_errors",
        "AppError": "_errors",
        "FlowError": "_errors",
        "ErrorCode": "_errors",
        "format_error": "_errors",
        "format_render_error": "_errors",
        # State
        "Store": "state",
        "combine_reducers": "state",
        # App
        "App": "app",
        "run": "app",
        "render_html": "app",
        # Flow
        "FlowScreen": "flow",
        "Flow": "flow",
        "FlowState": "flow",
        # Form
        "form": "form",
        "form_reducer": "form",
        "make_form_reducer": "form",
        # Help
        "HelpRenderer": "help",
        # Dev
        "DevServer": "dev",
    }
    if name in _imports:
        import importlib

        module = importlib.import_module(f"milo.{_imports[name]}")
        return getattr(module, name)
    raise AttributeError(f"module 'milo' has no attribute {name!r}")


# Free-threaded Python marker (PEP 703)
def _Py_mod_gil() -> int:  # noqa: N802
    return 0


__version__ = "0.1.0"
__all__ = [
    "BUILTIN_ACTIONS",
    "Action",
    "App",
    "AppError",
    "AppStatus",
    "Call",
    "Delay",
    "DevServer",
    "ErrorCode",
    "FieldSpec",
    "FieldState",
    "FieldType",
    "Flow",
    "FlowError",
    "FlowScreen",
    "FlowState",
    "Fork",
    "FormError",
    "FormState",
    "HelpRenderer",
    "InputError",
    "Key",
    "MiloError",
    "Put",
    "Quit",
    "ReducerResult",
    "RenderTarget",
    "Screen",
    "Select",
    "SpecialKey",
    "StateError",
    "Store",
    "Transition",
    "combine_reducers",
    "form",
    "form_reducer",
    "format_error",
    "format_render_error",
    "make_form_reducer",
    "render_html",
    "run",
]
