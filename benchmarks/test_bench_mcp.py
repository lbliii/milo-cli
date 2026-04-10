"""MCP request/response cycle benchmarks — JSON-RPC overhead and tool dispatch."""

from __future__ import annotations

import json

from conftest import _build_cli

from milo._mcp_router import dispatch
from milo.mcp import _CLIHandler, _list_tools

# ---------------------------------------------------------------------------
# JSON serialization/deserialization
# ---------------------------------------------------------------------------


def test_bench_json_parse_request(benchmark) -> None:
    """Cost of parsing a typical tools/call JSON-RPC request."""
    request_str = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cmd-0", "arguments": {"value": "hello", "count": 5}},
        }
    )
    benchmark(json.loads, request_str)


def test_bench_json_serialize_small_result(benchmark) -> None:
    """Cost of serializing a small tool result."""
    result = {
        "content": [{"type": "text", "text": '{"status": "ok", "value": 42}'}],
    }
    response = {"jsonrpc": "2.0", "id": 1, "result": result}
    benchmark(json.dumps, response)


def test_bench_json_serialize_large_result(benchmark) -> None:
    """Cost of serializing a large tool result (100 items)."""
    items = [{"id": i, "name": f"item-{i}", "status": "active", "score": i * 1.5} for i in range(100)]
    result = {
        "content": [{"type": "text", "text": json.dumps(items, indent=2)}],
    }
    response = {"jsonrpc": "2.0", "id": 1, "result": result}
    benchmark(json.dumps, response)


# ---------------------------------------------------------------------------
# MCP router dispatch
# ---------------------------------------------------------------------------


def test_bench_mcp_dispatch_tools_list(benchmark) -> None:
    """Cost of routing + executing tools/list."""
    cli = _build_cli(10)
    tools = _list_tools(cli)
    handler = _CLIHandler(cli, cached_tools=tools)
    benchmark(dispatch, handler, "tools/list", {})


def test_bench_mcp_dispatch_tools_call(benchmark) -> None:
    """Cost of routing + executing tools/call for a simple command."""
    cli = _build_cli(5)
    handler = _CLIHandler(cli)
    params = {"name": "cmd-0", "arguments": {"value": "test", "count": 1}}
    benchmark(dispatch, handler, "tools/call", params)


def test_bench_mcp_dispatch_initialize(benchmark) -> None:
    """Cost of routing + executing initialize."""
    cli = _build_cli(5)
    handler = _CLIHandler(cli)
    benchmark(dispatch, handler, "initialize", {})


# ---------------------------------------------------------------------------
# _list_tools generation
# ---------------------------------------------------------------------------


def test_bench_list_tools_5(benchmark) -> None:
    """Generate tools/list for 5 commands."""
    cli = _build_cli(5)
    benchmark(_list_tools, cli)


def test_bench_list_tools_20(benchmark) -> None:
    """Generate tools/list for 20 commands."""
    cli = _build_cli(20)
    benchmark(_list_tools, cli)


def test_bench_list_tools_50(benchmark) -> None:
    """Generate tools/list for 50 commands."""
    cli = _build_cli(50)
    benchmark(_list_tools, cli)


# ---------------------------------------------------------------------------
# Full round-trip: parse → dispatch → serialize
# ---------------------------------------------------------------------------


def test_bench_mcp_roundtrip(benchmark) -> None:
    """Full JSON-RPC round-trip: parse request → route → call tool → serialize response.

    Simulates the hot path in run_mcp_server() without actual stdin/stdout.
    """
    cli = _build_cli(5)
    tools = _list_tools(cli)
    handler = _CLIHandler(cli, cached_tools=tools)

    request_str = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cmd-0", "arguments": {"value": "test", "count": 1}},
        }
    )

    def roundtrip():
        # 1. Parse
        request = json.loads(request_str)
        # 2. Route + execute
        result = dispatch(handler, request["method"], request.get("params", {}))
        # 3. Serialize response
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        return json.dumps(response)

    benchmark(roundtrip)
