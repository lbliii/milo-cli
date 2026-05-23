# Steward Questions

These are the SME questions the bootstrap cannot answer from source,
tests, docs, changelog, or recent PR titles alone. Treat every item as
manual-confirmation-needed until the maintainer answers it or source
evidence is added.

## Root Constitution

- Which names in `src/milo/__init__.py` are considered permanent public
  API versus alpha-stage convenience exports?
- Should this repo add a CODEOWNERS file even though there is currently
  one maintainer, or should root guidance continue to say governance is
  maintainer-routed?
- Which release changes should require site release notes in
  `site/content/releases/` in addition to a `changelog.d/` fragment?

## Milo Core

- Which MCP protocol features are strategic commitments versus current
  implementation details?
- Which `Config`, plugin, middleware, pipeline, and completion APIs should
  be treated as public for compatibility promises?
- What breaking-change policy should apply before the project leaves
  alpha status?

## Terminal Input

- Which terminals or platforms are explicitly supported beyond the
  behavior covered by `tests/test_input.py` and `tests/test_compat.py`?
- Should unsupported escape sequences be documented as best-effort
  behavior or intentionally left as implementation detail?
- What manual terminal cleanup checks should reviewers run before merging
  raw-mode or resize changes?

## Templates And Default UX

- Which bundled components are stable enough for users to import directly
  from `components/_defs.kida`?
- What level of visual churn is acceptable in help, form, and progress
  output before it needs migration notes?
- Should display-cell helper behavior be documented as public API or as
  template implementation support?

## Scaffold And Verify Onboarding

- Should `milo verify` remain a stable public API, or can check names and
  report shape change freely during alpha?
- What generated project shape should be considered the long-term
  canonical Milo app layout?
- Which verifier failures should be hard failures versus warnings as the
  agent workflow evolves?

## Tests

- Are there test classes or fixtures that are intentionally public
  examples for downstream users to copy?
- Which flaky or slow tests are tolerated because they catch
  free-threading issues?
- Should every bug fix require a regression test, or are there categories
  where `no test impact` is acceptable by default?

## Agent Docs

- Which agent integrations should docs name explicitly, and which should
  stay provider-neutral?
- Should quickstart docs optimize for local repo development or installed
  package usage first?
- Which troubleshooting cases are common enough to deserve first-class
  tables rather than issue-specific notes?

## Site And Reference Docs

- What is the product story for Milo relative to the rest of the Bengal
  ecosystem as the packages evolve?
- Which pages are canonical references versus tutorial material that can
  be more narrative?
- How much migration guidance should be preserved for pre-0.3 APIs?

## Examples

- Which examples are flagship and should receive stricter smoke coverage?
- Which examples are allowed to be larger integration showcases rather
  than minimal copy paths?
- Should examples demonstrate optional extras such as YAML or watch
  behavior, or keep to the default install only?

## Benchmarks

- Which benchmark workloads are release-blocking when they regress?
- What threshold should count as meaningful regression outside the CI
  comparison comment?
- Should baseline files record machine details, or should they stay
  intentionally coarse and relative?
