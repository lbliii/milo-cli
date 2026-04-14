#!/usr/bin/env python3
"""Lint for silent exception swallowing patterns that ruff S110 misses.

Checks production code (src/) for:
1. contextlib.suppress(Exception) without a ``# silent:`` justification
2. ``except ...: continue`` without logging or a ``# silent:`` comment

Exit code 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SUPPRESS_RE = re.compile(r"contextlib\.suppress\(\s*Exception\s*\)")
_SILENT_TAG = re.compile(r"#\s*silent:")

SRC = Path("src")


def _check_file(path: Path) -> list[str]:
    violations: list[str] = []
    lines = path.read_text().splitlines()

    for i, line in enumerate(lines, 1):
        # Pattern 1: contextlib.suppress(Exception) without justification
        if _SUPPRESS_RE.search(line) and not _SILENT_TAG.search(line):
            violations.append(
                f"{path}:{i}: contextlib.suppress(Exception) without '# silent: <reason>'"
            )

        # Pattern 2: bare except-continue (no logging on same or next line)
        stripped = line.strip()
        if stripped in ("continue", "continue  # noqa"):
            # Walk back to find enclosing except
            for j in range(i - 2, max(i - 5, -1), -1):
                prev = lines[j].strip() if 0 <= j < len(lines) else ""
                if prev.startswith("except"):
                    # Check if there's logging between except and continue
                    block = "\n".join(lines[j : i - 1])
                    if "log" not in block and "warn" not in block and "# silent:" not in block:
                        violations.append(
                            f"{path}:{i}: except-continue without logging or '# silent: <reason>'"
                        )
                    break

    return violations


def main() -> int:
    if not SRC.exists():
        return 0

    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        violations.extend(_check_file(path))

    for v in violations:
        print(v, file=sys.stderr)

    if violations:
        print(
            f"\n{len(violations)} silent-exception violation(s). "
            "Add '# silent: <reason>' to justify, or add logging.",
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
