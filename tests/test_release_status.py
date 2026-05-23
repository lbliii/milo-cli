"""Tests for scripts/release_status.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_release_status_script():
    script = Path(__file__).parent.parent / "scripts" / "release_status.py"
    spec = importlib.util.spec_from_file_location("release_status", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _facts(**overrides):
    release_status = _load_release_status_script()
    base = {
        "package_name": "milo-cli",
        "pyproject_version": "0.3.1",
        "module_version": "0.3.1",
        "lock_version": "0.3.1",
        "head_sha": "abc1234",
        "local_tags": ("v0.3.0",),
        "remote_tags": ("refs/tags/v0.3.0",),
        "pypi_version": "",
        "changelog_versions": ("0.3.1", "0.3.0"),
        "release_note_versions": ("0.3.1", "0.3.0"),
        "pending_fragments": (),
        "empty_fragments": (),
        "changed_since_current_tag": (),
        "changed_released_notes": (),
        "tag_diff_warnings": (),
        "remote_checked": True,
        "pypi_checked": False,
    }
    base.update(overrides)
    return release_status.ReleaseFacts(**base)


class TestReleaseStatus:
    def test_allows_next_patch_after_released_tag(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(_facts())

        messages = [check.message for check in report.checks]
        assert report.has_errors is False
        assert report.latest_released_version == "0.3.0"
        assert report.suggested_next_version == "0.3.1"
        assert any("Current version 0.3.1 is newer" in msg for msg in messages)

    def test_rejects_metadata_left_on_already_released_version(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(
                pyproject_version="0.3.0",
                module_version="0.3.0",
                lock_version="0.3.0",
                changelog_versions=("0.3.0",),
                release_note_versions=("0.3.0",),
                changed_since_current_tag=("CHANGELOG.md", "site/content/releases/0.3.0.md"),
            )
        )

        messages = [check.message for check in report.checks]
        assert report.has_errors is True
        assert any("Version 0.3.0 is already released/tagged" in msg for msg in messages)
        assert any("Release surfaces for already-tagged 0.3.0 changed" in msg for msg in messages)
        assert report.suggested_next_version == "0.3.1"

    def test_rejects_version_drift_between_metadata_files(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(_facts(module_version="0.3.0"))

        assert report.has_errors is True
        assert any("disagrees with src/milo/__init__.py" in c.message for c in report.checks)

    def test_rejects_version_already_on_pypi(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(
                local_tags=(),
                remote_tags=(),
                pypi_version="0.3.1",
                pypi_checked=True,
            )
        )

        assert report.has_errors is True
        assert any("Version 0.3.1 is already released/tagged" in c.message for c in report.checks)

    def test_warns_about_pending_fragments(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(pending_fragments=("template-check.fixed.md",))
        )

        assert any(
            check.level == "warn" and "Pending changelog fragments" in check.message
            for check in report.checks
        )

    def test_rejects_empty_changelog_fragments(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(
                pending_fragments=("empty.fixed.md",),
                empty_fragments=("empty.fixed.md",),
            )
        )

        assert report.has_errors is True
        assert any("Empty changelog fragments found" in c.message for c in report.checks)

    def test_warns_when_prior_release_notes_changed(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(changed_released_notes=("site/content/releases/0.3.0.md",))
        )

        assert any(
            check.level == "warn" and "Already-tagged release note files changed" in check.message
            for check in report.checks
        )

    def test_warns_when_tag_diff_cannot_be_checked(self):
        release_status = _load_release_status_script()

        report = release_status.analyze_release_state(
            _facts(tag_diff_warnings=("Release tag v0.3.0 exists on origin but is not local.",))
        )

        assert any(
            check.level == "warn" and "exists on origin" in check.message for check in report.checks
        )

    def test_remote_only_current_tag_reports_missing_local_diff(self, tmp_path):
        release_status = _load_release_status_script()

        changed, warnings = release_status._read_changed_since_current_tag(
            tmp_path,
            "0.3.1",
            (),
            ("refs/tags/v0.3.1",),
        )

        assert changed == ()
        assert warnings == (
            "Release tag v0.3.1 exists on origin but is not available locally; "
            "run with --fetch-tags to check release-surface drift.",
        )

    def test_remote_only_historical_tag_reports_missing_local_diff(self, tmp_path):
        release_status = _load_release_status_script()
        note = tmp_path / "site" / "content" / "releases" / "0.3.0.md"
        note.parent.mkdir(parents=True)
        note.write_text("release notes\n", encoding="utf-8")

        changed, warnings = release_status._read_changed_released_notes(
            tmp_path,
            "0.3.1",
            (),
            ("refs/tags/v0.3.0",),
        )

        assert changed == ()
        assert warnings == (
            "Release tag v0.3.0 exists on origin but is not available locally; "
            "run with --fetch-tags to check site/content/releases/0.3.0.md "
            "for historical edits.",
        )

    def test_reads_empty_fragments_from_disk(self, tmp_path):
        release_status = _load_release_status_script()
        fragment_dir = tmp_path / "changelog.d"
        fragment_dir.mkdir()
        (fragment_dir / ".gitkeep").write_text("", encoding="utf-8")
        (fragment_dir / "empty.fixed.md").write_text(" \n", encoding="utf-8")
        (fragment_dir / "full.fixed.md").write_text("Fixed the release guard.\n", encoding="utf-8")

        assert release_status._read_empty_fragments(tmp_path) == ("empty.fixed.md",)
