"""Milo CLI registry — tracks installed CLIs for gateway discovery."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REGISTRY_DIR = Path.home() / ".milo"
_REGISTRY_FILE = _REGISTRY_DIR / "registry.json"


@dataclass(frozen=True, slots=True)
class HealthResult:
    """Result of a CLI health check."""

    name: str
    reachable: bool
    latency_ms: float
    error: str = ""
    stale: bool = False


def _load() -> dict[str, Any]:
    """Load the registry file."""
    if not _REGISTRY_FILE.exists():
        return {"version": 1, "clis": {}}
    try:
        return json.loads(_REGISTRY_FILE.read_text())
    except json.JSONDecodeError:
        return {"version": 1, "clis": {}}
    except OSError:
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
    project_root: str = "",
) -> None:
    """Register a CLI in the milo registry.

    Args:
        name: CLI name (used as namespace prefix in the gateway).
        command: Shell command to start the CLI with --mcp.
        description: Human-readable description.
        version: CLI version string.
        project_root: Absolute path to the project root.
    """
    data = _load()
    entry: dict[str, Any] = {
        "command": command,
        "description": description,
        "version": version,
    }
    if project_root:
        entry["project_root"] = project_root
        entry["fingerprint"] = fingerprint(command, project_root)
    entry["installed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    data["clis"][name] = entry
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


def fingerprint(command: list[str], project_root: str) -> str:
    """Compute a SHA-256 fingerprint for a CLI entry."""
    content = json.dumps({"command": command, "project_root": project_root}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _health_check_entry(name: str, info: dict[str, Any]) -> HealthResult:
    """Ping a single CLI entry using pre-loaded registry info."""
    command = info.get("command", [])
    if not command:
        return HealthResult(name=name, reachable=False, latency_ms=0.0, error="No command")

    start = time.monotonic()
    try:
        input_data = '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        result = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=10,
        )
        elapsed = (time.monotonic() - start) * 1000

        # Check for valid response
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                response = json.loads(line)
                if response.get("id") == 1 and "result" in response:
                    # Check staleness
                    stored_fp = info.get("fingerprint", "")
                    project_root = info.get("project_root", "")
                    stale = False
                    if stored_fp and project_root:
                        current_fp = fingerprint(command, project_root)
                        stale = current_fp != stored_fp
                    return HealthResult(
                        name=name,
                        reachable=True,
                        latency_ms=round(elapsed, 2),
                        stale=stale,
                    )
            except json.JSONDecodeError:
                continue

        return HealthResult(
            name=name,
            reachable=False,
            latency_ms=round(elapsed, 2),
            error="No valid response",
        )
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return HealthResult(
            name=name, reachable=False, latency_ms=round(elapsed, 2), error="Timeout"
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return HealthResult(name=name, reachable=False, latency_ms=round(elapsed, 2), error=str(e))


def health_check(name: str) -> HealthResult:
    """Ping a registered CLI with initialize and measure latency."""
    data = _load()
    clis = data.get("clis", {})
    if name not in clis:
        return HealthResult(name=name, reachable=False, latency_ms=0.0, error="Not registered")
    return _health_check_entry(name, clis[name])


def check_all(clis: dict[str, dict[str, Any]] | None = None) -> list[HealthResult]:
    """Run health checks on all registered CLIs in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if clis is None:
        clis = list_clis()
    if not clis:
        return []

    max_workers = min(8, len(clis))
    results: dict[str, HealthResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_health_check_entry, name, info): name
            for name, info in clis.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()

    # Preserve original ordering
    return [results[name] for name in clis]


def doctor() -> str:
    """Generate a diagnostic report for all registered CLIs."""
    clis = list_clis()
    if not clis:
        return "No CLIs registered. Use --mcp-install on a milo CLI.\n"

    lines: list[str] = []
    lines.append("milo gateway — diagnostic report")
    lines.append(f"Registry: {_REGISTRY_FILE}")
    lines.append(f"CLIs: {len(clis)}")
    lines.append("")

    results = check_all(clis)
    for r in results:
        status = "OK" if r.reachable else "FAIL"
        stale_marker = " [STALE]" if r.stale else ""
        lines.append(f"  {r.name}: {status} ({r.latency_ms:.0f}ms){stale_marker}")
        if r.error:
            lines.append(f"    Error: {r.error}")

    lines.append("")

    healthy = sum(1 for r in results if r.reachable)
    lines.append(f"Summary: {healthy}/{len(results)} reachable")
    stale = sum(1 for r in results if r.stale)
    if stale:
        lines.append(f"  {stale} stale (fingerprint mismatch)")
    lines.append("")
    return "\n".join(lines)
