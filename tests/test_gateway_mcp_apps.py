"""Gateway integration contracts for stable MCP Apps resources and metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pytest

from milo import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE, MCPAppError
from milo._errors import ErrorCode
from milo.gateway import (
    _classify_gateway_exception,
    _discover_all,
    _gateway_ui_uri,
    _GatewayHandler,
)


def _ui_capabilities() -> dict[str, Any]:
    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


class _Child:
    """In-memory child transport covering discovery, calls, and resource reads."""

    def __init__(
        self,
        name: str,
        *,
        tools: list[dict[str, Any]],
        resources: list[dict[str, Any]],
    ) -> None:
        self.name = name
        self._tools = tools
        self._resources = resources
        self.read_error: dict[str, Any] | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def fetch_tools(self) -> list[dict[str, Any]]:
        return deepcopy(self._tools)

    def send_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, deepcopy(params)))
        if method == "resources/list":
            return {"resources": deepcopy(self._resources)}
        if method == "prompts/list":
            return {"prompts": []}
        if method == "tools/call":
            return {
                "content": [{"type": "text", "text": f"called {self.name}"}],
                "structuredContent": {"child": self.name, "arguments": params["arguments"]},
            }
        if method == "resources/read":
            if self.read_error is not None:
                return deepcopy(self.read_error)
            resource = next(item for item in self._resources if item["uri"] == params["uri"])
            return {
                "contents": [
                    {
                        "uri": resource["uri"],
                        "mimeType": resource["mimeType"],
                        "text": f"<!doctype html><p>{self.name}</p>",
                        "_meta": deepcopy(resource.get("_meta", {})),
                    }
                ]
            }
        return {}


def _ui_resource(uri: str = "ui://shared/view", *, name: str = "Shared view") -> dict[str, Any]:
    return {
        "uri": uri,
        "name": name,
        "description": "Interactive child view",
        "mimeType": MCP_APPS_MIME_TYPE,
        "_meta": {
            "ui": {
                "csp": {"connectDomains": ["https://api.example.test"]},
                "prefersBorder": True,
            }
        },
    }


def _ui_tool(uri: str = "ui://shared/view", *, name: str = "show") -> dict[str, Any]:
    return {
        "name": name,
        "description": "Show child data",
        "inputSchema": {"type": "object", "properties": {}},
        "_meta": {
            "ui": {"resourceUri": uri, "visibility": ["model", "app"]},
            "audit": {"source": "child"},
        },
    }


def test_single_child_round_trip_preserves_ui_contract_and_structured_content() -> None:
    child = _Child("weather", tools=[_ui_tool()], resources=[_ui_resource()])
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    gateway_uri = _gateway_ui_uri("weather", "ui://shared/view")

    assert state.tools[0]["name"] == "weather.show"
    assert state.tools[0]["_meta"] == {
        "ui": {"resourceUri": gateway_uri, "visibility": ["model", "app"]},
        "audit": {"source": "child"},
    }
    assert state.resources[0] == {
        **_ui_resource(),
        "uri": gateway_uri,
    }
    assert state.resource_routing[gateway_uri] == ("weather", "ui://shared/view")

    handler = _GatewayHandler(
        {
            "weather": {"command": ["weather"]},
        },
        state,
        {"weather": child},
    )
    initialized = handler.initialize(_ui_capabilities())
    assert initialized["capabilities"]["extensions"] == {
        MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
    }
    assert handler.list_tools({})["tools"] == state.tools
    assert handler.list_resources({})["resources"] == state.resources

    read = handler.read_resource({"uri": gateway_uri})
    assert read["contents"][0] == {
        "uri": gateway_uri,
        "mimeType": MCP_APPS_MIME_TYPE,
        "text": "<!doctype html><p>weather</p>",
        "_meta": _ui_resource()["_meta"],
    }
    called = handler.call_tool({"name": "weather.show", "arguments": {"city": "Oslo"}})
    assert called["structuredContent"] == {
        "child": "weather",
        "arguments": {"city": "Oslo"},
    }


def test_unnegotiated_host_gets_text_tool_fallback_and_no_ui_resources() -> None:
    regular = {
        "uri": "config://weather",
        "name": "config",
        "mimeType": "application/json",
    }
    child = _Child(
        "weather",
        tools=[_ui_tool()],
        resources=[_ui_resource(), regular],
    )
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    handler = _GatewayHandler({}, state, {"weather": child})

    initialized = handler.initialize({})
    assert "extensions" not in initialized["capabilities"]
    tool = handler.list_tools({})["tools"][0]
    assert tool["_meta"] == {"audit": {"source": "child"}}
    assert handler.list_resources({})["resources"] == [
        {**regular, "uri": "weather/config://weather"}
    ]

    gateway_uri = _gateway_ui_uri("weather", "ui://shared/view")
    with pytest.raises(MCPAppError) as exc_info:
        handler.read_resource({"uri": gateway_uri})
    assert exc_info.value.code is ErrorCode.UI_UNSUPPORTED
    assert exc_info.value.context["reason"] == "ui_extension_not_negotiated"


def test_multi_child_collision_rewrites_each_link_to_its_own_resource() -> None:
    alpha = _Child("alpha", tools=[_ui_tool()], resources=[_ui_resource()])
    beta = _Child("beta", tools=[_ui_tool()], resources=[_ui_resource()])
    clis = {"alpha": {"command": ["alpha"]}, "beta": {"command": ["beta"]}}
    children = {"alpha": alpha, "beta": beta}

    state = _discover_all(clis, children)
    alpha_uri = _gateway_ui_uri("alpha", "ui://shared/view")
    beta_uri = _gateway_ui_uri("beta", "ui://shared/view")

    assert alpha_uri != beta_uri
    assert [resource["uri"] for resource in state.resources] == [alpha_uri, beta_uri]
    assert [tool["_meta"]["ui"]["resourceUri"] for tool in state.tools] == [
        alpha_uri,
        beta_uri,
    ]

    handler = _GatewayHandler(clis, state, children)
    handler.initialize(_ui_capabilities())
    assert handler.read_resource({"uri": alpha_uri})["contents"][0]["text"].endswith("alpha</p>")
    assert handler.read_resource({"uri": beta_uri})["contents"][0]["text"].endswith("beta</p>")


def test_parallel_ui_discovery_order_is_deterministic_under_collisions() -> None:
    clis = {f"child-{index}": {"command": [f"child-{index}"]} for index in range(8)}
    children = {name: _Child(name, tools=[_ui_tool()], resources=[_ui_resource()]) for name in clis}
    expected_tools = [f"{name}.show" for name in clis]
    expected_resources = [_gateway_ui_uri(name, "ui://shared/view") for name in clis]

    for _ in range(20):
        state = _discover_all(clis, children)
        assert [tool["name"] for tool in state.tools] == expected_tools
        assert [resource["uri"] for resource in state.resources] == expected_resources


def test_namespacing_is_encoded_and_duplicate_child_entries_are_first_wins() -> None:
    first = _ui_resource(name="First")
    duplicate = _ui_resource(name="Duplicate")
    first_tool = _ui_tool()
    duplicate_tool = {**_ui_tool(), "description": "Duplicate tool"}
    child = _Child(
        "team/weather",
        tools=[first_tool, duplicate_tool],
        resources=[first, duplicate],
    )

    state = _discover_all(
        {"team/weather": {"command": ["weather"]}},
        {"team/weather": child},
    )

    assert _gateway_ui_uri("team/weather", "ui://shared/view") == (
        "ui://milo-gateway/team%2Fweather/ui%3A%2F%2Fshared%2Fview"
    )
    assert len(state.resources) == 1
    assert state.resources[0]["name"] == "First"
    assert len(state.tools) == 1
    assert state.tools[0]["description"] == "Show child data"


def test_missing_child_link_is_not_advertised_as_a_broken_ui_reference() -> None:
    child = _Child("broken", tools=[_ui_tool("ui://missing/view")], resources=[])
    state = _discover_all({"broken": {"command": ["broken"]}}, {"broken": child})

    assert state.tools[0]["_meta"] == {
        "ui": {"visibility": ["model", "app"]},
        "audit": {"source": "child"},
    }
    assert state.resources == []


def test_malformed_ui_resource_is_omitted_and_cannot_satisfy_a_tool_link() -> None:
    malformed = {**_ui_resource(), "mimeType": "text/html"}
    child = _Child("broken", tools=[_ui_tool()], resources=[malformed])
    state = _discover_all({"broken": {"command": ["broken"]}}, {"broken": child})

    assert state.resources == []
    assert state.tools[0]["_meta"]["ui"] == {"visibility": ["model", "app"]}


def test_ui_resource_lifecycle_failures_return_repairable_gateway_errors() -> None:
    child = _Child("weather", tools=[_ui_tool()], resources=[_ui_resource()])
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    uri = _gateway_ui_uri("weather", "ui://shared/view")
    handler = _GatewayHandler({}, state, {"weather": child})
    handler.initialize(_ui_capabilities())

    with pytest.raises(MCPAppError) as unknown:
        handler.read_resource({"uri": "ui://milo-gateway/unknown/resource"})
    assert unknown.value.code is ErrorCode.UI_RESOURCE_NOT_FOUND
    assert unknown.value.context["reason"] == "unknown_gateway_ui_resource"

    unavailable = _GatewayHandler({}, state, {})
    unavailable.initialize(_ui_capabilities())
    with pytest.raises(MCPAppError) as missing_child:
        unavailable.read_resource({"uri": uri})
    assert missing_child.value.code is ErrorCode.UI_RESOURCE_READ
    assert missing_child.value.context["reason"] == "cli_unavailable"

    child.read_error = {
        "error": {
            "code": -32603,
            "message": "No response from weather",
            "data": {"reason": "child_timeout", "child": "weather"},
        }
    }
    with pytest.raises(MCPAppError) as timeout:
        handler.read_resource({"uri": uri})
    assert timeout.value.code is ErrorCode.UI_RESOURCE_READ
    assert timeout.value.context["reason"] == "child_timeout"
    assert timeout.value.context["childCode"] == -32603
    code, data = _classify_gateway_exception(timeout.value)
    assert code == -32602
    assert data is not None
    assert data["resourceUri"] == uri
    assert data["child"] == "weather"


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("child_disconnected", -32603),
        ("child_parse_error", -32700),
    ],
)
def test_gateway_preserves_child_disconnect_and_parse_reasons(reason: str, code: int) -> None:
    child = _Child("weather", tools=[_ui_tool()], resources=[_ui_resource()])
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    uri = _gateway_ui_uri("weather", "ui://shared/view")
    child.read_error = {
        "error": {
            "code": code,
            "message": f"weather: {reason}",
            "data": {"reason": reason, "child": "weather"},
        }
    }
    handler = _GatewayHandler({}, state, {"weather": child})
    handler.initialize(_ui_capabilities())

    with pytest.raises(MCPAppError) as exc_info:
        handler.read_resource({"uri": uri})
    assert exc_info.value.context["reason"] == reason
    assert exc_info.value.context["childCode"] == code


def test_gateway_wraps_child_transport_exception_without_leaking_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    child = _Child("weather", tools=[_ui_tool()], resources=[_ui_resource()])
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    uri = _gateway_ui_uri("weather", "ui://shared/view")
    handler = _GatewayHandler({}, state, {"weather": child})
    handler.initialize(_ui_capabilities())

    with (
        patch.object(child, "send_call", side_effect=BrokenPipeError("child stdin closed")),
        pytest.raises(MCPAppError) as exc_info,
    ):
        handler.read_resource({"uri": uri})
    assert exc_info.value.context["reason"] == "child_transport_error"
    assert capsys.readouterr().out == ""


def test_gateway_discovery_advertises_mcp_apps_support() -> None:
    handler = _GatewayHandler({}, _discover_all({}, {}), {})
    discovered = handler.server_discover({})
    assert discovered["capabilities"]["extensions"] == {
        MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
    }


def test_stateless_client_capabilities_enable_ui_per_request() -> None:
    child = _Child("weather", tools=[_ui_tool()], resources=[_ui_resource()])
    state = _discover_all({"weather": {"command": ["weather"]}}, {"weather": child})
    handler = _GatewayHandler({}, state, {"weather": child})
    request_meta = {
        "_meta": {"io.modelcontextprotocol/clientCapabilities": _ui_capabilities()["capabilities"]}
    }

    assert handler.list_tools(request_meta)["tools"] == state.tools
    assert handler.list_resources(request_meta)["resources"] == state.resources
    uri = _gateway_ui_uri("weather", "ui://shared/view")
    assert handler.read_resource({"uri": uri, **request_meta})["contents"][0]["uri"] == uri
