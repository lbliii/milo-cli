"""Tests for Context, global options, fuzzy matching, and error enhancements."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from milo._errors import (
    ConfigError,
    ErrorCode,
    MiloError,
    PipelineError,
    PluginError,
    format_error,
)
from milo.commands import CLI
from milo.context import Context, get_context, set_context

# ---------------------------------------------------------------------------
# Context basics
# ---------------------------------------------------------------------------


class TestContext:
    def test_defaults(self):
        ctx = Context()
        assert ctx.verbosity == 0
        assert ctx.format == "plain"
        assert ctx.color is True
        assert ctx.globals == {}

    def test_quiet(self):
        ctx = Context(verbosity=-1)
        assert ctx.quiet is True
        assert ctx.verbose is False

    def test_verbose(self):
        ctx = Context(verbosity=1)
        assert ctx.verbose is True
        assert ctx.quiet is False

    def test_debug(self):
        ctx = Context(verbosity=2)
        assert ctx.debug is True
        assert ctx.verbose is True

    def test_log_respects_verbosity(self, capsys):
        ctx = Context(verbosity=0)
        ctx.log("normal", level=0)
        ctx.log("verbose", level=1)
        captured = capsys.readouterr()
        assert "normal" in captured.err
        assert "verbose" not in captured.err

    def test_log_verbose(self, capsys):
        ctx = Context(verbosity=1)
        ctx.log("verbose", level=1)
        captured = capsys.readouterr()
        assert "verbose" in captured.err

    def test_frozen(self):
        ctx = Context()
        with pytest.raises(AttributeError):
            ctx.verbosity = 5

    def test_globals(self):
        ctx = Context(globals={"environment": "production"})
        assert ctx.globals["environment"] == "production"


class TestContextVar:
    def test_get_default(self):
        ctx = get_context()
        assert isinstance(ctx, Context)
        assert ctx.verbosity == 0

    def test_set_and_get(self):
        ctx = Context(verbosity=2)
        set_context(ctx)
        assert get_context() is ctx


# ---------------------------------------------------------------------------
# Global options on CLI
# ---------------------------------------------------------------------------


class TestGlobalOptions:
    def test_global_option_registration(self):
        cli = CLI(name="app")
        cli.global_option(
            "environment", short="-e", default="local", description="Config environment"
        )
        assert len(cli._global_options) == 1
        assert cli._global_options[0].name == "environment"

    def test_global_option_in_parser(self):
        cli = CLI(name="app")
        cli.global_option("environment", short="-e", default="local")

        @cli.command("build", description="Build")
        def build() -> str:
            return "built"

        parser = cli.build_parser()
        args = parser.parse_args(["-e", "production", "build"])
        assert args.environment == "production"

    def test_verbose_flag(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build() -> str:
            return "built"

        parser = cli.build_parser()
        args = parser.parse_args(["-v", "build"])
        assert args.verbose == 1

        args2 = parser.parse_args(["-vv", "build"])
        assert args2.verbose == 2

    def test_quiet_flag(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build() -> str:
            return "built"

        parser = cli.build_parser()
        args = parser.parse_args(["-q", "build"])
        assert args.quiet is True

    def test_no_color_flag(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build() -> str:
            return "built"

        parser = cli.build_parser()
        args = parser.parse_args(["--no-color", "build"])
        assert args.no_color is True


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------


class TestContextInjection:
    def test_ctx_injected_into_handler(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build(ctx: Context = None) -> dict:
            return {"verbosity": ctx.verbosity, "color": ctx.color}

        result = cli.run(["-v", "build"])
        assert result == {"verbosity": 1, "color": True}

    def test_ctx_with_quiet(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build(ctx: Context = None) -> int:
            return ctx.verbosity

        result = cli.run(["-q", "build"])
        assert result == -1

    def test_ctx_globals_populated(self):
        cli = CLI(name="app")
        cli.global_option("environment", short="-e", default="local")

        @cli.command("build", description="Build")
        def build(ctx: Context = None) -> str:
            return ctx.globals.get("environment", "none")

        result = cli.run(["-e", "prod", "build"])
        assert result == "prod"

    def test_ctx_not_in_schema(self):
        """Context parameter should not appear in JSON schema."""
        from milo.schema import function_to_schema

        def build(output: str, ctx: Context = None) -> str:
            return output

        schema = function_to_schema(build)
        assert "ctx" not in schema.get("properties", {})
        assert "output" in schema["properties"]

    def test_handler_without_ctx_still_works(self):
        cli = CLI(name="app")

        @cli.command("greet", description="Greet")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        result = cli.run(["greet", "--name", "World"])
        assert result == "Hello, World!"


# ---------------------------------------------------------------------------
# Fuzzy command matching
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    def test_suggest_close_match(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build():
            pass

        @cli.command("serve", description="Serve")
        def serve():
            pass

        assert cli.suggest_command("bild") == "build"
        assert cli.suggest_command("serv") == "serve"

    def test_suggest_no_match(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build():
            pass

        assert cli.suggest_command("zzzzz") is None

    def test_suggest_dotted_path(self):
        cli = CLI(name="app")
        site = cli.group("site")

        @site.command("build", description="Build")
        def build():
            pass

        assert cli.suggest_command("site.bild") == "site.build"

    def test_call_unknown_with_suggestion(self):
        cli = CLI(name="app")

        @cli.command("build", description="Build")
        def build():
            pass

        with pytest.raises(ValueError, match="Did you mean 'build'"):
            cli.call("bild")


# ---------------------------------------------------------------------------
# Enhanced errors
# ---------------------------------------------------------------------------


class TestEnhancedErrors:
    def test_error_with_suggestion(self):
        err = MiloError(
            ErrorCode.CMD_NOT_FOUND,
            "Command not found: bild",
            suggestion="Did you mean 'build'?",
        )
        compact = err.format_compact()
        assert "M-CMD-001" in compact
        assert "hint:" in compact
        assert "build" in compact

    def test_error_with_docs_url(self):
        err = MiloError(
            ErrorCode.CFG_PARSE,
            "Invalid YAML",
            docs_url="https://docs.example.com/config",
        )
        compact = err.format_compact()
        assert "docs:" in compact

    def test_error_with_context(self):
        err = MiloError(
            ErrorCode.PIP_PHASE,
            "Phase failed",
            context={"phase": "render", "duration": 1.5},
        )
        assert err.context["phase"] == "render"

    def test_config_error(self):
        err = ConfigError(ErrorCode.CFG_PARSE, "Bad YAML")
        assert isinstance(err, MiloError)

    def test_pipeline_error(self):
        err = PipelineError(ErrorCode.PIP_PHASE, "Phase failed")
        assert isinstance(err, MiloError)

    def test_plugin_error(self):
        err = PluginError(ErrorCode.PLG_LOAD, "Plugin not found")
        assert isinstance(err, MiloError)

    def test_format_error_with_suggestion(self):
        err = MiloError(
            ErrorCode.CMD_NOT_FOUND,
            "Not found",
            suggestion="Try 'build'",
        )
        output = format_error(err)
        assert "hint:" in output
        assert "Try 'build'" in output

    def test_new_error_codes(self):
        assert ErrorCode.CFG_PARSE.value == "M-CFG-001"
        assert ErrorCode.PIP_PHASE.value == "M-PIP-001"
        assert ErrorCode.PLG_LOAD.value == "M-PLG-001"
        assert ErrorCode.CMD_NOT_FOUND.value == "M-CMD-001"


class TestContextEnhancements:
    def test_dry_run_default(self):
        ctx = Context()
        assert ctx.dry_run is False

    def test_dry_run_set(self):
        ctx = Context(dry_run=True)
        assert ctx.dry_run is True

    def test_output_file_default(self):
        ctx = Context()
        assert ctx.output_file == ""

    def test_is_ci_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            ctx = Context()
            assert ctx.is_ci is False

    def test_is_ci_with_env(self):
        with patch.dict(os.environ, {"CI": "true"}):
            ctx = Context()
            assert ctx.is_ci is True

    def test_info_writes_to_stderr(self, capsys):
        ctx = Context(color=False)
        ctx.info("hello")
        assert "info: hello" in capsys.readouterr().err

    def test_success_writes_to_stderr(self, capsys):
        ctx = Context(color=False)
        ctx.success("done")
        assert "OK: done" in capsys.readouterr().err

    def test_warning_writes_to_stderr(self, capsys):
        ctx = Context(color=False)
        ctx.warning("watch out")
        assert "warning: watch out" in capsys.readouterr().err

    def test_error_writes_to_stderr(self, capsys):
        ctx = Context(color=False)
        ctx.error("bad")
        assert "error: bad" in capsys.readouterr().err

    def test_warning_shown_when_quiet(self, capsys):
        ctx = Context(verbosity=-1, color=False)
        ctx.warning("still shown")
        assert "warning: still shown" in capsys.readouterr().err

    def test_info_suppressed_when_quiet(self, capsys):
        ctx = Context(verbosity=-1, color=False)
        ctx.info("hidden")
        assert capsys.readouterr().err == ""

    def test_confirm_dry_run_returns_false(self):
        ctx = Context(dry_run=True, color=False)
        assert ctx.confirm("Delete?") is False

    def test_confirm_non_interactive_returns_default(self):
        ctx = Context(color=False)
        # If stdin is not a TTY (e.g., in tests), returns default
        if not sys.stdin.isatty():
            assert ctx.confirm("Delete?", default=True) is True
            assert ctx.confirm("Delete?", default=False) is False

    def test_progress_context_manager(self, capsys):
        ctx = Context(color=False)
        with ctx.progress(total=10, label="Test") as p:
            for _ in range(10):
                p.update(1)
        # Should write something to stderr
        err = capsys.readouterr().err
        assert "Test" in err

    def test_progress_quiet_mode(self, capsys):
        ctx = Context(verbosity=-1, color=False)
        with ctx.progress(total=5) as p:
            p.update(5)
        assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Context.run_app (CLI-to-App bridge)
# ---------------------------------------------------------------------------


class TestRunApp:
    def test_run_app_returns_final_state(self):
        """run_app launches an App and returns the final state."""
        from dataclasses import dataclass as dc
        from unittest.mock import MagicMock, patch

        @dc(frozen=True)
        class PickState:
            picked: str = "hello"

        def picker_reducer(state, action):
            if state is None:
                return PickState()
            return state

        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("{{ state.picked }}")
        env = MagicMock()
        env.get_template.return_value = tmpl

        ctx = Context()
        with patch("milo.app.is_tty", return_value=False), patch("sys.stdout"):
            result = ctx.run_app(
                reducer=picker_reducer,
                template="picker.kida",
                initial_state=PickState(),
                env=env,
            )
        assert isinstance(result, PickState)
        assert result.picked == "hello"

    def test_run_app_passes_env(self):
        """run_app forwards the env parameter to App."""
        from unittest.mock import MagicMock, patch

        env = MagicMock()
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("x")
        env.get_template.return_value = tmpl

        def r(s, a):
            return s or 0

        ctx = Context()
        with patch("milo.app.is_tty", return_value=False), patch("sys.stdout"):
            ctx.run_app(reducer=r, template="t.kida", initial_state=0, env=env)
        env.get_template.assert_called()
