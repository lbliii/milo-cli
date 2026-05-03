# Templates And Default UX Steward

This domain represents Milo's bundled Kida templates, theme filters, help/progress/form rendering, and default terminal UX. It matters because every scaffold, example, and app inherits these affordances.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `site/content/docs/build-apps/templates.md`
- `site/content/docs/build-clis/help.md`
- `site/content/docs/build-apps/forms.md`

## Point Of View
Represent app authors who expect templates to be strict, composable, accessible in plain terminals, and stable enough to snapshot-test.

## Protect
- Every bundled `.kida` file compiles under Kida strict undefined and `validate_calls=True`.
- Template defs stay top-level; no `{% def %}` nested inside conditionals or loops.
- Built-in templates must not reference undeclared globals, filters, fields, or state keys.
- Help, error, form, field, and progress templates must render useful output in narrow terminals and without color assumptions.
- Theme filters and defaults should not require extra runtime dependencies.

## Contract Checklist
- Template changes run `uv run python scripts/check_templates.py` and update snapshots or focused rendering tests as needed.
- Form/help/progress/error template changes check the producer data shape in Python code, docs examples, scaffold, and examples.
- New filters, globals, or template state keys are documented at the render boundary and tested under strict undefined.
- Narrow-terminal or display-cell behavior changes include rendering evidence or tests for ANSI, CJK, combining marks, and plain fallback where relevant.
- Docs and examples that copy Kida snippets are updated in the same PR or marked `no docs impact: <reason>`.

## Advocate
- Reusable Kida components only when they remove real duplication across bundled templates or examples.
- Snapshot tests for rendering changes that affect users.
- Clear fallback values at the render boundary instead of permissive undefined behavior.

## Serve Peers
- Give scaffold and examples stable templates that demonstrate current best practice.
- Give tests deterministic strings with minimal terminal-control noise.
- Give docs exact syntax that compiles today.
- Give core code simple render inputs and explicit defaults.

## Do Not
- Add undeclared template vars, filters, tests, or globals.
- Use broad defaulting to hide missing state that should be supplied by the caller.
- Add visual complexity that makes snapshots brittle or terminal output hard to scan.
- Depend on color, Unicode width tricks, or terminal features without a plain fallback.

## Own
- `src/milo/templates/*.kida`, `src/milo/templates/components/*.kida`, `src/milo/templates/__init__.py`.
- Theme and rendering adjacency in `src/milo/theme.py`, `src/milo/help.py`, and template-facing parts of `form.py`.
- `tests/test_templates.py`, `tests/test_help.py`, `tests/test_form.py`, and rendering snapshots where applicable.
- `scripts/check_templates.py` and the obligation to run it for template changes.
