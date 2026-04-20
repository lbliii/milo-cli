# AGENTS.md

milo-cli is infrastructure. One decorator becomes an argparse CLI, an MCP tool, and an llms.txt entry — so every bug you introduce propagates into the CLIs built on top of it, and from there into the AI agents and humans calling those CLIs. The people downstream can't see milo, can't audit it, and can't defend themselves from what it does. Treat the rules below as safety rules, not style rules.

---

## North star

**One function, three protocols — humans and AI agents both native.** milo-cli exists so a single typed Python function is simultaneously a human CLI command, an MCP tool with a real JSON Schema, and a discoverable llms.txt entry. Every decision routes back to that: types that drive schemas, pure Python you can audit, free-threading correctness under true parallelism. If a change doesn't serve that goal, it isn't worth shipping.

---

## Design philosophy

- **Pure Python is a constraint.** One runtime dep (`kida-templates`). No C extensions, no `click`, no `rich`. If the dispatch path needs to get faster, the answer is better Python. Compiling something kills the "audit-everything" promise.
- **Types are the contract.** `function_to_schema` infers JSON Schema from annotations + `Annotated[...]` constraints. No parallel schema definitions, no Pydantic models shadowing the signature. If the type can't express it, fix the type.
- **Elm architecture means pure reducers.** `Store`, sagas, and `App` assume reducers are side-effect-free and deterministic. Effects go through saga middleware (`Call`, `Put`, `Fork`, ...) or `Cmd`. A reducer that does I/O is a bug, not a shortcut.
- **Frozen config > locks.** `CLI`, `CommandDef`, and the config dataclasses are `frozen=True, slots=True`. Registration happens at import; runtime changes are lifecycle events, not mutations.
- **Sans-I/O protocols.** MCP dispatch, schema generation, and command resolution don't touch sockets or stdout. They return values. Load-bearing for testability and for the stdin/stdout JSON-RPC transport.
- **Free-threading is first-class.** CI runs on 3.14t with `PYTHON_GIL=0` and asserts `sys._is_gil_enabled() is False`. Shared-mutable state is reviewed on that assumption. We are the ecosystem's canary for free-threaded CLIs.
- **Lazy imports everywhere.** `milo/__init__.py` uses `__getattr__`; unused modules never load. Don't add top-level imports in `__init__.py` — it pays a startup cost on every CLI invocation.
- **Sharp edges are bugs.** Silent `except`, `type: ignore`, ambiguous flags, unhelpful errors — not taste, bugs. S110 is re-enabled in CI and the last four PRs have all been sharp-edge hunts. Target for `type: ignore` is zero.

---

## Stakes

When you change something in milo-cli, the blast radius is:

- **Schema generation bugs** → An AI agent sees a tool signature that doesn't match reality. It sends valid-looking JSON that the function rejects, or worse, accepts silently. Harm: agent workflows abort mid-task, or structured output gets corrupted in ways the agent has no way to detect.
- **MCP dispatch bugs** → `tools/list`, `tools/call`, `resources/read`, streaming progress. A subtly broken response breaks every Claude/DORI/Pounce client calling a milo CLI. Debuggable only with JSON-RPC trace logs.
- **Free-threaded races** → Store dispatch, saga executor, tick threads, SIGWINCH — all can run truly in parallel on 3.14t. No GIL safety net. A race we ship normalizes "free-threading is flaky" for every Python project watching us.
- **Command dispatch bugs** → `CLI.run()`, `CLI.call()`, and MCP `tools/call` all route through the same resolver (d6306f6). Break one and you break the other two. Harm: CLIs work interactively but agents get errors, or vice versa.
- **Terminal rendering bugs** → Alternate screen buffer not restored, cursor left off, raw mode leaked. Harm: the user's terminal is broken after our CLI exits. Happens silently unless you actually run the app to completion.
- **Pipeline orchestration bugs** → Phase retries, dependency cycles, output capture. These power real deployment tooling for downstream consumers. Harm: a phase appears to succeed but didn't; or a deploy hangs forever.
- **Startup-cost regressions** → The lazy-import contract is load-bearing. A stray top-level import in `__init__.py` adds latency to every CLI invocation in every downstream project.

milo-cli is 0.2.x / alpha but has real consumers (Pounce, DORI evaluating). Calibrate accordingly — the API can still move, but not carelessly.

---

## Who reads your output

- **AI agents** — Claude, DORI, gateway clients. They read JSON Schemas, tool descriptions, error `code` fields, and structured content. If the schema lies, the agent has no recourse.
- **Human CLI users** — migrating from argparse/click. They read `--help`, tracebacks, and the did-you-mean suggestions. Error messages must tell them what to do next.
- **Downstream framework consumers** — Pounce first, then DORI and enterprise tooling. They read public API names, `__all__`, and migration notes. Breaking changes cost them a rewrite.
- **Contributors** — know argparse and MCP at the surface, not our internals. They read `cli.py`, `mcp.py`, `state.py`, and examples.
- **Me (Lawrence)** — read diffs. Put the what in code, the why in the PR.

---

## Escape hatches — stop and ask

Forks where I want a check-in, not a judgment call:

- **New runtime dependency.** Zero beyond `kida-templates` is the point. "It already does what we need" is the default answer. Ask.
- **Touching the command-dispatch path** (`cli.py`, `commands.py`, `_mcp_router.py`). All three callers — `run()`, `call()`, `tools/call` — share this resolver. Show it still works for all three. Benchmarks for hot-path changes.
- **Touching the saga executor or Store dispatch lock** (`state.py`). Thread-safety on 3.14t is load-bearing. Show before/after benchmarks from `tests/test_bench_contention.py`. Can't measure → don't change.
- **Public API change** (`milo.__all__`, `CLI`, `@command`, `Context`, saga effects, `Store`, `App`). Ask whether the break is worth it. Downstream projects pin ranges.
- **New global option or config field.** The surface is already wide. Reshape an existing one first. Speculative config is a smell.
- **New saga effect or `Cmd` variant.** The effect set is deliberately small. Compose existing ones first.
- **MCP protocol surface change** (annotations, resources, prompts, streaming). Spec-compliance matters; sketch the change and ask.
- **Top-level import in `milo/__init__.py`.** Breaks the lazy-import contract. Ask.
- **Dead code you found.** Flag in the PR, let me decide — it might be public API or load-bearing for an example.
- **Test disagrees with code.** Ask which is authoritative before "fixing" either.
- **Can't reproduce a reported bug.** Stop. Ask for a minimal repro or env dump. Don't guess.
- **Adjacent issues found mid-task.** List in the PR description. Don't fold them in — exception: refactors, where I prefer one bundled PR.

---

## Anti-patterns

Things that look reasonable and are wrong here:

- **C extensions or compiled deps "just for the hot path."** No. The whole point is pure, auditable Python.
- **`try: ... except Exception: pass`.** S110 is re-enabled in CI. If you must swallow, annotate the suppression with a `# silent: <reason>` comment and list the file under per-file ignores — see `version_check.py` and `gateway.py` for examples.
- **`# type: ignore`.** Target is zero. Narrow the type or fix the code. If you have to, own it in the PR description.
- **Pydantic / attrs / dataclasses-json for schemas.** `function_to_schema` plus `Annotated` constraints is the contract. Don't shadow it.
- **Reducers that do I/O, logging, or `time.time()`.** Pure functions only. Side effects go through sagas or `Cmd`.
- **Speculative config options** for "future flexibility." If no one's asking, don't add it. Configs are easier to add than to remove.
- **Defensive validation inside internal code.** Validate at the boundary (the `@command` decorator, the MCP dispatch entry, the CLI parser). Internal code trusts its callers.
- **Abstractions for hypothetical protocols or effects.** MCP is real. A "future transport" is not. YAGNI.
- **Top-level imports in `milo/__init__.py`.** Every downstream CLI pays the cost on every invocation. Use `__getattr__`.
- **Refactoring during a bug fix.** Separate PR. Exception: the refactor *is* the fix, or it's a rename-across-files cleanup.
- **`print()` in library code.** T20 is enabled. Use the context's output path or raise.

---

## Done criteria

A change is done when all of these hold:

- [ ] `make lint`, `make ty`, `make test-cov` clean. No new `type: ignore`, no new S110 suppressions without a `# silent:` justification and per-file entry.
- [ ] Coverage floor (80%, branch-aware) still holds.
- [ ] Tests exercise the *interesting* path: both modes of a flag, MCP dispatch *and* CLI dispatch *and* `call()` for command changes, the failure path for saga effects, malformed input for schema inference.
- [ ] Hot-path changes (`state.py` dispatch, `commands.py` resolution, `schema.py` inference) include a benchmark in the PR. "Didn't benchmark" is OK only if you say why.
- [ ] Free-threading-sensitive? Note what you thought about — shared-mutable state, reentrant dispatch, executor ordering. 3.14t is where we run.
- [ ] Public API changed → towncrier fragment in `changelog.d/`, migration note if breaking, `__all__` updated.
- [ ] Error messages tell the reader what to do next, not just what went wrong.
- [ ] PR description explains *why*. The diff explains what.

"Tests pass" is not "done." Tests pass on broken code all the time — especially in a framework where the test is usually a snapshot.

---

## Review and assimilation

- **I read diff-first, description-second.** Tight diff + clear why merges fast; sprawling diff gets questions.
- **One concern per PR.** If the diff needs section headers, it's two PRs. Exception: renames across many files — one bundled PR beats review churn.
- **Commit style:** see `git log`. `fix:`/`refactor:`/`deps:`/`release:` prefixes or plain descriptive imperative. Body = motivation.
- **Don't trailing-summary me.** If the diff is readable, I can read it.
- **Flag surprises.** Weird test, unused public name, unreachable branch, unexpected `# silent:` suppression — put it in the PR description. Don't fix silently, don't ignore.

---

## When this file is wrong

It will be. Tell me. The worst outcome is that it sits here for a year contradicting how the project actually works. Updates to AGENTS.md are a first-class PR — short, focused, and welcome.
