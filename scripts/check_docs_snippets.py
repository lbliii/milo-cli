#!/usr/bin/env python3
"""Verify explicitly tagged Markdown code fences.

Only fences with a ``milo-docs:*`` directive are checked. This keeps the gate
safe to add incrementally while giving docs authors a way to prove runnable
snippets, Python snippets, and Kida snippets do not drift.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = (
    ROOT / "README.md",
    ROOT / "docs",
    ROOT / "site" / "content" / "docs",
    ROOT / "examples",
    ROOT / "src" / "milo" / "_scaffold" / "default" / "README.md",
)
FENCE_RE = re.compile(r"^```(?P<info>[^\n`]*)\n(?P<body>.*?)(?:\n```)", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class Snippet:
    path: Path
    line: int
    language: str
    directive: str
    options: dict[str, str]
    code: str

    @property
    def label(self) -> str:
        return f"{self.path}:{self.line}"


def _iter_markdown(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    docs: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        candidates = sorted(path.rglob("*.md")) if path.is_dir() else [path]
        for candidate in candidates:
            if "__pycache__" in candidate.parts:
                continue
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                docs.append(candidate)
    return docs


def _parse_info(info: str) -> tuple[str, str | None, dict[str, str]]:
    tokens = shlex.split(info)
    language = ""
    directive: str | None = None
    options: dict[str, str] = {}

    for index, token in enumerate(tokens):
        if token.startswith("milo-docs:"):
            directive = token.split(":", 1)[1]
        elif "=" in token:
            key, value = token.split("=", 1)
            options[key] = value
        elif index == 0:
            language = token

    return language, directive, options


def iter_snippets(paths: Iterable[Path]) -> list[Snippet]:
    snippets: list[Snippet] = []
    for path in _iter_markdown(paths):
        text = path.read_text(encoding="utf-8")
        for match in FENCE_RE.finditer(text):
            language, directive, options = _parse_info(match.group("info"))
            if directive is None:
                continue
            snippets.append(
                Snippet(
                    path=path,
                    line=text.count("\n", 0, match.start()) + 1,
                    language=language,
                    directive=directive,
                    options=options,
                    code=match.group("body").strip("\n"),
                )
            )
    return snippets


def _check_run(snippet: Snippet, repo_root: Path, timeout: int) -> list[str]:
    cwd = repo_root / snippet.options.get("cwd", ".")
    if not cwd.exists() or not cwd.is_dir():
        return [f"{snippet.label}: cwd does not exist: {cwd}"]

    try:
        result = subprocess.run(
            ["/bin/sh", "-c", snippet.code],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [f"{snippet.label}: command timed out after {timeout}s"]

    if result.returncode == 0:
        return []

    detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
    return [f"{snippet.label}: command failed\n{detail}"]


def _check_python(snippet: Snippet) -> list[str]:
    try:
        compile(snippet.code, snippet.label, "exec")
    except SyntaxError as exc:
        return [f"{snippet.label}: Python snippet does not compile: {exc}"]
    return []


def _check_kida(snippet: Snippet) -> list[str]:
    from milo.templates import get_env

    try:
        get_env().from_string(snippet.code, name=snippet.label)
    except Exception as exc:
        formatter = getattr(exc, "format_compact", None)
        detail = formatter() if callable(formatter) else f"{type(exc).__name__}: {exc}"
        return [f"{snippet.label}: Kida snippet does not compile\n{detail}"]
    return []


def check_snippet(snippet: Snippet, repo_root: Path, timeout: int = 30) -> list[str]:
    if snippet.directive == "skip":
        if snippet.options.get("reason"):
            return []
        return [f"{snippet.label}: milo-docs:skip requires reason=<why>"]

    if snippet.directive == "run":
        if snippet.language not in {"bash", "sh", "shell"}:
            return [f"{snippet.label}: milo-docs:run only supports shell fences"]
        return _check_run(snippet, repo_root=repo_root, timeout=timeout)

    if snippet.directive == "compile":
        if snippet.language == "python":
            return _check_python(snippet)
        if snippet.language == "kida":
            return _check_kida(snippet)
        return [f"{snippet.label}: unsupported compile language: {snippet.language or '<none>'}"]

    return [f"{snippet.label}: unknown directive milo-docs:{snippet.directive}"]


def check_paths(paths: Sequence[Path], repo_root: Path = ROOT, timeout: int = 30) -> list[str]:
    errors: list[str] = []
    for snippet in iter_snippets(paths):
        errors.extend(check_snippet(snippet, repo_root=repo_root, timeout=timeout))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Markdown files or directories to scan")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout for runnable snippets")
    args = parser.parse_args(argv)

    paths = args.paths or list(DEFAULT_TARGETS)
    errors = check_paths(paths, timeout=args.timeout)
    if errors:
        for error in errors:
            sys.stderr.write(error + "\n\n")
        sys.stderr.write(f"FAIL: {len(errors)} docs snippet check(s) failed\n")
        return 1

    count = len(iter_snippets(paths))
    sys.stdout.write(f"OK: {count} tagged docs snippet(s) passed\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
