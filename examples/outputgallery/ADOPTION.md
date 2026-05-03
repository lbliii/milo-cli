# Output Gallery Adoption Guide

This guide maps the gallery commands to real migration targets for Bengal-style
static-site CLIs.

## Migration Recipes

| Current output problem | Gallery command | Copy this pattern |
|---|---|---|
| Broken links appear as a flat list | `graph` | Source page -> edge -> target topology |
| Directive render errors look like generic exceptions | `directive` | Source, contract, expected, actual, fix |
| Build logs bury the verdict | `audit --depth summary` | Outcome header plus grouped counts |
| Build logs are too long for CI | `audit --style ci` | Stable ASCII-safe structure |
| Maintainers need exact repair context | `audit --focus LNK001` | Single issue drilldown |
| Performance regressions are hard to see | `heat`, `spark` | Sparklines and phase heat |
| Cache behavior is opaque | `cache` | Reuse bars plus invalidation causes |
| Interactive tools need a target surface | `browser`, `live` | Keyboard hints, lanes, detail panes |

## Before And After

### Broken Links

Before:

```text
BROKEN /docs/pipelines/#parallel-work content/docs/routing.md:82
BROKEN ../../private/notes.md content/blog/milo-bridge.md:31
BROKEN / content/index.md:19
```

After:

```text
content/docs/routing.md [docs]
  ├─ ✖ /docs/pipelines/#parallel-work
     missing anchor
     fix  rename the heading id or update the link
```

### Directive Failures

Before:

```text
Error: unknown directive bengal-card-grid
```

After:

```text
╭─ ◆ DIR001 ::bengal-card-grid
│ source    content/docs/components.md:57
│ expected  ::card-grid{columns=3}
│ actual    ::bengal-card-grid
│ fix       Register the directive or replace it.
╰────────────────────────────────────────────────────────
```

### CI Summary

Before:

```text
Checked 248 pages.
5 broken links.
3 directive errors.
4 warnings.
```

After:

```text
Publish blocked - 8 blockers, 4 warnings
severity xxxxx !!! ^^^^
links       ########.......... 5
directives  =====............. 3
warnings    ------............ 4
```

## Copy Strategy

Start by copying templates into the downstream CLI and wiring them to existing
data structures. Keep command return values as plain dictionaries or lists so
MCP and `--format json` stay useful. Only extract shared primitives after two or
three downstream outputs use the same shape.

For fixed-width topology, use Milo's display-cell filters (`cell_fit`,
`cell_pad`, `cell_truncate`, and `cell_width`) instead of character-count
padding. These filters ignore ANSI escape sequences and account for wide Unicode
characters, so box edges and columns stay aligned in real terminals.

## Review Checklist

- The first screen states the verdict.
- Every blocker includes location, target, and repair hint.
- Boxed or columnar output is asserted by display-cell width, not `len()`.
- Default output hides low-value rows and says how to expand them.
- CI and ASCII-safe modes preserve all required information.
- JSON output stays structured and does not include progress chatter.
- Glyphs are defined in one visible grammar.
