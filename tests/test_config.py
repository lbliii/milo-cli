"""Tests for the configuration system."""

from __future__ import annotations

import json

import pytest

from milo.config import Config, ConfigSpec


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temp directory with sample config files."""
    # Main TOML config
    (tmp_path / "app.toml").write_text(
        '[site]\ntitle = "My Site"\nurl = "http://localhost"\n\n'
        '[build]\noutput = "_site"\nminify = false\n'
    )
    # Override TOML
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "build.toml").write_text("[build]\nparallel = true\n")
    # Production overlay
    (tmp_path / "config" / "production.toml").write_text(
        '[site]\nurl = "https://example.com"\n\n[build]\nminify = true\n'
    )
    # JSON config
    (tmp_path / "extra.json").write_text(json.dumps({"features": {"search": True}}))
    return tmp_path


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestConfigLoad:
    def test_load_toml(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.title") == "My Site"
        assert config.get("build.output") == "_site"

    def test_load_multiple_sources(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml", "config/build.toml"))
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.title") == "My Site"
        assert config.get("build.parallel") is True

    def test_load_glob_pattern(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml", "config/*.toml"))
        config = Config.load(spec, root=tmp_config)
        assert config.get("build.parallel") is True

    def test_load_json(self, tmp_config):
        spec = ConfigSpec(sources=("extra.json",))
        config = Config.load(spec, root=tmp_config)
        assert config.get("features.search") is True

    def test_load_with_defaults(self, tmp_config):
        spec = ConfigSpec(
            sources=("app.toml",),
            defaults={"site": {"lang": "en"}, "build": {"verbose": False}},
        )
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.lang") == "en"
        assert config.get("site.title") == "My Site"  # file overrides default

    def test_from_dict(self):
        config = Config.from_dict({"site": {"title": "Test"}})
        assert config.get("site.title") == "Test"


# ---------------------------------------------------------------------------
# Deep merge and precedence
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_file_overrides_defaults(self, tmp_config):
        spec = ConfigSpec(
            sources=("app.toml",),
            defaults={"site": {"title": "Default Title"}},
        )
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.title") == "My Site"

    def test_later_file_overrides_earlier(self, tmp_config):
        # config/production.toml has site.url override
        spec = ConfigSpec(sources=("app.toml", "config/production.toml"))
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.url") == "https://example.com"
        assert config.get("build.minify") is True

    def test_deep_merge_preserves_siblings(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml", "config/production.toml"))
        config = Config.load(spec, root=tmp_config)
        # site.title from app.toml, site.url from production
        assert config.get("site.title") == "My Site"
        assert config.get("site.url") == "https://example.com"


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------


class TestEnvVars:
    def test_env_prefix(self, tmp_config, monkeypatch):
        monkeypatch.setenv("MYAPP_SITE_URL", "https://env.example.com")
        monkeypatch.setenv("MYAPP_BUILD_WORKERS", "4")
        spec = ConfigSpec(sources=("app.toml",), env_prefix="MYAPP_")
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.url") == "https://env.example.com"
        assert config.get("build.workers") == "4"

    def test_env_overrides_file(self, tmp_config, monkeypatch):
        monkeypatch.setenv("MYAPP_SITE_TITLE", "Env Title")
        spec = ConfigSpec(sources=("app.toml",), env_prefix="MYAPP_")
        config = Config.load(spec, root=tmp_config)
        assert config.get("site.title") == "Env Title"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfiles:
    def test_profile_overrides(self, tmp_config):
        spec = ConfigSpec(
            sources=("app.toml",),
            profiles={
                "dev": {"build.output": "dev_out", "build.minify": False},
                "prod": {"build.output": "dist", "build.minify": True},
            },
        )
        dev = Config.load(spec, root=tmp_config, profile="dev")
        assert dev.get("build.output") == "dev_out"
        assert dev.get("build.minify") is False

        prod = Config.load(spec, root=tmp_config, profile="prod")
        assert prod.get("build.output") == "dist"
        assert prod.get("build.minify") is True

    def test_unknown_profile_ignored(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config, profile="nonexistent")
        assert config.get("site.title") == "My Site"


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------


class TestOverlays:
    def test_overlay_applies(self, tmp_config):
        spec = ConfigSpec(
            sources=("app.toml",),
            overlays={"production": "config/production.toml"},
        )
        config = Config.load(spec, root=tmp_config, overlay="production")
        assert config.get("site.url") == "https://example.com"
        assert config.get("build.minify") is True

    def test_overlay_overrides_everything(self, tmp_config, monkeypatch):
        monkeypatch.setenv("MYAPP_SITE_URL", "https://env.example.com")
        spec = ConfigSpec(
            sources=("app.toml",),
            env_prefix="MYAPP_",
            overlays={"production": "config/production.toml"},
        )
        # Overlay is last, so it wins over env vars
        config = Config.load(spec, root=tmp_config, overlay="production")
        assert config.get("site.url") == "https://example.com"

    def test_unknown_overlay_ignored(self, tmp_config):
        spec = ConfigSpec(
            sources=("app.toml",),
            overlays={"production": "config/production.toml"},
        )
        config = Config.load(spec, root=tmp_config, overlay="staging")
        assert config.get("site.url") == "http://localhost"


# ---------------------------------------------------------------------------
# Origin tracking
# ---------------------------------------------------------------------------


class TestOriginTracking:
    def test_origin_from_file(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        origin = config.origin_of("site.title")
        assert "file:" in origin
        assert "app.toml" in origin

    def test_origin_from_defaults(self, tmp_config):
        spec = ConfigSpec(
            sources=(),
            defaults={"site": {"lang": "en"}},
        )
        config = Config.load(spec, root=tmp_config)
        assert config.origin_of("site.lang") == "defaults"

    def test_origin_from_env(self, tmp_config, monkeypatch):
        monkeypatch.setenv("MYAPP_NEW_KEY", "value")
        spec = ConfigSpec(env_prefix="MYAPP_")
        config = Config.load(spec, root=tmp_config)
        assert config.origin_of("new.key") == "env"

    def test_origin_from_profile(self, tmp_config):
        spec = ConfigSpec(
            profiles={"dev": {"build.debug": True}},
        )
        config = Config.load(spec, root=tmp_config, profile="dev")
        assert config.origin_of("build.debug") == "profile:dev"

    def test_origin_unknown_key(self):
        config = Config.from_dict({})
        assert config.origin_of("nonexistent") == ""


# ---------------------------------------------------------------------------
# Utility methods
# ---------------------------------------------------------------------------


class TestConfigUtils:
    def test_as_dict(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        d = config.as_dict()
        assert isinstance(d, dict)
        assert d["site"]["title"] == "My Site"
        # Modifying the dict shouldn't affect config
        d["site"]["title"] = "Changed"
        assert config.get("site.title") == "My Site"

    def test_to_state(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        state = config.to_state()
        assert state["site"]["title"] == "My Site"

    def test_contains(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        assert "site.title" in config
        assert "nonexistent" not in config

    def test_get_default(self):
        config = Config.from_dict({})
        assert config.get("missing", "fallback") == "fallback"

    def test_repr(self, tmp_config):
        spec = ConfigSpec(sources=("app.toml",))
        config = Config.load(spec, root=tmp_config)
        r = repr(config)
        assert "Config" in r


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestConfigErrors:
    def test_unsupported_format(self, tmp_path):
        (tmp_path / "config.xml").write_text("<config/>")
        spec = ConfigSpec(sources=("config.xml",))
        with pytest.raises(ValueError, match="Unsupported config format"):
            Config.load(spec, root=tmp_path)

    def test_yaml_loads_or_clear_error(self, tmp_path):
        (tmp_path / "config.yaml").write_text("site:\n  title: Test\n")
        spec = ConfigSpec(sources=("config.yaml",))
        # If pyyaml is installed, it loads. If not, clear error message.
        try:
            config = Config.load(spec, root=tmp_path)
            assert config.get("site.title") == "Test"
        except ImportError:
            pytest.skip("pyyaml not installed")

    def test_missing_overlay_warns(self, tmp_path):
        spec = ConfigSpec(sources=(), overlays={"prod": "config/prod.toml"})
        with pytest.warns(UserWarning, match="Config overlay file not found"):
            Config.load(spec, root=tmp_path, overlay="prod")


class TestConfigValidation:
    def test_valid_config(self):
        spec = ConfigSpec(
            defaults={"name": "myapp", "debug": False, "workers": 4},
        )
        config = Config.from_dict({"name": "other", "debug": True, "workers": 8})
        errors = config.validate(spec)
        assert errors == []

    def test_type_mismatch_string_for_int(self):
        spec = ConfigSpec(
            defaults={"workers": 4},
        )
        config = Config.from_dict({"workers": "abc"})
        errors = config.validate(spec)
        assert len(errors) == 1
        assert "workers" in errors[0]
        assert "int" in errors[0]

    def test_type_mismatch_string_for_bool(self):
        spec = ConfigSpec(
            defaults={"debug": False},
        )
        config = Config.from_dict({"debug": "maybe"})
        errors = config.validate(spec)
        assert len(errors) == 1
        assert "debug" in errors[0]

    def test_valid_string_coercion(self):
        """Env vars come as strings — valid numeric strings should pass."""
        spec = ConfigSpec(
            defaults={"workers": 4},
        )
        config = Config.from_dict({"workers": "8"})
        errors = config.validate(spec)
        assert errors == []

    def test_nested_validation(self):
        spec = ConfigSpec(
            defaults={"build": {"parallel": True, "workers": 4}},
        )
        config = Config.from_dict({"build": {"parallel": True, "workers": "abc"}})
        errors = config.validate(spec)
        assert len(errors) == 1
        assert "build.workers" in errors[0]

    def test_no_defaults_returns_empty(self):
        spec = ConfigSpec()
        config = Config.from_dict({"anything": "goes"})
        errors = config.validate(spec)
        assert errors == []

    def test_missing_key_not_error(self):
        """Missing keys are not validation errors (they use defaults)."""
        spec = ConfigSpec(
            defaults={"name": "app", "debug": False},
        )
        config = Config.from_dict({"name": "myapp"})
        errors = config.validate(spec)
        assert errors == []

    def test_dict_where_scalar_expected(self):
        spec = ConfigSpec(
            defaults={"name": "myapp"},
        )
        config = Config.from_dict({"name": {"nested": "bad"}})
        errors = config.validate(spec)
        assert len(errors) == 1

    def test_int_for_float_allowed(self):
        spec = ConfigSpec(
            defaults={"threshold": 0.5},
        )
        config = Config.from_dict({"threshold": 1})
        errors = config.validate(spec)
        assert errors == []


class TestConfigInit:
    def test_init_toml(self, tmp_path):
        from milo.config import Config, ConfigSpec

        spec = ConfigSpec(
            sources=("app.toml",),
            defaults={"name": "myapp", "debug": False},
        )
        path = Config.init(spec, root=tmp_path)
        assert path.exists()
        assert path.suffix == ".toml"
        content = path.read_text()
        assert "myapp" in content

    def test_init_yaml(self, tmp_path):
        from milo.config import Config, ConfigSpec

        spec = ConfigSpec(
            sources=("config.yaml",),
            defaults={"name": "myapp"},
        )
        path = Config.init(spec, root=tmp_path, fmt="yaml")
        assert path.exists()
        content = path.read_text()
        assert "myapp" in content

    def test_init_json(self, tmp_path):
        from milo.config import Config, ConfigSpec

        spec = ConfigSpec(
            sources=("config.json",),
            defaults={"name": "myapp"},
        )
        path = Config.init(spec, root=tmp_path, fmt="json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "myapp"

    def test_init_no_sources(self, tmp_path):
        from milo.config import Config, ConfigSpec

        spec = ConfigSpec(defaults={"key": "val"})
        path = Config.init(spec, root=tmp_path)
        assert path.exists()
