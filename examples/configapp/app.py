"""Configapp — configuration system with TOML files, profiles, and overlays.

Demonstrates: ConfigSpec, Config.load(), dot-notation access, origin tracking,
Config.validate(), Config.init() scaffolding.

    uv run python examples/configapp/app.py show
    uv run python examples/configapp/app.py show --key site.title
    uv run python examples/configapp/app.py origin --key site.url
    uv run python examples/configapp/app.py show --profile writer
    uv run python examples/configapp/app.py show --format json
    uv run python examples/configapp/app.py validate
    uv run python examples/configapp/app.py init --dir /tmp/newproject
"""

from __future__ import annotations

from pathlib import Path

from milo import CLI, Config, ConfigSpec, Context

_ROOT = Path(__file__).parent

spec = ConfigSpec(
    sources=("configapp.toml",),
    env_prefix="CAPP_",
    defaults={
        "site": {
            "title": "My Site",
            "url": "http://localhost:8080",
            "description": "",
        },
        "build": {
            "output": "_site",
            "drafts": False,
            "minify": False,
        },
    },
    profiles={
        "writer": {"build.drafts": True},
        "preview": {"site.url": "http://localhost:3000"},
    },
    overlays={
        "production": "production.toml",
    },
)

cli = CLI(
    name="configapp",
    description="Configuration system example — TOML, profiles, overlays, origin tracking.",
    version="0.1.0",
)

cli.global_option("profile", short="-p", description="Config profile to activate")
cli.global_option("overlay", short="-O", description="Environment overlay to apply")


def _load_config(ctx: Context) -> Config:
    """Load config with optional profile and overlay from global options."""
    return Config.load(
        spec,
        root=_ROOT,
        profile=ctx.globals.get("profile", ""),
        overlay=ctx.globals.get("overlay", ""),
    )


@cli.command("show", description="Show merged configuration")
def show(key: str = "", ctx: Context = None) -> dict | str:
    """Show the full merged config, or a single key with dot-notation."""
    config = _load_config(ctx)
    if key:
        value = config.get(key)
        return {key: value} if value is not None else {"error": f"Key {key!r} not found"}
    return config.as_dict()


@cli.command("origin", description="Show where a config value came from")
def origin(key: str, ctx: Context = None) -> dict:
    """Trace the origin of a specific config key."""
    config = _load_config(ctx)
    value = config.get(key)
    source = config.origin_of(key)
    return {"key": key, "value": value, "origin": source}


@cli.command("dump", description="Dump config as Store-compatible state")
def dump(ctx: Context = None) -> dict:
    """Dump the merged config as a flat state dict for the Store."""
    config = _load_config(ctx)
    return config.to_state()


@cli.command("validate", description="Validate config against the spec")
def validate(ctx: Context = None) -> dict:
    """Check that all config values match the types defined in spec.defaults."""
    config = _load_config(ctx)
    errors = config.validate(spec)
    if errors:
        for err in errors:
            ctx.warning(err)
        return {"valid": False, "errors": errors}
    ctx.success("Config is valid")
    return {"valid": True, "errors": []}


@cli.command("init", description="Scaffold a new config file from defaults")
def init(dir: str = ".", ctx: Context = None) -> dict:
    """Create a config file from spec defaults in the given directory."""
    target = Path(dir)
    if ctx.dry_run:
        ctx.warning(f"Dry-run: would create config in {target}")
        return {"action": "dry-run", "dir": str(target)}

    path = Config.init(spec, root=target)
    ctx.success(f"Created {path}")
    return {"action": "created", "path": str(path)}


if __name__ == "__main__":
    cli.run()
