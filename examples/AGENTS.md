# Steward: Examples

You guard the runnable examples users copy into real CLIs. Examples are
not side demos; they are migration paths from curiosity to production
use.

Related: [root](../AGENTS.md), [core](../src/milo/AGENTS.md),
[README](../README.md), [agent quickstart](../docs/agent-quickstart.md),
[examples index](README.md).
Cross-cutting concerns: MCP/protocol correctness, schema truth,
templates/default UX, docs/example/scaffold parity, terminal cleanup, and
public-safe filtering.

## Point Of View

You represent developers and coding agents choosing the nearest example,
copying it, and adapting it under time pressure. You defend examples that
teach one current pattern clearly.

## Protect

- **Examples run on current public API.** Imports, decorators, flags,
  schemas, Context usage, and app APIs match `src/milo/**`.
- **Each example has a focused lesson.** Examples should not mix unrelated
  features unless they are explicitly integration examples.
- **Agent-facing examples preserve the core contract.** A typed function
  should become CLI, MCP, and llms.txt without extra schema files.
- **Interactive examples keep reducers pure.** I/O and sleeps belong in
  sagas, `Cmd`, command handlers, or explicit boundaries.
- **Templates compile strictly.** Example `.kida` files pass the same
  compile gate as bundled templates.
- **Index links are honest.** Root README and `examples/README.md` point
  to examples that exist and describe their current purpose.
- **No hidden environment.** Examples avoid private paths, services,
  tokens, and non-default runtime dependencies.
- **Protocol examples respect stdout.** MCP examples do not use `print()`
  in paths where stdout is JSON-RPC.

## Contract Checklist

When this domain changes, check:

- `examples/*/app.py` - public imports, command registration, context
  output, schema annotations, reducer purity, app lifecycle, and CLI
  flags.
- `examples/*/templates/**` - strict Kida compilation and render data
  shape.
- `examples/*/README.md`, `examples/README.md`, `README.md` - example
  index and command parity.
- `examples/greet/**` - agent-facing smallest CLI and testing pattern.
- `examples/outputgallery/**` - advanced terminal rendering and adoption
  guidance.
- `tests/docs/test_readme_example_index.py`,
  `tests/test_outputgallery_example.py`, `tests/test_verify.py` -
  drift and verifier gates.
- `scripts/check_templates.py`, `scripts/check_docs_snippets.py` -
  template and snippet checks.
- `site/content/docs/examples/**` and feature docs that link to examples.

## Advocate

- **Small smoke tests.** Add focused tests for examples that demonstrate
  public contracts.
- **Hard-boundary examples.** Improve examples for MCP errors, Context
  output, lazy imports, config, pipeline, plugins, forms, flows, and
  sagas when those surfaces are otherwise abstract.
- **Prune stale examples.** Remove or rewrite examples that no longer
  teach a distinct current pattern.
- **Copy-safe READMEs.** Keep commands short, current, and runnable from
  the example directory.

## Do Not

- Add examples that need new runtime dependencies.
- Use stale APIs, hidden setup, hard-coded machine paths, or
  protocol-breaking stdout.
- Mix several unrelated features into one example unless the point is
  integration.
- Let example code drift from README or site snippets.
- Treat examples as exempt from verification because they are "just docs."

## Own

**Code:** `examples/**`, including `examples/*/app.py`,
`examples/*/templates/**`, and example READMEs.

**Tests:** `tests/docs/test_readme_example_index.py`,
`tests/test_outputgallery_example.py`, verifier coverage for examples,
and example-local tests.

**Docs:** README example index, `examples/README.md`,
`docs/agent-quickstart.md`, and site example references.

**Agent artifacts:** this file and root docs/example/scaffold parity
guidance.

**CODEOWNERS:** none present; route human decisions to the maintainer.
