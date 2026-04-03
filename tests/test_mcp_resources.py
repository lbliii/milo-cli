"""Tests for MCP resources support (F3)."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo.testing._mcp import MCPClient


@pytest.fixture
def cli() -> CLI:
    """Build a CLI with resources."""
    app = CLI(name="testapp", description="Test", version="1.0.0")

    @app.resource("config://app", description="App configuration")
    def get_config() -> dict:
        return {"debug": True, "port": 8080}

    @app.resource("status://health", description="Health status", mime_type="application/json")
    def health() -> str:
        return '{"status": "ok"}'

    @app.command("greet", description="Say hello")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    return app


class TestResourceRegistration:
    def test_resources_registered(self, cli: CLI) -> None:
        assert "config://app" in cli._resources
        assert "status://health" in cli._resources

    def test_walk_resources(self, cli: CLI) -> None:
        resources = cli.walk_resources()
        assert len(resources) == 2
        uris = [uri for uri, _ in resources]
        assert "config://app" in uris


class TestMCPResourcesList:
    def test_list_resources(self, cli: CLI) -> None:
        client = MCPClient(cli)
        resources = client.list_resources()
        # 2 user resources + 1 built-in (milo://stats)
        assert len(resources) == 3
        names = [r["name"] for r in resources]
        assert "get_config" in names
        assert "Server Statistics" in names

    def test_resource_fields(self, cli: CLI) -> None:
        client = MCPClient(cli)
        resources = client.list_resources()
        config = next(r for r in resources if r["uri"] == "config://app")
        assert config["description"] == "App configuration"
        assert config["mimeType"] == "text/plain"


class TestMCPResourcesRead:
    def test_read_dict_resource(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.read_resource("config://app")
        contents = result["contents"]
        assert len(contents) == 1
        assert '"debug"' in contents[0]["text"]

    def test_read_string_resource(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.read_resource("status://health")
        contents = result["contents"]
        assert contents[0]["mimeType"] == "application/json"

    def test_read_unknown_resource(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.read_resource("unknown://foo")
        assert result["contents"] == []


class TestInitializeCapabilities:
    def test_includes_resources(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.initialize()
        assert "resources" in result["capabilities"]
        assert "prompts" in result["capabilities"]
