---
title: Configuration
nav_title: Config
description: Configuration system with TOML/YAML/JSON loading, deep merge, profiles, and origin tracking.
weight: 60
draft: false
lang: en
tags: [config, toml, yaml, profiles, overlays]
keywords: [config, configuration, toml, yaml, json, profiles, overlays, merge, origin]
category: usage
icon: settings
---

Milo's configuration system loads settings from multiple sources, merges them with clear precedence, and tracks where each value came from.

## ConfigSpec

Declare your configuration schema with `ConfigSpec`:

```python
from milo import ConfigSpec

spec = ConfigSpec(
    sources=("myapp.toml", "config/*.yaml"),
    env_prefix="MYAPP_",
    defaults={
        "site": {"title": "My Site", "url": "http://localhost:8080"},
        "build": {"output": "_site", "drafts": False},
    },
    profiles={
        "writer": {"build.drafts": True},
        "preview": {"site.url": "http://localhost:3000"},
    },
    overlays={
        "production": "config/production.yaml",
    },
)
```

| Field | Purpose |
|---|---|
| `sources` | File glob patterns to load (TOML, YAML, JSON) |
| `env_prefix` | Environment variable prefix for overrides |
| `defaults` | Lowest-precedence default values |
| `profiles` | Named override sets, selected at load time |
| `overlays` | Environment-specific config files |

## Loading config

```python
from milo import Config

config = Config.load(spec, root=Path("."), profile="writer", overlay="production")
```

### Merge precedence

Sources merge lowest-to-highest:

1. `defaults` — baseline values
2. File sources — in glob order
3. Environment variables — `MYAPP_SITE_URL` becomes `site.url`
4. Profile overrides — selected via `profile=`
5. Overlay file — environment-specific file

## Accessing values

Use dot-notation to access nested values:

```python
url = config.get("site.url", "http://localhost")
title = config.get("site.title")
output = config.get("build.output", "_site")
```

Check if a key exists:

```python
if "site.url" in config:
    print(config.get("site.url"))
```

## Origin tracking

Every value tracks where it came from:

```python
config.origin_of("site.url")      # "file:myapp.toml"
config.origin_of("build.drafts")  # "profile:writer"
config.origin_of("site.title")    # "defaults"
```

Origins use prefixes: `defaults`, `file:<path>`, `env`, `profile:<name>`, `overlay:<name>`.

## Environment variables

With `env_prefix="MYAPP_"`, environment variables map to nested keys:

```bash
export MYAPP_SITE_URL=https://example.com
export MYAPP_BUILD_OUTPUT=dist
```

These become `{"site": {"url": "https://example.com"}, "build": {"output": "dist"}}` and merge at precedence level 3.

## Supported file formats

| Format | Extension | Library |
|---|---|---|
| TOML | `.toml` | `tomllib` (stdlib) |
| YAML | `.yaml`, `.yml` | `pyyaml` (optional) |
| JSON | `.json` | `json` (stdlib) |

## Store integration

Convert config to a Store-compatible state dict:

```python
initial_state = config.to_state()
store = Store(reducer, initial_state=initial_state)
```

Or create a Config from an existing dict:

```python
config = Config.from_dict({"site": {"url": "http://localhost"}}, origin="test")
```

## Validating config

`Config.validate()` checks that loaded values match the types declared in your spec's defaults:

```python
errors = config.validate(spec)
if errors:
    for err in errors:
        print(f"Config error: {err}")
```

Type expectations are inferred from the default values. For example, if `defaults` has `{"build": {"drafts": False}}`, then `build.drafts` must be a boolean. String values from environment variables are coerced where possible (e.g. `"true"` to `bool`, `"42"` to `int`).

Returns an empty list when validation passes.

## Generating a starter config

`Config.init()` writes a starter config file populated with your spec's defaults:

```python
path = Config.init(spec, root=Path("."), format="toml")
print(f"Created {path}")
```

The filename is derived from the first entry in `spec.sources`. The `format` parameter controls the output format: `"toml"` (default), `"yaml"`, or `"json"`.

This is useful for `myapp init` commands that scaffold a fresh configuration file for new users.

:::{tip}
Combine with [[docs/usage/context|Context]] to let users select profiles via `--profile` global options that flow through to config loading.
:::
