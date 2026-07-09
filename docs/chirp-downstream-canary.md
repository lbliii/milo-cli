# Chirp Downstream Canary

The versioned canary proves that released Milo can express the representative
contract of a released, demanding downstream CLI without importing either
project from an unreleased branch.

## Pinned release pair

| Project | Package | Release | Source identity |
| --- | --- | --- | --- |
| Milo | `milo-cli` | `0.4.1` | PyPI wheel for tag `v0.4.1` |
| Chirp | `bengal-chirp` | `0.10.0` | tag `v0.10.0`, commit `3f80f81d587e81a72dfacc7f7148e79bf1134d99` |

The canary uses `uv run --no-project --isolated` with exact package pins. The
runner rejects distributions located inside the Milo checkout, so a passing
receipt cannot silently test local `main`.

## Run it

```bash milo-docs:skip reason=downloads-two-exact-pypi-releases-in-an-isolated-environment
make chirp-canary
```

The command requires Python 3.14t with `PYTHON_GIL=0` and prints one JSON
receipt. The weekly and path-filtered
[`downstream-chirp.yml`](../.github/workflows/downstream-chirp.yml) workflow
runs the same target.

## What it proves

The released Chirp side freezes its eleven-command help headings, ordering,
positionals, and option inventory and checks parsing, exit `0`/`1`/`2`,
stdout/stderr ownership, custom version output, app-resolution diagnostics, and
lazy root-help imports.

The Milo side registers the same command names and option shapes lazily from
the committed manifest, using public `CLI.lazy_command()` and precomputed JSON
Schema only. It checks:

- every command and flag appears in generated help;
- command handlers remain unimported during help and discovery;
- `check` returns structured data through CLI, `call_raw`, and a real stdio MCP
  exchange;
- parse failures remain on stderr with exit `2`;
- `check`, `diff`, and `routes` are the finite read-only MCP and `llms.txt`
  surface shipped by Chirp 0.10.0;
- `security-check`, server, scaffold, filesystem, database, and code-generation
  commands remain CLI-only; and
- safe MCP tools retain `readOnlyHint`.

This is compatibility evidence, not a second Chirp implementation. Chirp owns
its real handlers, output renderers, app resolution, scaffolds, server and
database lifecycle, and final golden-output migration suite.

## Advance the pins

Pin updates are intentional compatibility reviews:

1. Read both release notes and identify CLI, schema, dependency, or protocol
   changes.
2. Update `versions` and the immutable Chirp commit in
   `tests/downstream/chirp_canary/contract.json`.
3. Refresh help headings, positionals, and options from the tagged Chirp
   compatibility suite; do not scrape an unreleased branch.
4. Update the exact pins in `Makefile`, the workflow job name, this page, and
   the canary contract test.
5. Run `make chirp-canary`, the focused tests, and normal release-class Milo
   checks. If a surface changed, name it in both projects' release notes.

The canary intentionally does not use a compatible range, even though Chirp
declares `milo-cli>=0.4.1,<0.5`. Release CI evidence should always identify the
exact pair it actually tested.
