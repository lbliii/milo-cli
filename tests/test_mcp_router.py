"""Tests for milo._mcp_router — MCP method dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from milo._mcp_router import dispatch


class TestDispatch:
    def _make_handler(self):
        handler = MagicMock()
        handler.initialize.return_value = {"protocolVersion": "2025-11-25"}
        handler.list_tools.return_value = {"tools": []}
        handler.call_tool.return_value = {"content": []}
        handler.list_resources.return_value = {"resources": []}
        handler.read_resource.return_value = {"contents": []}
        handler.list_prompts.return_value = {"prompts": []}
        handler.get_prompt.return_value = {"messages": []}
        return handler

    def test_initialize(self):
        handler = self._make_handler()
        params = {"clientInfo": {"name": "test"}}
        result = dispatch(handler, "initialize", params)
        handler.initialize.assert_called_once_with(params)
        assert result == {"protocolVersion": "2025-11-25"}

    def test_tools_list(self):
        handler = self._make_handler()
        params = {}
        result = dispatch(handler, "tools/list", params)
        handler.list_tools.assert_called_once_with(params)
        assert result == {"tools": []}

    def test_tools_call(self):
        handler = self._make_handler()
        params = {"name": "greet", "arguments": {"name": "Alice"}}
        result = dispatch(handler, "tools/call", params)
        handler.call_tool.assert_called_once_with(params)
        assert result == {"content": []}

    def test_resources_list(self):
        handler = self._make_handler()
        params = {}
        result = dispatch(handler, "resources/list", params)
        handler.list_resources.assert_called_once_with(params)
        assert result == {"resources": []}

    def test_resources_read(self):
        handler = self._make_handler()
        params = {"uri": "config://app"}
        result = dispatch(handler, "resources/read", params)
        handler.read_resource.assert_called_once_with(params)
        assert result == {"contents": []}

    def test_prompts_list(self):
        handler = self._make_handler()
        params = {}
        result = dispatch(handler, "prompts/list", params)
        handler.list_prompts.assert_called_once_with(params)
        assert result == {"prompts": []}

    def test_prompts_get(self):
        handler = self._make_handler()
        params = {"name": "deploy-checklist"}
        result = dispatch(handler, "prompts/get", params)
        handler.get_prompt.assert_called_once_with(params)
        assert result == {"messages": []}

    def test_notifications_initialized_returns_none(self):
        handler = self._make_handler()
        result = dispatch(handler, "notifications/initialized", {})
        assert result is None
        # No handler method should be called for notifications
        handler.initialize.assert_not_called()
        handler.list_tools.assert_not_called()

    def test_unknown_method_raises_value_error(self):
        handler = self._make_handler()
        with pytest.raises(ValueError, match="Unknown method"):
            dispatch(handler, "nonexistent/method", {})

    def test_unknown_method_includes_method_name(self):
        handler = self._make_handler()
        with pytest.raises(ValueError, match="bogus/route"):
            dispatch(handler, "bogus/route", {})
