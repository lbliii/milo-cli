# Chirp CLI Adoption Contract

Status: **five generic contracts approved and implemented; release required before downstream migration**
Milo issue: [#75](https://github.com/lbliii/milo-cli/issues/75)
Chirp source audited: [`9d2279f`](https://github.com/lbliii/chirp/commit/9d2279fc6f30b4b4c61e8bc658adf9296afd1e17)
on July 7, 2026

This document defines what Chirp owns, what Milo can express today through
public APIs, and which generic Milo contracts Chirp needs before replacing its
argparse entrypoint. The maintainer approved all five contracts on July 7,
2026; Milo's #76 implementation contains no Chirp-specific runtime behavior.

## Compatibility Promise

Migration is acceptable only when an existing Chirp user can keep:

- Command names, required values, option spellings, defaults, and help meaning.
- Exit code `0` for success/help/version, `1` for command failures, and `2` for
  argparse usage failures.
- Successful machine-readable output on stdout and diagnostics on stderr.
- `-V` / `--version`, including the chirp, kida, pounce, and Python report.
- Lazy command-module imports for cheap root help and version output.
- `module:attribute`, default `app`, and app-factory resolution.
- All current scaffold, server, contract, route, security, freeze, migration,
  and Shape-codegen behavior.

Milo may add `--mcp`, `--llms-txt`, completions, and structured programmatic
dispatch. Additive agent surfaces are expected. Existing Chirp syntax and
observable terminal behavior may not regress to obtain them.

## Source Inventory

Chirp registers the `chirp` console script to `chirp.cli:main`. The root parser
is stdlib argparse and registers eleven flat subcommands. Command modules are
imported only after parsing selects one. Evidence:

- [entrypoint and parser](https://github.com/lbliii/chirp/blob/9d2279fc6f30b4b4c61e8bc658adf9296afd1e17/src/chirp/cli/__init__.py#L1-L92)
- [command and flag declarations](https://github.com/lbliii/chirp/blob/9d2279fc6f30b4b4c61e8bc658adf9296afd1e17/src/chirp/cli/__init__.py#L94-L321)
- [lazy command dispatch](https://github.com/lbliii/chirp/blob/9d2279fc6f30b4b4c61e8bc658adf9296afd1e17/src/chirp/cli/__init__.py#L323-L373)
- [app and factory resolution](https://github.com/lbliii/chirp/blob/9d2279fc6f30b4b4c61e8bc658adf9296afd1e17/src/chirp/cli/_resolve.py#L12-L55)

| Command | Current syntax that must survive | Runtime class |
|---|---|---|
| `new` | positional `name`; `--minimal`, `--stream`, `--sse`, `--shell`, `--ai`, `--with-chirpui` | Filesystem mutation, scaffold remains Chirp-owned |
| `run` | positional `app`; server options `--host`, `--port`, `--production`, `--workers`, `--metrics`, `--rate-limit`, `--queue`, `--sentry-dsn` | Long-running, CLI-only |
| `dev` | same as `run` | Long-running, CLI-only |
| `check` | positional `app`; strictness, coverage, deploy, JSON, baseline, and info flags | Finite; human and agent useful |
| `diff` | positional `app`; required `--base`; JSON/strictness/deploy/info flags | Finite; human and agent useful |
| `routes` | positional `app` | Finite, read-only |
| `security-check` | positional `app` | Finite, read-only |
| `freeze` | positional `app` and `output`; `--exclude` requires one or more values | Filesystem mutation |
| `makemigrations` | required `--db`, required `--schema`, optional `--migrations-dir` | Database/filesystem mutation |
| `migrate` | required `--db`, optional `--migrations-dir` | Database mutation |
| `shapes-codegen` | optional positional `path`; `--dry-run`, `--audit`, legacy `--migrations` spelling | Read-only today |

Nine of eleven commands use at least one positional. No command aliases or
nested command groups exist in the audited parser. The root `-V` / `--version`
action loads dependency versions lazily; running with no command prints help
and exits `0`.

## What Milo Already Covers

The executable fixture in `tests/test_chirp_adoption_contract.py` uses only
`from milo import ...` and `from milo.testing import ...`. It proves:

| Chirp requirement | Milo public contract | Status |
|---|---|---|
| Typed string, integer, boolean, list, and optional values | Function annotations and defaults generate argparse and JSON Schema | Covered, except positional presentation |
| Hyphenated command names | `@cli.command("security-check")` | Covered |
| Shared `run` / `dev` implementation | Register one function under two command definitions | Covered |
| Lazy command modules | `cli.lazy_command(..., schema=...)` avoids importing the handler for help and discovery | Covered |
| Structured check/diff results | Return dict/dataclass; `invoke`, `call`, `call_raw`, and MCP share dispatch | Covered |
| Contract failure repair | Raise Milo errors with stable codes and argument/constraint context | Covered after #85/#86 |
| Destructive migration metadata | `annotations={"destructiveHint": True}` and optional human `confirm=` | Covered |
| Test capture | `cli.invoke()` separates stdout, stderr, result, exception, and exit code | Covered |
| Agent discovery | MCP `tools/list` and llms.txt derive from the same command schema | Covered |
| App import resolution | Keep `chirp.cli._resolve.resolve_app()` inside Chirp handlers | Chirp-owned; no Milo change |

Milo's public command registration, lazy schemas, aliases, annotations, and
display policy live in `src/milo/commands.py:249-349`. Parser construction and
validation remain generated from the command schema.

## Approved Generic Contracts

These findings were the implementation inputs for #76. The approved public
shapes are `Positional` / `Option` annotation metadata, command `surfaces`,
structured `M-CMD-004` lazy failures, `version_flags` / `version_report`, and
`terminal_renderer`.

The steward signals below preserve the pre-implementation evidence, impact,
and requested fix for auditability. The implemented direction and parity
matrix record the current behavior.

### 1. Positional and Option Presentation

Steward: Milo Core
Area: CLI argument presentation metadata
Severity: P1
Invariant: An adopter must preserve established argv while retaining one schema
and dispatch path.
Evidence: Chirp declares positional values at
`chirp/src/chirp/cli/__init__.py:45-48,95-96,140-143,180-191,218-252,297-305`.
Milo unconditionally renders every schema property as
`--<parameter-name>` at `src/milo/commands.py:768-849`.
`tests/test_chirp_adoption_contract.py:145-153` reproduces exit `2` for the
existing `chirp check myapp:app` syntax.
User Impact: Nine commands would require breaking argv changes, including
`run`, `check`, and `freeze`.
Required Fix: Add framework-neutral, typed presentation metadata for
positional parameters and option aliases while keeping
`function_to_schema()` authoritative. The design must also map `minItems >= 1`
to argparse's one-or-more list behavior.
Required Proof: Preserve Chirp positionals and `--migrations` spelling across
CLI help and invocation while `call`, MCP, schema, and llms.txt retain the same
Python parameter identity.
Collateral: Public API, lazy schema format, help, completions, docs, scaffold,
benchmarks, changelog, and migration guidance.
Confidence: high
Verification Status: machine-verified

Implemented direction: `Annotated[..., Positional(...)]` and
`Annotated[..., Option(...)]` emit the ignorable `x-milo-cli` JSON Schema
extension. `function_to_schema()` remains the sole schema source.

### 2. Per-Surface Command Visibility

Steward: Milo Core
Area: CLI/MCP/llms visibility policy
Severity: P1
Invariant: `tools/list` must advertise only tools that are safe and finite to
call, without hiding valid human commands.
Evidence: Chirp `run` and `dev` start long-running servers
(`chirp/src/chirp/cli/__init__.py:128-137`). Milo's `hidden` field is consumed
by both argparse and MCP listing (`src/milo/commands.py:716-718` and
`src/milo/mcp.py:327-330`).
`tests/test_chirp_adoption_contract.py:156-177` proves the only current choices
are visible on both surfaces or hidden on both.
User Impact: Exposing `run`/`dev` as MCP tools creates calls that do not return;
hiding them removes supported human commands.
Required Fix: Add one framework-neutral command visibility policy shared by
CLI, MCP, and llms.txt discovery. MCP call must enforce the same policy as
tools/list.
Required Proof: `run` and `dev` remain in CLI help and dispatch but are absent
and uncallable over MCP; other Chirp commands remain parity-tested.
Collateral: Public API, command definitions, MCP, llms.txt, help, docs,
scaffold, tests, and changelog.
Confidence: high
Verification Status: machine-verified

### 3. Lazy Resolution Must Fail Nonzero

Steward: Milo Core
Area: Lazy command error boundary
Severity: P1
Invariant: Import failures are command failures and must retain nonzero exit
semantics plus structured programmatic/MCP diagnostics.
Evidence: Chirp invalid app imports exit `1` in
`chirp/tests/test_cli_check.py:51-65` and `chirp/tests/test_cli_run.py:140-151`.
Milo writes a lazy import diagnostic and returns from
`src/milo/commands.py:951-967`; `tests/test_chirp_adoption_contract.py:192-203`
proves the resulting CLI exit code is currently `0`.
User Impact: CI or deployment scripts can report success when a selected
command module cannot import.
Required Fix: Return or raise a structured Milo error whose terminal boundary
exits `1`, while MCP and programmatic callers receive repair data.
Required Proof: CLI, `invoke`, `call`, `call_raw`, and MCP parity tests for a
missing module and missing attribute.
Collateral: Error reference, lazy-command docs, tests, and changelog.
Confidence: high
Verification Status: machine-verified

### 4. Root Version Contract

Steward: Milo Core
Area: Root option and version presentation
Severity: P2
Invariant: Stable root flags and their output remain compatible during
adoption.
Evidence: Chirp defines `-V` / `--version` with a lazy multi-package report at
`chirp/src/chirp/cli/__init__.py:13-40,91`; Chirp tests assert both aliases and
the dependency report at `chirp/tests/test_cli.py:50-72`. Milo exposes only a
fixed `--version` string at `src/milo/commands.py:611-614`.
`tests/test_chirp_adoption_contract.py:180-189` proves `-V` exits `2` and the
long form omits dependency versions.
User Impact: Existing scripts lose `-V`; diagnostics lose kida, pounce, and
Python versions.
Required Fix: Support a lazy public version-report callback and explicit short
alias, or an equivalent reviewed root-option hook.
Required Proof: Exact alias, stdout, exit code, and no-import-until-selected
tests.
Collateral: Root option metadata, help, docs, benchmark, and changelog.
Confidence: high
Verification Status: machine-verified

### 5. Terminal Presentation Without Protocol Prints

Steward: Milo Core
Area: Structured result and terminal rendering boundary
Severity: P2
Invariant: Reusable paths return values; terminal formatting must not corrupt
MCP stdout or require duplicate command implementations.
Evidence: Chirp command modules print successful tables/JSON and diagnostics
directly (`chirp/src/chirp/cli/_check.py:45-79`, `_routes.py:27-57`,
`_freeze.py:27-36`). Milo owns result serialization after handler execution at
`src/milo/commands.py:873-885`, but `CLI.command` has no terminal renderer or
option-alias metadata (`tests/test_chirp_adoption_contract.py:206-210`).
User Impact: Reusing current Chirp handlers would corrupt MCP stdout; returning
structured values changes established human tables and the `--json` spelling.
Required Fix: Add a terminal-only result renderer/presentation hook and a
reviewed compatibility path for legacy output-format aliases. Structured
dispatch must continue to receive the unrendered value.
Required Proof: Golden stdout/stderr and exit-code tests beside `call_raw` and
MCP structured-content assertions for check, diff, routes, and freeze.
Collateral: Public API, help, output docs, examples, scaffold, benchmarks, and
changelog.
Confidence: high
Verification Status: machine-verified

## Cross-Surface Parity Matrix

| Surface | Required Chirp behavior | Current evidence | Gate |
|---|---|---|---|
| Human CLI | Existing argv, help meaning, exit codes, stdout/stderr | Positionals, aliases, custom version reports, and terminal renderers pass | Downstream golden fixtures |
| `CLI.invoke` | Same parse/output/exit behavior captured | Eight #76 contract proofs pass | Downstream golden fixtures |
| `CLI.call` / `call_raw` | Pure kwargs to structured value; no terminal prints | Representative check passes | Chirp handlers must return values |
| MCP `tools/list` | Finite safe commands only; truthful schemas/annotations | `surfaces` filters list and call consistently | Chirp command classification |
| MCP `tools/call` | Same defaults/validation; structured failures/results | #85/#86 provide the dispatch contract | Chirp error adapters |
| llms.txt | Same visible command set and descriptions | `surfaces` and positional labels pass | Chirp command classification |
| Lazy startup | Root help/version avoid command imports | Precomputed schema and lazy version callback pass | Downstream import canary |
| JSON mode | Stable Chirp payload and stdout | Renderer is bypassed for JSON/programmatic/MCP paths | Chirp payload golden files |
| Scaffold | Existing Chirp project templates and safe defaults | Chirp-owned | Smoke test after dependency change |

## Ownership Boundary

### Chirp owns

- The eleven command implementations, `resolve_app()`, App/config/server
  semantics, contract rules, scaffolds, database operations, and freeze logic.
- Refactoring command modules so core functions return frozen/structured values
  rather than printing from reusable paths.
- Mapping domain failures to stable Milo error data without leaking database
  credentials or private filesystem paths.
- Deciding which finite commands are safe agent tools and assigning MCP
  annotations. `run` and `dev` are CLI-only.
- Golden compatibility fixtures for current stdout, stderr, help meaning, and
  exit codes.

### Milo owns

- Generic positional/option presentation metadata that remains tied to the
  single generated schema.
- Generic per-surface visibility enforced consistently by CLI, MCP, and
  llms.txt.
- Nonzero, structured lazy-resolution failures.
- Root version/option and terminal rendering hooks justified by the Chirp
  reproducer, with no Chirp conditionals.
- Parser/startup benchmarks and public documentation for the new contracts.

### Shared release work

- Chirp may add `milo-cli` only after explicit dependency approval. Both
  projects already require Python 3.14+ and `kida-templates>=0.9`; Milo pins
  Kida below 0.10, so compatible release ranges must be recorded.
- A downstream canary must pin released versions rather than silently tracking
  either main branch.
- Release notes must name argv/help/output changes even when additive.

## Ordered Migration Plan

1. **Human review this contract.** Completed July 7, 2026: all five generic
   contracts approved.
2. **Implement #76 in Milo.** Completed from the five gap reproducers with no
   Chirp imports or conditions; public API, docs, changelog, and benchmarks move
   together.
3. **Release Milo.** Do not make Chirp depend on an unreleased branch.
4. **Build a Chirp adapter branch.** Register all eleven commands lazily with
   precomputed schemas. Keep `resolve_app`, scaffolds, and domain logic in
   Chirp.
5. **Migrate finite read-only commands first.** `routes`, `check`, `diff`, and
   `security-check` prove output/error parity before filesystem, database, or
   long-running commands move.
6. **Migrate mutations with annotations.** `new`, `freeze`,
   `makemigrations`, and `migrate` receive destructive/idempotent hints and
   explicit terminal confirmation policy where appropriate.
7. **Migrate CLI-only servers last.** `run` and `dev` prove per-surface
   visibility and shutdown behavior without entering MCP discovery.
8. **Add #77 downstream canary.** Pin released versions and assert help,
   parsing, exit, stdout/stderr, structured calls, MCP, llms.txt, and lazy
   imports under Python 3.14 free-threading.
9. **Publish #78 migration guide.** Only after the canary proves the path.

## Proof and Risk Plan

- Focused machine proof: `PYTHON_GIL=0 .venv/bin/pytest -q
  tests/test_chirp_adoption_contract.py` (`8 passed` on July 7, 2026).
- Chirp source proof is pinned to the commit above; refresh the inventory if
  Chirp main changes before implementation.
- Performance: benchmark root help, `-V`/`--version`, selected command parse,
  parser construction, and module imports against Chirp's current argparse
  entrypoint. No speed claim is made by this inventory.
- Concurrency: registration and parser construction are startup-local. Domain
  server/database lifecycle stays in Chirp. Any new shared cache or renderer
  state requires a separate free-threading review.
- Security: never place database credentials from `--db` in logs, MCP schemas,
  error data, or canary snapshots. Long-running and unsafe commands must be
  excluded from MCP unless explicitly reviewed.
- Public-safe review: this document names only public repositories, commands,
  package contracts, and source evidence.

## Review Decision

The inventory originally disproved “Chirp can migrate today with public Milo
APIs only.” The five framework-neutral blockers now have executable Milo
contracts. Chirp still must wait for a released Milo version, then prove its
own adapter, golden terminal output, dependency range, and downstream canary.
