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

    def format_help(self) -> str:
        """Format help using kida template if available, else fall back to default."""
        try:
            return self._render_with_template()
        except Exception:
            return super().format_help()

    def _render_with_template(self) -> str:
        """Render help through the kida help template."""
        from milo.templates import get_env

        env = get_env()
        template = env.get_template("help.txt")

        groups = []
        for action_group in self._action_groups:  # type: ignore[attr-defined]
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
                for action in action_group._group_actions
            ]
            if actions:
                groups.append({
                    "title": action_group.title or "",
                    "actions": actions,
                })

        state = HelpState(
            prog=self._prog,
            description=self._root_section.heading or "",
            groups=tuple(groups),
        )

        return template.render(state=state)
