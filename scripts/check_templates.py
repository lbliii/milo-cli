#!/usr/bin/env python3
"""Compile every .kida template under milo's built-ins and examples.

Uses ``milo.templates.get_env()`` so validation runs in terminal autoescape
mode with ``inline_components=True`` and ``validate_calls=True`` — the same
configuration that ships at runtime. This catches unknown filters, unknown
globals, arity mismatches, and syntax errors that the upstream
``kida check`` CLI misses because it only knows HTML-autoescape filters.
It also mirrors Kida's strict end-tag and fragile-path checks inside that
Milo-aware environment.

Exit code 0 = clean, 1 = one or more templates failed to compile.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUILTIN = ROOT / "src" / "milo" / "templates"
EXAMPLES = ROOT / "examples"


def _iter_templates(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.kida") if "__pycache__" not in p.parts)


def _check_root(root: Path, label: str) -> list[str]:
    from kida import FileSystemLoader
    from kida.analysis.fragile_paths import check_fragile_paths
    from kida.lexer import Lexer
    from kida.parser import Parser

    from milo.templates import get_env

    def explicit_close_suggestion(block_type: str) -> str:
        if block_type == "block":
            return "{% endblock %}"
        return f"{{% end{block_type} %}}"

    def check_strict_closures(path: Path, rel: str, env: Any) -> list[str]:
        source = path.read_text(encoding="utf-8")
        lexer_config = getattr(env, "_lexer_config", None)
        if lexer_config is None:
            return [
                f"[{label}] {rel}\n"
                "lint/internal: kida environment no longer exposes lexer configuration; "
                "strict end-tag lint could not run"
            ]
        lexer = Lexer(source, lexer_config)
        tokens = list(lexer.tokenize())
        parser = Parser(
            tokens,
            name=rel,
            filename=str(path),
            source=source,
            autoescape=env.select_autoescape(rel),
        )
        parser.parse()
        unified_end_closures = getattr(parser, "_unified_end_closures", None)
        if unified_end_closures is None:
            return [
                f"[{label}] {rel}\n"
                "lint/internal: kida parser no longer exposes unified end closures; "
                "strict end-tag lint could not run"
            ]
        errors: list[str] = []
        for lineno, _col, closing in unified_end_closures:
            want = explicit_close_suggestion(closing)
            errors.append(
                f"[{label}] {rel}:{lineno}\n"
                f"strict: unified {{% end %}} closes '{closing}' — prefer {want}"
            )
        return errors

    env = get_env(loader=FileSystemLoader(str(root)))
    errors: list[str] = []
    for path in _iter_templates(root):
        rel = path.relative_to(root).as_posix()
        try:
            tmpl = env.get_template(rel)
            errors.extend(check_strict_closures(path, rel, env))
            ast = getattr(tmpl, "_optimized_ast", None)
            if ast is None:
                errors.append(
                    f"[{label}] {rel}\n"
                    "lint/internal: kida template no longer exposes optimized AST; "
                    "fragile-path lint could not run"
                )
                continue
            errors.extend(
                (
                    f"[{label}] {rel}:{issue.lineno}\n"
                    "lint/fragile-path: "
                    f'{{% {issue.statement} "{issue.target}" %}} '
                    "is in the same folder as the caller — "
                    f'prefer "{issue.suggestion}" so folder moves stay zero-edit'
                )
                for issue in check_fragile_paths(ast, rel)
            )
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
