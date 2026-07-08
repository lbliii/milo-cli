# Milo Agent Constitution

## North Star

Milo exists to prove that one typed Python function can safely become a
human CLI command, an MCP tool with a truthful JSON Schema, and an
llms.txt entry. We protect that shared contract for humans, agents, and
downstream CLIs through pure Python, auditable types, deterministic
state, and free-threading correctness.

The public promise is visible in `README.md`, `site/content/_index.md`,
`docs/agent-quickstart.md`, and `docs/testing.md`: write a function with
annotations and a docstring, then let Milo derive the argparse command,
MCP schema, structured dispatch behavior, and agent-readable discovery.

## Non-Negotiables

- **Pure Python runtime.** `pyproject.toml` keeps one runtime dependency:
  `kida-templates`. Do not add `click`, `rich`, Pydantic, attrs,
  C extensions, or compiled hot-path shortcuts.
- **Python 3.14+ and free-threading.** `pyproject.toml` requires
  Python 3.14+, CI runs with `PYTHON_GIL=0`, and
  `src/milo/__init__.py` exposes the `_Py_mod_gil()` marker.
- **Types are the contract.** `src/milo/schema.py` is the source for
  JSON Schema from annotations, `Annotated[...]` constraints, docstrings,
  and defaults.
- **Context injection is invisible to agents.** `function_to_schema()`
  omits `Context` and `ctx` parameters; dispatch paths inject them.
- **Reducers stay pure.** I/O, logging, clocks, sleeps, random values,
  and subprocess work belong in sagas, `Cmd`, command handlers, or
  explicit boundary code.
- **Protocol code returns values.** Command resolution, schema
  generation, MCP dispatch, and JSON-RPC classification return
  structured data unless they are at a transport boundary.
- **Runtime state has a concurrency story.** Shared mutable state in
  `state.py`, `app.py`, `gateway.py`, `_child.py`, registries, or
  observers needs locks, ordering notes, and tests.
- **Public imports stay lazy.** Do not add top-level public imports to
  `src/milo/__init__.py`; route public names through `__getattr__` and
  `__all__`.
- **Sharp edges are bugs.** Silent `except`, unexplained `type: ignore`,
  ambiguous flags, unhelpful errors, and `print()` in library code need
  removal or explicit justification.
- **Templates are strict.** Bundled, example, and scaffold `.kida` files
  must compile under Kida strict undefined with `validate_calls=True`.

## Architecture Boundaries

<!-- markdownlint-disable MD013 -->
| Path | Steward / Contract |
| --- | --- |
| `src/milo/commands.py`, `_command_defs.py`, `groups.py`, `cli.py` | Core command registration, resolution, help, `invoke`, `call`, `call_raw`, and CLI flags. |
| `src/milo/schema.py` | Single JSON Schema source and `Annotated` constraint markers. |
| `src/milo/mcp.py`, `_mcp_router.py`, `_jsonrpc.py`, `_child.py`, `gateway.py`, `registry.py` | MCP wire behavior, JSON-RPC diagnostics, gateway routing, and child process lifecycle. |
| `src/milo/state.py`, `_types.py`, `app.py`, `reducers.py`, `flow.py`, `form.py` | Elm-style runtime, effects, sagas, terminal app lifecycle, and pure reducers. |
| `src/milo/input/` and `src/milo/_compat.py` | Terminal input, raw mode, resize handling, and platform isolation. |
| `src/milo/templates/`, `theme.py`, `help.py`, `_cells.py`, `components_cli.py` | Kida environment, bundled templates, display-cell layout, help rendering, and default terminal UX. |
| `src/milo/_scaffold/`, `src/milo/verify.py` | `milo new`, scaffolded tests, onboarding output, and self-diagnosis. |
| `docs/` | Agent-facing quickstart and testing instructions. |
| `site/content/docs/`, `site/content/releases/`, `site/config/` | Public site, reference docs, release notes, and navigation. |
| `examples/` | Runnable examples users and agents copy. |
| `tests/` and `src/milo/testing/` | Regression proof, testing helpers, snapshots, and contract fixtures. |
| `benchmarks/` | Hot-path performance evidence and baselines. |
| `.github/workflows/`, `Makefile`, `pyproject.toml`, `uv.lock` | CI, release, dependency, package, and task-runner surfaces. |
<!-- markdownlint-enable MD013 -->

## Governance Alignment

- CODEOWNERS is the source of truth when present. This repository
  currently has no `CODEOWNERS`, `.github/CODEOWNERS`, `OWNERS`, or
  `MAINTAINERS`; route human decisions to the maintainer.
- Stewards advise; the implementing agent owns the integrated patch.
- Canonical user-facing knowledge lives in `README.md`, `docs/`, and
  `site/content/docs/`.
- Release and CI behavior is encoded in `.github/workflows/`, `Makefile`,
  `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, and `changelog.d/`.

## Stop And Ask

- New runtime dependency, compiled extension, or optional dependency
  promoted into the default install.
- Public API change: `milo.__all__`, lazy exports, `CLI`, `Group`,
  `@command`, `Context`, schema markers, runtime types, config objects,
  middleware, or plugin hooks.
- Command-dispatch changes in `commands.py`, `_command_defs.py`,
  `groups.py`, `cli.py`, or `_mcp_router.py`.
- MCP protocol surface changes: version, annotations, resources,
  prompts, streaming progress, gateway namespacing, error codes, JSON-RPC
  shape, or child process behavior.
- State runtime changes in `state.py`, `app.py`, terminal cleanup, saga
  cancellation, dispatch locking, listener ordering, or executor sizing.
- New global option, config field, saga effect, `Cmd` variant, scaffold
  shape, verifier check, registry path, or migration.
- Security, auth, subprocess execution, network access, release
  publishing, registry persistence, or child-process lifecycle changes.
- A test disagrees with code, a bug cannot be reproduced, or the fix
  requires dead-code removal or adjacent cleanup to proceed.

## Anti-Patterns

- Adding a second schema source, validation framework, or typed model
  layer instead of improving annotations and `function_to_schema()`.
- Duplicating command dispatch behavior across CLI, programmatic, and MCP
  paths instead of sharing resolution and argument semantics.
- Treating `print()` as harmless in library code; MCP stdout is a JSON-RPC
  transport.
- Catching broad exceptions without reporting them or documenting
  `# silent: <reason>` where teardown or notification semantics require it.
- Hiding type problems with `type: ignore` before narrowing the type or
  improving the API.
- Putting I/O, clocks, sleeps, random generation, subprocess work, or
  mutation in reducers.
- Adding internal defensive validation that duplicates boundary
  validation and obscures the real contract.
- Adding speculative config, future transports, broad abstractions, or
  effects before existing composition fails.
- Adding top-level imports to `milo/__init__.py`.
- Adding Kida templates with undeclared variables, unknown filters,
  unknown globals, missing defaults, or `{% def %}` nested inside blocks.

## Steward System

We read this root constitution plus the closest scoped `AGENTS.md` before
editing. Root carries cross-cutting invariants; scoped files carry local
point of view, contracts, evidence, and review hooks.

Every steward has:

- Point Of View: who or what the domain represents.
- Protect: invariants, contracts, quality bars, and failure modes.
- Contract Checklist: concrete files, tests, docs, examples, and generated
  artifacts to inspect when the domain moves.
- Advocate: investments the domain should push for.
- Own: code, tests, docs, agent artifacts, and governance notes.
- Optional Do Not and Serve Peers sections only when they add information
  a careful reader could not infer from Protect.

Cross-boundary PRs include Steward Notes naming consulted stewards,
accepted findings, deferred findings, risks, proof, collateral, and
follow-up.

### Contract Checklist

- Contract changes identify every surface that should agree: CLI,
  programmatic call, MCP, schema, llms.txt, docs, examples, scaffold,
  tests, benchmarks, and changelog.
- Each accepted finding names required proof and collateral updates, or
  explicitly records `no collateral: <reason>`.
- Cross-surface fixes include a parity matrix in Steward Notes when
  behavior must agree across multiple entrypoints.
- Docs, examples, scaffold, and site pages move in the same PR as
  user-facing behavior unless the synthesis records why they are
  unaffected.
- Public API changes update `src/milo/__init__.py`, typing checks, docs,
  examples, scaffold, and changelog as applicable.

### Steward Signal Format

Use this exact shape for review, bugbash, self-audit, and planning
signals:

```text
Steward:
Area:
Severity: P0/P1/P2/P3
Invariant:
Evidence: <source-file:line> [-> <doc-file:line> for content audit]
User Impact:
Required Fix:
Required Proof:
Collateral:
Confidence:
Verification Status: machine-verified / manual-confirmation-needed / not-machine-verifiable
```

### Convergence Rule

Two or more independent stewards flagging the same factual finding is an
automatic P0 until the implementing agent disproves it with source
evidence. If the finding is disproved, record the verification result in
`STEWARD_AUDIT.md` and do not carry the claim forward.

### Steward Swarms

Trigger phrases:

- `ask stewards`
- `bugbash`
- `review swarm`
- `steward synthesis`
- `audit docs`
- `content audit`
- `accuracy pass`

For implementation swarms, consult affected stewards and synthesize
accepted, merged, rejected, and deferred findings. For roadmap or backlog
work, consult all scoped stewards and return convergence, minority
reports, dependencies, risks, ranked backlog, and not-now items.

Stewards advise only. The implementing agent owns final scope,
integration, and proof.

### Global Sweep

When we accept a P0, grep the entire source, docs, examples, scaffold,
and site tree for the same wrong claim or pattern before closing it.
Record the command or search terms in Steward Notes or
`STEWARD_AUDIT.md`.

## Free-Threading And Concurrency

This concern activates for `state.py`, `app.py`, `_child.py`, `gateway.py`,
`registry.py`, `observability.py`, `dev.py`, pipeline globals, listener
lists, thread pools, timers, and terminal state.

- Shared mutable state needs a named lock, ownership boundary, and
  shutdown/cancellation behavior.
- Store dispatch must remain serialized while listeners avoid reentrant
  deadlock.
- Sagas, `Cmd`, `Race`, `All`, `Take`, `TakeEvery`, `TakeLatest`,
  `Debounce`, and `Timeout` need deterministic cancellation semantics.
- Tests for concurrency-sensitive changes run under `PYTHON_GIL=0`.
- Performance shortcuts cannot rely on the GIL or unsynchronized caches.

Required evidence: stress tests, lock-order notes, cancellation tests,
shutdown tests, or a written `no concurrency impact: <reason>`.

## MCP And Protocol Correctness

This concern activates for commands, groups, schema, llms.txt, MCP,
gateway, registry, child transport, middleware, streaming, and context
output.

- `tools/list` must describe what `tools/call` accepts.
- CLI `invoke`, programmatic `call`/`call_raw`, and MCP `tools/call`
  should agree on command lookup, defaults, Context injection, errors,
  and result serialization.
- JSON-RPC stdout must stay clean; diagnostics go to stderr or structured
  return values.
- MCP errors need machine-readable repair data where Milo owns the error.

Required evidence: parity tests across entrypoints, malformed input
tests, JSON-RPC transport tests, and docs/example updates.

## Schema Truth

This concern activates for `schema.py`, `commands.py`, `groups.py`,
`form.py`, `llms.py`, `mcp.py`, docs, examples, and scaffold.

- `function_to_schema()` is the only command schema source.
- Defaults, optionality, `Literal`, `Enum`, dataclasses, TypedDict,
  containers, `Annotated` constraints, and docstring descriptions must
  produce truthful JSON Schema.
- `Context` and `ctx` are dispatch details, not schema parameters.
- Strict mode and `warn_missing_docs=True` support verifier and agent
  repair loops.

Required evidence: schema tests, llms.txt expectations, MCP tools/list
assertions, and docs/snippet updates when user-facing.

## Terminal Cleanup And Rendering

This concern activates for `app.py`, `input/`, `_compat.py`, templates,
theme, display-cell helpers, help, forms, and examples with TUIs.

- Raw mode, alternate screen, cursor visibility, mouse mode, resize
  monitors, tick threads, and Store shutdown must be restored even when
  render, reducer, input, or teardown code fails.
- Terminal layout uses display-cell width helpers where Unicode or ANSI
  makes `len()` wrong.
- Templates must compile under strict Kida settings and render useful
  output without assuming color.

Required evidence: cleanup tests, input tests, template compile checks,
render tests, snapshots, or manual terminal notes.

## Docs, Examples, And Scaffold Parity

This concern activates for user-visible behavior, CLI flags, public API,
schema, MCP, app lifecycle, templates, scaffold, verifier, and release
notes.

- README, agent docs, site docs, examples, scaffold README, and tests must
  describe the same commands and contracts.
- `milo new` projects should pass their generated tests and `milo verify`.
- Examples are copy paths, not decorative demos.
- Docs snippets that claim execution should be tagged for
  `scripts/check_docs_snippets.py` when practical.

Required evidence: docs-test, example smoke tests, scaffold tests,
README index tests, or a `no docs impact: <reason>` note.

## Performance And Startup Cost

This concern activates for schema inference, command resolution, Store
dispatch, saga execution, rendering, gateway dispatch, child process
routing, template loading, and import paths.

- Do not add startup imports to `milo/__init__.py`.
- Do not trade correctness or lifecycle semantics for cached speed.
- Benchmarks name workload, Python build, GIL state, baseline, and
  whether a speed claim is being made.

Required evidence: focused benchmark, baseline note, or
`no benchmark impact: <reason>`.

## Release And Dependency Surface

This concern activates for `pyproject.toml`, `uv.lock`, `.github/`,
`Makefile`, `CHANGELOG.md`, `changelog.d/`, `site/content/releases/`,
package data, and public version metadata.

- Runtime dependency changes are maintainer-confirmed.
- Source changes that affect users need a towncrier fragment unless the
  PR is explicitly marked otherwise.
- Package data must include bundled templates, scaffold files, and
  `py.typed`.
- Release notes should agree with package metadata and changelog intent.

## Security And Subprocess Boundaries

This concern activates for subprocesses, child MCP servers, registry
paths, config reads/writes, version checks, docs commands, and examples.

- Subprocess calls need explicit lifecycle, timeout, stderr/stdout
  handling, and cleanup behavior.
- Registry and config writes need path clarity and atomicity where
  persistence matters.
- Network or publishing behavior belongs at explicit boundaries.
- User-supplied paths and command examples must avoid hidden private
  machine assumptions.

## Known Regression Patterns

- **Fabricated CLI or config fields.** Shape: docs or examples mention a
  flag, option, or config field that argparse, schema, or config code does
  not expose. Verification: grep `commands.py`, `groups.py`, `config.py`,
  docs snippets, and tests for the exact name.
- **Unverified finding regression.** Shape: a reviewer reports a source
  divergence that a grep would disprove. Verification: every factual
  P0/P1 carries machine-verified, manual-confirmation-needed, or
  not-machine-verifiable status.
- **Narrow-fix regression.** Shape: a P0 is corrected in one page or test
  but survives in sibling docs, examples, scaffold, or site pages.
  Verification: run the Global Sweep before closing the P0.
- **CLI/programmatic/MCP drift.** Shape: `invoke`, `call`, `call_raw`, and
  `tools/call` disagree on defaults, Context injection, errors, or result
  serialization. Evidence: `tests/test_command_contract.py`,
  `tests/test_mcp_handler.py`, and `tests/test_ai_native.py`.
- **Schema requiredness drift.** Shape: agents see schema that differs
  from function signature defaults, bool flags, `Literal`, or docstrings.
  Evidence: `tests/test_schema_v2.py`, `tests/test_lazy.py`, and
  `tests/test_command_contract.py`.
- **Silent exception relapse.** Shape: broad exceptions hide product
  errors without `# silent: <reason>`. Evidence: Ruff `S110` policy and
  existing annotations in `app.py`, `mcp.py`, `gateway.py`, and `_compat.py`.
- **Template strictness drift.** Shape: `.kida` files compile only because
  undefined values or invalid calls are ignored. Verification:
  `uv run python scripts/check_templates.py`.
- **Terminal cleanup regression.** Shape: alternate screen, raw mode,
  cursor, mouse mode, resize monitor, tick thread, or Store shutdown is
  left broken after errors. Evidence: `tests/test_app.py`,
  `tests/test_input.py`, and `tests/test_compat.py`.
- **Verifier/scaffold drift.** Shape: generated projects or examples no
  longer pass `milo verify`. Evidence: `tests/test_scaffold.py` and
  `tests/test_verify.py`.
- **Docs-example index drift.** Shape: an example exists but README or
  examples README no longer points to it. Evidence:
  `tests/docs/test_readme_example_index.py`.

## Done Criteria

- `make lint`, `make ty`, and `make test-cov` are clean unless the PR
  explicitly documents why a narrower check was chosen.
- Run `uv run python scripts/check_templates.py` when touching
  `src/milo/templates/`, `examples/*/templates/`, scaffold templates, or
  Kida-facing docs/examples.
- Run `make docs-test` when touching docs snippets, examples,
  scaffold README, templates, or site docs that claim runnable behavior.
- Coverage stays at or above the branch-aware 80% floor.
- Tests exercise the interesting path: schema, CLI dispatch,
  programmatic call, MCP dispatch, malformed input, failure diagnostics,
  concurrency, terminal cleanup, template compilation, scaffold, verifier,
  or docs drift as relevant.
- Every accepted steward finding has one of: test updated,
  docs/example/scaffold updated, benchmark note added, changelog fragment
  added, or `no collateral: <reason>` in Steward Notes.
- Contract-affecting PRs include a parity matrix covering the surfaces
  touched, such as CLI invoke, CLI call, MCP, schema, llms.txt, docs,
  examples, scaffold, verifier, and tests.
- Hot-path changes include benchmark notes for schema inference, command
  resolution, Store dispatch, saga execution, rendering, gateway dispatch,
  startup imports, or child process routing.
- Free-threading-sensitive changes include notes on shared mutable state,
  lock ordering, reentrant dispatch, cancellation, executor ordering, or
  why none apply.
- Public API changes include a towncrier fragment, migration notes if
  breaking, and `__all__` updates when needed.
- Error messages tell the reader what to do next.
