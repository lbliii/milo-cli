#!/usr/bin/env python3
"""Report whether the worktree is ready to prepare or publish a release."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_VERSION_RE = re.compile(r"^##\s+(\d+\.\d+\.\d+)\b", re.MULTILINE)
INIT_VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Check:
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class ReleaseFacts:
    package_name: str
    pyproject_version: str
    module_version: str
    lock_version: str
    head_sha: str
    local_tags: tuple[str, ...]
    remote_tags: tuple[str, ...] = ()
    pypi_version: str = ""
    changelog_versions: tuple[str, ...] = ()
    release_note_versions: tuple[str, ...] = ()
    pending_fragments: tuple[str, ...] = ()
    empty_fragments: tuple[str, ...] = ()
    changed_since_current_tag: tuple[str, ...] = ()
    changed_released_notes: tuple[str, ...] = ()
    tag_diff_warnings: tuple[str, ...] = ()
    remote_checked: bool = False
    pypi_checked: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    current_version: str
    latest_released_version: str
    suggested_next_version: str
    checks: tuple[Check, ...]

    @property
    def has_errors(self) -> bool:
        return any(check.level == "error" for check in self.checks)


def _parse_version(version: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _next_patch(version: str) -> str:
    parsed = _parse_version(version)
    if parsed is None:
        return version
    major, minor, patch = parsed
    return f"{major}.{minor}.{patch + 1}"


def _max_version(versions: set[str]) -> str:
    valid = [(version, _parse_version(version)) for version in versions]
    parsed = [(version, parts) for version, parts in valid if parts is not None]
    if not parsed:
        return ""
    return max(parsed, key=lambda item: item[1])[0]


def _tag_to_version(tag: str) -> str | None:
    name = tag.rsplit("/", 1)[-1].removesuffix("^{}")
    if name.startswith("v"):
        name = name[1:]
    return name if _parse_version(name) is not None else None


def _released_versions(facts: ReleaseFacts) -> set[str]:
    versions: set[str] = set()
    for tag in (*facts.local_tags, *facts.remote_tags):
        version = _tag_to_version(tag)
        if version is not None:
            versions.add(version)
    if facts.pypi_version:
        versions.add(facts.pypi_version)
    return versions


def analyze_release_state(facts: ReleaseFacts) -> ReleaseReport:
    checks: list[Check] = []
    current = facts.pyproject_version
    versions = _released_versions(facts)
    latest = _max_version(versions)
    suggested = _next_patch(latest or current)

    def add(level: str, message: str) -> None:
        checks.append(Check(level, message))

    if facts.module_version != current:
        add(
            "error",
            f"pyproject version {current} disagrees with src/milo/__init__.py "
            f"version {facts.module_version}.",
        )
    if facts.lock_version and facts.lock_version != current:
        add("error", f"pyproject version {current} disagrees with uv.lock {facts.lock_version}.")

    if not facts.remote_checked:
        add("warn", "Remote tags were not checked; pass --remote for release prep.")
    if not facts.pypi_checked:
        add("warn", "PyPI was not checked; pass --pypi before publishing.")
    elif not facts.pypi_version:
        add("warn", "PyPI was checked, but no latest version could be read.")

    current_released = current in versions
    if current_released:
        add(
            "error",
            f"Version {current} is already released/tagged. Bump to {suggested} before "
            "editing release notes or building artifacts.",
        )
    else:
        current_parts = _parse_version(current)
        latest_parts = _parse_version(latest)
        if latest and current_parts is not None and latest_parts is not None:
            if current_parts < latest_parts:
                add(
                    "error",
                    f"Current version {current} is older than released version {latest}. "
                    f"Bump to at least {suggested}.",
                )
            else:
                add("ok", f"Current version {current} is newer than latest released {latest}.")
        elif latest:
            add("warn", f"Could not compare current version {current} to latest released {latest}.")

    if facts.changed_since_current_tag:
        changed = ", ".join(facts.changed_since_current_tag)
        add(
            "error",
            f"Release surfaces for already-tagged {current} changed after the tag: {changed}. "
            f"Move those edits to {suggested}.",
        )
    if facts.changed_released_notes:
        changed = ", ".join(facts.changed_released_notes)
        add(
            "warn",
            "Already-tagged release note files changed after their tags: "
            f"{changed}. Verify this is an intentional historical correction.",
        )
    for warning in facts.tag_diff_warnings:
        add("warn", warning)

    if facts.changelog_versions:
        top = facts.changelog_versions[0]
        if top != current:
            add("error", f"Top CHANGELOG.md section is {top}, but package version is {current}.")
    else:
        add("error", "CHANGELOG.md has no version section.")

    if current not in facts.release_note_versions:
        add("error", f"Missing site/content/releases/{current}.md.")

    if facts.pending_fragments:
        fragments = ", ".join(facts.pending_fragments)
        add(
            "warn",
            f"Pending changelog fragments remain: {fragments}. Compile or intentionally "
            "consolidate them before publishing.",
        )
    if facts.empty_fragments:
        fragments = ", ".join(facts.empty_fragments)
        add(
            "error",
            f"Empty changelog fragments found: {fragments}. Remove them or add release-note "
            "content before preparing a release.",
        )

    if not checks:
        add("ok", f"Release surfaces look aligned for {current}.")

    return ReleaseReport(
        current_version=current,
        latest_released_version=latest,
        suggested_next_version=suggested,
        checks=tuple(checks),
    )


def _run_git(root: Path, args: list[str], *, timeout: int = 20) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found on PATH")
    result = subprocess.run(
        [git, *args],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _read_pyproject(root: Path) -> tuple[str, str]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    return str(project["name"]), str(project["version"])


def _read_module_version(root: Path) -> str:
    text = (root / "src" / "milo" / "__init__.py").read_text(encoding="utf-8")
    match = INIT_VERSION_RE.search(text)
    if match is None:
        raise RuntimeError("Could not find __version__ in src/milo/__init__.py")
    return match.group(1)


def _read_lock_version(root: Path, package_name: str) -> str:
    lock_path = root / "uv.lock"
    if not lock_path.exists():
        return ""
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    for package in data.get("package", []):
        if package.get("name") == package_name:
            return str(package.get("version", ""))
    return ""


def _read_changelog_versions(root: Path) -> tuple[str, ...]:
    path = root / "CHANGELOG.md"
    if not path.exists():
        return ()
    return tuple(CHANGELOG_VERSION_RE.findall(path.read_text(encoding="utf-8")))


def _read_release_note_versions(root: Path) -> tuple[str, ...]:
    release_dir = root / "site" / "content" / "releases"
    if not release_dir.exists():
        return ()
    versions: list[str] = []
    for path in sorted(release_dir.glob("*.md")):
        version = path.stem
        if _parse_version(version) is not None:
            versions.append(version)
    return tuple(versions)


def _read_pending_fragments(root: Path) -> tuple[str, ...]:
    fragment_dir = root / "changelog.d"
    if not fragment_dir.exists():
        return ()
    return tuple(
        path.name
        for path in sorted(fragment_dir.iterdir())
        if path.is_file() and path.name != ".gitkeep"
    )


def _read_empty_fragments(root: Path) -> tuple[str, ...]:
    fragment_dir = root / "changelog.d"
    if not fragment_dir.exists():
        return ()
    empty: list[str] = []
    for path in sorted(fragment_dir.iterdir()):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            empty.append(path.name)
    return tuple(empty)


def _read_local_tags(root: Path) -> tuple[str, ...]:
    output = _run_git(root, ["tag", "--list", "v*"])
    return tuple(line for line in output.splitlines() if line)


def _read_remote_tags(root: Path) -> tuple[str, ...]:
    output = _run_git(root, ["ls-remote", "--tags", "origin", "v*"])
    tags: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2:
            tags.append(parts[1])
    return tuple(tags)


def _tag_names(tags: tuple[str, ...]) -> set[str]:
    return {tag.rsplit("/", 1)[-1].removesuffix("^{}") for tag in tags}


def _read_changed_since_current_tag(
    root: Path,
    version: str,
    local_tags: tuple[str, ...],
    remote_tags: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tag = f"v{version}"
    local_tag_names = _tag_names(local_tags)
    remote_tag_names = _tag_names(remote_tags)
    if tag not in local_tag_names:
        if tag in remote_tag_names:
            return (), (
                f"Release tag {tag} exists on origin but is not available locally; "
                "run with --fetch-tags to check release-surface drift.",
            )
        return (), ()
    try:
        output = _run_git(
            root,
            [
                "diff",
                "--name-only",
                f"{tag}..HEAD",
                "--",
                "CHANGELOG.md",
                f"site/content/releases/{version}.md",
            ],
        )
    except RuntimeError as exc:
        return (), (f"Could not check release surfaces against local tag {tag}: {exc}",)
    return tuple(line for line in output.splitlines() if line), ()


def _read_changed_released_notes(
    root: Path,
    current_version: str,
    local_tags: tuple[str, ...],
    remote_tags: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    changed: list[str] = []
    warnings: list[str] = []
    local_tag_names = _tag_names(local_tags)
    remote_tag_names = _tag_names(remote_tags)
    versions = sorted(
        version
        for version in {_tag_to_version(tag) for tag in (*local_tags, *remote_tags)}
        if version is not None
    )
    for version in versions:
        if version == current_version:
            continue
        path = f"site/content/releases/{version}.md"
        if not (root / path).exists():
            continue
        tag = f"v{version}"
        if tag not in local_tag_names:
            if tag in remote_tag_names:
                warnings.append(
                    f"Release tag {tag} exists on origin but is not available locally; "
                    f"run with --fetch-tags to check {path} for historical edits."
                )
            continue
        try:
            output = _run_git(root, ["diff", "--name-only", f"{tag}..HEAD", "--", path])
        except RuntimeError as exc:
            warnings.append(f"Could not check {path} against local tag {tag}: {exc}")
            continue
        changed.extend(line for line in output.splitlines() if line)
    return tuple(sorted(set(changed))), tuple(warnings)


def _read_pypi_version(package_name: str, *, timeout: int = 10) -> str:
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except OSError, urllib.error.URLError, json.JSONDecodeError:
        return ""
    return str(data.get("info", {}).get("version", ""))


def collect_release_facts(
    root: Path,
    *,
    fetch_tags: bool = False,
    remote: bool = False,
    pypi: bool = False,
) -> ReleaseFacts:
    package_name, pyproject_version = _read_pyproject(root)
    if fetch_tags:
        _run_git(root, ["fetch", "--tags", "origin"], timeout=60)
    local_tags = _read_local_tags(root)
    remote_tags = _read_remote_tags(root) if remote else ()
    pypi_version = _read_pypi_version(package_name) if pypi else ""
    changed_since_current_tag, current_tag_warnings = _read_changed_since_current_tag(
        root, pyproject_version, local_tags, remote_tags
    )
    changed_released_notes, released_note_warnings = _read_changed_released_notes(
        root, pyproject_version, local_tags, remote_tags
    )
    return ReleaseFacts(
        package_name=package_name,
        pyproject_version=pyproject_version,
        module_version=_read_module_version(root),
        lock_version=_read_lock_version(root, package_name),
        head_sha=_run_git(root, ["rev-parse", "--short", "HEAD"]),
        local_tags=local_tags,
        remote_tags=remote_tags,
        pypi_version=pypi_version,
        changelog_versions=_read_changelog_versions(root),
        release_note_versions=_read_release_note_versions(root),
        pending_fragments=_read_pending_fragments(root),
        empty_fragments=_read_empty_fragments(root),
        changed_since_current_tag=changed_since_current_tag,
        changed_released_notes=changed_released_notes,
        tag_diff_warnings=(*current_tag_warnings, *released_note_warnings),
        remote_checked=remote,
        pypi_checked=pypi,
    )


def _format_report(facts: ReleaseFacts, report: ReleaseReport) -> str:
    lines = [
        f"Package: {facts.package_name}",
        f"Current version: {report.current_version}",
        f"HEAD: {facts.head_sha}",
        f"Latest released/tagged: {report.latest_released_version or 'none found'}",
        f"Suggested next patch: {report.suggested_next_version}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        marker = {"ok": "OK", "warn": "WARN", "error": "ERROR"}.get(check.level, check.level)
        lines.append(f"- {marker}: {check.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fetch-tags", action="store_true", help="Run git fetch --tags first.")
    parser.add_argument("--remote", action="store_true", help="Check tags on origin.")
    parser.add_argument("--pypi", action="store_true", help="Check the latest PyPI version.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        facts = collect_release_facts(
            args.root.resolve(),
            fetch_tags=args.fetch_tags,
            remote=args.remote,
            pypi=args.pypi,
        )
    except Exception as exc:
        sys.stderr.write(f"release-status: {exc}\n")
        return 2

    report = analyze_release_state(facts)
    if args.json:
        sys.stdout.write(json.dumps({"facts": asdict(facts), "report": asdict(report)}, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_report(facts, report) + "\n")
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
