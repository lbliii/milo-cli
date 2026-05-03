"""Tests for the advanced outputgallery example."""

from __future__ import annotations

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from milo._cells import cell_width


def _load_outputgallery():
    path = Path(__file__).resolve().parents[1] / "examples" / "outputgallery" / "app.py"
    spec = spec_from_file_location("outputgallery_example_app", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_app = _load_outputgallery()
cli = _app.cli
audit_resource = _app.audit_resource


def test_audit_plain_groups_static_site_diagnostics():
    result = cli.invoke(["audit", "--limit", "2"])

    assert result.exit_code == 0
    assert result.exception is None
    assert "Bengal build audit" in result.output
    assert "Broken links" in result.output
    assert "Directive render failures" in result.output
    assert "Issue Mix" in result.output
    assert "LNK001" in result.output
    assert "✖" in result.output
    assert "rerun with --limit 0" in result.output
    assert "content/docs/routing.md" in result.output


def test_audit_json_keeps_machine_readable_shape():
    result = cli.invoke(["audit", "--format", "json"])
    ascii_result = cli.invoke(["audit", "--style", "ascii", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    ascii_data = json.loads(ascii_result.output)
    assert data["title"] == "Bengal build audit"
    assert data["status"]["level"] == "error"
    assert data["severity_rail"] == "✖✖✖✖✖ ◆◆◆ ▲▲▲▲"
    assert ascii_data["severity_rail"] == data["severity_rail"]
    assert data["sections"][0]["title"] == "Broken links"
    assert data["sections"][0]["hidden"] == 2


def test_audit_ascii_style_uses_portable_shape():
    result = cli.invoke(["audit", "--style", "ascii", "--limit", "1"])

    assert result.exit_code == 0
    assert "+----------------------------------------------------------------------------+" in result.output
    assert "x links" in result.output
    assert "LNK001" in result.output


def test_audit_progressive_disclosure_modes():
    summary = cli.invoke(["audit", "--depth", "summary"])
    focus = cli.invoke(["audit", "--focus", "LNK001"])

    assert summary.exit_code == 0
    assert "summary view" in summary.output
    assert "Groups" in summary.output
    assert "content/docs/routing.md" not in summary.output
    assert focus.exit_code == 0
    assert "Issue drilldown" in focus.output
    assert "LNK001" in focus.output
    assert "content/docs/routing.md:82" in focus.output


def test_clean_profile_reports_success_with_warning_context():
    result = cli.invoke(["audit", "--profile", "clean"])

    assert result.exit_code == 0
    assert "Ready to publish" in result.output
    assert "Warnings" in result.output


def test_catalog_and_timeline_render_useful_shapes():
    catalog = cli.invoke(["catalog"])
    timeline = cli.invoke(["timeline"])

    assert catalog.exit_code == 0
    assert "Grouped diagnostics" in catalog.output
    assert "Character atlas" in catalog.output
    assert "Suppressed detail" in catalog.output
    assert timeline.exit_code == 0
    assert "Build timeline" in timeline.output
    assert "Critical Path" in timeline.output
    assert "link-check" in timeline.output


def test_grammar_documents_glyphs_and_styles():
    result = cli.invoke(["grammar"])

    assert result.exit_code == 0
    assert "Visual grammar" in result.output
    assert "blocker" in result.output
    assert "ascii" in result.output
    assert "ci" in result.output


def test_atlas_renders_character_map_dashboard():
    result = cli.invoke(["atlas"])

    assert result.exit_code == 0
    assert "Content health atlas" in result.output
    assert "Signal Rings" in result.output
    assert "Branch Map" in result.output
    assert "Score Panels" in result.output
    assert "✖ ✖ ◆" in result.output


def test_bengal_diagnostic_views_render():
    graph = cli.invoke(["graph"])
    directive = cli.invoke(["directive"])
    warnings = cli.invoke(["warnings"])

    assert graph.exit_code == 0
    assert "Link graph" in graph.output
    assert "redirect loop" in graph.output
    assert directive.exit_code == 0
    assert "Directive contracts" in directive.output
    assert "DIR002" in directive.output
    assert warnings.exit_code == 0
    assert "Warning budget" in warnings.output
    assert "content quality" in warnings.output


def test_build_telemetry_views_render():
    heat = cli.invoke(["heat"])
    spark = cli.invoke(["spark"])
    cache = cli.invoke(["cache"])

    assert heat.exit_code == 0
    assert "Build heat" in heat.output
    assert "Issue Density" in heat.output
    assert spark.exit_code == 0
    assert "Build trends" in spark.output
    assert "cache hit" in spark.output
    assert cache.exit_code == 0
    assert "Cache and fingerprints" in cache.output
    assert "Invalidations" in cache.output


def test_layout_adaptation_views_render():
    wide = cli.invoke(["layout"])
    narrow = cli.invoke(["layout", "--width", "narrow"])

    assert wide.exit_code == 0
    assert "Capability Matrix" in wide.output
    assert "wide tty" in wide.output
    assert narrow.exit_code == 0
    assert "narrow tty" in narrow.output
    assert "agent/pipe" in narrow.output


def test_fixed_width_panels_use_display_cell_width():
    for argv in (["grammar"], ["layout"], ["browser"]):
        result = cli.invoke(argv)
        assert result.exit_code == 0
        boxed = [
            line
            for line in result.output.splitlines()
            if any(ch in line for ch in "│╭╰├┤╮╯")
        ]
        assert boxed
        assert {cell_width(line) for line in boxed} == {78}


def test_open_cards_use_even_fading_rules():
    for argv in (
        ["catalog"],
        ["audit", "--limit", "1"],
        ["directive"],
        ["audit", "--focus", "LNK001"],
        ["atlas"],
        ["primitives"],
    ):
        result = cli.invoke(argv)
        assert result.exit_code == 0
        rules = [
            line
            for line in result.output.splitlines()
            if line.startswith(("╭─", "├─", "╰─"))
            and not line.endswith(("╮", "┤", "╯"))
        ]
        assert rules
        assert {cell_width(line) for line in rules} == {78}
        assert all(line.endswith("╌┄") for line in rules)


def test_live_interactive_showcase_views_render():
    live = cli.invoke(["live"])
    browser = cli.invoke(["browser"])

    assert live.exit_code == 0
    assert "Live build" in live.output
    assert "link-check" in live.output
    assert browser.exit_code == 0
    assert "Issue browser" in browser.output
    assert "LNK001" in browser.output
    assert "copy-code" in browser.output


def test_primitives_view_renders_copyable_defs():
    result = cli.invoke(["primitives"])

    assert result.exit_code == 0
    assert "Primitive shelf" in result.output
    assert "issue_rail" in result.output
    assert "meter_row" in result.output
    assert "LNK001" in result.output


def test_audit_resource_exposes_full_fixture():
    data = audit_resource()

    assert data["sections"][0]["hidden"] == 0
    assert len(data["sections"][0]["items"]) == 5
