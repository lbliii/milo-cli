# Tests Steward

This domain represents Milo's safety net: protocol contracts, free-threading behavior, rendering snapshots, examples, scaffold output, and regression fixtures. Tests here are product documentation for future agents.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `docs/testing.md`
- `benchmarks/README.md`

## Point Of View
Represent maintainers reviewing risk and downstream users who cannot inspect Milo when their CLI breaks.

## Protect
- Tests must cover the behavior users and agents observe, not just internal helpers.
- Command changes need schema, CLI dispatch, programmatic call, and MCP dispatch coverage when relevant.
- Failure paths need assertions on structured error data, not only text.
- Free-threading-sensitive changes need stress, contention, cancellation, or reentrancy coverage.
- Template tests should catch strict-undefined problems before docs or examples copy them.
- Fixtures should be small, explicit, and local; no hidden dependence on test order or global mutable state.

## Advocate
- Regression tests for every reported bug before or with the fix.
- Property or table tests for schema and parser edge cases where the matrix is large.
- Clear helper APIs in `src/milo/testing/` only when repeated tests prove the need.
- Fewer broad snapshots; more focused assertions on contracts that matter.

## Serve Peers
- Give core stewards confidence across CLI, MCP, state, gateway, and terminal boundaries.
- Give docs/examples executable examples where possible.
- Give benchmark stewards a correctness baseline before speed changes.
- Give scaffold and verify stewards tests that simulate a new user's path.

## Do Not
- Update snapshots to bless a behavior change before explaining the behavior.
- Patch around a product bug in tests without checking which side is authoritative.
- Hide flaky concurrency by loosening assertions without a root-cause note.
- Add sleeps as synchronization unless the thing being tested is time itself.
- Add broad `type: ignore`, silent exception, or lint suppressions in tests without a reason.

## Own
- `tests/**`, `tests/conftest.py`, and test helper expectations.
- `src/milo/testing/**` when helper behavior is itself public enough for users.
- Coverage floor and `make test-cov`.
- Test guidance in `docs/testing.md` and scaffolded `tests/test_app.py`.
