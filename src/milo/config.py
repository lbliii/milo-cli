"""Configuration system with deep merge, environment overlays, and origin tracking."""

from __future__ import annotations

import glob as globmod
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfigSpec:
    """Declarative configuration schema.

    Describes where config comes from and how it merges::

        cli.config_spec = ConfigSpec(
            sources=("bengal.toml", "config/*.yaml"),
            env_prefix="BENGAL_",
            profiles={"writer": {"build.drafts": True}},
            overlays={"production": "config/production.yaml"},
        )
    """

    sources: tuple[str, ...] = ()
    """File patterns to load (TOML via stdlib, YAML via optional pyyaml)."""

    env_prefix: str = ""
    """Environment variable prefix. BENGAL_BUILD_OUTPUT -> build.output."""

    defaults: dict[str, Any] = field(default_factory=dict)
    """Default values (lowest precedence)."""

    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Named override sets, selected via --profile."""

    overlays: dict[str, str] = field(default_factory=dict)
    """Environment -> file path mapping for env-specific config."""


class Config:
    """Immutable, merged configuration with origin tracking.

    Usage::

        config = Config.load(spec, root=Path("."), profile="dev", overlay="production")
        url = config.get("site.url", "http://localhost")
        print(config.origin_of("site.url"))  # "file:config/site.yaml"
    """

    def __init__(self, data: dict[str, Any], origins: dict[str, str]) -> None:
        self._data = data
        self._origins = origins

    @classmethod
    def load(
        cls,
        spec: ConfigSpec,
        *,
        root: Path | None = None,
        profile: str = "",
        overlay: str = "",
    ) -> Config:
        """Load, merge, and freeze config from all sources.

        Merge precedence (lowest to highest):
        1. spec.defaults
        2. File sources (in order)
        3. Environment variables
        4. Profile overrides
        5. Overlay file
        """
        root = root or Path.cwd()
        data: dict[str, Any] = {}
        origins: dict[str, str] = {}

        # 1. Defaults
        if spec.defaults:
            _deep_merge(data, spec.defaults, origins, origin="defaults")

        # 2. File sources
        for pattern in spec.sources:
            matched = sorted(globmod.glob(str(root / pattern)))
            for filepath in matched:
                file_data = _load_file(filepath)
                _deep_merge(data, file_data, origins, origin=f"file:{filepath}")

        # 3. Environment variables
        if spec.env_prefix:
            env_data = _load_env_vars(spec.env_prefix)
            _deep_merge(data, env_data, origins, origin="env")

        # 4. Profile overrides
        if profile and profile in spec.profiles:
            profile_data = _expand_dotted(spec.profiles[profile])
            _deep_merge(data, profile_data, origins, origin=f"profile:{profile}")

        # 5. Overlay file
        if overlay and overlay in spec.overlays:
            overlay_path = root / spec.overlays[overlay]
            if overlay_path.exists():
                overlay_data = _load_file(str(overlay_path))
                _deep_merge(data, overlay_data, origins, origin=f"overlay:{overlay}")

        return cls(data, origins)

    @classmethod
    def from_dict(cls, data: dict[str, Any], origin: str = "dict") -> Config:
        """Create a Config from a plain dictionary."""
        origins: dict[str, str] = {}
        _track_origins(data, origins, origin, prefix="")
        return cls(data, origins)

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access: ``config.get("site.url")``."""
        parts = key.split(".")
        current = self._data
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def origin_of(self, key: str) -> str:
        """Return the source that contributed a key's value."""
        return self._origins.get(key, "")

    def as_dict(self) -> dict[str, Any]:
        """Return a deep copy of the merged config."""
        import copy

        return copy.deepcopy(self._data)

    def to_state(self) -> dict[str, Any]:
        """Convert to a Store-compatible state dict."""
        return self.as_dict()

    def validate(self, spec: ConfigSpec, *, raise_on_error: bool = False) -> list[str]:
        """Validate config values against the spec's defaults for type consistency.

        Returns a list of error messages. An empty list means validation passed.
        Type expectations are inferred from the default values in ``spec.defaults``.

        When *raise_on_error* is True, raises :class:`ConfigError` if any
        validation errors are found instead of returning the list.
        """
        errors: list[str] = []
        if not spec.defaults:
            return errors
        self._validate_types(spec.defaults, self._data, errors, prefix="")
        if errors and raise_on_error:
            from milo._errors import ConfigError, ErrorCode

            raise ConfigError(
                ErrorCode.CFG_VALIDATE,
                f"Config validation failed with {len(errors)} error(s): {'; '.join(errors)}",
                suggestion="Check config files and environment variables for type mismatches.",
                context={"errors": errors},
            )
        return errors

    @staticmethod
    def _validate_types(
        defaults: dict[str, Any],
        actual: dict[str, Any],
        errors: list[str],
        prefix: str,
    ) -> None:
        """Recursively check that actual values match the types of defaults."""
        for key, default_val in defaults.items():
            dotted = f"{prefix}{key}" if prefix else key
            if key not in actual:
                continue
            actual_val = actual[key]

            if isinstance(default_val, dict):
                if isinstance(actual_val, dict):
                    Config._validate_types(default_val, actual_val, errors, prefix=f"{dotted}.")
                else:
                    errors.append(
                        f"{dotted}: expected a table/dict, got {type(actual_val).__name__}"
                    )
                continue

            # Scalar default but got a dict
            if isinstance(actual_val, dict):
                errors.append(f"{dotted}: expected {type(default_val).__name__}, got a table/dict")
                continue

            expected_type = type(default_val)
            # Allow int where float is expected
            if expected_type is float and isinstance(actual_val, int):
                continue
            # Coerce string env vars to expected type
            if isinstance(actual_val, str) and expected_type is not str:
                try:
                    if expected_type is bool:
                        if actual_val.lower() not in ("true", "false", "1", "0", "yes", "no"):
                            errors.append(f"{dotted}: expected bool, got {actual_val!r}")
                    elif expected_type is int:
                        int(actual_val)
                    elif expected_type is float:
                        float(actual_val)
                except ValueError, TypeError:
                    errors.append(
                        f"{dotted}: expected {expected_type.__name__}, got {actual_val!r}"
                    )

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __repr__(self) -> str:
        return f"Config({list(self._data.keys())})"

    @staticmethod
    def init(
        spec: ConfigSpec,
        *,
        root: Path | None = None,
        fmt: str = "toml",
    ) -> Path:
        """Generate a starter config file from a ConfigSpec.

        Writes spec.defaults to the first source pattern's filename.
        Returns the path of the created file.
        """
        root = root or Path.cwd()

        # Determine filename from first source pattern, or use a default
        filename = spec.sources[0].replace("*", "app") if spec.sources else f"config.{fmt}"

        filepath = root / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = spec.defaults or {}

        if fmt == "toml" or filepath.suffix == ".toml":
            _write_toml(filepath, data)
        elif fmt in ("yaml", "yml") or filepath.suffix in (".yaml", ".yml"):
            _write_yaml(filepath, data)
        elif fmt == "json" or filepath.suffix == ".json":
            import json

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        else:
            _write_toml(filepath, data)

        return filepath


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_file(filepath: str) -> dict[str, Any]:
    """Load a TOML or YAML file."""
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".toml":
        with open(path, "rb") as f:
            return tomllib.load(f)

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as e:
            msg = (
                f"Cannot load {path.name}: PyYAML is required for YAML config files. "
                "Install it with: pip install pyyaml"
            )
            raise ImportError(msg) from e
        with open(path) as f:
            return yaml.safe_load(f) or {}

    if suffix == ".json":
        import json

        with open(path) as f:
            return json.load(f)

    msg = f"Unsupported config format: {suffix}"
    raise ValueError(msg)


def _load_env_vars(prefix: str) -> dict[str, Any]:
    """Load environment variables with a given prefix into nested dict.

    BENGAL_SITE_URL -> {"site": {"url": "value"}}
    """
    result: dict[str, Any] = {}
    prefix_upper = prefix.upper()
    for key, value in os.environ.items():
        if not key.startswith(prefix_upper):
            continue
        # Strip prefix and convert to nested path
        remainder = key[len(prefix_upper) :].lower()
        parts = remainder.split("_")
        # Build nested dict
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result


def _deep_merge(
    target: dict[str, Any],
    source: dict[str, Any],
    origins: dict[str, str],
    origin: str,
    prefix: str = "",
) -> None:
    """Deep merge source into target, tracking origins for leaf values."""
    for key, value in source.items():
        dotted = f"{prefix}{key}" if prefix else key
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value, origins, origin, prefix=f"{dotted}.")
        else:
            target[key] = value
            if isinstance(value, dict):
                _track_origins(value, origins, origin, prefix=f"{dotted}.")
            else:
                origins[dotted] = origin


def _track_origins(
    data: dict[str, Any],
    origins: dict[str, str],
    origin: str,
    prefix: str,
) -> None:
    """Recursively track origins for all keys in a dict."""
    for key, value in data.items():
        dotted = f"{prefix}{key}" if prefix else key
        origins[dotted] = origin
        if isinstance(value, dict):
            _track_origins(value, origins, origin, prefix=f"{dotted}.")


def _expand_dotted(flat: dict[str, Any]) -> dict[str, Any]:
    """Expand dotted keys into nested dicts.

    {"build.output": "_site"} -> {"build": {"output": "_site"}}
    """
    result: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result


def _write_toml(filepath: Path, data: dict[str, Any]) -> None:
    """Write a dict as TOML (stdlib-only, simple values)."""
    lines: list[str] = []
    _write_toml_section(data, lines, prefix="")
    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")


def _write_toml_section(data: dict[str, Any], lines: list[str], prefix: str) -> None:
    """Recursively write TOML sections."""
    # Write simple values first
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_value(value)}")

    # Then nested tables
    for key, value in data.items():
        if isinstance(value, dict):
            section = f"{prefix}{key}" if prefix else key
            lines.append(f"\n[{section}]")
            _write_toml_section(value, lines, prefix=f"{section}.")


def _toml_value(value: Any) -> str:
    """Format a Python value as TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_toml_value(v) for v in value)
        return f"[{items}]"
    return f'"{value}"'


def _write_yaml(filepath: Path, data: dict[str, Any]) -> None:
    """Write a dict as YAML."""
    try:
        import yaml  # type: ignore[import-untyped]

        with open(filepath, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    except ImportError:
        # Fallback: simple YAML writer
        lines: list[str] = []
        _write_yaml_simple(data, lines, indent=0)
        with open(filepath, "w") as f:
            f.write("\n".join(lines) + "\n")


def _write_yaml_simple(data: dict[str, Any], lines: list[str], indent: int) -> None:
    """Simple YAML writer for basic types."""
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            _write_yaml_simple(value, lines, indent + 1)
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            lines.extend(f"{prefix}  - {item}" for item in value)
        else:
            lines.append(f"{prefix}{key}: {value}")
