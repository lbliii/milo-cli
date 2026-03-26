"""Tests for help.py — HelpRenderer."""

from __future__ import annotations

import argparse

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
            groups=(
                {"title": "options", "actions": [{"dest": "verbose", "help": "Be verbose"}]},
            ),
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
