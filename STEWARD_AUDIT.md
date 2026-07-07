# Steward Audit

This file records the Phase 4 self-audit of the AGENTS.md steward
network. Subagents audited scoped steward mandates against source, tests,
docs, and examples. Findings below preserve the requested Steward Signal
Format and verification status.

## Synthesis

- Accepted steward-network fixes: none; returned findings describe
  source, test, or docs backlog items rather than contradictions in the
  AGENTS.md network itself.
- Deferred implementation findings: all raw findings below. They are
  useful backlog signals but are outside the steward-network bootstrap
  patch unless the maintainer asks to expand scope.
- Rejected findings: none so far.
- Convergence rule: no duplicate finding from two independent stewards
  has converged into an automatic P0 so far.
- Verification gate: all accepted raw findings below were reported as
  machine-verified by the auditing subagent and include command or grep
  receipts.
- Incomplete audits: Terminal Input, Scaffold And Verify Onboarding, and
  Benchmarks timed out and were closed with no findings recorded. Their
  absence here is not evidence of no issues.

## Raw Signals

### Milo Core

Steward: Milo Core
Area: MCP tools/list and tools/call parity
Severity: P1
Invariant: `tools/list` must describe what `tools/call` accepts; MCP
dispatch must not expose unadvertised commands.
Evidence: `src/milo/mcp.py:303` skips hidden commands in `_list_tools`,
while `src/milo/mcp.py:384` dispatches any resolved name through
`cli.call_raw()`. Receipt:
`rg -n "hidden|def _list_tools|def _call_tool|cli.call_raw" src/milo/mcp.py tests/test_mcp_handler.py`
found `src/milo/mcp.py:303: if cmd.hidden:` and
`tests/test_mcp_handler.py:90: assert "hidden-cmd" not in names`.
Behavior receipt: a direct `_list_tools` / `_call_tool` check returned
`tools= []` and a successful hidden command call with text `secret`.
User Impact: An MCP client that knows a hidden command name can invoke it
even though discovery says it is unavailable.
Required Fix: Make `_call_tool()` reject hidden commands with structured
`errorData`, or intentionally expose them in `tools/list`; the safer fix
is rejection.
Required Proof: Add a regression test that a hidden command is absent
from `tools/list` and returns an MCP error from `tools/call`.
Collateral: none if preserving current hidden-command documentation;
update docs only if hidden MCP semantics change.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. MCP now rejects hidden commands and
commands beneath hidden groups before lazy resolution or handler execution,
with `M-CMD-001` repair data. Gateway routing remains derived solely from
discovery and now returns the same structured identity for unroutable names.

Steward: Milo Core
Area: Shared dispatch argument semantics
Severity: P2
Invariant: `CLI.invoke()`, `CLI.call()`, `CLI.call_raw()`, and MCP
`tools/call` must agree on error behavior for unsupported arguments.
Evidence: `src/milo/commands.py:1036` filters programmatic kwargs to
handler parameters; `tests/test_ai_native.py:219` asserts extra kwargs
are ignored; `tests/test_ai_native.py:316` asserts MCP with `bogus`
succeeds. Receipt: a grep for
`test_call_filters_extra_kwargs`, `test_call_tool_unexpected_arg_reports_argument`,
and `_filter_call_kwargs` over `src/milo/commands.py` and
`tests/test_ai_native.py`.
Behavior receipt: a direct parity check returned success for
`cli.call(... bogus=1)` and MCP, while `cli.invoke(... --bogus 1)` exited
2.
User Impact: Typos or stale agent arguments are silently dropped in
programmatic and MCP paths while the human CLI reports an error.
Required Fix: Validate unknown kwargs before filtering for `call`,
`call_raw`, and MCP, while continuing to hide or inject `Context`.
Required Proof: Add parity tests for unknown arguments across `invoke`,
`call`, `call_raw`, and `_call_tool`.
Collateral: update tests that currently encode ignored extra kwargs; no
docs impact unless public behavior is intentionally retained.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. `invoke`, `call`, `call_raw`, and MCP all
reject unknown arguments. Programmatic paths raise `InputError`; MCP exposes
`M-INP-005`, `argument`, `reason`, `constraint`, `suggestion`, and schema;
argv parsing retains argparse's nonzero unknown-option diagnostic.

Steward: Milo Core
Area: Protocol error boundary for before-command hooks
Severity: P1
Invariant: Protocol paths return values or structured data; MCP-owned
failures should not escape as process exits.
Evidence: `src/milo/commands.py:1079` runs before hooks before the
handler `try`; `src/milo/commands.py:1123` catches hook exceptions and
calls `sys.exit(1)`; `src/milo/mcp.py:408` catches `Exception`, not
`SystemExit`. Receipt: a grep for `_execute_command`,
`_run_before_command_hooks`, `sys.exit(1)`, and `except Exception as e`
over `src/milo/commands.py`, `src/milo/mcp.py`, and
`tests/test_commands_middleware.py`.
Behavior receipt: a bad `before_command` hook produced `SystemExit 1`
from both `cli.call("greet")` and `_call_tool(...)`.
User Impact: A hook failure can terminate an MCP server instead of
returning `isError` with repairable `errorData`.
Required Fix: Make before-hook execution honor `raise_on_error` or raise
a Milo error for programmatic/MCP paths, then let `_call_tool()` structure
the failure.
Required Proof: Add tests for before-hook failures through `call`,
`call_raw`, and MCP `tools/call`.
Collateral: none unless hook error semantics are documented.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Before-command hook failures now raise
protocol-safe `M-CMD-003` errors for programmatic and MCP dispatch instead of
escaping as `SystemExit`; terminal dispatch still reports the error and exits
nonzero. Focused tests cover `invoke`, `call`, `call_raw`, and `tools/call`.

Steward: Milo Core
Area: Lazy public API manifest
Severity: P3
Invariant: Public names exposed through `__getattr__` should be listed in
`__all__`.
Evidence: `src/milo/__init__.py:57` maps `SagaContext`;
`src/milo/__init__.py:58` maps `EffectResult`; both are absent from
`__all__`. Receipt: a parser check over `src/milo/__init__.py` returned
`mapped_not_all= ['EffectResult', 'SagaContext']`. Test receipt:
`rg -n "__all__|SagaContext|EffectResult" tests/test_milo_init.py src/milo/__init__.py`
showed only spot checks for `Action`, `App`, and `Store`.
User Impact: `milo.SagaContext` and `milo.EffectResult` are accessible
lazy exports but omitted from `from milo import *`.
Required Fix: Add both names to `__all__` with maintainer confirmation,
or remove them from the lazy map if internal.
Required Proof: Add an exhaustive test that the lazy public map and
`__all__` agree.
Collateral: changelog/docs only if treated as a public API correction.
Confidence: medium
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06 with maintainer approval. `SagaContext` and
`EffectResult` are now present in `__all__`; the lazy import manifest is a
module-level data contract, and an exhaustive test requires it to equal
`__all__`. The newly public `validate_arguments` follows the same lazy path.

### Tests

Steward: Tests
Area: `src/milo/testing/_snapshot.py` saga helper correctness
Severity: P1
Invariant: Test helpers must be proof surfaces; `src/milo/testing/**`
helper APIs should make regressions fail, not pass.
Evidence: `src/milo/testing/_snapshot.py:83` defines `assert_saga`;
`src/milo/testing/_snapshot.py:93` sends the next value;
`src/milo/testing/_snapshot.py:95` returns on `StopIteration` even if
expected steps remain. Receipt: a direct `.venv/bin/python -c ...`
script printed `accepted missing expected step` after expecting a second
unproduced `Put(Action("b"))`.
User Impact: A saga regression that drops a later effect can be silently
accepted by the public-ish testing helper.
Required Fix: Make `assert_saga` fail when the saga stops before all
expected steps are consumed, and preferably fail if unexpected extra
effects remain after expected steps.
Required Proof: Add focused `tests/test_testing.py` cases for early
exhaustion and extra yielded effects.
Collateral: no docs impact unless documenting stricter helper behavior.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. `assert_saga()` now fails when a saga
stops before all expected steps are consumed and when it yields an
unexpected extra effect. Proof:
`.venv/bin/pytest tests/test_testing.py -q` (`33 passed`) and
`uv run ruff check src/milo/testing/_snapshot.py tests/test_testing.py`
(`All checks passed`).

Steward: Tests
Area: `tests/test_effects_stress.py` free-threading stress synchronization
Severity: P2
Invariant: Concurrency-sensitive tests run under `PYTHON_GIL=0` and avoid
sleeps as synchronization.
Evidence: Receipts found sleep-based synchronization comments at
`tests/test_effects_stress.py:150`, `tests/test_effects_stress.py:199`,
and `tests/test_effects_stress.py:205`; another receipt counted 87
`time.sleep` calls across selected state/effects tests.
User Impact: Free-threaded stress tests can be slow or flaky because
readiness and cancellation are inferred from wall-clock delays.
Required Fix: Replace readiness sleeps with explicit synchronization,
observable waiter registration, events, barriers, or condition polling
tied to the behavior under test.
Required Proof: Run affected stress tests under `PYTHON_GIL=0`.
Collateral: none; test-only stability issue.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Free-threading stress tests now coordinate
readiness, cancellation, handler completion, worker saturation, and teardown
through observable waiter registration and events. The launch-blocking
`test_stress_take_latest_contention` flake from issue #86 also proves the
final payload exactly across 25 consecutive runs. The sole remaining 2 ms
delay paces the contention workload itself; it is not used to infer
readiness or completion.

Steward: Tests
Area: `src/milo/testing/_mcp.py` structured error assertions
Severity: P2
Invariant: Failure tests check error codes, `errorData`, argument
context, constraints, and suggestions where Milo owns the error.
Evidence: `src/milo/testing/_mcp.py:23` defines `CallResult` with only
`text`, `is_error`, and `structured`; `src/milo/testing/_mcp.py:60`
receives raw `_call_tool` output; `src/milo/testing/_mcp.py:63` returns
without `errorData`. Existing helper tests assert only text and
`is_error`.
User Impact: Tests written through `MCPClient` cannot assert Milo-owned
structured repair data.
Required Fix: Expose `errorData` or the raw call response through
`CallResult`, and update `tests/test_testing_mcp.py` to assert a
structured error path.
Required Proof: Add an MCPClient failure test for missing or invalid
arguments that checks `errorData.argument` and `errorData.reason`.
Collateral: update testing docs if they show MCPClient error assertions.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. `CallResult.error_data` now exposes the
MCP response's structured repair payload, with a missing-argument
regression asserting both `argument` and `reason`.

Steward: Tests
Area: `src/milo/testing/_snapshot.py` render helper API
Severity: P3
Invariant: Public-ish testing helper parameters should be meaningful and
covered.
Evidence: `src/milo/testing/_snapshot.py:21` declares
`width: int = 80`, but the receipt
`rg -n "width" src/milo/testing/_snapshot.py tests/test_testing.py`
found no other use or test.
User Impact: The public render helper advertises a width control that
does nothing.
Required Fix: Either pass `width` into the render environment/template
contract if supported, or remove the parameter before it becomes
documented.
Required Proof: Add a focused `assert_renders` width behavior test if
retained, or update tests to confirm the simpler signature if removed.
Collateral: check README and `docs/testing.md` only if documented there.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. `assert_renders(width=...)` now passes
the requested width into the template render context, with a focused test
proving custom widths are observable.

### Agent Docs

Steward: Agent Docs
Area: `docs/agent-quickstart.md` MCP tool naming
Severity: P1
Invariant: Commands match reality; quickstart reaches MCP.
Evidence: The quickstart registers a direct MCP server but later tells
the user to call `my_cli.greet`; direct MCP tests assert tool name
`greet`, while gateway code prefixes `{cli_name}.{original_name}`.
Receipts cited `docs/agent-quickstart.md:94`, `:103`, `:111`, `:121`,
`:123`, `src/milo/mcp.py:301`-`:312`, `src/milo/gateway.py:291`-`:298`,
`examples/greet/tests/test_greet.py:37`-`:46`, and
`src/milo/_scaffold/default/tests/test_app.py:34`-`:36`.
User Impact: An agent following default direct registration can try to
call a non-existent `my_cli.greet`; that name is only valid through the
gateway path.
Required Fix: Split direct-server verification using `greet` from gateway
verification using `my_cli.greet`, or make gateway setup required before
instructing `my_cli.greet`.
Required Proof: Add or update a docs parity test for direct versus
gateway tool names.
Collateral: `docs/agent-quickstart.md`; check scaffold README wording.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Direct registration now instructs the
reader to call `greet`, while the gateway alternative explicitly uses
`my_cli.greet`. `tests/test_mcp_compat_docs.py` locks both names to their
respective setup paths.

Steward: Agent Docs
Area: scaffold README deep links
Severity: P2
Invariant: Generated onboarding must be followable from scaffold output.
Evidence: `src/milo/_scaffold/default/README.md:113`-`:115` points at
repo-relative docs paths; generated project files do not include `docs/`
or `site/`; scaffold code copies only the scaffold template tree.
User Impact: A user opening a newly scaffolded project gets dead local
doc paths unless they are inside the Milo source repository.
Required Fix: Replace generated README repo-relative doc paths with
public URLs or explicit source-repository links.
Required Proof: Add a scaffold README test that "More" links are absolute
URLs or paths present in the generated project.
Collateral: scaffold README; possibly `docs/agent-quickstart.md`.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Generated READMEs now link to the public
site or an explicit GitHub source page, and `tests/test_scaffold.py`
rejects repo-relative `docs/` and `site/` links in the More section.

Steward: Agent Docs
Area: snippet verification coverage
Severity: P2
Invariant: Runnable docs fences should use `milo-docs:*` directives when
the local checker can verify them.
Evidence: `scripts/check_docs_snippets.py` checks only `milo-docs:*`
fences; receipts found untagged shell/Python fences in
`docs/agent-quickstart.md` and `docs/testing.md`, while
`examples/greet/README.md` shows directive usage.
User Impact: Core agent docs can drift while `make docs-test` still
passes.
Required Fix: Tag practical Python fences with `milo-docs:compile`,
practical shell fences with `milo-docs:run`, and non-runnable setup
fences with `milo-docs:skip reason=...`.
Required Proof: Run `uv run python scripts/check_docs_snippets.py` over
the affected docs and scaffold README.
Collateral: `docs/agent-quickstart.md`, `docs/testing.md`, and scaffold
README if made checkable.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Python fences in both agent guides are
compiled, environment-dependent shell fences carry explicit skip reasons,
and `tests/test_docs_snippets.py` rejects future untagged Python or shell
fences in either guide.

### Templates And Default UX

Steward: Templates And Default UX
Area: `src/milo/templates/components/_defs.kida`
Severity: P2
Invariant: Unicode, ANSI, combining marks, and fixed-width terminal
layout use `_cells.py` helpers rather than `len()`.
Evidence: Receipts cited `_defs.kida` lines 79, 141, 156, 162, 203, 246,
and 290 using `| length` or string padding, plus `_cells.py:3`.
User Impact: Command names, panel titles, phase names, or colored/wide
text can misalign fixed terminal layouts.
Required Fix: Replace fixed-width `| length` and string-multiply padding
with `cell_width`, `cell_fit`, `cell_pad`, `cell_rpad`, `frame_line`, or
equivalent helpers.
Required Proof: Add focused render tests for `command_row`, `panel`,
`phase_detail`, `pipeline_detail`, and `pipeline_progress` using CJK and
ANSI-styled values.
Collateral: snapshots or examples only where rendered output
intentionally changes; otherwise `no docs impact: internal helper
correction`.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. `command_row`, `header_box`, `panel`,
`phase_detail`, `pipeline_detail`, and `pipeline_progress` now size and pad
dynamic text with display-cell helpers. Focused render tests cover CJK and
ANSI-aware column/border alignment. The proof also exposed and fixed
`panel()`'s invalid dynamic `BoxSet` lookup and title-fill precedence, with
all five supported border styles exercised. No benchmark impact: panel
width scanning remains linear in rendered content and other changes replace
code-point arithmetic with existing cell-width filters. No docs impact:
this restores the already documented fixed-width rendering contract.

### Site And Reference Docs

Steward: Site And Reference Docs
Area: Release notes / dependency surface
Severity: P1
Invariant: Release notes match changelog intent; `site/content/releases/**`,
`CHANGELOG.md`, `changelog.d/**`, and package metadata tell the same story.
Evidence: `pyproject.toml:12` and `uv.lock` require
`kida-templates>=0.9.0,<0.10.0`; `changelog.d/kida-0.9.changed.md:1`
records the 0.9 bump, while release and changelog text still mentioned
Kida 0.7.
User Impact: Users reading the current release surface get the wrong
runtime dependency range and upgrade context.
Required Fix: Align the public release/changelog surface with package
metadata.
Required Proof: Grep release surfaces for old Kida 0.7 claims and the
new `kida-templates>=0.9.0,<0.10.0` range.
Collateral: Release notes and changelog; no source behavior change.
Confidence: high
Verification Status: machine-verified

Resolution: Disproved on 2026-07-06. The cited Kida 0.7 text is scoped to
the historical 0.3.0 release. The current 0.3.1 release page,
`CHANGELOG.md` 0.3.1 section, `pyproject.toml`, and `uv.lock` all agree on
`kida-templates>=0.9.0,<0.10.0`; changing the 0.3.0 record would make the
release history inaccurate.

Steward: Site And Reference Docs
Area: Changelog / documentation information architecture
Severity: P2
Invariant: Navigation remains discoverable; release notes and changelog
point to authoritative public docs.
Evidence: `CHANGELOG.md:14` says the live-rendering docs page is
`usage/live.md`; docs IA tests retire the `usage` section; the actual
page is `site/content/docs/build-apps/live.md`.
User Impact: Contributors and release readers looking for the documented
live-rendering page are sent to a retired path.
Required Fix: Replace `usage/live.md` with the current docs path or add
an intentional redirect/reference.
Required Proof: Confirm `site/content/docs/usage/live.md` is absent,
`site/content/docs/build-apps/live.md` is present, and docs IA tests pass.
Collateral: Changelog/release surface only.
Confidence: high
Verification Status: machine-verified

Resolution: Disproved on 2026-07-06. `CHANGELOG.md` already points to
`docs/build-apps/live`, the current site page, and contains no
`usage/live.md` reference. The retired `usage/` section remains absent.

Steward: Site And Reference Docs
Area: Reference docs / platform paths
Severity: P3
Invariant: Public claims match code; path examples avoid hidden platform
assumptions.
Evidence: `_compat.py` returns `%LOCALAPPDATA%/milo` on Windows and
`~/.milo` on Unix, while MCP and command docs state Unix-only
`~/.milo/...` paths.
User Impact: Windows users get the wrong registry/cache location when
troubleshooting MCP installs and version-check caching.
Required Fix: Describe these as platform data-dir paths, with Unix and
Windows examples.
Required Proof: Update docs and verify with `tests/test_compat.py`
path expectations.
Collateral: MCP docs and command/version-check docs.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Version-cache and MCP-registry docs now
name Milo's platform data directory with both Unix and Windows paths.

Steward: Site And Reference Docs
Area: Docs snippets / checkability
Severity: P3
Invariant: Runnable claims are checkable; usage docs do not teach stale
or broken examples.
Evidence: `site/content/docs/build-clis/commands.md` has a tagged Python
snippet that uses `sys.stderr` without importing `sys`; the current
snippet checker compiles Python snippets and reported all tagged snippets
passed.
User Impact: A copied version-check example can raise `NameError` on the
update-notice path.
Required Fix: Add `import sys` to the snippet or avoid `sys.stderr`;
consider a stronger check mode later.
Required Proof: Re-run `uv run python scripts/check_docs_snippets.py`.
Collateral: Site command docs and snippet-check coverage if stronger
directive is added.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The version-check snippet imports `sys`
before using `sys.stderr`; the snippet remains under the compile gate and
a focused content assertion preserves the dependency.

### Examples

Steward: Examples
Area: examples/downloader reducer purity
Severity: P2
Invariant: Interactive examples keep reducers pure; I/O, logging, clocks,
sleeps, random values, and subprocess work belong in sagas, `Cmd`,
command handlers, or explicit boundary code.
Evidence: Auditor cited clock reads in `examples/downloader/app.py` from
the reducer path.
User Impact: Users copying the downloader example inherit nondeterminism,
weakening replay, snapshot tests, and free-threading reasoning.
Required Fix: Move clock reads out of `reducer()` into saga/Cmd/tick
payloads or boundary actions.
Required Proof: Add or update an example reducer test proving
deterministic elapsed/start-time behavior without wall-clock reads.
Collateral: `examples/downloader/app.py` and focused example test
coverage; no template collateral.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The reducer now derives elapsed time
deterministically from `@@TICK` actions using the same interval configured
on `App`; no wall-clock reads remain in reducer paths. Focused tests cover
tick progression and completion. No concurrency impact: example state is
immutable and the change adds no shared mutable state.

Steward: Examples
Area: README examples index API names
Severity: P3
Invariant: README indexes point to examples that exist and describe their
current purpose.
Evidence: Auditor found README rows teaching `before_run`/`after_run`
instead of `before_command`/`after_command`, and standalone
`@command`/`@resource` instead of `@cli.command`/`@cli.resource`.
User Impact: The root Examples Index teaches stale or imprecise API
names.
Required Fix: Update README example-index Key APIs to match actual
example code and public API names.
Required Proof: Add an index assertion or docs check that catches stale
Key API text, or record manual audit.
Collateral: `README.md`; optionally taskman docstrings.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The devtool and taskman rows now name
`before_command`/`after_command`, `@cli.command`, and `@cli.resource`.

Steward: Examples
Area: greet test template copy path
Severity: P3
Invariant: Copy-safe READMEs keep commands short, current, and runnable
from the example directory.
Evidence: `examples/greet/README.md` says the template is
`tests/test_greet.py` and tells users to copy it next to `app.py`, but
the template lives under `examples/greet/tests/` and assumes a `tests/`
subdirectory.
User Impact: Users can copy the test file into the wrong location.
Required Fix: Correct README guidance to copy into `tests/test_greet.py`
under the project directory, or adjust the template so "next to app.py"
is true.
Required Proof: Keep `uv run pytest examples/greet/tests/ -q` passing.
Collateral: `examples/greet/README.md`; possibly agent docs/testing docs.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The example, agent quickstart, and
testing guide all preserve the destination `tests/` directory.

Steward: Examples
Area: README index drift gate
Severity: P3
Invariant: Index links are honest and describe current purpose.
Evidence: Existing tests only check link substrings, so stale Key API
descriptions can pass.
User Impact: README descriptions can drift while the index test remains
green.
Required Fix: Strengthen `tests/test_readme_example_index.py` to validate
structured rows or known Key API text.
Required Proof: A failing fixture or assertion that catches the stale
README rows.
Collateral: `tests/test_readme_example_index.py`; `README.md` once stale
rows are corrected.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The README index test now verifies the
current hook and decorator names in the affected structured rows.

Steward: Templates And Default UX
Area: Help rendering docs parity
Severity: P2
Invariant: Built-in templates and docs describe the same render data
shape.
Evidence: Receipts cited site help docs for `state.epilog` and
`state.usage`, while `src/milo/help.py` constructs `HelpState` without
populating those values.
User Impact: Users overriding `help.kida` are told `state.epilog` and
`state.usage` are populated but receive empty defaults.
Required Fix: Populate `usage` and `epilog` from argparse, or change docs
to mark them as reserved/default-empty.
Required Proof: Add a help-rendering test with parser `usage` and
`epilog`, or a docs-only test if choosing documentation.
Collateral: `site/content/docs/build-clis/help.md`; no changelog unless
behavior changes.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. The help reference now marks
`state.epilog` and `state.usage` as reserved and empty by default, with a
content assertion preventing aspirational drift.

Steward: Templates And Default UX
Area: Form/select template docs parity
Severity: P3
Invariant: Docs, examples, and bundled templates describe the same
default UX.
Evidence: Site docs promise `[x]` / `[ ]` select indicators, while
`src/milo/templates/form.kida` and `field_select.kida` render an icon and
blank indentation.
User Impact: Docs promise a radio-style visual that the bundled templates
do not render.
Required Fix: Align docs with current icon-based UX or change templates
to render `[x]` / `[ ]`.
Required Proof: Add or update a form/select render assertion.
Collateral: `site/content/docs/build-apps/forms.md` and
`site/content/docs/build-apps/templates.md`; no examples impact unless
visual contract changes.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-06. Form and template docs now describe the
theme check icon and dimmed alternatives rendered by the bundled Kida
templates.

## Steward Notes — MCP Apps UI Primitives (#79)

- Consulted stewards: Milo Core, MCP And Protocol Correctness, Schema Truth,
  Tests, Agent Docs, Site And Reference Docs, Examples, and Benchmarks.
- Source contract: stable MCP Apps 2026-01-26 specification, extension
  `io.modelcontextprotocol/ui`, exact MIME type
  `text/html;profile=mcp-app`, and nested `_meta.ui` metadata. The deprecated
  flat `ui/resourceUri` shape is intentionally not emitted.
- Accepted public API: frozen/slotted `MCPAppCSP`, `MCPAppPermissions`,
  `MCPAppResourceMeta`, `MCPAppToolMeta`, `MCPAppVisibility`, and
  `MCPAppResourceDef`; public constants; `CLI.ui_resource()`; and `ui=` on
  eager, lazy, and grouped commands.
- Compatibility: clients without negotiated UI support receive the existing
  text/structured tool contract with no UI metadata. Existing non-UI resources,
  tools, prompts, protocol versions, and command schemas are unchanged.
- Security boundary: Milo transports declared resource metadata and HTML but
  does not render it, validate host-specific domains, create iframes, grant
  permissions, or enforce browser CSP. Hosts own those controls.
- Concurrency: definitions are immutable. Negotiation state and tool cache are
  owned by one `_CLIHandler` connection; the stdio loop remains serialized. No
  global mutable state or new lock ordering was introduced.
- Performance: `benchmarks/test_bench_mcp.py` includes a 20-tool linked UI
  metadata workload. A local Python 3.14.2 free-threading run with the GIL
  disabled measured a 402 microsecond median; no speed claim is made.
- Verification: `make ci` passed 1,538 tests with one skip and 82.30% branch
  coverage under `PYTHON_GIL=0`; all 37 tagged docs snippets passed; and Bengal
  built 165 pages with the repository's known autodoc, link, and config
  warnings. The four existing `ty` diagnostics remain unchanged.
- Collateral: public exports, command/group registration, MCP wire behavior,
  test-client negotiation, errors, docs, a minimal static UI-resource example,
  tests, benchmark, and changelog move together. Gateway rewriting is deferred
  to #80.

### #79 Parity Matrix

| Contract | API | Initialize | tools/list | resources/list/read | Existing client |
| --- | --- | --- | --- | --- | --- |
| UI resource | frozen definition | negotiated MIME | linked URI | exact MIME + metadata | omitted |
| Tool link | `ui=MCPAppToolMeta(...)` | extension response | nested `_meta.ui` | URI resolves locally | plain tool fallback |
| Missing link | registration order independent | not applicable | structured `M-UI-002` | not advertised | plain fallback |
| App-only tool | typed visibility | negotiated | omitted from model list | resource remains readable | omitted |
| Invalid read | typed URI/content boundary | capability required | not applicable | `M-UI-001`–`004` repair data | non-UI unchanged |

## Steward Notes — Dispatch Trust Hardening

- Consulted stewards: Milo Core, Tests, Agent Docs, Site And Reference
  Docs, Benchmarks.
- Accepted: hidden MCP dispatch, unknown-argument drift, before-hook process
  exits, runtime constraint enforcement, testing-helper gaps, display-cell
  layout, docs/example/scaffold drift.
- Rejected after verification: historical Kida 0.7 release mismatch and the
  retired `usage/live.md` claim.
- Deferred: downstream Chirp inventory (#75) requires the external repository;
  MCP Apps work (#79–#82) remains sequenced behind its protocol epic.
- Concurrency impact: no shared mutable runtime state or lock ordering changed.
  Validation operates on per-call dictionaries; gateway routing remains a
  read-only discovery map. Free-threading stress synchronization was made
  event-driven and verified under `PYTHON_GIL=0`.
- Performance: representative constrained validation measured a 2.666 µs
  median on local Python 3.14t with `PYTHON_GIL=0`. This is evidence of the
  workload cost, not a before/after speed claim.

### Parity Matrix

| Surface | Schema types/constraints | Unknown args | Context | Hidden tools | Hook failure |
| --- | --- | --- | --- | --- | --- |
| CLI `invoke` | enforced before handler | argparse rejects | injected, not public | absent from parser | stderr + nonzero exit |
| `CLI.call` | enforced; strings coerced | `InputError` | injected | programmatic policy unchanged | raises `M-CMD-003` |
| `CLI.call_raw` | enforced; strings coerced | `InputError` | injected | programmatic policy unchanged | raises `M-CMD-003` |
| MCP `tools/call` | enforced; strings coerced | structured `M-INP-005` | omitted/injected | structured `M-CMD-001` | structured `M-CMD-003` |
| Gateway `tools/call` | child contract preserved | child error preserved | child contract preserved | no route; `M-CMD-001` | child error preserved |
| `tools/list` / schema | single `function_to_schema()` source | exact properties | omitted | omitted | not applicable |

### Global Sweep Receipts

- Hidden-call claims: `rg -n "hidden=True|hidden commands|tools/call" README.md docs site/content src tests`.
- Silent argument filtering: `rg -n "_filter_call_kwargs|extra kwargs|unexpected_argument|bogus" src tests docs site/content`.
- Constraint enforcement: `rg -n "MinLen|exclusiveMinimum|validate_arguments|constraint_violation" src tests docs site/content examples`.

### Final Verification Receipts

- `PYTHON_GIL=0 .venv/bin/pytest -q --tb=short`: 1,569 passed, 1 skipped.
- `make ci`, twice consecutively: lint and format clean; the same four existing
  `ty` warnings; 82.07% branch-aware coverage; 1,569 passed, 1 skipped.
- `PYTHON_GIL=0 .venv/bin/pytest tests/ -n 4`, twice consecutively: 1,569
  passed, 1 skipped on each xdist run.
- `make docs-test`: all strict templates compile and 50 tagged snippets pass.
- `uv run towncrier build --draft`: fragments render under Added and Fixed.
- `PYTHON_GIL=0 ../.venv/bin/bengal build --environment production` from
  `site/`: 246 pages built. Bengal continues to report 64 pre-existing broken
  internal links and an autodoc CLI extraction warning; the build exits zero.

### Backlog Boundary

- #75's Chirp source inventory and Milo-side adoption contract are complete in
  `docs/chirp-adoption-contract.md`, pinned to Chirp commit `9d2279f`. The
  maintainer approved all five generic contracts; #76 implementation evidence
  is recorded below.
- #79–#82 and #87 introduce public protocol, verifier, Context, and lifecycle
  contracts and require maintainer confirmation before implementation.
- #88's README, verifier-first onboarding, comparison guide, launch-post draft,
  recording runbook, and clean-directory smoke proof are complete. Recording
  the video and choosing a launch date remain human-owned after #85/#86 land.
- #70 changes command dispatch, lazy resolution, and public option metadata;
  it remains a separately approved performance project.

## Steward Notes — Launch Package (#88)

Steward: Scaffold And Verify Onboarding
Area: Clean-machine `milo new` next steps
Severity: P1
Invariant: Generated projects run immediately without hidden setup.
Evidence: A clean-directory `uvx --python 3.14 --from milo-cli milo new
wow_cli` succeeded, but the generated next steps used `uv run python` and
`uv run pytest` even though the scaffold has no project metadata declaring
Milo or pytest.
User Impact: A first-time user can create the project successfully and then
fail on the very next documented command because `milo` is not importable.
Required Fix: Make generated commands self-contained without adding a runtime
dependency or changing the scaffold file layout.
Required Proof: Exercise the scaffold, command, tests, and verifier from a
fresh directory; keep a regression assertion over generated README and CLI
next-step commands.
Collateral: README front door, public quickstart, generated README, Claude MCP
registration examples, launch runbook, tests, and changelog.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-07. Generated next steps and the scaffold README
now request Python 3.14, `milo-cli`, and pytest explicitly through `uv`. A
published-package clean-directory smoke proved scaffold, command execution, and
verification; the exact current launch function passed all seven verifier
checks from a separate clean directory. Static regressions require the
self-contained commands in both CLI output and generated README.

### Launch Deliverables

- README: one-paste clean-machine proof appears before the feature inventory,
  and `milo verify` must pass before Claude registration.
- Public comparison: `site/content/docs/about/comparisons.md` states when to
  choose Milo, FastMCP, or Typer and links their official documentation.
- Launch post: `docs/launch-post.md` argues the one-definition position while
  naming Milo's limits and alternatives.
- Video runbook: `docs/launch-demo-script.md` contains a 75-second shot list,
  exact function, registration commands, privacy review, and acceptance checks.
- Proof: 56 tagged docs snippets pass; the production Bengal build emits the
  comparison page; the final `make ci` pass reports 1,583 passed, 1 skipped and
  82.27% coverage. The same four pre-existing `ty` warnings remain.
- Manual confirmation needed: record and review the final video, then choose
  the launch date after the trust-hardening changes are released.

## Steward Notes — Chirp Adoption Contract (#75)

- Consulted stewards: Milo Core, Tests, Agent Docs, and Chirp's public-surface
  and CLI/scaffold constitutions. Chirp was inspected read-only at public commit
  `9d2279fc6f30b4b4c61e8bc658adf9296afd1e17`.
- Accepted mappings: typed options/defaults, hyphenated commands, lazy commands
  with precomputed schemas, structured direct/MCP results, annotations,
  `invoke` capture, and llms.txt discovery.
- Accepted blockers: positional/option presentation metadata, CLI-visible but
  MCP-hidden commands, lazy import failures exiting zero, custom root version
  aliases/reporting, and terminal-only structured result rendering.
- Ownership: Chirp retains app resolution, commands, scaffolds, server,
  contract, freeze, and database behavior. Milo may add only generic contracts
  justified by executable reproducers; no Chirp conditionals are permitted.
- Proof: `PYTHON_GIL=0 .venv/bin/pytest -q
  tests/test_chirp_adoption_contract.py` (`8 passed`). The complete inventory,
  parity matrix, dependency/security notes, and migration order live in
  `docs/chirp-adoption-contract.md`.
- Concurrency impact: none; this batch adds a read-only inventory and tests.
- Performance: no speed claim. #76 must benchmark root help, version, parser
  construction, selected-command parsing, and command-module imports.
- Resolution: the maintainer approved all five public-contract proposals on
  2026-07-07; downstream dependency changes still require a released version.

## Steward Notes — Chirp Adoption Contracts (#76)

- Consulted stewards: Milo Core, Schema Truth, MCP And Protocol Correctness,
  Tests, Agent Docs, Site And Reference Docs, and Benchmarks.
- Approval: the maintainer approved all five contracts on 2026-07-07.
- Accepted implementation: `Positional` and `Option` annotation markers emit
  `x-milo-cli`; `surfaces` controls CLI/MCP/llms visibility; lazy imports fail
  as `M-CMD-004`; `version_flags` and `version_report` preserve root version
  behavior lazily; `terminal_renderer` formats only plain terminal output.
- Rejected scope: no Chirp imports, domain resolution, scaffold migration,
  server lifecycle, database behavior, or generic output-format alias was
  added to Milo.
- Concurrency impact: no shared mutable runtime state or lock ordering changed.
  Command metadata is immutable; the existing lazy-resolution lock remains the
  sole synchronization boundary. Renderers and version callbacks execute in
  the invoking thread.
- Performance: `benchmarks/test_bench_commands.py` measures representative
  parser construction with positionals, aliases, surfaces, a lazy version
  callback, and precomputed lazy schemas. The local Python 3.14.2 free-threading
  build (`gil_enabled=False`) measured a 581.292 µs median. This is a workload
  receipt without a before/after baseline or speed claim.
- Collateral: public exports, schema/dispatch/MCP/llms/help behavior, verifier,
  site and agent docs, README, changelog, benchmark catalog, and the pinned
  Chirp adoption contract moved together. No scaffold change: generated
  projects remain valid and the new presentation policies are opt-in.

### #76 Parity Matrix

| Surface | Presentation | Visibility | Lazy import | Result rendering |
| --- | --- | --- | --- | --- |
| CLI / `invoke` | positionals and aliases parsed | requires `"cli"` | stderr + exit 1 | renderer for plain terminal only |
| `CLI.call` | Python parameter names | always callable | raises `M-CMD-004` | structured value |
| `CLI.call_raw` | Python parameter names | always callable | raises `M-CMD-004` | structured/raw value |
| MCP `tools/list` | same schema with ignorable extension | requires `"mcp"` | unresolved no-schema tool skipped | not applicable |
| MCP `tools/call` | original property names | requires `"mcp"` | structured `errorData` | structured content |
| llms.txt | positional labels and option names | requires `"llms"` | precomputed schema avoids import | not applicable |

### #76 Proof

- `tests/test_chirp_adoption_contract.py` covers the pinned Chirp-shaped
  contract, including missing-module and missing-attribute failures.
- `tests/test_command_contract.py`, `tests/test_schema_v2.py`,
  `tests/test_lazy.py`, `tests/test_groups.py`, `tests/test_help.py`, and
  `tests/test_verify.py` cover framework-level edge cases.
- Final repository-wide lint, type, tests, docs snippets, site build, template
  checks, and free-threading/xdist receipts are recorded after integration.

## Steward Notes — Runtime Schema Round-Trip Audit

Steward: Milo Core
Area: JSON Schema `null` enforcement
Severity: P1
Invariant: Runtime dispatch must reject a value when every `anyOf` schema branch
rejects it.
Evidence: `_coerce_schema_type()` handled string, numeric, boolean, array, and
object types but had no `null` branch, so `{"type": "null"}` returned any input
unchanged. A nullable `anyOf` therefore accepted arbitrary values through its
null branch.
User Impact: Adapter-provided nullable schemas could allow an invalid value to
reach a command handler despite the advertised schema.
Required Fix: Accept only Python `None` for JSON Schema type `null`; preserve
structured `M-INP-006` type mismatch errors when no union branch matches.
Required Proof: Cover valid null, valid non-null, and invalid values through a
nullable `anyOf`, then rerun command/schema/MCP parity tests.
Collateral: #85 changelog fragment; no docs change because generated Optional
schemas retain their documented unwrapped representation.
Confidence: high
Verification Status: machine-verified

Resolution: Fixed on 2026-07-07. `type: "null"` now rejects every non-None
value. The focused schema, command-contract, and AI-native lanes pass 204 tests
under `PYTHON_GIL=0`.

## Steward Notes — MCP Apps Gateway Preservation (#80)

- Consulted stewards: Milo Core, MCP And Protocol Correctness, Tests, Agent
  Docs, Site And Reference Docs, Benchmarks, Release And Dependency Surface,
  and Security And Subprocess Boundaries.
- Accepted contract: the gateway negotiates MCP Apps with each child, rewrites
  UI resources to
  `ui://milo-gateway/{encoded-child}/{encoded-original-uri}`, rewrites the
  matching tool link and read response URI, and preserves MIME, resource
  metadata, text/blob content, and structured tool results.
- Compatibility: non-UI tools and resources retain their existing namespacing.
  Upstream clients without UI negotiation receive the existing tool fallback,
  with UI metadata and resources omitted. No new public Python name, runtime
  dependency, registry field, or transport was added.
- Collision policy: encoded child identity makes cross-child URI collisions
  impossible. Duplicate tool, resource, or prompt entries within one child use
  deterministic first-wins discovery and emit a warning. Invalid UI resources
  are omitted; broken tool links are removed rather than advertised.
- Lifecycle: unknown, unavailable, disconnected, timed-out, malformed, and
  transport-failed UI reads return existing `M-UI-002`–`004` structured repair
  data. Child stdout remains JSON-RPC-only, stderr remains isolated, and the
  established SIGTERM-to-SIGKILL cleanup path is unchanged.
- Concurrency and lock order: discovery workers own separate result values and
  the caller merges them in registry order. Each `ChildProcess` continues to
  serialize spawn, initialize, request, timeout cleanup, and idle-reaper kill
  through its single `_lock`; no additional lock or cross-child lock ordering
  was introduced. `_GatewayHandler` negotiation state is connection-owned and
  the stdio dispatcher remains serialized. Repeated eight-child collision
  discovery is covered under the repository's `PYTHON_GIL=0` suite.
- Performance: `benchmarks/test_bench_gateway.py` includes four-child,
  80-tool MCP Apps discovery and URI/link rewriting. A local Python 3.14.2
  free-threading run with the GIL disabled measured a 601 microsecond median;
  no speed claim is made.
- Verification: `make ci` passed 1,625 tests with one skip and 82.82% branch
  coverage under `PYTHON_GIL=0`; strict templates and all 61 tagged docs
  snippets passed; and Bengal built 166 pages with the repository's existing
  autodoc, internal-link, and analytics warnings. The same four existing `ty`
  diagnostics remain unchanged.
- Collateral: gateway and child transport code, single-/multi-child tests,
  child lifecycle tests, public MCP and error docs, agent quickstart, README,
  benchmark catalog, and changelog move together. No scaffold or example
  change: the #79 example already supplies the child-side contract.

### #80 Gateway Parity Matrix

| Surface | Non-UI host | UI-capable host | Child boundary |
| --- | --- | --- | --- |
| `initialize` | core capabilities | UI extension advertised | gateway always negotiates UI |
| `tools/list` | text/structured tool, no `_meta.ui` | namespaced tool + rewritten link | child metadata preserved |
| `resources/list` | existing non-UI resources | collision-safe gateway UI URI | original URI retained in route |
| `resources/read` | UI read rejected with `M-UI-003` | URI/content/metadata round trip | serialized child call under one lock |
| `tools/call` | existing result | structured result unchanged | original child tool name |
| child failure | non-UI behavior unchanged | `M-UI-004` repair data | timeout/disconnect/parse reason retained |

## Steward Notes — MCP Apps Verifier Conformance (#81)

- Consulted stewards: Scaffold And Verify Onboarding, Milo Core, MCP And
  Protocol Correctness, Tests, Agent Docs, Site And Reference Docs, Release And
  Dependency Surface, Security And Subprocess Boundaries, and Performance And
  Startup Cost.
- Approval: the maintainer approved the three stable verifier identities and
  their fail/exit semantics on 2026-07-07.
- Accepted contract: `mcp_apps_in_process` negotiates the extension and checks
  linked tool/resource/read views; `mcp_apps_gateway` runs the real single-child
  gateway projection and compares rewritten links and preserved metadata; and
  `mcp_apps_transport` repeats capability, list, link, and read validation over
  the existing subprocess JSON-RPC boundary.
- Payload boundary: verification accepts application-owned `str` content or a
  valid base64 blob and compares URI, MIME/profile, and metadata. It never
  parses, sanitizes, renders, or interprets application HTML.
- Exit behavior: all malformed URI, MIME/profile, metadata, missing-link,
  capability, render, payload-type, non-JSON stdout, or transport findings are
  failures with a stable check name and concrete repair action. Existing schema
  documentation warnings remain warnings and exit zero.
- Compatibility: non-UI CLIs receive three successful zero-resource rows. No
  public Python export, command flag, config field, runtime dependency, MCP
  method, error code, scaffold shape, or protocol version changed.
- Concurrency: the gateway check uses the existing deterministic one-child
  discovery worker and immutable local result values. It introduces no shared
  state, lock, listener, cancellation, or shutdown behavior; subprocess cleanup
  remains the existing `communicate`/timeout/kill/finally path.
- Performance: `milo verify` is an explicit diagnostic boundary rather than a
  runtime or startup hot path. The gateway view performs one local discovery,
  and each UI resource is read once in-process and once over the already-spawned
  subprocess. No speed claim is made and no benchmark is required.
- Collateral: scaffolded tests and README, root README, agent quickstart,
  testing guide, public quickstart, testing/reference pages, docs drift tests,
  malformed fixture coverage, and a towncrier fragment move together.
- Verification: `make ci` passed 1,636 tests with one skip and 82.80% branch
  coverage under `PYTHON_GIL=0`; the same four pre-existing `ty` warnings remain.
  `make docs-test` passed strict template compilation and all 61 tagged docs
  snippets. Bengal built the production site with its existing autodoc,
  internal-link, and analytics diagnostics.

### #81 Verifier Parity Matrix

| Contract | In-process | Gateway projection | Subprocess JSON-RPC |
| --- | --- | --- | --- |
| capability | discover + negotiated initialize | discover + negotiated initialize | discover + negotiated initialize responses |
| tool link | nested `_meta.ui.resourceUri` + visibility | child metadata preserved; URI rewritten | negotiated `tools/list` metadata |
| resource list | `ui://`, MIME/profile, name, metadata | resource fields preserved; URI rewritten | negotiated `resources/list` shape |
| resource read | exact URI/MIME/meta; text or base64 | #80 routing contract exercised by projection tests | one `resources/read` per registered or linked URI |
| malformed input | stable failed check + repair | omission/drift becomes failed parity check | JSON-RPC error/data becomes failed check + repair |
| no UI resources | zero-count success | zero-count success | zero-count success |

Steward: Scaffold And Verify Onboarding
Area: MCP Apps conformance before host registration
Severity: P1
Invariant: A linked interactive tool must not pass `milo verify` unless its
capability declaration, resource list/read views, gateway projection, and
subprocess transport agree.
Evidence: `src/milo/verify.py`; `tests/test_verify_mcp_apps.py`; generated
`src/milo/_scaffold/default/tests/test_app.py`.
User Impact: Broken links, malformed resource metadata, and render failures now
fail before an MCP host attempts to open the UI and name the next repair.
Required Fix: Keep the three stable check identities and validate protocol
shape without interpreting application HTML.
Required Proof: Good text/blob fixtures; URI, MIME, metadata, missing-link,
payload, render, capability, gateway, and subprocess failure fixtures; full
free-threaded CI and docs/scaffold gates.
Collateral: README, agent/testing docs, scaffold guidance, public site,
towncrier fragment, and Steward Notes.
Confidence: high
Verification Status: machine-verified

## Steward Notes — Framework-Neutral Interactive MCP App (#82)

- Consulted stewards: Examples, Milo Core, MCP And Protocol Correctness, Tests,
  Agent Docs, Site And Reference Docs, Security And Subprocess Boundaries, and
  Release And Dependency Surface.
- Accepted implementation: the existing one-file `examples/mcp_app/app.py`
  remains the smallest copy path and now owns a static HTML form plus a vanilla
  JSON-RPC 2.0 `postMessage` bridge. It performs `ui/initialize`, sends
  `ui/notifications/initialized`, consumes tool input/result notifications, and
  invokes `tools/call` with the direct or gateway-provided tool name.
- Dependency boundary: no web framework, JavaScript package, CDN, build step,
  runtime dependency, or Milo core HTML was added. Chirp and other frameworks
  that already own templates, assets, auth, or mutation semantics remain the
  HTML owners; Milo supplies typed command/schema/protocol metadata.
- Security: the view has no external assets or secrets, validates that incoming
  messages came from `window.parent`, uses `textContent`/input values instead of
  HTML injection, and leaves iframe sandbox, CSP, permissions, and host approval
  to the MCP Apps host.
- Concurrency: Python registration and the immutable HTML constant are
  startup-local. Browser request IDs and pending promises are iframe-event-loop
  state; no Python shared mutable state, lock, executor, cancellation, or
  shutdown behavior changed.
- Performance: this is a static example and test path, not a Milo runtime hot
  path. No cache or framework bootstrap was added and no speed claim is made.
- Collateral: example README, root/examples/site indexes, focused cross-surface
  tests, docs snippets, changelog, and Steward Notes move together.
- Verification: `make ci` passed 1,642 tests with one skip and 82.80% branch
  coverage under `PYTHON_GIL=0`; the same four pre-existing `ty` warnings remain.
  `make docs-test` passed strict templates and all 63 tagged snippets. Bengal
  built the site without a new diagnostic; its existing autodoc, internal-link,
  and analytics diagnostics remain.

### #82 Example Parity Matrix

| Surface | Proof |
| --- | --- |
| CLI | `forecast --city ... --format json` returns the typed structured value |
| schema | `function_to_schema(forecast)` preserves the documented city default |
| llms.txt | the same command and option/default appear in agent discovery |
| MCP tool | negotiated `tools/list` links the UI; `tools/call` returns `structuredContent` |
| resource | negotiated list/read preserves URI, MIME/profile, border metadata, and HTML |
| browser lifecycle | stable initialize/initialized and tool input/result messages; form calls `tools/call` |
| gateway | tool/resource URI rewriting, resource read, and namespaced call round-trip |
| verifier | all three #81 MCP Apps identities pass against the example subprocess |
| docs/free-threading | tagged README commands and the focused suite run under repository gates |

Steward: Examples
Area: Dependency-free interactive MCP Apps copy path
Severity: P2
Invariant: One typed function must remain the source for CLI, schema, MCP,
llms.txt, resource, gateway, and verifier behavior while application HTML stays
outside Milo core.
Evidence: `examples/mcp_app/app.py`; `examples/mcp_app/README.md`;
`tests/test_mcp_app_example.py`.
User Impact: Users can copy one file to see and test the complete interactive
MCP Apps lifecycle without adopting a web framework or JavaScript toolchain.
Required Fix: Keep the view dependency-free, host-negotiated, gateway-safe,
and backed by a useful structured fallback.
Required Proof: CLI/schema/llms/MCP/resource/gateway/verifier/docs parity under
`PYTHON_GIL=0`, plus strict docs and site checks.
Collateral: Root/examples/site indexes, example guidance, changelog, and
Steward Notes.
Confidence: high
Verification Status: machine-verified
