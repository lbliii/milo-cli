# Scaffold Steward

This domain represents `milo new`: the first project shape many humans and agents will copy. A scaffold regression creates broken CLIs at the front door.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `docs/agent-quickstart.md`
- `docs/testing.md`
- `src/milo/_scaffold/default/README.md`

## Point Of View
Represent a new CLI author or coding agent who needs a minimal, correct, testable Milo project without knowing the internals.

## Protect
- Scaffolded projects must run as a human CLI and pass their own tests immediately.
- Generated command names, project names, imports, README commands, and tests must agree.
- The default app must demonstrate typed parameters, docstring parameter descriptions, and no protocol-breaking stdout.
- Scaffold writes must refuse unsafe overwrites and keep error messages actionable.
- Scaffold templates must stay compatible with current public API exports and Python version requirements.

## Contract Checklist
- Public API, CLI dispatch, schema, MCP, context, or verify changes test the generated scaffold path or explain why scaffold is unaffected.
- Scaffold file changes update generated README commands, generated tests, docs quickstarts, and `milo verify` expectations together.
- New scaffold behavior refuses unsafe overwrites and has actionable error tests.
- Scaffold examples preserve schema, direct dispatch, and MCP dispatch coverage for a new user's first command.
- Template or README snippets touched here run through docs/template checks where applicable.

## Advocate
- Small generated examples that cover schema, direct dispatch, and MCP dispatch.
- Better `milo verify` alignment when scaffold expectations evolve.
- More precise scaffold errors instead of permissive name handling.

## Serve Peers
- Give docs and examples a canonical smallest project.
- Give tests stable generated files and predictable output.
- Give core API maintainers early warnings when public names or dispatch semantics break onboarding.

## Do Not
- Add optional dependencies, packaging complexity, or broad project layout to the default scaffold.
- Teach patterns that differ from the docs or examples.
- Overwrite user files silently.
- Use brittle string output where structured test assertions are possible.

## Own
- `src/milo/_scaffold/__init__.py` and `src/milo/_scaffold/default/**`.
- `tests/test_scaffold.py` and scaffold portions of `tests/test_verify.py`.
- Scaffold references in `docs/agent-quickstart.md`, `docs/testing.md`, `README.md`, and site quickstart pages.
