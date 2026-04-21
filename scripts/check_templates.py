#!/usr/bin/env python3
"""Compile every .kida template under milo's built-ins and examples.

Uses ``milo.templates.get_env()`` so validation runs in terminal autoescape
mode with ``inline_components=True`` and ``validate_calls=True`` — the same
configuration that ships at runtime. This catches unknown filters, unknown
globals, arity mismatches, and syntax errors that the upstream
``kida check`` CLI misses because it only knows HTML-autoescape filters.

Exit code 0 = clean, 1 = one or more templates failed to compile.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILTIN = ROOT / "src" / "milo" / "templates"
EXAMPLES = ROOT / "examples"


def _iter_templates(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.kida") if "__pycache__" not in p.parts)


def _check_root(root: Path, label: str) -> list[str]:
    from kida import FileSystemLoader

    from milo.templates import get_env

    env = get_env(loader=FileSystemLoader(str(root)))
    errors: list[str] = []
    for path in _iter_templates(root):
        rel = path.relative_to(root).as_posix()
        try:
            env.get_template(rel)
        except Exception as exc:
            formatter = getattr(exc, "format_compact", None)
            detail = formatter() if callable(formatter) else f"{type(exc).__name__}: {exc}"
            errors.append(f"[{label}] {rel}\n{detail}")
    return errors


def main() -> int:
    all_errors: list[str] = []
    all_errors.extend(_check_root(BUILTIN, "builtin"))

    if EXAMPLES.exists():
        for example in sorted(EXAMPLES.iterdir()):
            tmpl_dir = example / "templates"
            if tmpl_dir.is_dir():
                all_errors.extend(_check_root(tmpl_dir, f"examples/{example.name}"))

    if all_errors:
        for err in all_errors:
            sys.stderr.write(err + "\n\n")
        sys.stderr.write(f"FAIL: {len(all_errors)} template(s) failed to compile\n")
        return 1

    sys.stdout.write("OK: all templates compile cleanly\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
