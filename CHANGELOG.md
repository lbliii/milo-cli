# Changelog

All notable changes to Milo are documented here.

## 0.2.0 — Unreleased

### Added

- **Commands** — Lightweight `Cmd` effect type as a simpler alternative to sagas for one-shot side effects. A `Cmd` is a plain function `() -> Action | None` that runs on the thread pool.
- **Batch and Sequence combinators** — `Batch(*cmds)` runs commands concurrently; `Sequence(*cmds)` runs them serially. Both support recursive nesting.
- **`compact_cmds()`** — Helper to strip `None` entries from command tuples.
- **`TickCmd(interval)`** — Self-sustaining tick pattern. Schedules a single `@@TICK` after *interval* seconds. Return another `TickCmd` from `@@TICK` to keep ticking; omit to stop. Gives per-component, dynamic tick control.
- **`ViewState`** — Declarative terminal state (`alt_screen`, `cursor_visible`, `window_title`, `mouse_mode`). Returned via `ReducerResult(state, view=ViewState(...))`. The renderer diffs previous vs. current and applies only the changes.
- **Message filter** — `App(filter=fn)` accepts a function `(state, action) -> action | None` that intercepts actions before dispatch. Return `None` to drop, return a different action to transform.
- **Saga error recovery** — Unhandled saga exceptions now dispatch `@@SAGA_ERROR` instead of being swallowed silently. Payload: `{"error": "message", "type": "ExceptionTypeName"}`.
- **Cmd error recovery** — Unhandled `Cmd` exceptions dispatch `@@CMD_ERROR` with the same payload shape.
- **Bulletproof terminal cleanup** — Each step in `App.run()` finally block is individually guarded so a failure in one does not prevent the rest from running.

### Changed

- **`ReducerResult`** — now accepts `cmds` and `view` fields alongside `sagas`
- **`Quit`** — now accepts `cmds` and `view` fields alongside `sagas`
- **`combine_reducers`** — collects `cmds` and `view` from child reducers
- **`_TerminalRenderer`** — supports `apply_view_state()` for declarative terminal feature control

## 0.1.1 — 2026-03-31

### Added

- **Reducer combinators** — `quit_on`, `with_cursor`, `with_confirm` decorators eliminate boilerplate key handling in Elm-style reducers
- **Shell completions** — `install_completions()` generates bash/zsh/fish completions from CLI definitions
- **Doctor diagnostics** — `run_doctor()` with `Check` specs validates environment, dependencies, and config health
- **Version checking** — `check_version()` detects newer PyPI releases and prints upgrade notices (respects `NO_UPDATE_CHECK`)
- **`App.from_dir()`** — automatic template directory discovery relative to the calling file
- **`Context.run_app()`** — bridge CLI commands to interactive Elm Architecture apps
- **Built-in template macros** — `selectable_list`, `scrollable_list`, `format_time` in `components/_defs.kida`
- **`Config.validate()`** — type-check config values against spec defaults
- **Structured error handling** — `run()` shows `MiloError` code + hint; other exceptions show type + message with optional traceback
- **Command examples in help** — examples render in `HelpRenderer` and `generate_help_all()`
- **`invoke()` test helper** — split stdout/stderr for cleaner test assertions
- **Progress bars** — `CLIProgress` for long-running command feedback
- **`Context.log()`** — leveled logging to stderr (quiet/normal/verbose/debug)
- **Before/after hooks** — `HookRegistry` for command lifecycle interception
- **Confirm gates** — require user confirmation before destructive commands
- **Did-you-mean suggestions** — fuzzy match on unknown commands
- **Dry-run and output-file flags** — built-in global options for safe command execution
- **`Retry` saga effect** — retry with backoff for transient failures
- **`Config.init()` scaffolding** — generate starter config files
- **`devtool` example** — showcases doctor, hooks, examples-in-help, structured errors, and completions

### Changed

- **Modularized commands** — extracted `_command_defs.py` (data types) and `_cli_help.py` (help generation) from the monolithic `commands.py`
- **Shared JSON-RPC helpers** — extracted `_jsonrpc.py` with `MCP_VERSION` constant to reduce duplication in `gateway.py` and `mcp.py`
- **Unified command registration** — `_make_command_def` helper shared between CLI and Group
- **Updated all Elm examples** — counter, stopwatch, todo, filepicker, and wizard use the new combinator and `App.from_dir()` APIs

### Fixed

- **HelpRenderer as default formatter** — `CLI.build_parser()` and subparsers now wire `HelpRenderer` by default
- **Action group capture in help** — `_render_with_template()` uses formatter lifecycle instead of accessing parser attributes
- **Docstring propagation** — schema correctly propagates function docstrings to argparse help text
- **Package data** — `components/*.kida` included in distribution
- **Registry N+1 reads** — `doctor/check_all` uses `_health_check_entry` to batch file reads
- **MCP tool caching** — `_list_tools` cached in `run_mcp_server` to avoid recomputing on every `tools/list`
- **`execution_order()` performance** — parallel `seen` set eliminates per-iteration rebuild
- **`--version` rendering** — guards template path when no action groups are captured
- **`generate_help_all` formatting** — fixed unclosed backtick in global options section
- **uv detection** — version upgrade notices use `uv pip install` when running under uv

## 0.1.0 — 2026-03-26

Initial release. See [release notes](https://lbliii.github.io/milo/releases/0.1.0/).
