---
title: CLI & Commands
nav_title: CLI
description: AI-native CLI with typed commands, automatic argparse, MCP tools, and llms.txt.
weight: 50
draft: false
lang: en
tags: [cli, commands, ai-native, mcp]
keywords: [cli, command, decorator, argparse, mcp, llms-txt, ai-native]
category: usage
icon: terminal
---

Milo's `CLI` class turns decorated Python functions into CLI commands, MCP tools, and llms.txt entries — all from a single definition. Type annotations drive argument parsing, schema generation, and help text.

## Creating a CLI

```python
from milo import CLI

cli = CLI(name="myapp", description="My tool", version="1.0.0")
```

The `CLI` is the entry point for your application. It manages commands, groups, global options, and dispatches to handlers.

## Registering commands

Use the `@cli.command` decorator to register functions as CLI subcommands:

```python
@cli.command("greet", description="Say hello")
def greet(name: str, loud: bool = False) -> str:
    msg = f"Hello, {name}!"
    return msg.upper() if loud else msg
```

Type annotations are used to:

- Generate argparse arguments (`--name`, `--loud`)
- Generate MCP tool schemas for AI agents
- Determine required vs optional parameters (parameters with defaults are optional)

```
myapp greet --name Alice
myapp greet --name Alice --loud
```

## Command options

```python
@cli.command(
    "deploy",
    description="Deploy the application",
    aliases=("d",),          # Alternative names
    tags=("ops",),           # Grouping in llms.txt
    hidden=True,             # Omit from help and llms.txt
)
def deploy(target: str, dry_run: bool = False) -> dict: ...
```

## Supported parameter types

| Python type | argparse | JSON Schema |
|---|---|---|
| `str` | `--flag VALUE` | `"string"` |
| `int` | `--flag N` (type=int) | `"integer"` |
| `float` | `--flag N` (type=float) | `"number"` |
| `bool` | `--flag` (store_true) | `"boolean"` |
| `list[str]` | `--flag A B C` (nargs=*) | `"array"` |
| `X \| None` | optional | unwrapped to base type |

## Output formatting

Every command gets a `--format` flag automatically:

```
myapp greet --name Alice --format json
myapp greet --name Alice --format table
myapp greet --name Alice --format plain   # default
```

The handler's return value is serialized based on the chosen format. See [[docs/usage/output|Output Formatting]] for details.

## Running the CLI

```python
if __name__ == "__main__":
    cli.run()
```

`cli.run()` parses `sys.argv`, resolves the command, injects context, calls the handler, and formats the output.

## Built-in flags

Every CLI gets these flags automatically:

| Flag | Description |
|---|---|
| `--version` | Print version and exit |
| `--llms-txt` | Output an llms.txt AI discovery document |
| `--mcp` | Run as an MCP server (JSON-RPC on stdin/stdout) |
| `-v` / `--verbose` | Increase verbosity (stackable: `-vv` for debug) |
| `-q` / `--quiet` | Suppress non-error output |
| `--no-color` | Disable color output |

## Programmatic invocation

Call commands directly without going through argparse:

```python
result = cli.call("greet", name="Alice")
result = cli.call("site.build", output="_site")  # dotted paths for group commands
```

This is how the MCP server dispatches tool calls internally.

## Fuzzy matching

If a user mistypes a command, the CLI suggests the closest match:

```
$ myapp gret
Unknown command: 'gret'. Did you mean 'greet'?
```

## Shell completions

Milo can generate shell completion scripts for bash, zsh, and fish. Every CLI gets a `--completions` flag:

```
myapp --completions bash   # Print bash completion script
myapp --completions zsh    # Print zsh completion script
myapp --completions fish   # Print fish completion script
```

Add the output to your shell config to enable tab-completion for commands and flags:

:::{tab-set}
:::{tab-item} bash

```bash
eval "$(myapp --completions bash)"
```

Or add to `~/.bashrc` for persistence.

:::{/tab-item}

:::{tab-item} zsh

```bash
eval "$(myapp --completions zsh)"
```

Or add to `~/.zshrc` for persistence.

:::{/tab-item}

:::{tab-item} fish

```fish
myapp --completions fish | source
```

Or save to `~/.config/fish/completions/myapp.fish` for persistence.

:::{/tab-item}
:::{/tab-set}

Programmatically, use `install_completions()`:

```python
from milo.completions import install_completions

script = install_completions(cli, shell="zsh")  # or "bash", "fish"
```

If `shell` is omitted, it auto-detects from the `$SHELL` environment variable.

## Doctor diagnostics

The doctor system runs health checks against your CLI environment. Define what to verify, and `run_doctor` checks it all at once:

```python
from milo.doctor import run_doctor, format_doctor_report

report = run_doctor(
    cli,
    config_spec=spec,                          # Check config files exist
    required_env=("API_KEY", "DATABASE_URL"),   # Required env vars
    required_tools=("git", "node"),             # Required binaries on PATH
    custom_checks=(my_custom_check,),           # Callables returning Check
)

print(format_doctor_report(report))
```

Output:

```
  ✓ python: Python 3.14.0
  ✓ milo: milo 0.2.0
  ✓ config:myapp.toml: Found 1 file(s)
  ✓ env:API_KEY: Set
  ✗ env:DATABASE_URL: Not set
    hint: export DATABASE_URL=<value>
  ✓ tool:git: /usr/bin/git

5 passed, 0 warnings, 1 failures
```

Built-in checks include Python version, Milo version, config file discovery, and registered command count. Add custom checks by passing callables that return a `Check`:

```python
from milo.doctor import Check

def check_disk_space():
    free_gb = get_free_space()
    if free_gb < 1:
        return Check(name="disk", status="fail", message="Low disk space",
                     suggestion="Free up disk space")
    return Check(name="disk", status="ok", message=f"{free_gb:.1f} GB free")
```

The `DoctorReport` dataclass tracks counts: `report.ok`, `report.warnings`, `report.failures`.

## Version checking

Milo can check PyPI for newer versions of your package:

```python
from milo.version_check import check_version, format_version_notice

info = check_version("myapp", current_version="1.0.0")
if info and info.update_available:
    print(format_version_notice(info, prog="myapp"), file=sys.stderr)
```

```
A new version of myapp is available: 1.0.0 -> 1.2.0
  pip install --upgrade myapp
```

Key behaviors:

- **Caching** — results are cached in `~/.milo/cache/` for 24 hours to avoid hitting PyPI on every invocation.
- **Silent failures** — network errors, timeouts, and cache failures are swallowed; `check_version()` returns `None`.
- **Opt-out** — set `NO_UPDATE_CHECK=1` or `CI=1` to disable the check entirely.
- **Installer detection** — `format_version_notice()` detects `uv` vs `pip` and prints the correct upgrade command.

The `VersionInfo` dataclass contains `current`, `latest`, `update_available`, and an optional `message`.

:::{tip}
See [[docs/usage/groups|Command Groups]] for organizing commands into nested namespaces, [[docs/usage/context|Context]] for injecting execution context into handlers, and [[docs/usage/lazy|Lazy Loading]] for deferred imports.
:::
