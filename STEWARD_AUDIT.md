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
