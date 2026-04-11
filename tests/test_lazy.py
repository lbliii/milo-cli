"""Tests for lazy command loading."""

from __future__ import annotations

import sys
import threading

import pytest

from milo.commands import CLI, CommandDef, LazyCommandDef

# ---------------------------------------------------------------------------
# LazyCommandDef basics
# ---------------------------------------------------------------------------


class TestLazyCommandDef:
    def test_create(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        assert cmd.name == "greet"
        assert cmd.description == "Say hello"
        assert cmd.import_path == "_lazy_handlers:greet"
        assert cmd.hidden is False

    def test_resolve(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        resolved = cmd.resolve()
        assert isinstance(resolved, CommandDef)
        assert resolved.name == "greet"
        assert resolved.handler is not None
        assert resolved.handler(name="World") == "Hello, World!"

    def test_resolve_caches(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        first = cmd.resolve()
        second = cmd.resolve()
        assert first is second

    def test_schema_from_resolve(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        schema = cmd.schema
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"

    def test_schema_precomputed(self):
        pre_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
            schema=pre_schema,
        )
        # Schema available without resolving
        assert cmd.schema is pre_schema
        # Not yet resolved
        assert cmd._resolved is None

    def test_handler_property_resolves(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        handler = cmd.handler
        assert callable(handler)
        assert handler(name="Test") == "Hello, Test!"

    def test_invalid_import_path_no_colon(self):
        cmd = LazyCommandDef(
            "bad",
            "no_colon_here",
            description="Bad path",
        )
        with pytest.raises(ValueError, match=r"expected 'module\.path:attribute'"):
            cmd.resolve()

    def test_invalid_module(self):
        cmd = LazyCommandDef(
            "bad",
            "nonexistent.module:func",
            description="Bad module",
        )
        with pytest.raises(ModuleNotFoundError):
            cmd.resolve()

    def test_invalid_attribute(self):
        cmd = LazyCommandDef(
            "bad",
            "_lazy_handlers:nonexistent",
            description="Bad attr",
        )
        with pytest.raises(AttributeError):
            cmd.resolve()

    def test_thread_safety(self):
        cmd = LazyCommandDef(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        results = []
        errors = []

        def resolve_cmd():
            try:
                resolved = cmd.resolve()
                results.append(resolved)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_cmd) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
        # All threads should get the same resolved instance
        assert all(r is results[0] for r in results)


# ---------------------------------------------------------------------------
# CLI with lazy commands
# ---------------------------------------------------------------------------


class TestCLILazy:
    def test_lazy_command_registration(self):
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        assert "greet" in cli.commands
        assert isinstance(cli.commands["greet"], LazyCommandDef)

    def test_lazy_command_call(self):
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        result = cli.call("greet", name="Lazy")
        assert result == "Hello, Lazy!"

    def test_lazy_command_run(self):
        cli = CLI(name="app")
        cli.lazy_command(
            "add",
            "_lazy_handlers:add",
            description="Add numbers",
        )
        result = cli.run(["add", "--a", "3", "--b", "7"])
        assert result == 10

    def test_lazy_command_get_command(self):
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
            aliases=("g",),
        )
        cmd = cli.get_command("greet")
        assert cmd is not None
        assert cmd.name == "greet"

        # Alias lookup
        cmd_alias = cli.get_command("g")
        assert cmd_alias is not None
        assert cmd_alias.name == "greet"

    def test_lazy_and_eager_coexist(self):
        cli = CLI(name="app")

        @cli.command("eager", description="Eager command")
        def eager() -> str:
            return "eager"

        cli.lazy_command(
            "lazy",
            "_lazy_handlers:greet",
            description="Lazy command",
        )

        assert isinstance(cli.commands["eager"], CommandDef)
        assert isinstance(cli.commands["lazy"], LazyCommandDef)

        assert cli.call("eager") == "eager"
        assert cli.call("lazy", name="X") == "Hello, X!"

    def test_lazy_walk_commands(self):
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        walked = cli.walk_commands()
        assert any(path == "greet" for path, _ in walked)

    def test_lazy_with_precomputed_schema_no_import(self):
        """Ensure pre-computed schema avoids module import."""
        # Clear the module from cache to detect import
        mod_name = "_lazy_handlers"
        was_loaded = mod_name in sys.modules
        if was_loaded:
            saved = sys.modules.pop(mod_name)

        try:
            pre_schema = {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
            cli = CLI(name="app")
            cli.lazy_command(
                "greet",
                f"{mod_name}:greet",
                description="Say hello",
                schema=pre_schema,
            )

            # Building parser and accessing schema should NOT import the module
            cli.build_parser()
            cmd = cli.commands["greet"]
            _ = cmd.schema
            assert mod_name not in sys.modules
        finally:
            if was_loaded:
                sys.modules[mod_name] = saved


# ---------------------------------------------------------------------------
# Groups with lazy commands
# ---------------------------------------------------------------------------


class TestGroupLazy:
    def test_lazy_in_group(self):
        cli = CLI(name="app")
        site = cli.group("site")
        site.lazy_command(
            "build",
            "_lazy_handlers:greet",
            description="Build site",
        )
        cmd = cli.get_command("site.build")
        assert cmd is not None
        assert isinstance(cmd, LazyCommandDef)

    def test_lazy_in_group_call(self):
        cli = CLI(name="app")
        site = cli.group("site")
        site.lazy_command(
            "build",
            "_lazy_handlers:greet",
            description="Build site",
        )
        result = cli.call("site.build", name="GroupLazy")
        assert result == "Hello, GroupLazy!"

    def test_lazy_in_group_run(self):
        cli = CLI(name="app")
        site = cli.group("site")
        site.lazy_command(
            "add",
            "_lazy_handlers:add",
            description="Add numbers",
        )
        result = cli.run(["site", "add", "--a", "10", "--b", "20"])
        assert result == 30


# ---------------------------------------------------------------------------
# Lazy commands: default value propagation
# ---------------------------------------------------------------------------


class TestLazyDefaults:
    def test_lazy_command_uses_signature_defaults(self):
        """Lazy commands should use function defaults when args are omitted."""
        cli = CLI(name="app")
        cli.lazy_command(
            "add",
            "_lazy_handlers:add",
            description="Add numbers",
        )
        # b has default=0 in the handler; omitting --b should use 0, not None
        result = cli.run(["add", "--a", "5"])
        assert result == 5

    def test_lazy_command_precomputed_schema_with_defaults(self):
        """Pre-computed schemas with 'default' fields should propagate."""
        cli = CLI(name="app")
        cli.lazy_command(
            "add",
            "_lazy_handlers:add",
            description="Add numbers",
            schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer", "default": 0},
                },
                "required": ["a"],
            },
        )
        result = cli.run(["add", "--a", "5"])
        assert result == 5

    def test_lazy_command_bool_default_false(self):
        """Boolean defaults should work for lazy commands."""
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        result = cli.run(["greet", "--name", "World"])
        assert result == "Hello, World!"

    def test_lazy_command_bool_default_override(self):
        """Boolean flags should be overridable for lazy commands."""
        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        result = cli.run(["greet", "--name", "World", "--loud"])
        assert result == "HELLO, WORLD!"

    def test_schema_defaults_are_json_serializable(self):
        """function_to_schema() should only store JSON-safe defaults."""
        import json

        from milo.schema import function_to_schema

        def handler(name: str, count: int = 5, flag: bool = True) -> str:
            return ""

        schema = function_to_schema(handler)
        # Should not raise
        json.dumps(schema)
        assert schema["properties"]["count"]["default"] == 5
        assert schema["properties"]["flag"]["default"] is True

    def test_schema_omits_non_serializable_defaults(self):
        """Non-JSON-serializable defaults should be omitted from schema."""
        import json
        from pathlib import Path

        from milo.schema import function_to_schema

        def handler(output: Path = Path(".")) -> str:
            return ""

        schema = function_to_schema(handler)
        # Should not raise
        json.dumps(schema)
        # Path default should NOT be in the schema
        assert "default" not in schema["properties"]["output"]


# ---------------------------------------------------------------------------
# display_result suppression
# ---------------------------------------------------------------------------


class TestDisplayResult:
    def test_display_result_false_suppresses_plain(self):
        """display_result=False suppresses plain stdout output."""
        cli = CLI(name="app")

        @cli.command("info", display_result=False)
        def info() -> dict:
            return {"status": "ok", "count": 42}

        result = cli.invoke(["info"])
        assert result.output == ""
        assert result.result == {"status": "ok", "count": 42}

    def test_display_result_false_allows_json(self):
        """display_result=False still outputs with --format json."""
        cli = CLI(name="app")

        @cli.command("info", display_result=False)
        def info() -> dict:
            return {"status": "ok"}

        result = cli.invoke(["info", "--format", "json"])
        assert '"status"' in result.output

    def test_display_result_true_default(self):
        """By default, display_result=True and output is shown."""
        cli = CLI(name="app")

        @cli.command("info")
        def info() -> str:
            return "hello"

        result = cli.invoke(["info"])
        assert "hello" in result.output

    def test_lazy_display_result_false(self):
        """Lazy commands support display_result=False."""
        cli = CLI(name="app")
        cli.lazy_command(
            "add",
            "_lazy_handlers:add",
            description="Add numbers",
            display_result=False,
        )
        result = cli.invoke(["add", "--a", "3", "--b", "7"])
        assert result.output == ""
        assert result.result == 10


# ---------------------------------------------------------------------------
# MCP with lazy commands
# ---------------------------------------------------------------------------


class TestMCPLazy:
    def test_mcp_list_includes_lazy(self):
        from milo.mcp import _list_tools

        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
            schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        tools = _list_tools(cli)
        assert any(t["name"] == "greet" for t in tools)

    def test_mcp_call_lazy(self):
        from milo.mcp import _call_tool

        cli = CLI(name="app")
        cli.lazy_command(
            "greet",
            "_lazy_handlers:greet",
            description="Say hello",
        )
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "MCP"}})
        assert result["content"][0]["text"] == "Hello, MCP!"
