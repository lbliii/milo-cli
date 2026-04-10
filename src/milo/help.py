"""HelpRenderer — argparse formatter_class for styled help output."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HelpState:
    """State for help rendering."""

    prog: str = ""
    description: str = ""
    epilog: str = ""
    usage: str = ""
    groups: tuple[dict[str, Any], ...] = ()
    examples: tuple[dict[str, Any], ...] = ()
    commands: tuple[dict[str, Any], ...] = ()
    options: tuple[dict[str, Any], ...] = ()


class HelpRenderer(argparse.HelpFormatter):
    """Argparse formatter that renders through kida templates.

    Usage::

        parser = argparse.ArgumentParser(
            formatter_class=HelpRenderer,
        )
    """

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 24,
        width: int | None = None,
    ) -> None:
        super().__init__(prog, indent_increment, max_help_position, width)
        self._prog = prog
        self._captured_groups: list[dict[str, Any]] = []
        self._current_group_title: str = ""
        self._current_group_actions: list[argparse.Action] = []
        self._description_text: str = ""
        self._examples: tuple[dict[str, Any], ...] = ()

    def add_text(self, text: str | None) -> None:
        """Capture description text before passing to base."""
        if text and not self._description_text:
            self._description_text = text
        super().add_text(text)

    def start_section(self, heading: str | None) -> None:
        """Track the current section heading."""
        self._current_group_title = heading or ""
        self._current_group_actions = []
        super().start_section(heading)

    def add_arguments(self, actions: Any) -> None:
        """Capture actions for the current section."""
        self._current_group_actions.extend(actions)
        super().add_arguments(actions)

    def end_section(self) -> None:
        """Finalize the current section and store its actions."""
        if self._current_group_actions:
            actions = [
                {
                    "option_strings": action.option_strings,
                    "dest": action.dest,
                    "help": action.help or "",
                    "default": action.default,
                    "required": getattr(action, "required", False),
                    "choices": action.choices,
                    "nargs": action.nargs,
                    "metavar": action.metavar,
                }
                for action in self._current_group_actions
            ]
            self._captured_groups.append(
                {
                    "title": self._current_group_title,
                    "actions": actions,
                }
            )
        self._current_group_title = ""
        self._current_group_actions = []
        super().end_section()

    def format_help(self) -> str:
        """Format help using kida template if available, else fall back to default."""
        try:
            return self._render_with_template()
        except Exception:
            return super().format_help()

    def _render_with_template(self) -> str:
        """Render help through the kida help template.

        Argparse reuses formatter_class for non-help output (--version,
        add_subparsers prog extraction).  In those cases no action groups
        are captured, so we fall back to the default argparse formatter.
        """
        if not self._captured_groups:
            raise ValueError("no content for template")

        from milo.templates import get_env

        env = get_env()
        template = env.get_template("help.kida")

        state = HelpState(
            prog=self._prog,
            description=self._description_text,
            groups=tuple(self._captured_groups),
            examples=self._examples,
        )

        return template.render(state=state)


def help_formatter_with_examples(
    examples: tuple[dict[str, Any], ...],
) -> type[HelpRenderer]:
    """Create a HelpRenderer subclass that includes command examples."""

    class _HelpRendererWithExamples(HelpRenderer):
        def __init__(
            self,
            prog: str,
            indent_increment: int = 2,
            max_help_position: int = 24,
            width: int | None = None,
        ) -> None:
            super().__init__(prog, indent_increment, max_help_position, width)
            self._examples = examples

    return _HelpRendererWithExamples
