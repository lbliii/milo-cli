"""Tests for the advanced outputgallery example."""

from __future__ import annotations

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


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


def test_audit_resource_exposes_full_fixture():
    data = audit_resource()

    assert data["sections"][0]["hidden"] == 0
    assert len(data["sections"][0]["items"]) == 5
