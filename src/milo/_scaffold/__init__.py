"""Project scaffolding for `milo new`.

Templates live under ``default/`` and are copied with ``{{name}}`` substitution.
No template engine — a plain ``str.replace`` keeps scaffolding zero-dep and
auditable.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent / "default"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ScaffoldError(Exception):
    """Raised when a scaffold cannot be created."""


def scaffold(name: str, target_dir: Path) -> Path:
    """Create a new milo CLI project at ``target_dir / name``.

    Args:
        name: Project name. Must match ``^[a-z][a-z0-9_]*$`` so it works
            both as a directory name and as a Python identifier.
        target_dir: Parent directory in which the project dir is created.

    Returns:
        The created project directory path.

    Raises:
        ScaffoldError: If ``name`` is invalid or the target path exists.
    """
    if not _NAME_RE.match(name):
        raise ScaffoldError(
            f"Invalid project name '{name}'. "
            f"Use lowercase letters, digits, and underscores; start with a letter."
        )

    project_dir = target_dir / name
    if project_dir.exists():
        raise ScaffoldError(f"Refusing to overwrite existing path: {project_dir}")

    for src in _TEMPLATE_DIR.rglob("*"):
        rel = src.relative_to(_TEMPLATE_DIR)
        dst = project_dir / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        dst.write_text(content.replace("{{name}}", name), encoding="utf-8")

    return project_dir
