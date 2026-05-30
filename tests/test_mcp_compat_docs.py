"""Regression checks for MCP compatibility guidance in docs."""

from pathlib import Path

_ROOT = Path(__file__).parent.parent


def test_mcp_reference_documents_compatibility_matrix() -> None:
    text = (_ROOT / "site/content/docs/build-clis/mcp.md").read_text(encoding="utf-8")
    assert "### Compatibility matrix" in text
    assert "Legacy MCP client" in text
    assert "Probe-first client" in text
    assert "JSON-RPC `-32004`" in text
    assert "Milo gateway" in text


def test_agent_quickstart_documents_discovery_and_version_repair() -> None:
    text = (_ROOT / "docs/agent-quickstart.md").read_text(encoding="utf-8")
    assert "All seven checks should pass" in text
    assert "mcp_discover" in text
    assert "JSON-RPC `-32004`" in text
    assert "error.data.supported" in text
