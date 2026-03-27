"""Tests for MCP prompts support (F3)."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo.testing._mcp import MCPClient


@pytest.fixture
def cli() -> CLI:
    """Build a CLI with prompts."""
    app = CLI(name="testapp", description="Test", version="1.0.0")

    @app.prompt("deploy-checklist", description="Pre-deploy steps")
    def checklist(environment: str) -> list[dict]:
        return [
            {
                "role": "user",
                "content": {"type": "text", "text": f"Deploy checklist for {environment}"},
            },
        ]

    @app.prompt("greeting", description="Generate a greeting")
    def greeting(name: str = "World") -> str:
        return f"Hello, {name}! Welcome aboard."

    @app.command("greet", description="Say hello")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    return app


class TestPromptRegistration:
    def test_prompts_registered(self, cli: CLI) -> None:
        assert "deploy-checklist" in cli._prompts
        assert "greeting" in cli._prompts

    def test_walk_prompts(self, cli: CLI) -> None:
        prompts = cli.walk_prompts()
        assert len(prompts) == 2

    def test_auto_derive_arguments(self, cli: CLI) -> None:
        checklist_prompt = cli._prompts["deploy-checklist"]
        assert len(checklist_prompt.arguments) == 1
        assert checklist_prompt.arguments[0]["name"] == "environment"
        assert checklist_prompt.arguments[0]["required"] is True


class TestMCPPromptsList:
    def test_list_prompts(self, cli: CLI) -> None:
        client = MCPClient(cli)
        prompts = client.list_prompts()
        assert len(prompts) == 2
        names = [p["name"] for p in prompts]
        assert "deploy-checklist" in names
        assert "greeting" in names

    def test_prompt_has_arguments(self, cli: CLI) -> None:
        client = MCPClient(cli)
        prompts = client.list_prompts()
        checklist = next(p for p in prompts if p["name"] == "deploy-checklist")
        assert "arguments" in checklist
        assert checklist["arguments"][0]["name"] == "environment"


class TestMCPPromptsGet:
    def test_get_list_prompt(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.get_prompt("deploy-checklist", environment="production")
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "production" in result["messages"][0]["content"]["text"]

    def test_get_string_prompt(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.get_prompt("greeting", name="Alice")
        assert "messages" in result
        assert "Alice" in result["messages"][0]["content"]["text"]

    def test_get_unknown_prompt(self, cli: CLI) -> None:
        client = MCPClient(cli)
        result = client.get_prompt("nonexistent")
        assert result["messages"] == []
