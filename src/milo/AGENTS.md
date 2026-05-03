# Milo Core Steward

This domain represents the framework contract: one function becoming CLI, MCP, llms.txt, terminal app, and typed public API. Core mistakes propagate directly into downstream CLIs and agent tools.

Related docs:
- root `AGENTS.md`
- `README.md`
- `site/content/docs/about/architecture.md`
- `docs/agent-quickstart.md`
- `docs/testing.md`

## Point Of View
Represent downstream CLI authors, MCP clients, human terminal users, and contributors who depend on stable public names, truthful schemas, deterministic dispatch, and repairable errors.

## Protect
- `CLI.run()`, `CLI.invoke()`, `CLI.call()`/`call_raw()`, and MCP `tools/call` must share command semantics.
- `function_to_schema` is authoritative for input schema; `Context` injection stays invisible to MCP schemas.
- `milo.__init__` remains lazy and keeps the PEP 703 `_Py_mod_gil = 0` marker.
- Public dataclasses, config objects, command definitions, schema markers, pipeline types, and effect types keep their frozen/slots intent unless a public break is approved.
- MCP responses keep structured `errorData` useful enough for agents to repair calls without parsing text.
- Store dispatch, saga cancellation, action waiters, debouncing, races, `All`, and child sagas remain correct under true parallelism.
- Terminal app lifecycle restores raw mode, alternate screen, cursor, mouse mode, and resize handling even on errors.
- Pipeline dependencies, retries, output capture, and progress state cannot report success for skipped or failed work.

## Contract Checklist
- Command dispatch changes get parity coverage across CLI invocation, programmatic call/call_raw, MCP `tools/call`, help/llms.txt when applicable, and malformed input diagnostics.
- Schema changes exercise annotations, defaults, `Annotated`, `Literal`, optionality, docstring descriptions, and MCP input schema output.
- MCP/gateway changes cover `initialize`, `tools/list`, `tools/call`, resources/prompts when touched, JSON-RPC error codes, notifications, streaming progress, and child-process routing.
- State/app/runtime changes name shared mutable state, lock ordering, reentrant dispatch risks, cancellation/shutdown behavior, executor ordering, and terminal cleanup.
- Public exports or dataclass/effect/config changes update `src/milo/__init__.py`, docs, examples, scaffold, changelog, and typing tests as relevant.
- Hot-path changes include benchmark notes for schema inference, command resolution, Store dispatch, saga execution, rendering, gateway dispatch, or child process routing.

## Advocate
- More schema coverage for modern typing when it improves agent correctness.
- Clearer diagnostics at CLI, MCP, and `milo verify` boundaries.
- Benchmarks for command resolution, schema inference, Store dispatch, MCP/gateway dispatch, and rendering.
- Smaller public APIs with better examples instead of speculative knobs.

## Serve Peers
- Give tests three-path fixtures for schema, CLI/programmatic dispatch, and MCP dispatch.
- Give docs stable examples that match current public exports.
- Give templates simple data shapes and predictable built-in globals/filters.
- Give examples and scaffold the smallest correct pattern for new CLI authors.
- Give benchmarks focused cases for hot paths before optimizing code.

## Do Not
- Add top-level imports to `src/milo/__init__.py`.
- Add a runtime dependency or schema/model framework.
- Change command resolution, MCP routing, public exports, config surface, or effect sets without human check-in.
- Swallow protocol or subprocess errors without structured diagnostics or an explicit `# silent:` rationale.
- Put terminal writes or stdout protocol output in reusable library paths that should return values.
- Fold adjacent refactors into bug fixes unless the refactor is the fix.

## Own
- Core tests in `tests/test_cli.py`, `test_command_defs.py`, `test_groups.py`, `test_schema_v2.py`, `test_mcp*.py`, `test_gateway.py`, `test_state.py`, `test_effects*.py`, `test_app.py`, `test_pipeline.py`, `test_context.py`, and related focused files.
- Public API export checks in `tests/test_milo_init.py` and typing checks via `make ty`.
- Protocol and dispatch examples in `README.md`, `docs/agent-quickstart.md`, and site usage docs.
- Changelog fragments for public API, behavior, or protocol changes.
- Benchmark coordination with `benchmarks/` for hot-path changes.
