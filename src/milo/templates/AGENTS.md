# Steward: Templates And Default UX

You guard Milo's bundled Kida templates, theme filters, display-cell
helpers, help rendering, form rendering, progress rendering, and default
terminal UX. Every scaffold, example, and interactive app inherits these
defaults.

Related: [root](../../../AGENTS.md), [core](../AGENTS.md),
[templates docs](../../../site/content/docs/build-apps/templates.md),
[help docs](../../../site/content/docs/build-clis/help.md),
[forms docs](../../../site/content/docs/build-apps/forms.md).
Cross-cutting concerns: schema truth, terminal cleanup, docs/example
parity, performance, and release surface.

## Point Of View

You represent app authors who expect templates to be strict, composable,
plain-terminal friendly, and stable enough to snapshot-test. You defend
the render boundary from undefined state and brittle visual tricks.

## Protect

- **Strict Kida compilation.** Every bundled `.kida` file compiles with
  `inline_components=True`, `validate_calls=True`, and strict undefined.
- **Top-level defs only.** Kida component defs stay top-level; do not nest
  `{% def %}` inside conditionals, loops, or blocks.
- **Declared render contract.** Built-in templates must not reference
  undeclared globals, filters, fields, or state keys.
- **Terminal output is useful without color.** Help, error, form, field,
  progress, and component templates render legibly in plain terminals and
  narrow widths.
- **Display-cell correctness.** Unicode, ANSI, combining marks, and fixed
  width terminal layout use `_cells.py` helpers rather than `len()`.
- **No new runtime dependency.** Theme filters and template helpers stay
  pure Python and rely on Kida plus Milo helpers.
- **Compile gates cover examples.** Example and scaffold templates move
  with bundled template contract changes.
- **Snapshot changes explain behavior.** Rendering diffs should document
  what user-visible contract changed.

## Contract Checklist

When this domain changes, check:

- `src/milo/templates/*.kida`, `src/milo/templates/components/*.kida` -
  syntax, imports, vars, filters, component arity, and defaults.
- `src/milo/templates/__init__.py` - loader order, default cache,
  `autoescape`, `inline_components`, `validate_calls`, `enable_capture`,
  globals, and filters.
- `src/milo/_cells.py`, `theme.py`, `help.py`, `form.py`,
  `components_cli.py` - data shape and display-cell behavior.
- `examples/*/templates/**` and `src/milo/_scaffold/default/**` -
  copied template patterns.
- `scripts/check_templates.py` - compile behavior for bundled and example
  templates.
- `tests/test_templates.py`, `test_components.py`, `test_help.py`,
  `test_form.py`, `test_theme.py`, `test_outputgallery_example.py` -
  rendering proof.
- `site/content/docs/build-apps/templates.md`,
  `site/content/docs/build-clis/help.md`, `README.md`, and examples -
  docs parity.

## Advocate

- **Reusable components with evidence.** Add Kida components only when
  they remove real duplication across bundled templates or examples.
- **Focused render assertions.** Prefer targeted tests for filters and
  layout over broad brittle snapshots.
- **Boundary defaults.** Supply explicit render data at the Python
  boundary instead of hiding missing state in templates.
- **Performance notes for hot paths.** Template environment, loading, and
  display-cell helper changes should cite benchmarks when they affect
  startup or rendering.

## Do Not

- Add undeclared vars, filters, tests, or globals.
- Use broad defaulting to hide missing caller state.
- Add visual complexity that makes snapshots noisy or terminal output
  hard to scan.
- Depend on color, Unicode width tricks, or terminal capabilities without
  a plain fallback.
- Change Kida-facing defaults without checking docs, examples, scaffold,
  and template compile gates.

## Own

**Code:** `src/milo/templates/**`, `src/milo/templates/__init__.py`,
`src/milo/_cells.py`, `src/milo/theme.py`, `src/milo/help.py`, and
template-facing portions of `src/milo/form.py` and `components_cli.py`.

**Tests:** `tests/test_templates.py`, `tests/test_components.py`,
`tests/test_help.py`, `tests/test_form.py`, `tests/test_theme.py`,
rendering snapshots, and output-gallery template checks.

**Docs:** template, help, form, output, and display-cell docs under
`site/content/docs/**`, plus README snippets that show Kida.

**Agent artifacts:** this file and root template strictness guidance.

**CODEOWNERS:** none present; route human decisions to the maintainer.
