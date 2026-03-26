"""Structured output formatting for CLI commands."""

from __future__ import annotations

import json
import sys
from typing import Any


def format_output(data: Any, fmt: str = "plain", template: str = "") -> str:
    """Format command output based on requested format.

    Formats:
        plain  — human-readable (default)
        json   — JSON output
        table  — tabular output (for lists of dicts)
        template — render through a kida template
    """
    match fmt:
        case "json":
            return _format_json(data)
        case "table":
            return _format_table(data)
        case "template":
            return _format_template(data, template)
        case _:
            return _format_plain(data)


def _format_json(data: Any) -> str:
    """JSON output."""
    return json.dumps(data, indent=2, default=str)


def _format_plain(data: Any) -> str:
    """Human-readable plain output."""
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, dict):
                parts = [f"{v}" for v in item.values()]
                lines.append("  ".join(parts))
            else:
                lines.append(str(item))
        return "\n".join(lines)
    if isinstance(data, dict):
        lines = []
        max_key = max((len(str(k)) for k in data), default=0)
        for k, v in data.items():
            lines.append(f"  {k!s:<{max_key}}  {v}")
        return "\n".join(lines)
    return str(data)


def _format_table(data: Any) -> str:
    """Table output using kida's table filter if available."""
    if not isinstance(data, list):
        return _format_plain(data)

    if not data:
        return "(empty)"

    # Extract headers from first dict item
    if isinstance(data[0], dict):
        headers = list(data[0].keys())
        rows = [[str(item.get(h, "")) for h in headers] for item in data]
    else:
        headers = None
        rows = [[str(item)] for item in data]

    try:
        from kida import Environment

        env = Environment(autoescape="terminal")
        tmpl = env.from_string("{{ data | table(headers=headers) }}", name="table_fmt")
        return tmpl.render(data=rows, headers=headers or [])
    except ImportError:
        # Fallback: simple column alignment
        all_rows = [headers, *rows] if headers else rows
        widths = [max(len(str(cell)) for cell in col) for col in zip(*all_rows, strict=False)]
        lines = []
        for row in all_rows:
            lines.append("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths, strict=False)))
            if row is headers:
                lines.append("  ".join("-" * w for w in widths))
        return "\n".join(lines)


def _format_template(data: Any, template_name: str) -> str:
    """Render through a kida template."""
    if not template_name:
        return _format_plain(data)
    from milo.templates import get_env

    env = get_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(state=data)


def write_output(data: Any, fmt: str = "plain", template: str = "") -> None:
    """Format and write command output to stdout."""
    output = format_output(data, fmt=fmt, template=template)
    sys.stdout.write(output + "\n")
    sys.stdout.flush()
