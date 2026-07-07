"""Cross-surface proof for the dependency-free MCP Apps example (issue #82)."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from milo import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE, generate_llms_txt
from milo.gateway import _discover_all, _GatewayHandler
from milo.mcp import _CLIHandler
from milo.schema import function_to_schema
from milo.verify import verify

_ROOT = Path(__file__).resolve().parents[1]
_APP_PATH = _ROOT / "examples" / "mcp_app" / "app.py"


def _load_example() -> dict[str, Any]:
    return runpy.run_path(str(_APP_PATH))


def _ui_capabilities() -> dict[str, Any]:
    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


class _ExampleChild:
    """In-process child exposing the same calls used by the real gateway."""

    def __init__(self, cli: Any) -> None:
        self._handler = _CLIHandler(cli)
        self._handler.initialize(_ui_capabilities())

    def fetch_tools(self) -> list[dict[str, Any]]:
        return self._handler.list_tools({})["tools"]

    def send_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        methods: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "tools/call": self._handler.call_tool,
            "resources/list": self._handler.list_resources,
            "resources/read": self._handler.read_resource,
            "prompts/list": self._handler.list_prompts,
        }
        return methods[method](params)


def test_example_is_single_file_dependency_free_and_app_owned() -> None:
    source = _APP_PATH.read_text(encoding="utf-8")
    assert "from milo import" in source
    assert "import chirp" not in source
    assert "<script src=" not in source
    assert "ui/initialize" in source
    assert "ui/notifications/initialized" in source
    assert "ui/notifications/tool-input" in source
    assert "ui/notifications/tool-result" in source
    assert 'request("tools/call"' in source


def test_example_cli_schema_and_llms_txt_share_one_typed_function() -> None:
    namespace = _load_example()
    cli = namespace["cli"]
    forecast = namespace["forecast"]

    schema = function_to_schema(forecast)
    assert schema["properties"]["city"] == {
        "type": "string",
        "description": "City to forecast.",
        "default": "Boston",
    }
    invoked = cli.invoke(["forecast", "--city", "Oslo", "--format", "json"])
    assert invoked.exit_code == 0
    assert invoked.result == {
        "city": "Oslo",
        "condition": "sunny",
        "temperature_f": 72,
    }
    llms = generate_llms_txt(cli)
    assert "**forecast**: Get a weather forecast" in llms
    assert '`--city` (string, optional, default: "Boston")' in llms


def test_example_mcp_tool_resource_and_browser_protocol_round_trip() -> None:
    cli = _load_example()["cli"]
    handler = _CLIHandler(cli)
    initialized = handler.initialize(_ui_capabilities())
    assert initialized["capabilities"]["extensions"] == {
        MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
    }

    tool = handler.list_tools({})["tools"][0]
    assert tool["_meta"]["ui"]["resourceUri"] == "ui://weather-app/forecast"
    assert tool["inputSchema"]["properties"]["city"]["default"] == "Boston"
    called = handler.call_tool({"name": "forecast", "arguments": {"city": "Kyoto"}})
    assert called["structuredContent"] == {
        "city": "Kyoto",
        "condition": "sunny",
        "temperature_f": 72,
    }

    resource = next(
        item
        for item in handler.list_resources({})["resources"]
        if item["uri"] == "ui://weather-app/forecast"
    )
    assert resource["mimeType"] == MCP_APPS_MIME_TYPE
    assert resource["_meta"]["ui"]["prefersBorder"] is True
    content = handler.read_resource({"uri": resource["uri"]})["contents"][0]
    assert content["uri"] == resource["uri"]
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    assert 'request("ui/initialize"' in content["text"]
    assert "result?.hostContext?.toolInfo?.tool?.name" in content["text"]
    assert "result?.hostCapabilities?.serverTools" in content["text"]
    assert 'request("tools/call"' in content["text"]


def test_example_gateway_rewrites_links_reads_and_calls_without_losing_data() -> None:
    cli = _load_example()["cli"]
    child = _ExampleChild(cli)
    children: dict[str, Any] = {"weather": child}
    state = _discover_all({"weather": {}}, children)
    gateway = _GatewayHandler({"weather": {}}, state, children)
    gateway.initialize(_ui_capabilities())

    tool = gateway.list_tools({})["tools"][0]
    resource_uri = tool["_meta"]["ui"]["resourceUri"]
    assert tool["name"] == "weather.forecast"
    assert resource_uri.startswith("ui://milo-gateway/weather/")
    resources = gateway.list_resources({})["resources"]
    assert any(
        item["uri"] == resource_uri and item["mimeType"] == MCP_APPS_MIME_TYPE for item in resources
    )

    content = gateway.read_resource({"uri": resource_uri})["contents"][0]
    assert content["uri"] == resource_uri
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    called = gateway.call_tool({"name": "weather.forecast", "arguments": {"city": "Reykjavik"}})
    assert called["structuredContent"]["city"] == "Reykjavik"


def test_example_passes_all_mcp_apps_verifier_identities() -> None:
    report = verify(str(_APP_PATH), timeout=10.0)
    assert report.exit_code == 0, report.format()
    checks = {check.name: check for check in report.checks}
    for name in ("mcp_apps_in_process", "mcp_apps_gateway", "mcp_apps_transport"):
        assert checks[name].status == "ok"
        assert "1 tool link(s)" in checks[name].message
        assert "1 UI resource(s)" in checks[name].message


def test_example_docs_explain_framework_owned_html_boundary() -> None:
    readme = (_ROOT / "examples" / "mcp_app" / "README.md").read_text(encoding="utf-8")
    index = (_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    assert "no web" in readme
    assert "npm package, CDN, or runtime dependency" in readme
    assert "Chirp" in readme
    assert "let that framework produce the HTML resource" in readme
    assert "When Chirp or another web framework" in index
