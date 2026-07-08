# Contributing to Milo

Milo turns one typed Python function into a human CLI command, an MCP tool,
and an llms.txt entry. Contributions must preserve that shared contract and
the pure-Python, Python 3.14+, free-threading runtime.

## Before you start

1. Read [`AGENTS.md`](AGENTS.md) and the closest scoped `AGENTS.md` for every
   area you will edit.
2. Search [open issues](https://github.com/lbliii/milo-cli/issues) and discuss
   public API, protocol, runtime-state, dependency, security, or release
   changes with the maintainer before implementation.
3. Keep changes framework-neutral. Downstream applications may provide the
   reproducer, but Milo core does not gain downstream-specific branches.

## Development setup

Install [uv](https://docs.astral.sh/uv/), Git, and a Python 3.14t interpreter,
then run:

```bash
uv python install 3.14t
make setup
make install
```

The runtime has one dependency, `kida-templates`. Do not add a runtime or
compiled dependency without maintainer approval.

## Test in layers

Start with the narrowest test that proves the behavior, then run the
release-class gates before opening a pull request:

```bash
make lint
make ty
make test-cov
```

When docs, examples, templates, or scaffold instructions change, also run:

```bash
make docs-test
```

Template changes additionally require
`uv run python scripts/check_templates.py`. The Waypoint integration showcase
uses `make showcase-test`; the released Chirp downstream receipt uses
`make chirp-canary`.

CI runs the tests on ordinary Python 3.14 with the GIL enabled and on Python
3.14t with `PYTHON_GIL=0`. Concurrency-sensitive changes need focused stress,
ordering, cancellation, and shutdown proof, not just a passing default run.

The test layout is documented in [`tests/README.md`](tests/README.md): unit
properties, integration receipts, docs contracts, downstream fixtures, and
the existing component suites each have distinct ownership.

## Keep every surface truthful

For command, schema, or MCP changes, review all affected surfaces:

- CLI parsing, help, stdout/stderr, and exit codes;
- `invoke`, `call`, and `call_raw`;
- JSON Schema requiredness, defaults, constraints, and descriptions;
- MCP `tools/list`, `tools/call`, resources, and structured errors;
- llms.txt discovery;
- docs, examples, scaffold output, verifier checks, and tests; and
- startup cost and free-threading behavior where relevant.

Use public APIs in examples and tests. Library code returns values instead of
printing, reducers remain pure, templates compile under strict Kida settings,
and public imports remain lazy.

## Changelog and pull request

User-visible work needs one towncrier fragment under `changelog.d/`, named for
the issue and change category, for example `123.fixed.md`. Keep the fragment
short and user-facing.

A pull request should include:

- the issue it closes or advances;
- outcome and verification commands;
- Steward Notes for cross-boundary changes;
- a parity matrix when behavior spans CLI/programmatic/MCP/schema surfaces;
- concurrency and benchmark impact notes when those concerns activate; and
- collateral updates or an explicit reason they are unaffected.

Do not commit generated `site/public`, caches, coverage output, virtual
environments, credentials, tokens, or machine-specific paths.

## Security reports

Do not open a public issue for a suspected vulnerability. Follow
[`SECURITY.md`](SECURITY.md) so the maintainer can investigate privately.
