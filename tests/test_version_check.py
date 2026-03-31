"""Tests for the version_check module."""

from __future__ import annotations

import json
import os
from unittest.mock import patch


class TestVersionCheck:
    def test_skip_in_ci(self):
        from milo.version_check import check_version

        with patch.dict(os.environ, {"CI": "true"}):
            result = check_version("milo-cli", "0.1.0")
            assert result is None

    def test_skip_with_no_update_check(self):
        from milo.version_check import check_version

        with patch.dict(os.environ, {"NO_UPDATE_CHECK": "1"}):
            result = check_version("milo-cli", "0.1.0")
            assert result is None

    def test_version_info_dataclass(self):
        from milo.version_check import VersionInfo

        info = VersionInfo(
            current="0.1.0",
            latest="0.2.0",
            update_available=True,
            message="Update available",
        )
        assert info.update_available is True
        assert info.current == "0.1.0"

    def test_format_version_notice(self):
        from milo.version_check import VersionInfo, format_version_notice

        info = VersionInfo(current="0.1.0", latest="0.2.0", update_available=True)
        notice = format_version_notice(info, prog="myapp")
        assert "0.1.0" in notice
        assert "0.2.0" in notice
        assert "myapp" in notice

    def test_cached_check(self, tmp_path):
        import time

        from milo.version_check import check_version

        # Write a cached result
        cache_file = tmp_path / "test-pkg.version.json"

        cache_file.write_text(
            json.dumps(
                {
                    "latest": "0.1.0",
                    "checked_at": time.time(),
                }
            )
        )

        # Same version, should return None
        result = check_version("test-pkg", "0.1.0", cache_dir=tmp_path)
        assert result is None

    def test_cached_check_update_available(self, tmp_path):
        import time

        from milo.version_check import check_version

        cache_file = tmp_path / "test-pkg.version.json"
        cache_file.write_text(
            json.dumps(
                {
                    "latest": "0.2.0",
                    "checked_at": time.time(),
                }
            )
        )

        with patch.dict(os.environ, {"CI": "", "NO_UPDATE_CHECK": ""}, clear=False):
            result = check_version("test-pkg", "0.1.0", cache_dir=tmp_path)
        assert result is not None
        assert result.update_available is True

    def test_format_version_notice_detects_uv(self):
        from milo.version_check import VersionInfo, format_version_notice

        info = VersionInfo(current="0.1.0", latest="0.2.0", update_available=True)
        with patch("milo.version_check._detect_installer", return_value="uv"):
            notice = format_version_notice(info, prog="myapp")
        assert "uv pip install --upgrade myapp" in notice
        assert "pip install --upgrade" in notice

    def test_format_version_notice_falls_back_to_pip(self):
        from milo.version_check import VersionInfo, format_version_notice

        info = VersionInfo(current="0.1.0", latest="0.2.0", update_available=True)
        with patch("milo.version_check._detect_installer", return_value="pip"):
            notice = format_version_notice(info, prog="myapp")
        assert "pip install --upgrade myapp" in notice
        assert "uv" not in notice
