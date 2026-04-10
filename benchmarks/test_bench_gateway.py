"""Gateway benchmarks — discovery, proxied dispatch, and tool routing."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

from milo._mcp_router import dispatch
from milo.gateway import GatewayState, _discover_all, _GatewayHandler

# ---------------------------------------------------------------------------
# Mock ChildProcess — in-memory JSON-RPC instead of subprocess
# ---------------------------------------------------------------------------


class MockChildProcess:
    """In-memory mock of ChildProcess that responds to JSON-RPC calls.

    Avoids subprocess overhead so we measure only gateway logic.
    """

    def __init__(self, name: str, num_tools: int = 3) -> None:
        self.name = name
        self.command = ["mock"]
        self.idle_timeout = 300.0
        self._lock = threading.Lock()
        self._last_use = 0.0
        self._num_tools = num_tools
        self._tools = [
            {
                "name": f"cmd-{i}",
                "description": f"Command {i} from {name}",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            }
            for i in range(num_tools)
        ]
        self._initialized = True

    def send_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if method == "tools/list":
                return {"tools": self._tools}
            if method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"tool": tool_name, "args": arguments, "status": "ok"}
                            ),
                        }
                    ],
                }
            if method == "resources/list":
                return {"resources": []}
            if method == "prompts/list":
                return {"prompts": []}
            return {}

    def fetch_tools(self) -> list[dict[str, Any]]:
        result = self.send_call("tools/list", {})
        return result.get("tools", [])

    def ensure_alive(self) -> None:
        pass

    def is_idle(self) -> bool:
        return False

    def kill(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_children(n: int, tools_per_cli: int = 3) -> dict[str, MockChildProcess]:
    """Create N mock children with tools_per_cli tools each."""
    return {f"cli-{i}": MockChildProcess(f"cli-{i}", tools_per_cli) for i in range(n)}


def _make_clis_dict(n: int) -> dict[str, dict[str, Any]]:
    """Create a registry dict matching mock children."""
    return {
        f"cli-{i}": {"command": ["mock"], "description": f"CLI {i}", "version": "1.0"}
        for i in range(n)
    }


def _build_gateway(n: int, tools_per_cli: int = 3) -> tuple[_GatewayHandler, GatewayState, dict]:
    """Build a gateway with N mock children, fully discovered."""
    clis = _make_clis_dict(n)
    children = _make_mock_children(n, tools_per_cli)
    state = _discover_all(clis, children)
    handler = _GatewayHandler(clis, state, children)
    return handler, state, children


# ---------------------------------------------------------------------------
# 4.1: Gateway discovery cost
# ---------------------------------------------------------------------------


@pytest.fixture(params=[1, 4, 8], ids=["children-1", "children-4", "children-8"])
def child_count(request: pytest.FixtureRequest) -> int:
    return request.param


def test_bench_discovery(benchmark, child_count) -> None:
    """Cost of _discover_all() with N mock children.

    Measures: thread pool creation, parallel fetch_tools, namespace merging.
    """
    clis = _make_clis_dict(child_count)
    children = _make_mock_children(child_count)

    benchmark(_discover_all, clis, children)


def test_bench_discovery_many_tools(benchmark) -> None:
    """Discovery cost with 4 children, 20 tools each (80 total)."""
    clis = _make_clis_dict(4)
    children = _make_mock_children(4, tools_per_cli=20)
    benchmark(_discover_all, clis, children)


# ---------------------------------------------------------------------------
# 4.2: Proxied request latency
# ---------------------------------------------------------------------------


def test_bench_gateway_tools_list(benchmark) -> None:
    """Cost of gateway tools/list (pre-cached, just returns list)."""
    handler, _, _ = _build_gateway(4)
    benchmark(dispatch, handler, "tools/list", {})


def test_bench_gateway_tools_call(benchmark) -> None:
    """Cost of proxied tools/call through gateway to mock child."""
    handler, state, _ = _build_gateway(4)
    # Pick the first tool
    tool_name = state.tools[0]["name"]
    params = {"name": tool_name, "arguments": {"value": "test"}}
    benchmark(dispatch, handler, "tools/call", params)


def test_bench_gateway_initialize(benchmark) -> None:
    """Cost of gateway initialize response."""
    handler, _, _ = _build_gateway(4)
    benchmark(dispatch, handler, "initialize", {})


def test_bench_gateway_roundtrip(benchmark) -> None:
    """Full gateway round-trip: parse → route → proxy → serialize."""
    handler, state, _ = _build_gateway(4)
    tool_name = state.tools[0]["name"]
    request_str = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {"value": "test"}},
        }
    )

    def roundtrip():
        request = json.loads(request_str)
        result = dispatch(handler, request["method"], request.get("params", {}))
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        return json.dumps(response)

    benchmark(roundtrip)


# ---------------------------------------------------------------------------
# Tool routing overhead
# ---------------------------------------------------------------------------


def test_bench_tool_routing_lookup(benchmark) -> None:
    """Cost of tool routing dict lookup (the gateway's dispatch mechanism)."""
    _, state, _ = _build_gateway(8, tools_per_cli=10)
    # Pick a tool from the last child (worst-case dict lookup in practice)
    tool_name = state.tools[-1]["name"]

    def lookup():
        return state.tool_routing[tool_name]

    benchmark(lookup)


# ---------------------------------------------------------------------------
# Scaling: gateway with many tools
# ---------------------------------------------------------------------------


def test_bench_gateway_tools_list_80_tools(benchmark) -> None:
    """tools/list with 80 tools (4 CLIs x 20 tools)."""
    handler, _, _ = _build_gateway(4, tools_per_cli=20)
    benchmark(dispatch, handler, "tools/list", {})


def test_bench_gateway_tools_list_200_tools(benchmark) -> None:
    """tools/list with 200 tools (8 CLIs x 25 tools)."""
    handler, _, _ = _build_gateway(8, tools_per_cli=25)
    benchmark(dispatch, handler, "tools/list", {})
