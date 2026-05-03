# Milo Agent Constitution

## North Star
Milo exists to prove that one typed Python function can safely become a human CLI command, an MCP tool with a truthful JSON Schema, and an llms.txt entry. Protect the shared contract for humans, agents, and downstream CLIs: pure Python, auditable types, deterministic state, and free-threading correctness.

## Non-Negotiables
- Pure Python only. The one runtime dependency is `kida-templates`; no `click`, `rich`, Pydantic, attrs, C extensions, or compiled hot-path shortcuts.
- Types are the contract. `function_to_schema` derives JSON Schema from annotations, `Annotated[...]` constraints, docstrings, and defaults.
- Reducers are pure and deterministic. I/O, logging, sleeps, and clocks belong in sagas, `Cmd`, command handlers, or explicit boundary code.
- Runtime configuration is frozen where modeled that way. Registration happens at import; runtime change is a lifecycle event, not mutation by convenience.
- Protocol code is sans-I/O unless it is the transport boundary. Command resolution, schema generation, and MCP dispatch return values.
- Free-threading is first-class. Assume Python 3.14t with `PYTHON_GIL=0`; shared mutable state needs a concurrency story.
- Keep imports lazy. Do not add top-level imports to `milo/__init__.py`; public names route through `__getattr__`.
- Sharp edges are bugs: silent `except`, `type: ignore`, ambiguous flags, unhelpful errors, and `print()` in library code all need justification or removal.

## Architecture Boundaries
- `CLI.run()`, `CLI.invoke()`, `CLI.call()`/`call_raw()`, and MCP `tools/call` must agree on command resolution and argument behavior.
- `src/milo/schema.py` is the single schema source. Do not introduce parallel schema definitions or model classes that shadow signatures.
- `src/milo/mcp.py`, `src/milo/_mcp_router.py`, `src/milo/gateway.py`, and `src/milo/_jsonrpc.py` own MCP wire behavior and JSON-RPC diagnostics.
- `src/milo/state.py`, `src/milo/app.py`, reducers, effects, and `Cmd` own the Elm-style runtime and terminal app lifecycle.
- `src/milo/templates/`, example templates, and scaffold templates must compile under Kida strict undefined and `validate_calls=True`.
- `src/milo/_scaffold/`, `src/milo/verify.py`, docs, and examples are the onboarding contract for agents and new CLI authors.

## Stakes
- Schema drift makes agents send valid-looking JSON that the function rejects or silently misinterprets.
- MCP regressions break `tools/list`, `tools/call`, resources, prompts, progress, gateway routing, and agent repair loops.
- Command dispatch drift makes human CLIs work while programmatic or MCP calls fail, or the reverse.
- Free-threaded races in Store dispatch, saga execution, tick threads, child processes, or terminal state make 3.14t look flaky downstream.
- Terminal cleanup bugs leave alternate screen, raw mode, cursor visibility, mouse mode, or window title broken after exit.
- Scaffold, docs, examples, and `milo verify` regressions teach agents to create broken CLIs with confidence.
- Startup-cost regressions punish every downstream CLI invocation.

## Stop And Ask
- New runtime dependency, compiled extension, or optional dependency promoted into the default install.
- Public API change: `milo.__all__`, `CLI`, `@command`, `Context`, schema markers, saga effects, `Store`, `App`, pipeline types, plugin hooks.
- Command-dispatch changes in `commands.py`, `_command_defs.py`, `groups.py`, `cli.py`, or `_mcp_router.py`.
- MCP protocol surface changes: annotations, resources, prompts, streaming progress, gateway namespacing, error codes, JSON-RPC shape.
- State runtime changes in `state.py`, `app.py`, terminal cleanup, saga cancellation, dispatch locking, or executor ordering.
- New global option, config field, saga effect, `Cmd` variant, scaffold shape, or irreversible migration.
- Security/auth behavior, subprocess execution, registry paths, or child-process lifecycle changes.
- Test disagrees with code, a bug cannot be reproduced, or a change needs dead-code removal or adjacent cleanup to proceed.

## Anti-Patterns
- Adding a second schema source, validation framework, or typed model layer instead of improving annotations and `function_to_schema`.
- Catching broad exceptions without either reporting them or documenting a `# silent: <reason>` suppression in the lint configuration.
- `# type: ignore` as the first move. Narrow the type or fix the code.
- Reducers that do I/O, logging, `time.time()`, random generation, sleeps, subprocess work, or mutation outside returned state.
- Internal defensive validation that duplicates boundary validation and obscures the actual contract.
- Speculative config, future transports, broad abstractions, or new effects before existing composition fails.
- Top-level imports in `milo/__init__.py`.
- `print()` in library code; use context output, structured return values, stderr at transport boundaries, or exceptions.
- Kida templates with undeclared variables, missing defaults, unknown filters/globals, or `{% def %}` nested inside blocks.

## Steward System
Read this root constitution plus the closest scoped `AGENTS.md` before editing. Root is the constitution and routing guide; scoped files are domain stewards. Scoped stewards own local invariants, refusal patterns, docs, tests, examples, fixtures, and checks. Cross-boundary work needs `Steward Notes` in the PR description naming consulted stewards, decisions, risks, and follow-up.

Every steward uses this operating model:
- Point of View: who or what the domain represents.
- Protect: invariants, contracts, quality bars, and failure modes.
- Contract Checklist: concrete surfaces to inspect when the domain changes, including tests, docs, examples, and generated artifacts that should move with code.
- Advocate: features, fixes, and investments the domain should push for.
- Serve Peers: upstream and downstream domains that need clearer contracts, diagnostics, docs, tests, or ergonomics.
- Do Not: local anti-patterns.
- Own: tests, docs, examples, fixtures, and maintenance checks.

## Contract Checklist
- Contract changes identify every surface that should agree: CLI, programmatic call, MCP, schema, llms.txt, docs, examples, scaffold, tests, benchmarks, and changelog.
- Each accepted finding names required proof and collateral updates, or explicitly records `no collateral: <reason>`.
- Cross-surface fixes include a parity matrix in Steward Notes when behavior must agree across multiple entrypoints.
- Docs/examples/scaffold move in the same PR as user-facing behavior unless the synthesis records why they are unaffected.

## Steward Signal Format
Steward findings should be contract-oriented, evidence-backed, and collateral-aware. Prefer this shape for review, bugbash, and planning signals:
- Steward: domain name.
- Area: files or feature surface.
- Severity: P0/P1/P2/P3.
- Invariant: the contract being protected.
- Evidence: observed code, test, doc, or behavior proving the concern.
- User Impact: how humans, agents, or downstream CLIs experience the bug or drift.
- Required Fix: the smallest behavior or docs change that restores the invariant.
- Required Proof: tests, docs checks, snippets, benchmarks, or manual checks that must move with the fix.
- Collateral: docs, examples, scaffold, llms.txt, changelog, migration notes, or benchmarks that also need updates; write "none: <reason>" when not applicable.
- Confidence: high/medium/low.

## Steward Swarms
When the user asks for `ask stewards`, a bugbash, review swarm, or steward synthesis, and delegation is available, spawn independent steward agents for affected domains. Each steward agent reads this file plus its closest scoped `AGENTS.md`, advocates only for that domain's interests, and returns findings in the Steward Signal Format.

The implementing agent owns synthesis and final decisions. It accepts, merges, rejects, or defers findings; prevents unrelated scope expansion; records not-now items; and keeps the final patch coherent. Stewards advise and create useful tension, but they do not own the integrated implementation.

Use independent stewards for independent questions. Do not delegate the immediate blocker on the critical path if the implementing agent must resolve it before any other work can proceed.

## Steward Feedback Loop
- Steward miss: when a bug escapes an applicable steward, update the steward checklist, a regression test, a docs/snippet check, a routing rule, or record why the miss should not become policy.
- Steward overreach: when a steward repeatedly pulls unrelated work into PRs, narrow the checklist, split the steward, or move the concern to not-now/follow-up.
- Repeated high-quality findings should become checklist items; repeated noisy findings should be pruned or clarified.
- Steward guidance should evolve from evidence: escaped bugs, late collateral updates, CI/review misses, and recurring review comments.

## When To Consult
- Proactively consult stewards for cross-boundary, public-facing, hard-to-reverse, performance-sensitive, concurrency-sensitive, security-sensitive, or contract-affecting work.
- Use the nearest steward for local work.
- Use multiple stewards when ownership lines cross.
- Parallelize steward consultation only when questions are independent.
- Keep final synthesis and implementation accountability with the implementing agent.
- Keep PR scope bounded by accepted findings and their required proof/collateral. Defer unrelated steward suggestions to follow-up.

## Ask Stewards
Trigger phrase: `ask stewards`.

For implementation work, consult affected stewards and return the synthesis before or during the change. For backlog, roadmap, or prioritization work, consult all scoped stewards and produce a rollup with raw steward signals, confidence, dependencies, risks, convergence, minority reports, ranked backlog, and not-now items.

For implementation swarms and bugbashes, the synthesis must include:
- Accepted findings, merged duplicates, and rejected/deferred findings with reasons.
- Cross-cutting invariants and ownership boundaries.
- Required proof and collateral updates for each accepted finding.
- Minority reports or steward disagreements.
- A contract parity matrix when behavior spans surfaces such as CLI, programmatic call, MCP, schema, docs, examples, or scaffold.
- Final implementation accountability: stewards advise; the implementing agent owns the integrated fix.

## Extension Routing
- Public CLI commands, groups, global options, resources, prompts: `src/milo/commands.py`, `_command_defs.py`, `groups.py`, `mcp.py`, and `llms.py`.
- MCP transport and gateway: `src/milo/mcp.py`, `_jsonrpc.py`, `_mcp_router.py`, `_child.py`, `gateway.py`, and `registry.py`.
- Schema constraints: `src/milo/schema.py`; public exports route through `src/milo/__init__.py`.
- Interactive apps and state: `src/milo/app.py`, `state.py`, `reducers.py`, `flow.py`, `form.py`, and effect types in `_types.py`.
- Templates and default terminal UX: `src/milo/templates/`, `src/milo/theme.py`, `src/milo/help.py`, and `examples/*/templates/`.
- Scaffolding and verification: `src/milo/_scaffold/`, `src/milo/verify.py`, `docs/agent-quickstart.md`, and `docs/testing.md`.

## Done Criteria
- `make lint`, `make ty`, and `make test-cov` clean unless the PR explicitly documents why a narrower check was chosen.
- Run `uv run python scripts/check_templates.py` when touching `src/milo/templates/`, `examples/*/templates/`, scaffold templates, or Kida-facing docs/examples.
- Coverage stays at or above the branch-aware 80% floor.
- Tests exercise the interesting path: schema, CLI dispatch, programmatic call, MCP dispatch, malformed input, failure diagnostics, concurrency, terminal cleanup, or template compilation as relevant.
- Every accepted steward finding has one of: test updated, docs/example/scaffold updated, benchmark note added, or `no collateral: <reason>` in Steward Notes.
- Contract-affecting PRs include a short parity matrix covering the surfaces touched, such as CLI invoke, CLI call, MCP, schema, docs, examples, scaffold, and tests.
- Hot-path changes in schema inference, command resolution, Store dispatch, saga execution, rendering, gateway dispatch, or child process routing include benchmark notes.
- Free-threading-sensitive changes include notes on shared mutable state, lock ordering, reentrant dispatch, cancellation, executor ordering, or why none apply.
- Public API changes include a towncrier fragment in `changelog.d/`, migration notes if breaking, and `__all__` updates when needed.
- Error messages tell the reader what to do next.

## Review Notes
Keep PRs to one concern unless a mechanical rename is the concern. Follow existing commit style (`fix:`, `refactor:`, `deps:`, `release:` or a plain descriptive imperative). The diff should show what changed; the PR description should explain why. Flag surprises: weird tests, unused public names, unexpected suppressions, dead code, benchmark gaps, free-threading assumptions, and any steward disagreement.
