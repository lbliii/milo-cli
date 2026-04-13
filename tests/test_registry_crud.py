"""Tests for milo.registry — install, uninstall, list_clis, _load, _save."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

import milo.registry as registry_mod
from milo.registry import install, list_clis, registry_path, uninstall


@pytest.fixture
def tmp_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the registry at a temp directory."""
    reg_file = tmp_path / "registry.json"
    monkeypatch.setattr(registry_mod, "_REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(registry_mod, "_REGISTRY_FILE", reg_file)
    return reg_file


class TestLoadSave:
    def test_load_missing_file(self, tmp_registry: Path) -> None:
        data = registry_mod._load()
        assert data == {"version": 1, "clis": {}}

    def test_save_and_load(self, tmp_registry: Path) -> None:
        data = {"version": 1, "clis": {"app": {"command": ["python", "app.py"]}}}
        registry_mod._save(data)
        assert tmp_registry.exists()
        loaded = registry_mod._load()
        assert loaded == data

    def test_load_corrupted_json(self, tmp_registry: Path) -> None:
        tmp_registry.write_text("not valid json{{{")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            data = registry_mod._load()
        assert data == {"version": 1, "clis": {}}
        assert len(w) == 1
        assert "corrupted" in str(w[0].message).lower()

    def test_save_is_atomic(self, tmp_registry: Path) -> None:
        """The .tmp file should not persist after a successful save."""
        registry_mod._save({"version": 1, "clis": {}})
        tmp_file = tmp_registry.with_suffix(".tmp")
        assert not tmp_file.exists()
        assert tmp_registry.exists()


class TestInstall:
    def test_install_basic(self, tmp_registry: Path) -> None:
        install("myapp", ["python", "app.py", "--mcp"], description="My App", version="1.0.0")
        data = json.loads(tmp_registry.read_text())
        assert "myapp" in data["clis"]
        entry = data["clis"]["myapp"]
        assert entry["command"] == ["python", "app.py", "--mcp"]
        assert entry["description"] == "My App"
        assert entry["version"] == "1.0.0"
        assert "installed_at" in entry

    def test_install_with_project_root(self, tmp_registry: Path) -> None:
        install(
            "myapp",
            ["python", "app.py", "--mcp"],
            project_root="/home/user/project",
        )
        data = json.loads(tmp_registry.read_text())
        entry = data["clis"]["myapp"]
        assert entry["project_root"] == "/home/user/project"
        assert "fingerprint" in entry
        assert len(entry["fingerprint"]) == 64  # SHA-256 hex

    def test_install_overwrites_existing(self, tmp_registry: Path) -> None:
        install("myapp", ["python", "old.py"], version="1.0.0")
        install("myapp", ["python", "new.py"], version="2.0.0")
        data = json.loads(tmp_registry.read_text())
        assert data["clis"]["myapp"]["version"] == "2.0.0"
        assert data["clis"]["myapp"]["command"] == ["python", "new.py"]

    def test_install_multiple(self, tmp_registry: Path) -> None:
        install("app1", ["python", "a.py"])
        install("app2", ["python", "b.py"])
        data = json.loads(tmp_registry.read_text())
        assert len(data["clis"]) == 2


class TestUninstall:
    def test_uninstall_existing(self, tmp_registry: Path) -> None:
        install("myapp", ["python", "app.py"])
        result = uninstall("myapp")
        assert result is True
        data = json.loads(tmp_registry.read_text())
        assert "myapp" not in data["clis"]

    def test_uninstall_nonexistent(self, tmp_registry: Path) -> None:
        result = uninstall("nonexistent")
        assert result is False

    def test_uninstall_preserves_others(self, tmp_registry: Path) -> None:
        install("app1", ["python", "a.py"])
        install("app2", ["python", "b.py"])
        uninstall("app1")
        data = json.loads(tmp_registry.read_text())
        assert "app1" not in data["clis"]
        assert "app2" in data["clis"]


class TestListClis:
    def test_empty_registry(self, tmp_registry: Path) -> None:
        clis = list_clis()
        assert clis == {}

    def test_returns_registered_clis(self, tmp_registry: Path) -> None:
        install("app1", ["python", "a.py"], description="App 1")
        install("app2", ["python", "b.py"], description="App 2")
        clis = list_clis()
        assert len(clis) == 2
        assert "app1" in clis
        assert "app2" in clis
