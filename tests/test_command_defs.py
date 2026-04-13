"""Tests for milo._command_defs — CommandDef, LazyCommandDef, helpers."""

from __future__ import annotations

import inspect
import threading

import pytest

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

# ---------------------------------------------------------------------------
# Frozen dataclass basics
# ---------------------------------------------------------------------------


class TestCommandDef:
    def test_frozen(self) -> None:
        def handler(name: str) -> str:
            return name

        cmd = CommandDef(
            name="greet",
            description="Say hello",
            handler=handler,
            schema={"type": "object", "properties": {}},
        )
        with pytest.raises(AttributeError):
            cmd.name = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        def handler() -> None:
            pass

        cmd = CommandDef(name="x", description="", handler=handler, schema={})
        assert cmd.aliases == ()
        assert cmd.tags == ()
        assert cmd.hidden is False
        assert cmd.examples == ()
        assert cmd.confirm == ""
        assert cmd.annotations == {}
        assert cmd.display_result is True


class TestResourceDef:
    def test_frozen(self) -> None:
        r = ResourceDef(uri="config://app", name="App Config", description="desc", handler=dict)
        with pytest.raises(AttributeError):
            r.uri = "other"  # type: ignore[misc]
        assert r.mime_type == "text/plain"


class TestPromptDef:
    def test_frozen(self) -> None:
        p = PromptDef(name="deploy", description="desc", handler=lambda: "")
        with pytest.raises(AttributeError):
            p.name = "other"  # type: ignore[misc]
        assert p.arguments == ()


class TestGlobalOption:
    def test_defaults(self) -> None:
        opt = GlobalOption(name="verbose")
        assert opt.short == ""
        assert opt.option_type is str
        assert opt.default is None
        assert opt.is_flag is False


class TestInvokeResult:
    def test_defaults(self) -> None:
        r = InvokeResult(output="ok", exit_code=0)
        assert r.result is None
        assert r.exception is None
        assert r.stderr == ""


# ---------------------------------------------------------------------------
# LazyCommandDef
# ---------------------------------------------------------------------------


class TestLazyCommandDef:
    def test_basic_creation(self) -> None:
        lazy = LazyCommandDef(
            name="greet",
            import_path="json:dumps",
            description="JSON dumps",
        )
        assert lazy.name == "greet"
        assert lazy.description == "JSON dumps"
        assert lazy.aliases == ()

    def test_resolve_valid_path(self) -> None:
        lazy = LazyCommandDef(
            name="dumps",
            import_path="json:dumps",
            description="JSON dumps",
        )
        cmd = lazy.resolve()
        assert isinstance(cmd, CommandDef)
        assert cmd.name == "dumps"
        assert cmd.handler.__name__ == "dumps"

    def test_resolve_invalid_path_no_colon(self) -> None:
        lazy = LazyCommandDef(
            name="bad",
            import_path="json.dumps",  # missing colon
            description="",
        )
        with pytest.raises(LazyImportError, match="Invalid import_path"):
            lazy.resolve()

    def test_resolve_invalid_module(self) -> None:
        lazy = LazyCommandDef(
            name="bad",
            import_path="nonexistent.module:func",
            description="",
        )
        with pytest.raises(LazyImportError) as exc_info:
            lazy.resolve()
        assert isinstance(exc_info.value.cause, ModuleNotFoundError)

    def test_resolve_invalid_attr(self) -> None:
        lazy = LazyCommandDef(
            name="bad",
            import_path="json:nonexistent_function",
            description="",
        )
        with pytest.raises(LazyImportError) as exc_info:
            lazy.resolve()
        assert isinstance(exc_info.value.cause, AttributeError)

    def test_resolve_cached(self) -> None:
        lazy = LazyCommandDef(
            name="dumps",
            import_path="json:dumps",
            description="JSON dumps",
        )
        cmd1 = lazy.resolve()
        cmd2 = lazy.resolve()
        assert cmd1 is cmd2

    def test_schema_with_precomputed(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        lazy = LazyCommandDef(
            name="test",
            import_path="json:dumps",
            description="",
            schema=schema,
        )
        # Schema available without resolving
        assert lazy.schema == schema
        assert lazy._resolved is None

    def test_schema_without_precomputed_triggers_resolve(self) -> None:
        lazy = LazyCommandDef(
            name="test",
            import_path="json:dumps",
            description="",
        )
        schema = lazy.schema
        assert isinstance(schema, dict)
        assert lazy._resolved is not None

    def test_handler_property_triggers_resolve(self) -> None:
        lazy = LazyCommandDef(
            name="test",
            import_path="json:dumps",
            description="",
        )
        handler = lazy.handler
        assert callable(handler)
        assert lazy._resolved is not None

    def test_resolve_thread_safety(self) -> None:
        """Concurrent resolves should produce the same CommandDef."""
        lazy = LazyCommandDef(
            name="dumps",
            import_path="json:dumps",
            description="",
        )
        results = []
        barrier = threading.Barrier(4)

        def resolve():
            barrier.wait()
            results.append(lazy.resolve())

        threads = [threading.Thread(target=resolve) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 4
        assert all(r is results[0] for r in results)

    def test_aliases_and_tags_coerced_to_tuple(self) -> None:
        lazy = LazyCommandDef(
            name="test",
            import_path="json:dumps",
            description="",
            aliases=["a", "b"],
            tags=["t1"],
        )
        assert isinstance(lazy.aliases, tuple)
        assert isinstance(lazy.tags, tuple)
        assert lazy.aliases == ("a", "b")

    def test_examples_coerced_to_tuple(self) -> None:
        lazy = LazyCommandDef(
            name="test",
            import_path="json:dumps",
            description="",
            examples=[{"input": "x"}],
        )
        assert isinstance(lazy.examples, tuple)


# ---------------------------------------------------------------------------
# _make_command_def
# ---------------------------------------------------------------------------


class TestMakeCommandDef:
    def test_basic(self) -> None:
        def greet(name: str) -> str:
            """Say hello to someone."""
            return f"Hello {name}"

        cmd = _make_command_def("greet", greet)
        assert cmd.name == "greet"
        assert cmd.description == "Say hello to someone."
        assert "name" in cmd.schema.get("properties", {})

    def test_multiline_docstring_uses_first_line(self) -> None:
        def build(target: str) -> str:
            """Build the target.

            This is a longer description.
            """
            return target

        cmd = _make_command_def("build", build)
        assert cmd.description == "Build the target."

    def test_explicit_description_overrides_docstring(self) -> None:
        def handler(x: int) -> int:
            """Docstring description."""
            return x

        cmd = _make_command_def("test", handler, description="Custom desc")
        assert cmd.description == "Custom desc"

    def test_no_docstring(self) -> None:
        def handler(x: int) -> int:
            return x

        cmd = _make_command_def("test", handler)
        assert cmd.description == ""


# ---------------------------------------------------------------------------
# _is_context_param
# ---------------------------------------------------------------------------


class TestIsContextParam:
    def test_no_annotation(self) -> None:
        def handler(x):
            pass

        sig = inspect.signature(handler)
        assert _is_context_param(sig.parameters["x"]) is False

    def test_type_annotation_named_context(self) -> None:
        from milo.context import Context

        def handler(ctx: Context = None):
            pass

        sig = inspect.signature(handler)
        assert _is_context_param(sig.parameters["ctx"]) is True
