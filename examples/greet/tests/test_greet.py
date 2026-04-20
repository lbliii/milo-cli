"""Test template for a milo CLI — schema, direct dispatch, MCP dispatch.

Copy this file alongside your own CLI to verify:
  1. The generated JSON Schema matches your function signature.
  2. Direct invocation (via `cli.invoke`) returns the expected result.
  3. MCP dispatch (via `tools/call`) returns the expected response.

Run:
    uv run pytest examples/greet/tests/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the example's app.py importable without an installed package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cli, greet  # type: ignore[import-not-found]

from milo.mcp import _call_tool, _list_tools
from milo.schema import function_to_schema


class TestSchema:
    def test_generated_schema_matches_signature(self):
        schema = function_to_schema(greet)
        assert schema["type"] == "object"
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["loud"]["type"] == "boolean"
        assert schema["required"] == ["name"]
        assert schema["properties"]["loud"]["default"] is False

    def test_tool_appears_in_list_tools(self):
        tools = _list_tools(cli)
        names = [t["name"] for t in tools]
        assert "greet" in names

    def test_tool_input_schema_exposes_name(self):
        tools = _list_tools(cli)
        tool = next(t for t in tools if t["name"] == "greet")
        assert "name" in tool["inputSchema"]["properties"]
        assert "name" in tool["inputSchema"]["required"]


class TestDirectDispatch:
    def test_invoke_returns_string(self):
        result = cli.invoke(["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output

    def test_invoke_with_loud_flag(self):
        result = cli.invoke(["greet", "--name", "Alice", "--loud"])
        assert result.exit_code == 0
        assert "HELLO, ALICE!" in result.output

    def test_call_raw_returns_plain_value(self):
        assert cli.call_raw("greet", name="Bob") == "Hello, Bob!"


class TestMCPDispatch:
    def test_call_tool_returns_content(self):
        result = _call_tool(cli, {"name": "greet", "arguments": {"name": "Agent"}})
        assert result["content"][0]["text"] == "Hello, Agent!"
        assert "isError" not in result

    def test_call_tool_missing_required_arg_returns_argument_context(self):
        result = _call_tool(cli, {"name": "greet", "arguments": {}})
        assert result["isError"] is True
        assert result["errorData"]["argument"] == "name"
        assert result["errorData"]["reason"] == "missing_required_argument"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
