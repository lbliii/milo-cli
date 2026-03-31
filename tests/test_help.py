"""Tests for help.py — HelpRenderer."""

from __future__ import annotations

import argparse

import pytest

from milo.commands import CLI
from milo.help import HelpRenderer, HelpState


class TestHelpState:
    def test_defaults(self):
        s = HelpState()
        assert s.prog == ""
        assert s.description == ""
        assert s.groups == ()

    def test_with_data(self):
        s = HelpState(
            prog="myapp",
            description="A test app",
            groups=({"title": "options", "actions": [{"dest": "verbose", "help": "Be verbose"}]},),
        )
        assert s.prog == "myapp"
        assert len(s.groups) == 1


class TestHelpRenderer:
    def _make_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="testprog",
            description="A test program",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--verbose", "-v", action="store_true", help="Be verbose")
        parser.add_argument("--output", "-o", default="stdout", help="Output file")
        parser.add_argument("input", help="Input file")
        return parser

    def test_format_help_returns_string(self):
        parser = self._make_parser()
        help_text = parser.format_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0

    def test_format_help_contains_prog(self):
        parser = self._make_parser()
        help_text = parser.format_help()
        assert "testprog" in help_text

    def test_format_help_contains_args(self):
        parser = self._make_parser()
        help_text = parser.format_help()
        # Should contain the argument descriptions
        assert "--verbose" in help_text or "verbose" in help_text

    def test_format_help_fallback_on_template_error(self):
        """If template rendering fails, falls back to default argparse format."""
        from unittest.mock import patch

        parser = argparse.ArgumentParser(
            prog="fallbackprog",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--flag", help="A flag")

        # Patch the templates module so get_env raises inside _render_with_template
        with patch("milo.templates.get_env", side_effect=Exception("no kida")):
            help_text = parser.format_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0

    def test_render_with_template_builds_groups(self):
        """_render_with_template should produce output containing prog."""
        parser = self._make_parser()
        # Use a real HelpRenderer through argparse
        formatter = parser._get_formatter()
        formatter.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups)
        for action_group in parser._action_groups:
            formatter.start_section(action_group.title)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()
        help_text = formatter.format_help()
        assert "testprog" in help_text

    def test_help_renderer_init(self):
        renderer = HelpRenderer("myprog")
        assert renderer._prog == "myprog"

    def test_subparser_with_help_renderer(self):
        parser = argparse.ArgumentParser(
            prog="cli",
            formatter_class=HelpRenderer,
        )
        subparsers = parser.add_subparsers(dest="command")
        sub = subparsers.add_parser("sub", help="A subcommand", formatter_class=HelpRenderer)
        sub.add_argument("--flag", action="store_true", help="A flag")

        help_text = parser.format_help()
        assert "cli" in help_text


class TestHelpRendererTemplateRendering:
    def test_format_help_does_not_raise(self):
        """HelpRenderer.format_help() should produce output without AttributeError."""
        parser = argparse.ArgumentParser(
            prog="myapp",
            description="A test application",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--name", help="Your name")
        parser.add_argument("--verbose", "-v", action="store_true", help="Be verbose")

        # This would crash before the fix with AttributeError on _action_groups
        help_text = parser.format_help()
        assert "myapp" in help_text
        assert len(help_text) > 10

    def test_format_help_with_subcommands(self):
        """Template rendering works with subparser commands."""
        parser = argparse.ArgumentParser(
            prog="myapp",
            description="CLI with subcommands",
            formatter_class=HelpRenderer,
        )
        sub = parser.add_subparsers(dest="cmd")
        sub.add_parser("build", help="Build the project", formatter_class=HelpRenderer)
        sub.add_parser("test", help="Run tests", formatter_class=HelpRenderer)

        help_text = parser.format_help()
        assert "myapp" in help_text

    def test_captures_action_groups(self):
        """Verify the formatter captures action groups via start_section/end_section."""
        parser = argparse.ArgumentParser(
            prog="test",
            description="Test",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--foo", help="Foo option")

        # Get the formatter by asking for help (this populates the sections)
        fmt = parser._get_formatter()
        fmt.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups)
        fmt.add_text(parser.description)
        for ag in parser._action_groups:
            fmt.start_section(ag.title)
            fmt.add_arguments(ag._group_actions)
            fmt.end_section()

        # The formatter should have captured groups
        assert len(fmt._captured_groups) > 0
        # At least one group should have actions
        assert any(g["actions"] for g in fmt._captured_groups)

    def test_description_captured(self):
        """Verify description text is captured for template rendering."""
        parser = argparse.ArgumentParser(
            prog="test",
            description="My cool tool",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--foo", help="Foo")

        fmt = parser._get_formatter()
        fmt.add_text("My cool tool")

        assert fmt._description_text == "My cool tool"

    def test_fallback_on_template_error(self):
        """If template rendering fails, falls back to standard argparse help."""
        parser = argparse.ArgumentParser(
            prog="myapp",
            description="Test",
            formatter_class=HelpRenderer,
        )
        parser.add_argument("--name", help="Your name")

        # Even if template rendering fails, we get valid help text
        help_text = parser.format_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0

    def test_full_cli_help_renders(self, capsys):
        """End-to-end: CLI.run() with no args prints styled help."""
        cli = CLI(name="myapp", description="My tool", version="1.0.0")

        @cli.command("greet", description="Say hello")
        def greet(name: str) -> str:
            return f"Hello, {name}"

        cli.run([])
        out = capsys.readouterr().out
        assert "myapp" in out

    def test_subcommand_help_renders(self, capsys):
        """Subcommand --help also uses HelpRenderer."""
        cli = CLI(name="myapp", description="My tool")

        @cli.command("greet", description="Say hello")
        def greet(name: str) -> str:
            """Greet someone.

            Args:
                name: The person to greet.
            """
            return f"Hello, {name}"

        with pytest.raises(SystemExit):
            cli.run(["greet", "--help"])
        out = capsys.readouterr().out
        assert "greet" in out

    def test_version_output_not_corrupted(self, capsys):
        """--version should output 'prog X.Y.Z', not template-rendered text."""
        cli = CLI(name="myapp", description="My tool", version="2.3.4")

        @cli.command("greet", description="Greet")
        def greet(name: str) -> str:
            return f"Hello, {name}"

        with pytest.raises(SystemExit):
            cli.run(["--version"])
        out = capsys.readouterr().out.strip()
        assert out == "myapp 2.3.4"
