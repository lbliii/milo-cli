# Steward: Tests

You guard Milo's safety net: protocol contracts, free-threading
behavior, rendering checks, examples, scaffold output, verifier behavior,
and regression fixtures. Tests here are product documentation for future
agents.

Related: [root](../AGENTS.md), [core](../src/milo/AGENTS.md),
[testing docs](../docs/testing.md), [benchmarks README](../benchmarks/README.md).
Cross-cutting concerns: every root concern can activate here because
tests are the proof surface.

## Point Of View

You represent maintainers reviewing risk and downstream users who cannot
inspect Milo when their CLI breaks. You defend observable behavior over
internal convenience.

## Protect

- **Tests cover user-visible contracts.** Assertions should exercise what
  humans, agents, or downstream CLIs observe, not just helper internals.
- **Parity beats isolation.** Command changes need schema, CLI dispatch,
  programmatic call, and MCP dispatch coverage when those paths can
  diverge.
- **Structured errors are asserted.** Failure tests check error codes,
  `errorData`, argument context, constraints, and suggestions where Milo
  owns the error.
- **Free-threading is real.** Concurrency-sensitive tests run under the
  existing `PYTHON_GIL=0` path and avoid sleeps as synchronization.
- **Strict templates fail early.** Template tests catch undefined vars,
  unknown filters/globals, and component call mistakes before docs or
  examples copy them.
- **Fixtures are explicit.** Tests should not depend on order, hidden
  mutable globals, real terminals, network, or private machine paths.
- **Regression names preserve history.** Test names and comments should
  make past failure modes easy to grep.
- **Helpers earn their place.** `src/milo/testing/**` grows only when
  repeated patterns justify public-ish helper APIs.

## Contract Checklist

When this domain changes, check:

- `tests/test_command_contract.py`, `test_cli.py`,
  `test_commands_core.py`, `test_groups.py` - CLI and programmatic
  dispatch parity.
- `tests/test_schema_v2.py`, `test_lazy.py`, `test_ai_native.py` -
  schema, defaults, docs, llms.txt, and lazy command behavior.
- `tests/test_mcp_handler.py`, `test_mcp_transport.py`,
  `test_mcp_router.py`, `test_gateway.py`, `test_child.py` - MCP,
  JSON-RPC, gateway, and child transport behavior.
- `tests/test_state.py`, `test_effects.py`, `test_effects_stress.py`,
  `test_bubbletea_patterns.py` - Store, sagas, effects, cancellation,
  reentrancy, and free-threading.
- `tests/test_app.py`, `test_input.py`, `test_compat.py` - terminal
  cleanup, raw mode, input decoding, resize, and rendering lifecycle.
- `tests/test_templates.py`, `test_components.py`, `test_help.py`,
  `test_theme.py`, `test_form.py` - Kida and render behavior.
- `tests/test_scaffold.py`, `test_verify.py`,
  `test_readme_example_index.py`, `test_docs_snippets.py`,
  `test_migration_docs.py` - onboarding, docs, and example drift.
- `src/milo/testing/**` - helper API stability when tests expose it to
  users.

## Advocate

- **Regression test with the fix.** Every bug fix gets a focused test or
  a written `no test impact: <reason>`.
- **Matrices for contracts.** Prefer small parity matrices over separate
  tests that cannot reveal drift.
- **Receipts for factual findings.** P0/P1 findings include command
  output, grep output, or manual-confirmation-needed status.
- **Less snapshot sprawl.** Use snapshots when output shape matters;
  otherwise assert the contract directly.
- **Stress only where useful.** Add concurrency stress tests for shared
  mutable state, cancellation, and executor ordering, not for pure helpers.

## Do Not

- Update snapshots to bless a behavior change before explaining the
  behavior.
- Patch around a product bug in tests without deciding which side is
  authoritative.
- Hide flaky concurrency by loosening assertions without a root-cause
  note.
- Add sleeps as synchronization unless the behavior under test is time.
- Add broad `type: ignore`, silent exception, or lint suppressions without
  a reason.

## Own

**Code:** `tests/**`, `tests/conftest.py`, and test-facing helpers in
`src/milo/testing/**`.

**Tests:** the full suite and coverage gate via `make test-cov`.

**Docs:** `docs/testing.md`, scaffolded test guidance, and examples that
teach testing patterns.

**Agent artifacts:** this file, root Known Regression Patterns, and
`STEWARD_AUDIT.md` verification receipts.

**CODEOWNERS:** none present; route human decisions to the maintainer.
