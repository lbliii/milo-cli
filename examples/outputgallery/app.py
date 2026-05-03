"""Outputgallery - advanced terminal output patterns for Milo CLIs.

Demonstrates: dense human reports, progressive disclosure, structured JSON
fallbacks, grouped diagnostics, warning summaries, timelines, and next steps.

    uv run python examples/outputgallery/app.py audit
    uv run python examples/outputgallery/app.py audit --limit 2
    uv run python examples/outputgallery/app.py audit --depth summary
    uv run python examples/outputgallery/app.py audit --focus LNK001
    uv run python examples/outputgallery/app.py audit --profile clean
    uv run python examples/outputgallery/app.py audit --style ascii
    uv run python examples/outputgallery/app.py audit --format json
    uv run python examples/outputgallery/app.py atlas
    uv run python examples/outputgallery/app.py catalog
    uv run python examples/outputgallery/app.py directive
    uv run python examples/outputgallery/app.py graph
    uv run python examples/outputgallery/app.py grammar
    uv run python examples/outputgallery/app.py heat
    uv run python examples/outputgallery/app.py cache
    uv run python examples/outputgallery/app.py spark
    uv run python examples/outputgallery/app.py timeline
    uv run python examples/outputgallery/app.py warnings
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from kida import FileSystemLoader

from milo import CLI, Context, Ge, Le
from milo.templates import get_env

cli = CLI(
    name="outputgallery",
    description="Advanced Milo output patterns for real-world CLI reports.",
    version="0.1.0",
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env():
    return get_env(loader=FileSystemLoader(str(_TEMPLATE_DIR)))


def _plain_or_data(ctx: Context | None, template: str, **data):
    if ctx and ctx.format == "plain":
        return ctx.render(template, env=_env(), **data)
    return data[next(iter(data))]


def _visible(items: list[dict], limit: int) -> tuple[list[dict], int]:
    if limit <= 0:
        return items, 0
    return items[:limit], max(0, len(items) - limit)


def _bar(value: int, total: int, *, width: int = 18, fill: str = "█", empty: str = "░") -> str:
    filled = 0 if total <= 0 else round(value / total * width)
    filled = min(width, max(0, filled))
    return fill * filled + empty * (width - filled)


def _palette(style: str) -> dict[str, str]:
    if style in {"ascii", "ci"}:
        return {
            "blocker": "x",
            "directive": "!",
            "warning": "^",
            "healthy": ".",
            "skipped": "o",
            "docs": "D",
            "blog": "B",
            "root": "R",
            "assets": "A",
            "high": "#",
            "mid": "=",
            "low": "-",
            "empty": ".",
            "zone_fill": "#",
            "zone_empty": ".",
        }
    return {
        "blocker": "✖",
        "directive": "◆",
        "warning": "▲",
        "healthy": "●",
        "skipped": "◌",
        "docs": "▣",
        "blog": "◧",
        "root": "◇",
        "assets": "◈",
        "high": "▓",
        "mid": "▒",
        "low": "░",
        "empty": "·",
        "zone_fill": "■",
        "zone_empty": "□",
    }


def _with_codes(items: list[dict], code: str, glyph: str) -> list[dict]:
    return [{**item, "code": f"{code}{idx:03d}", "glyph": glyph} for idx, item in enumerate(items, 1)]


def _audit_fixture(profile: str, limit: int, style: str = "dense") -> dict:
    palette = _palette(style)
    broken_links = _with_codes([
        {
            "file": "content/docs/routing.md",
            "line": 82,
            "message": "Link target was not found",
            "target": "/docs/pipelines/#parallel-work",
            "hint": "Rename the anchor or add an explicit heading id.",
        },
        {
            "file": "content/blog/milo-bridge.md",
            "line": 31,
            "message": "Relative link escapes the content root",
            "target": "../../private/notes.md",
            "hint": "Move the note into public content or mark the link as external.",
        },
        {
            "file": "content/docs/templates.md",
            "line": 144,
            "message": "Asset reference has no generated fingerprint",
            "target": "/assets/site.css",
            "hint": "Use the asset pipeline helper so cache keys stay stable.",
        },
        {
            "file": "content/index.md",
            "line": 19,
            "message": "Redirect target creates a loop",
            "target": "/",
            "hint": "Point the redirect at a canonical destination.",
        },
        {
            "file": "content/changelog.md",
            "line": 203,
            "message": "Release note link resolves to a draft page",
            "target": "/docs/beta/llms/",
            "hint": "Publish the draft page or remove the release note link.",
        },
    ], "LNK", palette["blocker"])
    directives = _with_codes([
        {
            "file": "content/docs/components.md",
            "line": 57,
            "message": "Unknown directive 'bengal-card-grid'",
            "target": "::bengal-card-grid",
            "hint": "Register the directive or replace it with a supported block.",
        },
        {
            "file": "content/docs/mcp.md",
            "line": 118,
            "message": "Directive is missing required prop 'title'",
            "target": "::callout",
            "hint": "Add title=... or switch to a plain note.",
        },
        {
            "file": "content/docs/assets.md",
            "line": 41,
            "message": "Directive output changed after capture",
            "target": "::asset-table",
            "hint": "Move non-deterministic data into an explicit build input.",
        },
    ], "DIR", palette["directive"])
    warnings = _with_codes([
        {
            "file": "content/docs/install.md",
            "line": 12,
            "message": "Heading skips from h1 to h3",
            "target": "### Quick path",
            "hint": "Use a second-level heading to preserve document outline.",
        },
        {
            "file": "content/blog/launch.md",
            "line": 7,
            "message": "Description exceeds recommended social preview length",
            "target": "193 characters",
            "hint": "Keep descriptions near 150 characters.",
        },
        {
            "file": "content/docs/search.md",
            "line": 88,
            "message": "Search excerpt contains unresolved shortcode text",
            "target": "{{ index.count }}",
            "hint": "Render the shortcode before indexing.",
        },
        {
            "file": "content/docs/rss.md",
            "line": 33,
            "message": "Date lacks timezone",
            "target": "2026-05-03 09:00",
            "hint": "Write ISO 8601 with an explicit offset.",
        },
    ], "WRN", palette["warning"])

    if profile == "clean":
        broken_links = []
        directives = []
        warnings = warnings[:1]
    elif profile == "warnings":
        broken_links = []
        directives = directives[:1]

    visible_links, hidden_links = _visible(broken_links, limit)
    visible_directives, hidden_directives = _visible(directives, limit)
    visible_warnings, hidden_warnings = _visible(warnings, limit)

    blocking = len(broken_links) + len(directives)
    warning_count = len(warnings)
    total_issues = blocking + warning_count
    status_level = "success" if blocking == 0 else "error"
    status_message = "Ready to publish" if blocking == 0 else "Publish blocked"
    status_detail = (
        f"{warning_count} warning needs review"
        if total_issues == 1
        else f"{blocking} blockers, {warning_count} warnings"
    )
    total = max(total_issues, 1)
    issue_mix = [
        {
            "label": "links",
            "glyph": palette["blocker"],
            "count": len(broken_links),
            "bar": _bar(len(broken_links), total, fill=palette["high"], empty=palette["empty"]),
        },
        {
            "label": "directives",
            "glyph": palette["directive"],
            "count": len(directives),
            "bar": _bar(len(directives), total, fill=palette["mid"], empty=palette["empty"]),
        },
        {
            "label": "warnings",
            "glyph": palette["warning"],
            "count": warning_count,
            "bar": _bar(warning_count, total, fill=palette["low"], empty=palette["empty"]),
        },
    ]
    file_zones = [
        {
            "label": "docs",
            "glyph": palette["docs"],
            "count": 7,
            "bar": _bar(7, 12, width=12, fill=palette["zone_fill"], empty=palette["zone_empty"]),
        },
        {
            "label": "blog",
            "glyph": palette["blog"],
            "count": 2,
            "bar": _bar(2, 12, width=12, fill=palette["zone_fill"], empty=palette["zone_empty"]),
        },
        {
            "label": "root",
            "glyph": palette["root"],
            "count": 1,
            "bar": _bar(1, 12, width=12, fill=palette["zone_fill"], empty=palette["zone_empty"]),
        },
        {
            "label": "assets",
            "glyph": palette["assets"],
            "count": 2,
            "bar": _bar(2, 12, width=12, fill=palette["zone_fill"], empty=palette["zone_empty"]),
        },
    ]

    return {
        "title": "Bengal build audit",
        "subtitle": "condensed diagnostics for static-site generation",
        "version": "v2026.05",
        "style": style,
        "status": {"level": status_level, "message": status_message, "detail": status_detail},
        "issue_mix": issue_mix,
        "file_zones": file_zones,
        "severity_rail": " ".join(item["glyph"] * item["count"] for item in issue_mix if item["count"]),
        "metrics": [
            {"label": "Pages scanned", "value": "248"},
            {"label": "Assets fingerprinted", "value": "1,482"},
            {"label": "Broken links", "value": str(len(broken_links))},
            {"label": "Directive errors", "value": str(len(directives))},
            {"label": "Warnings", "value": str(warning_count)},
            {"label": "Elapsed", "value": "3.42s"},
        ],
        "sections": [
            {
                "title": "Broken links",
                "level": "error" if broken_links else "success",
                "summary": "navigation and references that would 404",
                "count": len(broken_links),
                "items": visible_links,
                "hidden": hidden_links,
            },
            {
                "title": "Directive render failures",
                "level": "error" if directives else "success",
                "summary": "markdown directives Bengal could not render deterministically",
                "count": len(directives),
                "items": visible_directives,
                "hidden": hidden_directives,
            },
            {
                "title": "Warnings",
                "level": "warning" if warnings else "success",
                "summary": "publishable, but likely worth cleanup",
                "count": warning_count,
                "items": visible_warnings,
                "hidden": hidden_warnings,
            },
        ],
        "next_steps": [
            "Fix blockers first; warnings can stay visible in the final summary.",
            "Use --limit 0 when a maintainer needs the full diagnostic list.",
            "Use --format json for agents, dashboards, and CI annotations.",
        ],
    }


def _find_issue(report: dict, code: str) -> dict:
    for section in report["sections"]:
        for item in section["items"]:
            if item["code"].lower() == code.lower():
                return {
                    "title": "Issue drilldown",
                    "subtitle": "single diagnostic with repair context",
                    "section": section["title"],
                    "item": item,
                    "next": [
                        "Apply the suggested fix.",
                        "Rerun audit --focus " + item["code"],
                        "Rerun audit --depth summary before publishing.",
                    ],
                }
    return {
        "title": "Issue drilldown",
        "subtitle": "single diagnostic with repair context",
        "section": "not found",
        "item": {
            "code": code,
            "glyph": "?",
            "file": "",
            "line": 0,
            "target": "",
            "hint": "",
            "message": "No issue matched that code.",
        },
        "next": ["Run audit --limit 0 to list every available diagnostic code."],
    }


@cli.command(
    "audit",
    description="Render a static-site build audit with grouped diagnostics",
    examples=(
        {"command": "outputgallery audit", "description": "Show a bounded human report"},
        {"command": "outputgallery audit --limit 0", "description": "Expand every issue"},
        {"command": "outputgallery audit --format json", "description": "Emit machine data"},
    ),
)
def audit(
    profile: Literal["broken", "warnings", "clean"] = "broken",
    limit: Annotated[int, Ge(0), Le(20)] = 3,
    depth: Literal["summary", "detail"] = "detail",
    focus: str = "",
    style: Literal["dense", "editorial", "ascii", "ci"] = "dense",
    ctx: Context = None,
) -> dict | str:
    """Show a static-site audit inspired by Bengal build diagnostics.

    Args:
        profile: Fixture profile to render.
        limit: Maximum items to show in each issue group. Use 0 for all.
        depth: Summary shows only verdict and grouped counts; detail includes issue rows.
        focus: Optional diagnostic code to drill into, for example LNK001.
        style: Human rendering style. JSON output always returns the dense data shape.
    """
    if ctx and ctx.format == "plain":
        report = _audit_fixture(profile, 0 if focus else limit, style)
        if focus:
            return ctx.render("focus.kida", env=_env(), focus=_find_issue(report, focus))
        if depth == "summary":
            return ctx.render("audit_summary.kida", env=_env(), report=report)
        template = "audit_ascii.kida" if style in {"ascii", "ci"} else "audit.kida"
        return ctx.render(template, env=_env(), report=report)
    return _audit_fixture(profile, limit, "dense")


@cli.command("grammar", description="Show the output gallery visual grammar")
def grammar(ctx: Context = None) -> dict | str:
    """Render the reusable glyph and style grammar for terminal reports."""
    data = {
        "title": "Visual grammar",
        "subtitle": "symbols, shapes, and fallback contracts for terminal reports",
        "glyphs": [
            {"glyph": "✖", "ascii": "x", "name": "blocker", "meaning": "must fix before publish"},
            {"glyph": "◆", "ascii": "!", "name": "contract", "meaning": "schema/render contract failed"},
            {"glyph": "▲", "ascii": "^", "name": "warning", "meaning": "publishable but noisy"},
            {"glyph": "●", "ascii": ".", "name": "healthy", "meaning": "complete or healthy"},
            {"glyph": "◌", "ascii": "o", "name": "skipped", "meaning": "not run or intentionally absent"},
        ],
        "zones": [
            {"glyph": "▣", "ascii": "D", "name": "docs", "meaning": "documentation content"},
            {"glyph": "◧", "ascii": "B", "name": "blog", "meaning": "blog or editorial content"},
            {"glyph": "◇", "ascii": "R", "name": "root", "meaning": "root/canonical routing"},
            {"glyph": "◈", "ascii": "A", "name": "assets", "meaning": "static assets"},
        ],
        "styles": [
            {"name": "dense", "use": "default high-signal human report"},
            {"name": "editorial", "use": "spacious report for review and screenshots"},
            {"name": "ascii", "use": "portable report for narrow glyph support"},
            {"name": "ci", "use": "stable CI log output with minimal ornament"},
        ],
    }
    return _plain_or_data(ctx, "grammar.kida", grammar=data)


@cli.command("graph", description="Render broken links as a topology view")
def graph(ctx: Context = None) -> dict | str:
    """Show broken links as a graph-shaped report for static-site builds."""
    data = {
        "title": "Link graph",
        "subtitle": "broken routes grouped by source page and target topology",
        "summary": {"status": "blocked", "sources": 4, "broken": 5, "loops": 1},
        "nodes": [
            {
                "source": "content/docs/routing.md",
                "owner": "docs",
                "edges": [
                    {
                        "glyph": "✖",
                        "target": "/docs/pipelines/#parallel-work",
                        "reason": "missing anchor",
                        "fix": "rename the heading id or update the link",
                    },
                    {
                        "glyph": "●",
                        "target": "/docs/templates/",
                        "reason": "ok",
                        "fix": "",
                    },
                ],
            },
            {
                "source": "content/blog/milo-bridge.md",
                "owner": "editorial",
                "edges": [
                    {
                        "glyph": "✖",
                        "target": "../../private/notes.md",
                        "reason": "escapes content root",
                        "fix": "move the note into public content",
                    }
                ],
            },
            {
                "source": "content/index.md",
                "owner": "routing",
                "edges": [
                    {
                        "glyph": "✖",
                        "target": "/",
                        "reason": "redirect loop",
                        "fix": "point at a canonical destination",
                    }
                ],
            },
        ],
        "next_steps": [
            "Fix redirect loops before ordinary missing anchors.",
            "Use the source page owner to split repair work.",
            "Keep successful edges visible when they explain nearby failures.",
        ],
    }
    return _plain_or_data(ctx, "graph.kida", graph=data)


@cli.command("directive", description="Render markdown directive failures as contract cards")
def directive(ctx: Context = None) -> dict | str:
    """Show directive render errors with source, contract, output, and fix."""
    data = {
        "title": "Directive contracts",
        "subtitle": "markdown directive failures with repairable boundaries",
        "cards": [
            {
                "code": "DIR001",
                "glyph": "◆",
                "name": "::bengal-card-grid",
                "source": "content/docs/components.md:57",
                "contract": "registered directive name",
                "expected": "::card-grid{columns=3}",
                "actual": "::bengal-card-grid",
                "impact": "blocker",
                "fix": "Register the directive or replace it with a supported block.",
            },
            {
                "code": "DIR002",
                "glyph": "◆",
                "name": "::callout",
                "source": "content/docs/mcp.md:118",
                "contract": "required prop: title",
                "expected": '::callout{title="MCP gateway"}',
                "actual": "::callout",
                "impact": "blocker",
                "fix": "Add title=... or switch to a plain note.",
            },
            {
                "code": "DIR003",
                "glyph": "◆",
                "name": "::asset-table",
                "source": "content/docs/assets.md:41",
                "contract": "deterministic captured output",
                "expected": "stable rows across render passes",
                "actual": "row order changed after capture",
                "impact": "blocker",
                "fix": "Move non-deterministic data into an explicit build input.",
            },
        ],
    }
    return _plain_or_data(ctx, "directive.kida", directives=data)


@cli.command("warnings", description="Render grouped publish warnings")
def warnings_report(ctx: Context = None) -> dict | str:
    """Show publishable warnings grouped by owner and warning type."""
    data = {
        "title": "Warning budget",
        "subtitle": "publishable issues grouped for cleanup planning",
        "budget": {"used": 4, "limit": 10, "bar": "████░░░░░░"},
        "groups": [
            {
                "name": "content quality",
                "owner": "docs",
                "glyph": "▲",
                "items": [
                    {
                        "file": "content/docs/install.md:12",
                        "message": "Heading skips from h1 to h3",
                        "fix": "Use a second-level heading.",
                    },
                    {
                        "file": "content/docs/rss.md:33",
                        "message": "Date lacks timezone",
                        "fix": "Write ISO 8601 with an explicit offset.",
                    },
                ],
            },
            {
                "name": "search preview",
                "owner": "site",
                "glyph": "▲",
                "items": [
                    {
                        "file": "content/blog/launch.md:7",
                        "message": "Description exceeds social preview length",
                        "fix": "Keep descriptions near 150 characters.",
                    },
                    {
                        "file": "content/docs/search.md:88",
                        "message": "Search excerpt contains unresolved shortcode text",
                        "fix": "Render the shortcode before indexing.",
                    },
                ],
            },
        ],
    }
    return _plain_or_data(ctx, "warnings.kida", warnings=data)


@cli.command("heat", description="Render build heatmaps for phase cost and issue density")
def heat(ctx: Context = None) -> dict | str:
    """Show compact heatmaps for build cost and content issue density."""
    data = {
        "title": "Build heat",
        "subtitle": "where time, churn, and issues concentrate",
        "rows": [
            {"name": "discover", "cells": "▁▁▂▂▃▂▁▁", "detail": "stable filesystem walk"},
            {"name": "parse", "cells": "▂▃▄▅▆▄▃▂", "detail": "directive-heavy docs pages"},
            {"name": "render", "cells": "▃▅▇██▇▅▃", "detail": "largest cost center"},
            {"name": "links", "cells": "▁▁▂▆█▃▂▁", "detail": "spike from routing changes"},
            {"name": "search", "cells": "▁▂▂▃▄▅▅▆", "detail": "index growth is linear"},
        ],
        "matrix": [
            {"zone": "docs", "cells": "▓▓▓▒░", "count": 7},
            {"zone": "blog", "cells": "▒░░░░", "count": 2},
            {"zone": "root", "cells": "▓░░░░", "count": 1},
            {"zone": "assets", "cells": "▒▒░░░", "count": 2},
        ],
    }
    return _plain_or_data(ctx, "heat.kida", heat=data)


@cli.command("spark", description="Render build trend sparklines")
def spark(ctx: Context = None) -> dict | str:
    """Show trend sparklines for repeated build signals."""
    data = {
        "title": "Build trends",
        "subtitle": "small multiples for repeated build runs",
        "series": [
            {"name": "render ms", "spark": "▂▃▄▆█▇▅▃", "now": "1.84s", "trend": "up"},
            {"name": "cache hit", "spark": "█▇▇▆▅▅▄▅", "now": "74%", "trend": "down"},
            {"name": "broken", "spark": "▁▁▂▂▆█▅▅", "now": "5", "trend": "up"},
            {"name": "warnings", "spark": "▂▂▃▃▄▅▄▅", "now": "4", "trend": "flat"},
        ],
    }
    return _plain_or_data(ctx, "spark.kida", spark=data)


@cli.command("cache", description="Render cache reuse and fingerprint telemetry")
def cache(ctx: Context = None) -> dict | str:
    """Show cache reuse, invalidation causes, and asset fingerprint health."""
    data = {
        "title": "Cache and fingerprints",
        "subtitle": "what rebuilt, what reused, and why",
        "summary": [
            {"label": "HTML reused", "value": "182/248", "bar": "███████░░░"},
            {"label": "Assets reused", "value": "1,471/1,482", "bar": "█████████░"},
            {"label": "Captures reused", "value": "91/104", "bar": "████████░░"},
        ],
        "invalidations": [
            {"glyph": "◆", "cause": "directive contract changed", "count": 3},
            {"glyph": "▲", "cause": "frontmatter touched", "count": 14},
            {"glyph": "✖", "cause": "missing fingerprint", "count": 1},
        ],
        "next_steps": [
            "Fix missing fingerprints before trusting CDN cache behavior.",
            "Track directive contract changes separately from content churn.",
        ],
    }
    return _plain_or_data(ctx, "cache.kida", cache=data)


@cli.command(
    "atlas",
    description="Render a character-map dashboard for site health",
)
def atlas(ctx: Context = None) -> dict | str:
    """Show a stylized character-map dashboard for dense terminal reports."""
    report = {
        "title": "Content health atlas",
        "subtitle": "shape-first dashboard for scanning a static site build",
        "version": "v2026.05",
        "legend": [
            {"glyph": "✖", "label": "broken link"},
            {"glyph": "◆", "label": "directive error"},
            {"glyph": "▲", "label": "warning"},
            {"glyph": "●", "label": "healthy cluster"},
        ],
        "rings": [
            {"name": "content", "status": "error", "map": "✖ ✖ ◆ ● ● ▲ ● ✖ ◆ ● ▲ ●"},
            {"name": "assets", "status": "warning", "map": "● ● ▲ ● ● ● ● ◌ ● ● ● ◌"},
            {"name": "routing", "status": "error", "map": "✖ ● ✖ ● ● ✖ ● ● ● ✖ ● ●"},
            {"name": "search", "status": "success", "map": "● ● ● ● ▲ ● ● ● ● ● ● ●"},
        ],
        "tree": [
            {"branch": "content/docs", "shape": "✖──◆──▲──●", "detail": "7 issues across 5 pages"},
            {"branch": "content/blog", "shape": "✖──▲──●", "detail": "2 issues across 2 pages"},
            {"branch": "content/index.md", "shape": "✖──◇", "detail": "redirect loop at root"},
            {"branch": "assets", "shape": "◈──▲──●", "detail": "fingerprint warning"},
        ],
        "panels": [
            {
                "title": "readability",
                "score": "82",
                "meter": "████████░░",
                "note": "outline drift in install guide",
            },
            {
                "title": "link graph",
                "score": "58",
                "meter": "█████░░░░░",
                "note": "5 links block publish",
            },
            {
                "title": "directives",
                "score": "67",
                "meter": "███████░░░",
                "note": "3 render contracts broken",
            },
        ],
        "next_steps": [
            "Read the densest ring first: routing contains the most hard blockers.",
            "Use the tree when assigning owners by content area.",
            "Use audit --limit 0 when you need precise locations.",
        ],
    }
    return _plain_or_data(ctx, "atlas.kida", report=report)


@cli.command(
    "catalog",
    description="Show reusable terminal output patterns and when to use them",
)
def catalog(ctx: Context = None) -> dict | str:
    """Render a compact catalog of output patterns for downstream CLIs."""
    patterns = {
        "title": "Output pattern catalog",
        "subtitle": "small shapes that keep complex CLI data readable",
        "principles": [
            {"label": "Separate data and chatter", "value": "stdout for results, stderr for status"},
            {"label": "Bound default detail", "value": "summaries first, full lists by flag"},
            {"label": "Use stable columns", "value": "align fields users compare repeatedly"},
            {"label": "Make repair obvious", "value": "each error gets a next action"},
        ],
        "patterns": [
            {
                "name": "Outcome header",
                "use_when": "A command changed or validated something important.",
                "shape": "One verdict, one count line, one elapsed/runtime detail.",
                "avoid": "Stacking many success lines that all compete for attention.",
            },
            {
                "name": "Grouped diagnostics",
                "use_when": "The user needs to fix many heterogeneous issues.",
                "shape": "Rail, glyph, code, location, target, and repair hint.",
                "avoid": "Sorting purely by file when different issue types need different actions.",
            },
            {
                "name": "Suppressed detail",
                "use_when": "The result can include dozens or hundreds of rows.",
                "shape": "Show the top N, state how many are hidden, include the expansion flag.",
                "avoid": "Dumping every row by default and pushing the summary off screen.",
            },
            {
                "name": "Timeline",
                "use_when": "The user needs to understand where time went.",
                "shape": "Short phase name, status, duration, and one anomaly note.",
                "avoid": "Verbose logs unless a phase fails or verbose mode is enabled.",
            },
            {
                "name": "Character atlas",
                "use_when": "The user needs to feel the topology of a result before reading rows.",
                "shape": "Glyph legend, rings, branch maps, and compact score panels.",
                "avoid": "Replacing precise diagnostics; maps should point users to details.",
            },
            {
                "name": "Risk matrix",
                "use_when": "A command is publishable but carries tradeoffs.",
                "shape": "Severity, affected area, blast radius, mitigation.",
                "avoid": "Color-only severity without text labels or counts.",
            },
            {
                "name": "Next-step footer",
                "use_when": "The output found work the user should do next.",
                "shape": "Two or three imperative steps, ordered by impact.",
                "avoid": "Generic docs links when the command can name the exact fix.",
            },
        ],
    }
    return _plain_or_data(ctx, "catalog.kida", patterns=patterns)


@cli.command("timeline", description="Show a condensed build timeline")
def timeline(ctx: Context = None) -> dict | str:
    """Render a status timeline for long-running build commands."""
    run = {
        "title": "Build timeline",
        "subtitle": "phase-level progress without log spam",
        "status": {"level": "warning", "message": "Built with warnings", "detail": "3.42s total"},
        "phases": [
            {
                "name": "discover",
                "status": "success",
                "duration": "120ms",
                "detail": "248 pages, 1,482 assets",
                "track": "████░░░░░░",
            },
            {
                "name": "parse",
                "status": "success",
                "duration": "410ms",
                "detail": "17 directive families",
                "track": "██████░░░░",
            },
            {
                "name": "render",
                "status": "warning",
                "duration": "1.84s",
                "detail": "4 pages reused stale captures",
                "track": "█████████░",
            },
            {
                "name": "link-check",
                "status": "error",
                "duration": "760ms",
                "detail": "5 broken links",
                "track": "███████░░░",
            },
            {
                "name": "write",
                "status": "success",
                "duration": "290ms",
                "detail": "_site/",
                "track": "█████░░░░░",
            },
        ],
        "next_steps": [
            "Open the audit report for locations and repair hints.",
            "Run with --verbose only when phase detail is needed.",
        ],
    }
    return _plain_or_data(ctx, "timeline.kida", run=run)


@cli.resource(
    "outputgallery://audit/broken",
    description="Static-site audit fixture with broken links and directive errors",
    mime_type="application/json",
)
def audit_resource() -> dict:
    """Expose the Bengal-style audit fixture to MCP clients."""
    return _audit_fixture("broken", 0)


if __name__ == "__main__":
    cli.run()
