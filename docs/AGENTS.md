# Agent Docs Steward

This domain represents the short, agent-facing docs outside the public website. These docs are operational instructions for creating, testing, and diagnosing Milo CLIs.

Related docs:
- root `AGENTS.md`
- `README.md`
- `site/content/docs/about/architecture.md`

## Point Of View
Represent coding agents and maintainers who need concise, executable instructions rather than a full reference manual.

## Protect
- Commands in docs must match current CLI flags, scaffold output, and public APIs.
- `docs/agent-quickstart.md` must get from function to working MCP tool without hidden steps.
- `docs/testing.md` must preserve the schema, direct dispatch, and MCP dispatch test layers.
- Error examples must preserve structured `errorData` fields agents can parse.
- Docs should distinguish warnings from failures for `milo verify`.

## Contract Checklist
- Public CLI, MCP, schema, scaffold, or verify changes update `docs/agent-quickstart.md` or `docs/testing.md`, or the PR explains why these docs are unaffected.
- New or changed command snippets use current flags, current import paths, and a runnable project shape.
- Structured error behavior changes include an agent-parseable example or a `no docs impact` note.
- Tagged code fences are covered by `uv run python scripts/check_docs_snippets.py`; untagged snippets must be intentionally illustrative.
- Cross-links to README, site docs, examples, scaffold, and tests remain pointed at existing files or pages.

## Advocate
- Troubleshooting tables that map symptoms to fixes agents can execute.
- Links from short docs to deeper site reference when detail would bloat the quick path.
- Updating docs in the same PR as public behavior, scaffold, or verify changes.

## Serve Peers
- Give scaffold, examples, and tests a consistent onboarding story.
- Give core API changes a place for migration notes before release docs are rebuilt.
- Give site docs concise source material for longer explanations.

## Do Not
- Document behavior that is not covered by tests or examples.
- Use command snippets that require private paths, interactive-only setup, or unstated services.
- Hide protocol caveats like stdout corruption for MCP tools.
- Turn quickstart docs into exhaustive architecture references.

## Own
- `docs/agent-quickstart.md` and `docs/testing.md`.
- Cross-links from `README.md` into these docs.
- Consistency with scaffold output, `milo verify`, and example tests.
