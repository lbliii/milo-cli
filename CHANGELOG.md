# Changelog

All notable changes to Milo are documented here.

## 0.3.1 — 2026-05-23

### Changed

- Bumped to `kida-templates>=0.9.0,<0.10.0`, refreshing the lockfile and release surface for Kida 0.9.
- Expanded the AGENTS.md steward network with verification-status signals, cross-cutting root concerns, known regression patterns, steward questions, and self-audit tracking. ([#steward-network](https://github.com/lbliii/milo-cli/issues/steward-network))
- Prepared the 0.3.1 release by aligning package metadata, changelog intent, and public site release notes.

### Fixed

- Strengthened `scripts/check_templates.py` to enforce Kida strict end-tag and fragile same-folder import checks in Milo's terminal-aware template environment, and cleaned the bundled component imports/error template to satisfy that gate.


## 0.3.0 — 2026-05-03

### Added

- Added migration recipes, example docs, and an opt-in Markdown snippet verifier for docs drift checks. ([#docs-migration-verifier](https://github.com/lbliii/milo-cli/issues/docs-migration-verifier))
- Added steward-priority coverage for command dispatch parity, runnable output-gallery adoption guidance, scaffolded `milo verify`, terminal cleanup, dispatch lock edges, and display-cell rendering benchmarks. ([#steward-priority-coverage](https://github.com/lbliii/milo-cli/issues/steward-priority-coverage))
- Added display-cell width template filters for terminal layouts: `cell_width`, `cell_fit`, `cell_pad`, `cell_rpad`, and `cell_truncate`. ([#terminal-cell-width](https://github.com/lbliii/milo-cli/issues/terminal-cell-width))
- Added display-cell exact topology filters for terminal templates: `rule_line`, `divider_line`, `bottom_rule`, `frame_line`, `rail_line`, `cell_fill`, `cell_meter`, `open_rule`, `open_rule_divider`, and `open_rule_end`. ([#terminal-open-rules](https://github.com/lbliii/milo-cli/issues/terminal-open-rules))
- Add silent-exception lint gate and `# silent: <reason>` annotations to prevent unlogged exception swallowing
- Adopt Kida 0.7 capabilities: `inline_components=True` and `validate_calls=True` defaults in `get_env()`; `enable_capture` opt-in kwarg on `get_env()` for static-site / capture flows; new `milo components` subcommand listing bundled and user-defined template defs (with `--json` for tooling, `--path` to scan extra dirs); `milo.live` re-exports for `LiveRenderer`, `Spinner`, `stream_to_terminal`, `terminal_env`; `kida.get_optimal_workers` now sizes the gateway, registry, and saga executor pools by workload type (IO_BOUND for I/O fan-out, RENDER for saga effects); `{% flush %}` boundaries added to `pipeline_progress` and `pipeline_detail` defs to encode streaming contract; CI gains a template compile-check via `scripts/check_templates.py`; new `examples/liverender` shows `LiveRenderer` outside the App harness; new docs page `docs/build-apps/live`.
- Agent-first improvements: structured MCP validation errors with argument/constraint context, `form_schema()` introspection helper, `llms.txt` required/optional/default markers, `docs/agent-quickstart.md`, `docs/testing.md`, and `examples/greet/` test template.
- Agent-native affordances: `milo new <name>` scaffold (app.py, tests, conftest, README), `milo verify <path>` six-check self-diagnosis (imports, CLI located, commands registered, schemas generate, in-process MCP list, subprocess MCP transport), `function_to_schema(..., warn_missing_docs=True)` surfacing undocumented typed params, README examples index with drift lint, and a Python 3.14+ preflight on `milo` with an actionable install hint instead of ImportError.

### Changed

- Reorganized the documentation site into reader-intent sections for About, Get Started, Build CLIs, Build Apps, Quality and Operations, Reference, Examples, and Applied Tutorials. ([#docs-site-ia](https://github.com/lbliii/milo-cli/issues/docs-site-ia))
- Tightened steward guidance with contract checklists, evidence-backed finding format, collateral update rules, synthesis requirements, and parity-matrix expectations for cross-surface work. ([#steward-contract-checklists](https://github.com/lbliii/milo-cli/issues/steward-contract-checklists))
- Added scoped AGENTS.md steward guidance for core Milo domains so future agent work has explicit ownership, consultation, and safety routing.
- Adopt Python 3.14+ patterns: PEP 695 type aliases in middleware, match/case in form key handlers, frozen+slotted dataclasses in tests
- Bumped to `kida-templates>=0.7.0,<0.8.0`. Kida 0.7 makes `strict_undefined=True` the default — milo's bundled templates already conformed, so no behaviour changes for callers using stock templates. User templates that relied on silent-undefined fallbacks now raise `UndefinedError` at render; opt back into the loose mode by passing `get_env(strict_undefined=False)`.

### Fixed

- Fixed command, MCP, schema, app runtime, flow, form, llms.txt, and docs regressions found in the project-wide bugbash, including Context injection parity, JSON-RPC invalid-request handling, gateway progress routing, Store shutdown/listener serialization, and CLI/schema contract drift. ([#bugbash-contracts](https://github.com/lbliii/milo-cli/issues/bugbash-contracts))


## 0.2.2 — 2026-04-13

### Added

- Added pipeline observability: `PhaseLog` dataclass with `@@PHASE_LOG` action and ring-buffer reducer for per-phase stdout/stderr capture (opt-in via `Pipeline(capture_output=True)`). New `phase_detail()` and `pipeline_detail()` kida macros for interactive TUI with cursor navigation, log scrolling, and auto-follow. `PipelineViewState` + `make_detail_reducer()` for Elm-style keyboard-driven expand/collapse interaction. `milo://pipeline/timeline` MCP resource exposes phase execution timeline as structured JSON. Gateway `--status` now shows real CLI metrics and pipeline state.

### Changed

- Bumped minimum kida-templates dependency to 0.5.0. This brings a correctness fix for variable bindings inside unrolled for-loops (affects form, select, pipeline, and component templates) and faster template compilation from cached `str.join` and filter folding.
- Optimized dispatch lock hold time by replacing SHA256 with builtin hash and deferring recording append outside the lock. Fixed `get_env()` singleton cache that was never written, reducing repeated calls from 122μs to 125ns. Added bulk task accounting for Batch effects.
- Refactored `CLI` command dispatch internals to share builtin-mode handling, command resolution, hook execution, middleware execution, generator consumption, and output writing across `run()`, `call()`, and `call_raw()` without changing the public API.

### Fixed

- Eliminate remaining sharp edges: warn on silent template/config fallbacks, validate PhasePolicy and pipeline dependencies eagerly, fix exit code on aborted confirmations (130 instead of 0), suppress `display_result=False` across all output formats, tighten Context injection type check, return `default` from `confirm()` in dry-run mode, add `fail_fast` option to hook invocation and parallel pipelines.
- Fix 7 Python 2 `except A, B:` syntax errors, replace silent exception swallowing with warnings/logging, add atomic file writes for registry and version cache, guard unhandled template lookups, and add `raise_on_error` to `Config.validate()`.
- Fix `call()` and `call_raw()` to re-raise exceptions instead of calling `sys.exit(1)`, restoring the pre-refactor behavior for programmatic invocations.
- Fix sharp edges: syntax errors, silent failures, strict APIs, tests

## 0.2.1 — 2026-04-12

### Fixed

- Fixed group bare invocation showing "Unknown command" instead of group help, and help output now lists subcommands by name instead of raw argparse internals.
- Lazy commands now propagate function signature defaults to argparse. Schema defaults are JSON-safe, boolean schema defaults are respected, boolean `default=True` parameters use `--no-xxx` flags, schema `enum` values become argparse `choices`, and a new `display_result=False` option suppresses plain-format output while preserving `--output-file` and `--format json`. `Group.lazy_command()` now supports `examples`, `confirm`, and `annotations` kwargs for parity with `CLI.lazy_command()`.

## 0.2.0 — 2026-04-10

### Added

- **Saga effects expansion** — Race (first-wins with loser cancellation), All (wait-all with fail-fast), Take (pause until action dispatched), and Debounce (cancel-and-restart timer). Fixed Python 2 exception syntax bug in pipeline handler introspection. Added gateway test suite covering namespacing, routing, proxying, idle reaping, and error handling.
- **Saga hardening** — SagaContext for structured cancellation trees, EffectResult handler registry, TakeEvery/TakeLatest higher-order effects, configurable thread pool (max_workers, on_pool_pressure), and comprehensive benchmarks and free-threading stress tests.
- **Orchestration hardening** — Timeout wrapper effect, TryCall structured error handling, and saga cancellation tokens. PhasePolicy with retry/skip/stop failure semantics, DFS cycle detection, and phase context forwarding. Per-request timeout and graceful child restart for MCP gateway. Tuple/set/frozenset schema support, `$ref` for recursive dataclasses, and fallback warnings.
- **Towncrier changelog** — Adopted Towncrier for changelog management. Fragments in `changelog.d/` are compiled into `CHANGELOG.md` at release time. CI enforces a fragment for every PR that touches `src/`.
- **Extended theme colors** — `ThemeStyle` supports 256-color (int index), truecolor (`#rrggbb` hex), and background colors (`bg` field) alongside existing named ANSI colors.
- **Pipeline TUI** — Interactive pipeline TUI in `buildpipe` example using `App` + `Store` + saga for real-time phase visualization with progress bar.
- **`pipeline_progress` macro** — Reusable `pipeline_progress(state)` component macro in `_defs.kida` for rendering `PipelineState` with phase status and progress bar.

### Changed

- **kida-templates 0.4.0** — Adopt match blocks, try/fallback error boundaries, and unless conditionals in templates; fix color detection to use public terminal_color API.

## 0.1.1 — 2026-04-02

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
- **Commands** — Lightweight `Cmd` effect type as a simpler alternative to sagas for one-shot side effects. A `Cmd` is a plain function `() -> Action | None` that runs on the thread pool.
- **Batch and Sequence combinators** — `Batch(*cmds)` runs commands concurrently; `Sequence(*cmds)` runs them serially. Both support recursive nesting.
- **`compact_cmds()`** — Helper to strip `None` entries from command tuples.
- **`TickCmd(interval)`** — Self-sustaining tick pattern. Schedules a single `@@TICK` after *interval* seconds. Return another `TickCmd` from `@@TICK` to keep ticking; omit to stop. Gives per-component, dynamic tick control.
- **`ViewState`** — Declarative terminal state (`alt_screen`, `cursor_visible`, `window_title`, `mouse_mode`). Returned via `ReducerResult(state, view=ViewState(...))`. The renderer diffs previous vs. current and applies only the changes.
- **Message filter** — `App(filter=fn)` accepts a function `(state, action) -> action | None` that intercepts actions before dispatch. Return `None` to drop, return a different action to transform.
- **Saga error recovery** — Unhandled saga exceptions now dispatch `@@SAGA_ERROR` instead of being swallowed silently. Payload: `{"error": "message", "type": "ExceptionTypeName"}`.
- **Cmd error recovery** — Unhandled `Cmd` exceptions dispatch `@@CMD_ERROR` with the same payload shape.
- **Bulletproof terminal cleanup** — Each step in `App.run()` finally block is individually guarded so a failure in one does not prevent the rest from running.
- **MCP dispatch router** — Extracted shared `_mcp_router.py` to deduplicate tool/resource/prompt dispatch between `mcp.py` and `gateway.py`
- **`spinner` example** — showcases `Cmd`, `Batch`, `TickCmd`, and `ViewState` patterns

### Changed

- **Modularized commands** — extracted `_command_defs.py` (data types) and `_cli_help.py` (help generation) from the monolithic `commands.py`
- **Shared JSON-RPC helpers** — extracted `_jsonrpc.py` with `MCP_VERSION` constant to reduce duplication in `gateway.py` and `mcp.py`
- **Unified command registration** — `_make_command_def` helper shared between CLI and Group
- **Updated all Elm examples** — counter, stopwatch, todo, filepicker, and wizard use the new combinator and `App.from_dir()` APIs
- **`ReducerResult`** — now accepts `cmds` and `view` fields alongside `sagas`
- **`Quit`** — now accepts `cmds` and `view` fields alongside `sagas`
- **`combine_reducers`** — collects `cmds` and `view` from child reducers
- **`_TerminalRenderer`** — supports `apply_view_state()` for declarative terminal feature control
- **Middleware wired into dispatch** — registered middleware now executes in `CLI.run()` and `CLI.call()` paths
- **Parallelized gateway** — health checks and gateway discovery use `ThreadPoolExecutor`
- **Lazy `walk_commands`** — converted to generators to avoid eager materialization
- **Workflow detection** — pre-computed property sets eliminate O(n²) redundant work

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
- **Version string drift** — `cli.py`, `mcp.py`, and `gateway.py` now use `__version__` from `__init__.py` instead of hardcoded strings
- **ViewState merging in `combine_reducers`** — multiple child reducers' ViewState fields are now merged instead of last-wins overwrite
- **Message filter + Ctrl+C** — `quit_dispatched` flag is only set after the filter passes, so filtered @@QUIT no longer locks out subsequent Ctrl+C
- **`CLI.call()` middleware context** — now provides a proper `Context` instead of `None`
- **Gateway child I/O timeout** — `_read_line()` enforces a 30-second deadline to prevent deadlocks when a child process dies mid-write
- **`ThreadPoolExecutor` shutdown** — `Store.shutdown()` now waits for pending work (`wait=True`)
- **Batch timeout** — nested `Batch` inside `Sequence` uses a 60-second timeout on `concurrent.futures.wait()`
- **Error recovery logging** — failed `@@SAGA_ERROR`/`@@CMD_ERROR` dispatches are logged at DEBUG level instead of silently swallowed
- **Before/after hook error handling** — before-command hook errors now exit with code 1; after-command hook errors are logged without crashing

## 0.1.0 — 2026-03-26

Initial release. See [release notes](https://lbliii.github.io/milo-cli/releases/0.1.0/).
