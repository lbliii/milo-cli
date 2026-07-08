# Chirp Downstream Canary

The versioned canary proves that released Milo can express the representative
contract of a released, demanding downstream CLI without importing either
project from an unreleased branch.

## Pinned release pair

| Project | Package | Release | Source identity |
| --- | --- | --- | --- |
| Milo | `milo-cli` | `0.4.1` | PyPI wheel for tag `v0.4.1` |
| Chirp | `bengal-chirp` | `0.9.0` | tag `v0.9.0`, commit `9ada3ba4b26ed37fbfde0ef69b60c3897830d3d3` |

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

The released Chirp side freezes its eleven-command help/usage inventory and
checks parsing, exit `0`/`1`/`2`, stdout/stderr ownership, custom version
output, app-resolution diagnostics, and lazy root-help imports.

The Milo side registers the same command names and option shapes lazily from
the committed manifest, using public `CLI.lazy_command()` and precomputed JSON
Schema only. It checks:

- every command and flag appears in generated help;
- command handlers remain unimported during help and discovery;
- `check` returns structured data through CLI, `call_raw`, and a real stdio MCP
  exchange;
- parse failures remain on stderr with exit `2`;
- `check`, `diff`, `routes`, and `security-check` are the finite read-only MCP
  and `llms.txt` surface;
- server, scaffold, filesystem, database, and code-generation commands remain
  CLI-only; and
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
3. Refresh usage entries from the tagged Chirp compatibility suite; do not
   scrape an unreleased branch.
4. Update the exact pins in `Makefile`, the workflow job name, this page, and
   the canary contract test.
5. Run `make chirp-canary`, the focused tests, and normal release-class Milo
   checks. If a surface changed, name it in both projects' release notes.

The canary intentionally does not use a compatible range. A range belongs in
Chirp's eventual dependency metadata after multiple exact release pairs have
passed; CI evidence should always identify the pair it actually tested.
