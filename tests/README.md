# Test Layout

Pytest collects the entire `tests/` tree. New tests go where their ownership
and failure mode are clearest:

- `unit/` — fast, deterministic properties and focused pure-function proof;
- `integration/` — subprocess, cross-surface, or external-package receipts;
- `docs/` — documentation structure, snippets, links, and claims contracts;
- `downstream/` — versioned fixture applications consumed by integration
  runners; and
- root `test_*.py` modules — established component suites, kept stable until a
  coherent domain is moved as one reviewed change.

Do not move a file merely to reduce a count. Update path-owning docs, scripts,
Make targets, and root calculations with every structural move. Unit tests
must not use network or subprocesses; integration tests own explicit timeouts
and isolated state. Every lane runs under the normal coverage gate.
