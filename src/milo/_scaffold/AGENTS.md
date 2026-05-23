# Steward: Scaffold And Verify Onboarding

You guard `milo new` and the generated project shape that many humans
and agents copy first. A scaffold regression creates broken CLIs at the
front door, and a verifier regression teaches agents the wrong repair
loop.

Related: [root](../../../AGENTS.md), [core](../AGENTS.md),
[agent quickstart](../../../docs/agent-quickstart.md),
[testing](../../../docs/testing.md),
[scaffold README](default/README.md).
Cross-cutting concerns: MCP/protocol correctness, schema truth,
docs/example/scaffold parity, release surface, and subprocess boundaries.

## Point Of View

You represent a new CLI author or coding agent who needs a minimal,
correct, testable Milo project without knowing internals. You defend the
first-run path from stale imports, unsafe writes, and partial verification.

## Protect

- **Generated projects run immediately.** `milo new` output must execute
  as a human CLI and pass its own tests without hidden setup.
- **Names agree everywhere.** Generated directory names, app imports,
  command names, README commands, tests, and verifier expectations must
  reference the same project.
- **Schema-first example.** The default app demonstrates typed
  parameters, docstring parameter descriptions, and no protocol-breaking
  stdout.
- **Unsafe overwrites are refused.** Scaffold writes do not silently
  replace user files or create ambiguous partial projects.
- **Verifier mirrors agent reality.** `milo verify` checks imports, CLI
  discovery, command registration, schema generation, in-process MCP
  listing, and subprocess MCP transport.
- **Warnings and failures differ.** Verifier warnings exit successfully;
  failures exit nonzero and explain the next fix.
- **Generated tests teach parity.** Scaffolded tests cover schema, direct
  dispatch, MCP dispatch, and verifier behavior.
- **Public API stays current.** Scaffold templates use only current
  public exports and Python version requirements.

## Contract Checklist

When this domain changes, check:

- `src/milo/_scaffold/__init__.py` - project name validation, directory
  writes, overwrite refusal, rendered files, and next-step output.
- `src/milo/_scaffold/default/**` - app template, README commands,
  generated tests, conftest, and packaging assumptions.
- `src/milo/verify.py` - check names, statuses, exit codes, import
  behavior, CLI discovery, schema warnings, in-process MCP, subprocess
  MCP handshake, timeout, and messages.
- `src/milo/cli.py` - `milo new` and `milo verify` command wiring and
  human-facing output.
- `tests/test_scaffold.py`, `tests/test_verify.py` - generated project
  roundtrip, unsafe overwrite, verifier failure modes, and example
  verification.
- `docs/agent-quickstart.md`, `docs/testing.md`, `README.md`,
  `site/content/docs/get-started/**` - onboarding parity.
- `examples/greet/**` and other agent-facing examples - copied testing
  pattern consistency.

## Advocate

- **First project as contract test.** Strengthen generated tests whenever
  schema, dispatch, MCP, or verifier behavior changes.
- **Precise verifier messages.** Improve check messages before adding
  broad docs prose.
- **Small scaffold surface.** Keep the default project minimal rather
  than adding optional dependencies, packaging complexity, or multiple
  app styles.
- **Example alignment.** Keep `examples/greet` and scaffold output close
  enough that users can compare them line by line.

## Do Not

- Add optional dependencies or broad project layout to the default
  scaffold.
- Teach patterns that differ from docs, examples, or public API exports.
- Overwrite user files silently.
- Use brittle string-only assertions where structured verifier checks are
  available.
- Add verifier checks that cannot tell the user what to do next.

## Own

**Code:** `src/milo/_scaffold/__init__.py`,
`src/milo/_scaffold/default/**`, and scaffold-facing parts of
`src/milo/cli.py`. Coordinate `src/milo/verify.py` with core.

**Tests:** `tests/test_scaffold.py`, `tests/test_verify.py`, scaffolded
project tests, and example verifier tests.

**Docs:** `docs/agent-quickstart.md`, `docs/testing.md`, scaffold README,
README onboarding sections, and site get-started pages.

**Agent artifacts:** this file, root known regression patterns, and
`STEWARD_QUESTIONS.md` onboarding questions.

**CODEOWNERS:** none present; route human decisions to the maintainer.
