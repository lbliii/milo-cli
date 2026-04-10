"""Tests for the MCP gateway — namespacing, routing, proxying, error handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from milo.gateway import (
    GatewayState,
    _discover_all,
    _GatewayHandler,
    _idle_reaper,
    _proxy_call,
    _proxy_prompt,
    _proxy_resource,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_child(
    name: str,
    tools: list[dict] | None = None,
    resources: list[dict] | None = None,
    prompts: list[dict] | None = None,
) -> MagicMock:
    """Build a mock ChildProcess with canned discovery responses."""
    child = MagicMock()
    child.name = name
    child.idle_timeout = 300.0
    child.is_idle.return_value = False

    tools = tools or []
    resources = resources or []
    prompts = prompts or []

    child.fetch_tools.return_value = tools

    def _send_call(method: str, params: dict[str, Any], **kw: Any) -> dict[str, Any]:
        if method == "resources/list":
            return {"resources": resources}
        if method == "prompts/list":
            return {"prompts": prompts}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": f"called {params['name']}"}]}
        if method == "resources/read":
            return {"contents": [{"uri": params["uri"], "text": "data"}]}
        if method == "prompts/get":
            return {"messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}]}
        return {}

    child.send_call.side_effect = _send_call
    return child


def _make_gateway_state(
    tools: list[dict] | None = None,
    tool_routing: dict | None = None,
    resources: list[dict] | None = None,
    resource_routing: dict | None = None,
    prompts: list[dict] | None = None,
    prompt_routing: dict | None = None,
) -> GatewayState:
    return GatewayState(
        tools=tools or [],
        tool_routing=tool_routing or {},
        resources=resources or [],
        resource_routing=resource_routing or {},
        prompts=prompts or [],
        prompt_routing=prompt_routing or {},
    )


# ---------------------------------------------------------------------------
# Discovery & Namespacing
# ---------------------------------------------------------------------------


class TestNamespacing:
    def test_tool_namespace_prefixed(self):
        """Tools are namespaced as cli_name.tool_name."""
        clis = {"taskman": {"command": ["python", "-m", "taskman", "--mcp"]}}
        children = {
            "taskman": _make_child(
                "taskman",
                tools=[{"name": "add", "description": "Add task", "inputSchema": {}}],
            ),
        }

        state = _discover_all(clis, children)

        assert len(state.tools) == 1
        assert state.tools[0]["name"] == "taskman.add"
        assert state.tool_routing["taskman.add"] == ("taskman", "add")

    def test_resource_namespace_prefixed(self):
        """Resources URIs are prefixed with cli_name/."""
        clis = {"deployer": {"command": ["deployer", "--mcp"]}}
        children = {
            "deployer": _make_child(
                "deployer",
                resources=[{"uri": "milo://stats", "name": "stats"}],
            ),
        }

        state = _discover_all(clis, children)

        assert len(state.resources) == 1
        assert state.resources[0]["uri"] == "deployer/milo://stats"
        assert state.resource_routing["deployer/milo://stats"] == ("deployer", "milo://stats")

    def test_prompt_namespace_prefixed(self):
        """Prompts are namespaced as cli_name.prompt_name."""
        clis = {"ghub": {"command": ["ghub", "--mcp"]}}
        children = {
            "ghub": _make_child(
                "ghub",
                prompts=[{"name": "review", "description": "Review PR"}],
            ),
        }

        state = _discover_all(clis, children)

        assert len(state.prompts) == 1
        assert state.prompts[0]["name"] == "ghub.review"
        assert state.prompt_routing["ghub.review"] == ("ghub", "review")

    def test_multiple_clis_namespaced(self):
        """Tools from multiple CLIs get distinct namespaces."""
        clis = {
            "taskman": {"command": ["taskman", "--mcp"]},
            "deployer": {"command": ["deployer", "--mcp"]},
        }
        children = {
            "taskman": _make_child("taskman", tools=[{"name": "add", "inputSchema": {}}]),
            "deployer": _make_child("deployer", tools=[{"name": "deploy", "inputSchema": {}}]),
        }

        state = _discover_all(clis, children)

        names = [t["name"] for t in state.tools]
        assert "taskman.add" in names
        assert "deployer.deploy" in names

    def test_tool_title_auto_generated(self):
        """Tools without a title get one from cli_name and description."""
        clis = {"myapp": {"command": ["myapp", "--mcp"]}}
        children = {
            "myapp": _make_child(
                "myapp",
                tools=[{"name": "build", "description": "Build project", "inputSchema": {}}],
            ),
        }

        state = _discover_all(clis, children)
        assert state.tools[0]["title"] == "myapp: Build project"

    def test_empty_registry(self):
        """Empty CLI registry produces empty state."""
        state = _discover_all({}, {})
        assert state.tools == []
        assert state.resources == []
        assert state.prompts == []

    def test_discovery_order_deterministic(self):
        """Tools appear in CLI registration order, not completion order."""
        clis = {
            "aaa": {"command": ["aaa"]},
            "zzz": {"command": ["zzz"]},
        }
        children = {
            "aaa": _make_child("aaa", tools=[{"name": "x", "inputSchema": {}}]),
            "zzz": _make_child("zzz", tools=[{"name": "y", "inputSchema": {}}]),
        }

        state = _discover_all(clis, children)
        names = [t["name"] for t in state.tools]
        assert names == ["aaa.x", "zzz.y"]


# ---------------------------------------------------------------------------
# Tool call proxying
# ---------------------------------------------------------------------------


class TestProxyCall:
    def test_proxy_call_routes_correctly(self):
        """Tool call is routed to the right child with original name."""
        child = _make_child("taskman")
        children = {"taskman": child}
        routing = {"taskman.add": ("taskman", "add")}

        result = _proxy_call(
            children, routing, {"name": "taskman.add", "arguments": {"title": "hi"}}
        )

        child.send_call.assert_called_once_with(
            "tools/call", {"name": "add", "arguments": {"title": "hi"}}
        )
        assert result["content"][0]["text"] == "called add"

    def test_proxy_call_unknown_tool(self):
        """Unknown tool name returns isError."""
        result = _proxy_call({}, {}, {"name": "nonexistent.tool", "arguments": {}})

        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_proxy_call_child_unavailable(self):
        """Missing child returns isError."""
        routing = {"taskman.add": ("taskman", "add")}

        result = _proxy_call({}, routing, {"name": "taskman.add", "arguments": {}})

        assert result["isError"] is True
        assert "not available" in result["content"][0]["text"]

    def test_proxy_call_child_error(self):
        """Child returning an error is surfaced correctly."""
        child = MagicMock()
        child.send_call.return_value = {"error": {"code": -1, "message": "broken"}}
        children = {"taskman": child}
        routing = {"taskman.add": ("taskman", "add")}

        result = _proxy_call(children, routing, {"name": "taskman.add", "arguments": {}})

        assert result["isError"] is True
        assert "broken" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Resource proxying
# ---------------------------------------------------------------------------


class TestProxyResource:
    def test_proxy_resource_routes_correctly(self):
        """Resource read is routed with original URI."""
        child = _make_child("deployer")
        children = {"deployer": child}
        routing = {"deployer/milo://stats": ("deployer", "milo://stats")}

        result = _proxy_resource(children, routing, {"uri": "deployer/milo://stats"})

        child.send_call.assert_called_once_with("resources/read", {"uri": "milo://stats"})
        assert result["contents"][0]["text"] == "data"

    def test_proxy_resource_unknown_uri(self):
        """Unknown URI returns empty contents."""
        result = _proxy_resource({}, {}, {"uri": "unknown://x"})
        assert result["contents"] == []

    def test_proxy_resource_child_unavailable(self):
        """Missing child returns empty contents."""
        routing = {"deployer/milo://stats": ("deployer", "milo://stats")}
        result = _proxy_resource({}, routing, {"uri": "deployer/milo://stats"})
        assert result["contents"] == []


# ---------------------------------------------------------------------------
# Prompt proxying
# ---------------------------------------------------------------------------


class TestProxyPrompt:
    def test_proxy_prompt_routes_correctly(self):
        """Prompt get is routed with original name."""
        child = _make_child("ghub")
        children = {"ghub": child}
        routing = {"ghub.review": ("ghub", "review")}

        result = _proxy_prompt(
            children, routing, {"name": "ghub.review", "arguments": {"pr": "123"}}
        )

        child.send_call.assert_called_once_with(
            "prompts/get", {"name": "review", "arguments": {"pr": "123"}}
        )
        assert result["messages"][0]["role"] == "user"

    def test_proxy_prompt_unknown(self):
        """Unknown prompt returns empty messages."""
        result = _proxy_prompt({}, {}, {"name": "nope.x"})
        assert result["messages"] == []

    def test_proxy_prompt_child_unavailable(self):
        """Missing child returns empty messages."""
        routing = {"ghub.review": ("ghub", "review")}
        result = _proxy_prompt({}, routing, {"name": "ghub.review"})
        assert result["messages"] == []


# ---------------------------------------------------------------------------
# GatewayHandler
# ---------------------------------------------------------------------------


class TestGatewayHandler:
    def _make_handler(self) -> tuple[_GatewayHandler, dict]:
        clis = {"taskman": {"command": ["taskman", "--mcp"]}}
        children = {
            "taskman": _make_child(
                "taskman",
                tools=[{"name": "add", "description": "Add task", "inputSchema": {}}],
            ),
        }
        state = _discover_all(clis, children)
        handler = _GatewayHandler(clis, state, children)
        return handler, children

    def test_initialize(self):
        handler, _ = self._make_handler()
        result = handler.initialize({})
        assert result["serverInfo"]["name"] == "milo-gateway"
        assert "taskman" in result["instructions"]

    def test_list_tools(self):
        handler, _ = self._make_handler()
        result = handler.list_tools({})
        names = [t["name"] for t in result["tools"]]
        assert "taskman.add" in names

    def test_call_tool(self):
        handler, _children = self._make_handler()
        result = handler.call_tool({"name": "taskman.add", "arguments": {"title": "test"}})
        assert "called add" in result["content"][0]["text"]

    def test_list_resources(self):
        clis = {"myapp": {"command": ["myapp"]}}
        children = {
            "myapp": _make_child("myapp", resources=[{"uri": "milo://stats", "name": "stats"}])
        }
        state = _discover_all(clis, children)
        handler = _GatewayHandler(clis, state, children)

        result = handler.list_resources({})
        assert len(result["resources"]) == 1

    def test_list_prompts(self):
        clis = {"myapp": {"command": ["myapp"]}}
        children = {
            "myapp": _make_child("myapp", prompts=[{"name": "help", "description": "Help"}])
        }
        state = _discover_all(clis, children)
        handler = _GatewayHandler(clis, state, children)

        result = handler.list_prompts({})
        assert len(result["prompts"]) == 1


# ---------------------------------------------------------------------------
# Idle reaping
# ---------------------------------------------------------------------------


class TestIdleReaper:
    def test_reap_idle_child(self):
        """Idle children get killed."""
        child = _make_child("taskman")
        child.is_idle.return_value = True
        children = {"taskman": child}

        # First sleep passes (reaper sleeps before checking), second raises
        call_count = [0]

        def _sleep_then_stop(_seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] > 1:
                raise StopIteration

        with patch("milo.gateway.time.sleep", side_effect=_sleep_then_stop):
            with pytest.raises(StopIteration):
                _idle_reaper(children)

        child.kill.assert_called_once()

    def test_keep_active_child(self):
        """Active children are not reaped."""
        child = _make_child("taskman")
        child.is_idle.return_value = False
        children = {"taskman": child}

        call_count = [0]

        def _sleep_then_stop(_seconds: float) -> None:
            call_count[0] += 1
            if call_count[0] > 1:
                raise StopIteration

        with patch("milo.gateway.time.sleep", side_effect=_sleep_then_stop):
            with pytest.raises(StopIteration):
                _idle_reaper(children)

        child.kill.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_discovery_tool_failure_continues(self):
        """If one CLI fails tool discovery, others still work."""
        clis = {
            "good": {"command": ["good"]},
            "bad": {"command": ["bad"]},
        }
        good_child = _make_child("good", tools=[{"name": "ok", "inputSchema": {}}])
        bad_child = _make_child("bad")
        bad_child.fetch_tools.side_effect = RuntimeError("connection refused")
        children = {"good": good_child, "bad": bad_child}

        state = _discover_all(clis, children)

        # Good CLI's tools should still be present
        assert len(state.tools) == 1
        assert state.tools[0]["name"] == "good.ok"

    def test_discovery_resource_failure_continues(self):
        """If resource discovery fails, tools and prompts still work."""
        clis = {"myapp": {"command": ["myapp"]}}
        child = _make_child(
            "myapp",
            tools=[{"name": "run", "inputSchema": {}}],
            prompts=[{"name": "help", "description": "Help"}],
        )
        # Override send_call to fail on resources/list
        original_side_effect = child.send_call.side_effect

        def _failing_resources(method, params, **kw):
            if method == "resources/list":
                raise ConnectionError("dead")
            return original_side_effect(method, params, **kw)

        child.send_call.side_effect = _failing_resources
        children = {"myapp": child}

        state = _discover_all(clis, children)

        assert len(state.tools) == 1
        assert len(state.prompts) == 1
        assert len(state.resources) == 0

    def test_proxy_call_empty_arguments(self):
        """Tool call with missing arguments key defaults to empty dict."""
        child = _make_child("taskman")
        children = {"taskman": child}
        routing = {"taskman.add": ("taskman", "add")}

        _proxy_call(children, routing, {"name": "taskman.add"})

        child.send_call.assert_called_once_with("tools/call", {"name": "add", "arguments": {}})

    def test_proxy_prompt_missing_arguments(self):
        """Prompt get with no arguments key defaults to empty dict."""
        child = _make_child("ghub")
        children = {"ghub": child}
        routing = {"ghub.review": ("ghub", "review")}

        _proxy_prompt(children, routing, {"name": "ghub.review"})

        child.send_call.assert_called_once_with("prompts/get", {"name": "review", "arguments": {}})
