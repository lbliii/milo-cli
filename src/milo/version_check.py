"""Non-blocking version check with periodic caching."""

from __future__ import annotations

import json
import logging
import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from milo._compat import data_dir

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """Result of a version check."""

    current: str
    latest: str
    update_available: bool
    message: str = ""


_CACHE_DIR = data_dir() / "cache"
_CHECK_INTERVAL = 86400  # 24 hours


def check_version(
    package_name: str,
    current_version: str,
    *,
    cache_dir: Path | None = None,
    check_interval: int = _CHECK_INTERVAL,
) -> VersionInfo | None:
    """Check PyPI for a newer version. Returns None if check is skipped.

    Caches the result to avoid hitting PyPI on every invocation.
    Returns None if within the cache interval or on any error.
    """
    cache = cache_dir or _CACHE_DIR

    # Respect NO_UPDATE_CHECK / CI
    if os.environ.get("NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None

    cache_file = cache / f"{package_name}.version.json"

    # Check cache freshness
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("checked_at", 0) < check_interval:
                latest = data.get("latest", current_version)
                if latest != current_version:
                    return VersionInfo(
                        current=current_version,
                        latest=latest,
                        update_available=True,
                        message=f"Update available: {current_version} -> {latest}",
                    )
                return None
        except Exception as e:
            warnings.warn(
                f"Failed to read version cache {cache_file}: {e}",
                stacklevel=2,
            )

    # Fetch from PyPI
    try:
        latest = _fetch_latest_version(package_name)
    except Exception as e:
        _logger.debug("Version check failed for %s: %s", package_name, e)
        return None

    # Cache the result (atomic write via temp file + rename)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_file.with_suffix(".tmp")
        content = json.dumps({"latest": latest, "checked_at": time.time()})
        tmp_path.write_text(content)
        os.replace(tmp_path, cache_file)
    except Exception as e:
        warnings.warn(
            f"Failed to write version cache {cache_file}: {e}",
            stacklevel=2,
        )

    if latest and latest != current_version:
        return VersionInfo(
            current=current_version,
            latest=latest,
            update_available=True,
            message=f"Update available: {current_version} -> {latest}",
        )

    return None


def format_version_notice(info: VersionInfo, *, prog: str = "") -> str:
    """Format a user-friendly update notice for stderr."""
    name = prog or "this package"
    installer = _detect_installer()
    upgrade_cmd = (
        f"  {installer} install --upgrade {name}"
        if installer != "uv"
        else f"  uv pip install --upgrade {name}"
    )
    return f"A new version of {name} is available: {info.current} -> {info.latest}\n{upgrade_cmd}"


def _detect_installer() -> str:
    """Detect the package installer (uv or pip)."""
    import shutil

    if shutil.which("uv"):
        return "uv"
    return "pip"


def _fetch_latest_version(package_name: str) -> str:
    """Fetch the latest version from PyPI JSON API."""
    import urllib.request

    url = f"https://pypi.org/pypi/{package_name}/json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})

    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read())
        return data["info"]["version"]
