"""`milo components` — discover bundled and user-defined template components.

Walks the bundled ``src/milo/templates/components/`` tree (and any extra path
the caller supplies) and lists the ``{% def %}`` macros each template exposes.
Backed by Kida's ``Template.def_metadata()`` introspection.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from kida import FileSystemLoader

_BUNDLED_ROOT = Path(__file__).parent / "templates"


def _collect_defs(roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    """Walk *roots* and return one row per (template_name, def_name) pair."""
    from milo.templates import get_env

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        env = get_env(loader=FileSystemLoader(str(root)))
        for path in sorted(root.rglob("*.kida")):
            rel = path.relative_to(root).as_posix()
            try:
                tpl = env.get_template(rel)
            except Exception as exc:
                rows.append({"template": rel, "error": f"{type(exc).__name__}: {exc}"})
                continue
            for name, meta in tpl.def_metadata().items():
                key = (rel, name)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_metadata_row(rel, name, meta, root))
    return rows


def _metadata_row(template: str, name: str, meta: Any, root: Path) -> dict[str, Any]:
    params = [
        {
            "name": p.name,
            "annotation": p.annotation,
            "required": p.is_required,
            "has_default": p.has_default,
        }
        for p in getattr(meta, "params", ())
    ]
    return {
        "template": template,
        "root": str(root),
        "name": name,
        "lineno": getattr(meta, "lineno", None),
        "params": params,
        "slots": list(getattr(meta, "slots", ())),
        "has_default_slot": getattr(meta, "has_default_slot", False),
        "depends_on": sorted(getattr(meta, "depends_on", frozenset()) or ()),
    }


def _format_plain(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no components found)\n"
    by_template: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_template.setdefault(row["template"], []).append(row)

    lines: list[str] = []
    for template in sorted(by_template):
        lines.append(template)
        for row in by_template[template]:
            if "error" in row:
                lines.append(f"  ! {row['error']}")
                continue
            params = ", ".join(_format_param(p) for p in row["params"])
            lines.append(f"  {row['name']}({params})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_param(param: dict[str, Any]) -> str:
    suffix = "" if param["required"] else "?"
    return f"{param['name']}{suffix}"


def _to_jsonable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        clean = {k: (asdict(v) if is_dataclass(v) else v) for k, v in row.items()}
        out.append(clean)
    return out


def run(*, paths: tuple[Path, ...] = (), as_json: bool = False) -> int:
    """Entry point used by ``milo components``. Returns exit code."""
    roots = (_BUNDLED_ROOT, *paths)
    rows = _collect_defs(roots)
    if as_json:
        json.dump(_to_jsonable(rows), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_plain(rows))
    return 0
