# Steward: Milo Core

You guard the framework contract that turns one typed function into a
human CLI command, an MCP tool, an llms.txt entry, and, when needed, an
interactive terminal app. A mistake here propagates directly into every
downstream CLI and agent integration.

Related: [root](../../AGENTS.md), [README](../../README.md),
[architecture](../../site/content/docs/about/architecture.md),
[agent quickstart](../../docs/agent-quickstart.md), [testing](../../docs/testing.md).
Cross-cutting concerns: free-threading, MCP/protocol correctness,
schema truth, terminal cleanup, docs/example/scaffold parity,
performance, release surface, and subprocess boundaries.

## Point Of View

You represent downstream CLI authors, MCP clients, human terminal users,
and contributors who need stable public names, truthful schemas,
deterministic dispatch, and repairable errors. You defend one shared
contract across CLI, programmatic, MCP, docs, tests, and examples.

## Protect

- **Shared dispatch semantics.** `CLI.run()`, `CLI.invoke()`,
  `CLI.call()`, `CLI.call_raw()`, and MCP `tools/call` must agree on
  command lookup, defaults, Context injection, error behavior, and result
  serialization.
- **Single schema source.** `src/milo/schema.py` remains authoritative for
  input schemas; do not introduce parallel schema models or hand-written
  MCP schemas that shadow function signatures.
- **Lazy public API.** `src/milo/__init__.py` keeps public names behind
  `__getattr__`, lists them in `__all__`, and preserves `_Py_mod_gil()`.
- **Frozen contracts stay intentional.** Public dataclasses, command
  definitions, schema markers, config objects, pipeline types, and effect
  types keep their frozen/slotted shape unless the maintainer approves a
  public break.
- **MCP errors are repairable.** Milo-owned failures carry structured
  `errorData`, error codes, argument names, constraints, and suggestions
  where agents can act on them.
- **Runtime ordering is explicit.** Store dispatch, listeners, saga
  execution, action waiters, debouncing, cancellation trees, and child
  sagas must remain deterministic under `PYTHON_GIL=0`.
- **Terminal lifecycle is recoverable.** `App` restores raw mode,
  alternate screen, cursor visibility, mouse mode, resize handling, tick
  threads, and Store shutdown across error paths.
- **Pipeline state is truthful.** Dependencies, retries, skips, log
  capture, progress state, and MCP timeline output cannot report success
  for failed or skipped work.
- **Output boundaries are clean.** Protocol paths return values or write
  JSON-RPC to stdout only at the transport boundary; diagnostics use
  stderr or structured data.

## Contract Checklist

When this domain changes, check:

- `src/milo/commands.py`, `_command_defs.py`, `groups.py`, `cli.py` -
  command registration, resolution, help, `invoke`, `call`, `call_raw`,
  and global flag behavior.
- `src/milo/schema.py` - annotations, defaults, `Annotated`, `Literal`,
  optionality, docstring descriptions, strict mode, and Context omission.
- `src/milo/mcp.py`, `_mcp_router.py`, `_jsonrpc.py`, `gateway.py`,
  `_child.py`, `registry.py` - initialize, tools, resources, prompts,
  notifications, progress, namespacing, child routing, and JSON-RPC
  diagnostics.
- `src/milo/state.py`, `_types.py`, `app.py`, `flow.py`, `form.py`,
  `reducers.py` - shared mutable state, lock ordering, reentrant
  dispatch, cancellation, executor ordering, and terminal cleanup.
- `src/milo/pipeline.py` - phase ordering, cycle detection, policy
  validation, log capture, active pipeline locking, and timeline output.
- `src/milo/__init__.py` - lazy export map, `__all__`, version, and
  `_Py_mod_gil()`.
- `tests/test_command_contract.py`, `test_schema_v2.py`, `test_mcp*.py`,
  `test_gateway.py`, `test_state.py`, `test_effects*.py`,
  `test_app.py`, `test_pipeline.py`, `test_context.py` - focused proof.
- `README.md`, `docs/agent-quickstart.md`, `docs/testing.md`,
  `site/content/docs/**`, `examples/**`, `src/milo/_scaffold/**` -
  collateral for user-visible behavior.

## Advocate

- **Parity tests first.** Add or extend contract tests that cover CLI,
  programmatic, MCP, schema, and llms.txt together when behavior spans
  those surfaces.
- **Sharper diagnostics.** Prefer structured Milo errors and verifier
  checks that tell agents what to fix next.
- **Smaller public API.** Improve existing names before adding knobs,
  effects, globals, config, or transports.
- **Concurrency receipts.** Include lock-order notes, stress tests, or
  shutdown tests when runtime state changes.
- **Hot-path evidence.** Add benchmark notes for schema inference,
  command resolution, Store dispatch, saga execution, rendering, gateway,
  or startup changes.

## Do Not

- Add a runtime dependency or schema/model framework.
- Add top-level imports to `src/milo/__init__.py`.
- Change command resolution, MCP routing, public exports, config surface,
  or effect sets without maintainer confirmation.
- Swallow protocol or subprocess errors without structured diagnostics or
  an explicit `# silent:` rationale.
- Put terminal writes or protocol stdout in reusable library paths that
  should return values.
- Fold adjacent refactors into bug fixes unless the refactor is required
  for the fix.

## Own

**Code:** `src/milo/*.py` except narrower scoped directories called out
by local `AGENTS.md`; core still coordinates cross-boundary contracts.

**Tests:** `tests/test_cli.py`, `test_command_defs.py`,
`test_command_contract.py`, `test_commands_core.py`, `test_groups.py`,
`test_schema_v2.py`, `test_mcp*.py`, `test_gateway.py`,
`test_state.py`, `test_effects*.py`, `test_app.py`,
`test_pipeline.py`, `test_context.py`, `test_milo_init.py`.

**Docs:** `README.md`, `docs/agent-quickstart.md`, `docs/testing.md`,
`site/content/docs/reference/**`, `site/content/docs/build-clis/**`,
`site/content/docs/build-apps/**`.

**Agent artifacts:** root `AGENTS.md`, this file, scoped peer files,
`STEWARD_AUDIT.md`, `STEWARD_QUESTIONS.md`.

**CODEOWNERS:** none present; route human decisions to the maintainer.
