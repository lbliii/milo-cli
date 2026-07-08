"""Regression checks for MCP compatibility guidance in docs."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_reference_documents_compatibility_matrix() -> None:
    text = (_ROOT / "site/content/docs/build-clis/mcp.md").read_text(encoding="utf-8")
    assert "### Compatibility matrix" in text
    assert "Legacy MCP client" in text
    assert "Probe-first client" in text
    assert "JSON-RPC `-32004`" in text
    assert "Milo gateway" in text


def test_agent_quickstart_documents_discovery_and_version_repair() -> None:
    text = (_ROOT / "docs/agent-quickstart.md").read_text(encoding="utf-8")
    assert "All ten checks should pass" in text
    assert "mcp_discover" in text
    assert "mcp_apps_in_process" in text
    assert "mcp_apps_gateway" in text
    assert "mcp_apps_transport" in text
    assert "JSON-RPC `-32004`" in text
    assert "error.data.supported" in text


def test_mcp_reference_documents_stable_apps_contract() -> None:
    text = (_ROOT / "site/content/docs/build-clis/mcp.md").read_text(encoding="utf-8")
    assert "MCP Apps 2026-01-26" in text
    assert "io.modelcontextprotocol/ui" in text
    assert "text/html;profile=mcp-app" in text
    assert "_meta.ui.resourceUri" in text
    assert "deprecated flat" in text
    assert '`_meta["ui/resourceUri"]`' in text
    assert "does not render HTML" in text


def test_mcp_reference_documents_gateway_ui_contract() -> None:
    text = (_ROOT / "site/content/docs/build-clis/mcp.md").read_text(encoding="utf-8")
    assert "Gateway namespacing and lifecycle" in text
    assert "ui://milo-gateway/weather/ui%3A%2F%2Fweather%2Fdashboard" in text
    assert "deterministic first-wins" in text
    assert "disconnect, timeout, parse, or unavailable" in text
    assert "M-UI-004" in text
    assert "mcp_apps_in_process" in text
    assert "mcp_apps_gateway" in text
    assert "mcp_apps_transport" in text
    assert "does not parse" in text


def test_agent_quickstart_distinguishes_direct_and_gateway_tool_names() -> None:
    text = (_ROOT / "docs/agent-quickstart.md").read_text(encoding="utf-8")
    assert 'Use the `greet` tool to greet "Bob"' in text
    assert "`my_cli.greet` tool instead" in text
