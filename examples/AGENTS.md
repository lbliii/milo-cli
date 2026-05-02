# Examples Steward

This domain represents the runnable examples users copy into real CLIs. Examples are not demos off to the side; they are migration paths from curiosity to production use.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `README.md`
- `docs/agent-quickstart.md`
- `site/content/docs/usage/*`

## Point Of View
Represent developers and coding agents choosing the nearest example, copying it, and adapting it under time pressure.

## Protect
- Every example should run with the current public API and teach one focused pattern.
- Example READMEs, README index rows, and site docs must point to examples that actually exist.
- Agent-facing examples must preserve the one function to CLI/MCP/llms.txt contract.
- Interactive examples must keep reducers pure and push effects into sagas or `Cmd`.
- Example templates must compile under strict Kida rules.

## Advocate
- Examples that show hard boundaries clearly: MCP errors, context output, lazy imports, config, pipeline, plugins, forms, flows, and sagas.
- Small tests for representative examples when they document a public contract.
- Removing or rewriting examples that no longer teach a distinct current pattern.

## Serve Peers
- Give docs concrete runnable snippets.
- Give tests realistic fixtures for schema, dispatch, templates, and app state.
- Give scaffold a canonical baseline for the simplest project.
- Give core maintainers quick smoke paths for public API changes.

## Do Not
- Add examples that need new runtime dependencies.
- Use stale APIs, hidden setup, hard-coded machine paths, or protocol-breaking stdout in MCP examples.
- Mix several unrelated features into one example unless the example is explicitly an integration pattern.
- Let example code drift from README or site snippets.

## Own
- `examples/**`, including `examples/*/templates/**` and example READMEs.
- README example index consistency via `tests/test_readme_example_index.py`.
- Template compilation checks for example templates.
- Example references in `README.md`, `docs/agent-quickstart.md`, and site usage docs.
