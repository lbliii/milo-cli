"""Tests for {{name}} — schema, direct dispatch, MCP dispatch.

Three layers cover the common regression surface:
  1. Schema    — `function_to_schema(greet)` matches the function signature.
  2. Direct    — `cli.invoke([...])` returns the expected output.
  3. MCP       — `_call_tool(cli, {...})` returns the expected response and,
                 on error, structured `errorData` with `argument` context.
"""

from __future__ import annotations

import sys

import pytest

from app import cli, greet

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
        assert "greet" in [t["name"] for t in tools]


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
