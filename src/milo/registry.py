"""Milo CLI registry — tracks installed CLIs for gateway discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REGISTRY_DIR = Path.home() / ".milo"
_REGISTRY_FILE = _REGISTRY_DIR / "registry.json"


def _load() -> dict[str, Any]:
    """Load the registry file."""
    if not _REGISTRY_FILE.exists():
        return {"version": 1, "clis": {}}
    try:
        return json.loads(_REGISTRY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "clis": {}}


def _save(data: dict[str, Any]) -> None:
    """Save the registry file."""
    _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    _REGISTRY_FILE.write_text(json.dumps(data, indent=2) + "\n")


def install(
    name: str,
    command: list[str],
    *,
    description: str = "",
    version: str = "",
) -> None:
    """Register a CLI in the milo registry.

    Args:
        name: CLI name (used as namespace prefix in the gateway).
        command: Shell command to start the CLI with --mcp.
        description: Human-readable description.
        version: CLI version string.
    """
    data = _load()
    data["clis"][name] = {
        "command": command,
        "description": description,
        "version": version,
    }
    _save(data)
    sys.stderr.write(f"Registered {name!r} in {_REGISTRY_FILE}\n")
    sys.stderr.write(f"  Command: {' '.join(command)}\n")
    if description:
        sys.stderr.write(f"  Description: {description}\n")
    sys.stderr.write("\n")
    sys.stderr.write("Tools are available via the milo gateway:\n")
    sys.stderr.write("  uv run python -m milo.gateway --mcp\n")
    sys.stderr.flush()


def uninstall(name: str) -> bool:
    """Remove a CLI from the milo registry. Returns True if it was found."""
    data = _load()
    if name not in data.get("clis", {}):
        sys.stderr.write(f"{name!r} not found in registry\n")
        return False
    del data["clis"][name]
    _save(data)
    sys.stderr.write(f"Removed {name!r} from {_REGISTRY_FILE}\n")
    return True


def list_clis() -> dict[str, dict[str, Any]]:
    """Return all registered CLIs."""
    data = _load()
    return data.get("clis", {})


def registry_path() -> Path:
    """Return the registry file path."""
    return _REGISTRY_FILE
