"""Contract tests for the stable MCP Apps UI extension."""

from __future__ import annotations

import base64
import io
import json
import runpy
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_args
from unittest.mock import patch

import pytest

from milo import (
    CLI,
    MCP_APPS_EXTENSION_ID,
    MCP_APPS_MIME_TYPE,
    MCPAppCSP,
    MCPAppError,
    MCPAppPermissions,
    MCPAppResourceDef,
    MCPAppResourceMeta,
    MCPAppToolMeta,
    MCPAppVisibility,
)
from milo._errors import ErrorCode
from milo._jsonrpc import (
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
)
from milo._mcp_router import UnsupportedProtocolVersionError, dispatch
from milo.mcp import (
    _classify_exception,
    _CLIHandler,
    _list_resources,
    _list_tools,
    _list_ui_resources,
    _read_ui_resource,
    run_mcp_server,
)


def _ui_capabilities() -> dict[str, object]:
    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


def _modern_params(*, ui: bool) -> dict[str, object]:
    capabilities = _ui_capabilities()["capabilities"] if ui else {}
    return {
        "_meta": {
            MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION,
            MCP_CLIENT_INFO_META_KEY: {"name": "ui-client", "version": "1.0"},
            MCP_CLIENT_CAPABILITIES_META_KEY: capabilities,
        }
    }


def _make_ui_cli() -> CLI:
    cli = CLI(name="weather", description="Weather tools")

    @cli.ui_resource(
        "ui://weather/dashboard",
        name="Weather dashboard",
        description="Interactive forecast",
        meta=MCPAppResourceMeta(
            csp=MCPAppCSP(
                connect_domains=["https://api.weather.test"],
                resource_domains=("https://cdn.weather.test",),
            ),
            permissions=MCPAppPermissions(geolocation=True),
            domain="weather.example.test",
            prefers_border=False,
        ),
    )
    def dashboard() -> str:
        return "<!doctype html><html><body>Weather</body></html>"

    @cli.command(
        "forecast",
        description="Get the forecast",
        ui=MCPAppToolMeta("ui://weather/dashboard"),
    )
    def forecast(city: str = "Boston") -> dict[str, str]:
        return {"city": city, "condition": "sunny"}

    @cli.command(
        "refresh",
        ui=MCPAppToolMeta("ui://weather/dashboard", visibility=("app",)),
    )
    def refresh() -> dict[str, bool]:
        return {"refreshed": True}

    return cli


def test_typed_contracts_are_frozen_and_validate_protocol_values() -> None:
    assert get_args(MCPAppVisibility) == ("model", "app")
    meta = MCPAppToolMeta("ui://weather/dashboard", visibility=("model", "model"))
    assert meta.visibility == ("model",)
    with pytest.raises(FrozenInstanceError):
        meta.resource_uri = "ui://other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="ui://"):
        MCPAppToolMeta("https://example.test/dashboard")
    with pytest.raises(ValueError, match="visibility"):
        MCPAppToolMeta("ui://weather/dashboard", visibility=())
    with pytest.raises(ValueError, match="visibility"):
        MCPAppToolMeta(
            "ui://weather/dashboard",
            visibility=("other",),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="non-empty strings"):
        MCPAppCSP(connect_domains=[""])
    with pytest.raises(ValueError, match="must use"):
        MCPAppResourceDef(
            uri="ui://weather/dashboard",
            name="dashboard",
            description="",
            handler=lambda: "<!doctype html><html></html>",
            mime_type="text/html",
        )


def test_ui_resource_registration_reserves_scheme_and_rejects_duplicates() -> None:
    cli = CLI(name="app")
    with pytest.raises(ValueError, match="ui_resource"):
        cli.resource("ui://app/view")

    decorator = cli.ui_resource("ui://app/view")
    decorator(lambda: "<!doctype html><html></html>")
    with pytest.raises(ValueError, match="already registered"):
        cli.ui_resource("ui://app/view")


def test_grouped_and_mounted_tools_preserve_stable_ui_links() -> None:
    child = CLI(name="child")

    @child.ui_resource("ui://child/view")
    def child_view() -> str:
        return "<!doctype html><html></html>"

    admin = child.group("admin")

    @admin.command("show", ui=MCPAppToolMeta("ui://child/view"))
    def show() -> str:
        return "shown"

    root = CLI(name="root")
    root.mount("child", child)
    assert _list_tools(root)[0]["name"] == "child.admin.show"
    assert _list_tools(root)[0]["_meta"]["ui"]["resourceUri"] == "ui://child/view"
    assert root.walk_ui_resources()[0][0] == "ui://child/view"

    colliding = CLI(name="colliding")

    @colliding.ui_resource("ui://child/view")
    def colliding_view() -> str:
        return "<!doctype html><html></html>"

    before_groups = root.groups
    with pytest.raises(ValueError, match="collision"):
        root.mount("collision", colliding)
    assert root.groups == before_groups


def test_initialize_negotiates_extension_and_server_discover_advertises_support() -> None:
    handler = _CLIHandler(_make_ui_cli())

    fallback = dispatch(handler, "initialize", {})
    assert fallback is not None
    assert "extensions" not in fallback["capabilities"]

    unsupported = handler.initialize(
        {
            "capabilities": {
                "extensions": {
                    MCP_APPS_EXTENSION_ID: {"mimeTypes": ["text/html"]},
                }
            }
        }
    )
    assert "extensions" not in unsupported["capabilities"]

    negotiated = dispatch(handler, "initialize", _ui_capabilities())
    assert negotiated is not None
    assert negotiated["capabilities"]["extensions"] == {
        MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
    }

    discovered = dispatch(handler, "server/discover", {})
    assert discovered is not None
    assert MCP_APPS_EXTENSION_ID in discovered["capabilities"]["extensions"]


def test_modern_ui_negotiation_is_request_scoped_without_state_leakage() -> None:
    handler = _CLIHandler(_make_ui_cli())

    negotiated = dispatch(handler, "tools/list", _modern_params(ui=True))
    plain = dispatch(handler, "tools/list", _modern_params(ui=False))
    negotiated_again = dispatch(handler, "tools/list", _modern_params(ui=True))

    assert negotiated is not None
    assert plain is not None
    assert negotiated_again is not None
    assert "_meta" in negotiated["tools"][0]
    assert "_meta" not in plain["tools"][0]
    assert negotiated_again["tools"] == negotiated["tools"]


def test_modern_ui_negotiation_is_isolated_across_free_threaded_requests() -> None:
    handler = _CLIHandler(_make_ui_cli())

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(dispatch, handler, "tools/list", _modern_params(ui=index % 2 == 0))
            for index in range(100)
        ]

    for index, future in enumerate(futures):
        result = future.result()
        assert result is not None
        if index % 2 == 0:
            assert "_meta" in result["tools"][0]
        else:
            assert "_meta" not in result["tools"][0]


def test_negotiated_list_and_read_round_trip_preserves_metadata() -> None:
    cli = _make_ui_cli()
    handler = _CLIHandler(cli)
    handler.initialize(_ui_capabilities())

    tools = handler.list_tools({})["tools"]
    assert [tool["name"] for tool in tools] == ["forecast"]
    assert tools[0]["_meta"] == {
        "ui": {
            "resourceUri": "ui://weather/dashboard",
            "visibility": ["model", "app"],
        }
    }

    resources = handler.list_resources({})["resources"]
    resource = next(item for item in resources if item["uri"] == "ui://weather/dashboard")
    assert resource["mimeType"] == MCP_APPS_MIME_TYPE
    assert resource["_meta"]["ui"] == {
        "csp": {
            "connectDomains": ["https://api.weather.test"],
            "resourceDomains": ["https://cdn.weather.test"],
        },
        "permissions": {"geolocation": {}},
        "domain": "weather.example.test",
        "prefersBorder": False,
    }

    result = handler.read_resource({"uri": "ui://weather/dashboard"})
    content = result["contents"][0]
    assert content["uri"] == tools[0]["_meta"]["ui"]["resourceUri"]
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    assert content["text"].startswith("<!doctype html>")
    assert content["_meta"] == resource["_meta"]
    app_call = handler.call_tool({"name": "refresh", "arguments": {}})
    assert app_call["structuredContent"] == {"refreshed": True}


def test_negotiated_dispatch_routes_list_read_and_call_end_to_end() -> None:
    handler = _CLIHandler(_make_ui_cli())
    initialized = dispatch(handler, "initialize", _ui_capabilities())
    assert initialized is not None

    listed_tools = dispatch(handler, "tools/list", {})
    listed_resources = dispatch(handler, "resources/list", {})
    read = dispatch(handler, "resources/read", {"uri": "ui://weather/dashboard"})
    called = dispatch(
        handler,
        "tools/call",
        {"name": "forecast", "arguments": {"city": "Tokyo"}},
    )

    assert listed_tools is not None
    assert listed_tools["tools"][0]["_meta"]["ui"]["resourceUri"] == ("ui://weather/dashboard")
    assert listed_resources is not None
    assert any(
        resource["uri"] == "ui://weather/dashboard" for resource in listed_resources["resources"]
    )
    assert read is not None
    assert read["contents"][0]["mimeType"] == MCP_APPS_MIME_TYPE
    assert called is not None
    assert called["structuredContent"] == {"city": "Tokyo", "condition": "sunny"}


def test_json_rpc_transport_covers_ui_round_trip_and_repair_errors() -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": _ui_capabilities(),
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "ui://weather/dashboard"},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "forecast", "arguments": {"city": "Seoul"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "ui://weather/missing"},
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/read",
            "params": {"uri": "ui://"},
        },
    ]
    stdin = io.StringIO("".join(f"{json.dumps(request)}\n" for request in requests))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
        run_mcp_server(_make_ui_cli())

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["result"]["capabilities"]["extensions"]
    assert responses[1]["result"]["tools"][0]["_meta"]["ui"]["resourceUri"] == (
        "ui://weather/dashboard"
    )
    assert any(
        resource["uri"] == "ui://weather/dashboard"
        for resource in responses[2]["result"]["resources"]
    )
    assert responses[3]["result"]["contents"][0]["mimeType"] == MCP_APPS_MIME_TYPE
    assert responses[4]["result"]["structuredContent"] == {
        "city": "Seoul",
        "condition": "sunny",
    }

    missing = responses[5]["error"]
    assert missing["code"] == -32602
    assert missing["data"]["errorCode"] == "M-UI-002"
    assert missing["data"]["reason"] == "missing_ui_resource"
    assert missing["data"]["resourceUri"] == "ui://weather/missing"
    assert "suggestion" in missing["data"]

    malformed = responses[6]["error"]
    assert malformed["code"] == -32602
    assert malformed["data"]["errorCode"] == "M-UI-001"
    assert malformed["data"]["reason"] == "invalid_ui_resource_uri"


def test_unnegotiated_connection_gets_text_fallback_and_no_ui_resources() -> None:
    cli = _make_ui_cli()
    handler = _CLIHandler(cli)
    handler.initialize({})

    tools = handler.list_tools({})["tools"]
    assert [tool["name"] for tool in tools] == ["forecast"]
    assert "_meta" not in tools[0]
    assert all(
        not item["uri"].startswith("ui://") for item in handler.list_resources({})["resources"]
    )
    with pytest.raises(MCPAppError) as exc_info:
        handler.read_resource({"uri": "ui://weather/dashboard"})
    assert exc_info.value.code is ErrorCode.UI_UNSUPPORTED
    assert exc_info.value.context["reason"] == "ui_extension_not_negotiated"
    code, data = _classify_exception(exc_info.value)
    assert code == -32602
    assert data is not None
    assert data["errorCode"] == "M-UI-003"
    assert data["reason"] == "ui_extension_not_negotiated"


def test_linked_missing_resource_is_repairable_and_not_advertised() -> None:
    cli = CLI(name="broken")

    @cli.command("broken", ui=MCPAppToolMeta("ui://broken/missing"))
    def broken() -> str:
        return "fallback"

    with pytest.raises(MCPAppError) as exc_info:
        _list_tools(cli)
    error = exc_info.value
    assert error.code is ErrorCode.UI_RESOURCE_NOT_FOUND
    assert error.context == {
        "reason": "missing_ui_resource",
        "tool": "broken",
        "resourceUri": "ui://broken/missing",
    }
    code, data = _classify_exception(error)
    assert code == -32602
    assert data is not None
    assert data["resourceUri"] == "ui://broken/missing"
    assert _list_tools(cli, include_ui=False)[0]["name"] == "broken"


def test_missing_malformed_and_invalid_content_resources_are_structured() -> None:
    cli = _make_ui_cli()
    with pytest.raises(MCPAppError) as malformed:
        _read_ui_resource(cli, {"uri": 1}, enabled=True)
    assert malformed.value.code is ErrorCode.UI_INVALID_RESOURCE

    with pytest.raises(MCPAppError) as missing:
        _read_ui_resource(cli, {"uri": "ui://missing/view"}, enabled=True)
    assert missing.value.code is ErrorCode.UI_RESOURCE_NOT_FOUND

    invalid = CLI(name="invalid")

    @invalid.ui_resource("ui://invalid/view")
    def invalid_view() -> dict[str, str]:  # type: ignore[return-value]
        return {"html": "no"}

    with pytest.raises(MCPAppError) as invalid_content:
        _read_ui_resource(invalid, {"uri": "ui://invalid/view"}, enabled=True)
    assert invalid_content.value.code is ErrorCode.UI_INVALID_RESOURCE

    failed = CLI(name="failed")

    @failed.ui_resource("ui://failed/view")
    def failed_view() -> str:
        raise RuntimeError("template missing")

    with pytest.raises(MCPAppError) as failed_read:
        _read_ui_resource(failed, {"uri": "ui://failed/view"}, enabled=True)
    assert failed_read.value.code is ErrorCode.UI_RESOURCE_READ
    assert failed_read.value.context["reason"] == "ui_resource_read_failed"


def test_binary_resource_content_is_deterministic_base64() -> None:
    cli = CLI(name="binary")

    @cli.ui_resource("ui://binary/view")
    def binary_view() -> bytes:
        return b"<!doctype html><html></html>"

    result = _read_ui_resource(cli, {"uri": "ui://binary/view"}, enabled=True)
    blob = result["contents"][0]["blob"]
    assert base64.b64decode(blob) == b"<!doctype html><html></html>"


def test_existing_resources_and_ui_tool_calls_remain_unchanged() -> None:
    cli = _make_ui_cli()

    @cli.resource("config://weather", mime_type="application/json")
    def config() -> dict[str, bool]:
        return {"metric": True}

    assert _list_resources(cli) == [
        {
            "uri": "config://weather",
            "name": "config",
            "description": "",
            "mimeType": "application/json",
        }
    ]
    assert len(_list_ui_resources(cli)) == 1
    result = _CLIHandler(cli).call_tool({"name": "forecast", "arguments": {"city": "Paris"}})
    assert result["structuredContent"] == {"city": "Paris", "condition": "sunny"}


def test_lazy_tool_link_serializes_without_importing_handler() -> None:
    cli = CLI(name="lazy")

    @cli.ui_resource("ui://lazy/view")
    def view() -> str:
        return "<!doctype html><html></html>"

    lazy = cli.lazy_command(
        "forecast",
        "module_that_must_not_import:forecast",
        schema={"type": "object", "properties": {}},
        ui=MCPAppToolMeta("ui://lazy/view"),
    )

    tools = _list_tools(cli)
    assert lazy._resolved is None
    assert tools[0]["_meta"]["ui"]["resourceUri"] == "ui://lazy/view"


def test_existing_protocol_version_rejection_still_precedes_ui_dispatch() -> None:
    handler = _CLIHandler(_make_ui_cli())
    with pytest.raises(UnsupportedProtocolVersionError):
        dispatch(
            handler,
            "resources/list",
            {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}},
        )


def test_minimal_public_example_keeps_structured_fallback() -> None:
    path = Path(__file__).parents[1] / "examples" / "mcp_app" / "app.py"
    namespace = runpy.run_path(str(path))
    cli = namespace["cli"]

    invoked = cli.invoke(["forecast", "--city", "Oslo", "--format", "json"])
    assert invoked.exit_code == 0
    assert invoked.result == {
        "city": "Oslo",
        "condition": "sunny",
        "temperature_f": 72,
    }
    tool = _list_tools(cli)[0]
    assert tool["_meta"]["ui"]["resourceUri"] == "ui://weather-app/forecast"
