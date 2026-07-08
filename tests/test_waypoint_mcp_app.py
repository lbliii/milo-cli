"""MCP Apps attempt-graph proof for the Waypoint showcase (issue #102)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from milo import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE
from milo.gateway import _discover_all, _GatewayHandler
from milo.mcp import _CLIHandler
from milo.verify import verify

_ROOT = Path(__file__).resolve().parents[1]
_APP_PATH = _ROOT / "showcase" / "waypoint" / "app.py"
_GIT = shutil.which("git")


def _load_app() -> ModuleType:
    module_name = "_test_waypoint_mcp_app"
    spec = importlib.util.spec_from_file_location(module_name, _APP_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _git_run(repo: Path, *args: str) -> str:
    assert _GIT is not None
    completed = subprocess.run(
        (_GIT, "-C", str(repo), *args),
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


def _ui_capabilities() -> dict[str, Any]:
    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


@pytest.fixture
def graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    _git_run(tmp_path, "init", "-b", "main")
    _git_run(tmp_path, "config", "user.name", "Waypoint Apps Tests")
    _git_run(tmp_path, "config", "user.email", "waypoint-apps@example.test")
    _git_run(tmp_path, "config", "commit.gpgsign", "false")
    story = tmp_path / "story.txt"
    story.write_text("base\n", encoding="utf-8")
    _git_run(tmp_path, "add", "story.txt")
    _git_run(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)
    module = _load_app()
    module.create_intent("Race implementations", intent_id="race", agent="lead")
    story.write_text("alpha one\n", encoding="utf-8")
    module.create_checkpoint("race", "start alpha", attempt_id="alpha", agent="agent-a")
    story.write_text("alpha one\nalpha two\n", encoding="utf-8")
    module.create_checkpoint("race", "finish alpha", attempt_id="alpha", agent="agent-a")
    story.write_text("beta\n", encoding="utf-8")
    module.create_checkpoint("race", "try beta", attempt_id="beta", agent="agent-b")
    return module, tmp_path


class _WaypointChild:
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


def test_plain_host_gets_structured_graph_without_ui_advertisement(
    graph: tuple[ModuleType, Path],
) -> None:
    module, _ = graph
    handler = _CLIHandler(module.cli)
    tool = next(item for item in handler.list_tools({})["tools"] if item["name"] == "attempt-graph")
    assert "_meta" not in tool
    assert all(
        item["uri"] != "ui://waypoint/attempts" for item in handler.list_resources({})["resources"]
    )

    called = handler.call_tool({"name": "attempt-graph", "arguments": {"intent_id": "race"}})
    data = called["structuredContent"]
    assert data["intents"][0]["id"] == "race"
    assert [(item["attempt"], len(item["checkpoints"])) for item in data["attempts"]] == [
        ("alpha", 2),
        ("beta", 1),
    ]
    assert data["attempts"][0]["checkpoints"][1]["why"] == "finish alpha"


def test_apps_host_negotiates_link_resource_and_dependency_free_protocol(
    graph: tuple[ModuleType, Path],
) -> None:
    module, _ = graph
    handler = _CLIHandler(module.cli)
    initialized = handler.initialize(_ui_capabilities())
    assert initialized["capabilities"]["extensions"] == {
        MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]}
    }
    tool = next(item for item in handler.list_tools({})["tools"] if item["name"] == "attempt-graph")
    assert tool["_meta"]["ui"] == {
        "resourceUri": "ui://waypoint/attempts",
        "visibility": ["model", "app"],
    }
    resource = next(
        item
        for item in handler.list_resources({})["resources"]
        if item["uri"] == "ui://waypoint/attempts"
    )
    assert resource["mimeType"] == MCP_APPS_MIME_TYPE
    assert resource["_meta"]["ui"]["prefersBorder"] is True
    content = handler.read_resource({"uri": resource["uri"]})["contents"][0]
    html = content["text"]
    assert content["mimeType"] == MCP_APPS_MIME_TYPE
    assert "<script src=" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert 'request("ui/initialize"' in html
    assert 'request("tools/call"' in html
    assert "ui/notifications/tool-input" in html
    assert "ui/notifications/tool-result" in html
    assert "hostContext?.toolInfo?.tool?.name" in html
    assert "hostCapabilities?.serverTools" in html
    assert 'siblingTool(toolName, "pick")' in html
    assert "textContent" in html
    assert "Winner:" in html


def test_attempt_inspection_filter_and_invalid_filter_are_structured(
    graph: tuple[ModuleType, Path],
) -> None:
    module, _ = graph
    focused = module.attempt_graph(intent_id="race", attempt_id="beta")
    assert [item["attempt"] for item in focused["attempts"]] == ["beta"]
    assert focused["selected_attempt"] == "beta"
    with pytest.raises(ValueError, match="intent_id is required"):
        module.attempt_graph(attempt_id="beta")


def test_gateway_rewrites_tool_link_resource_and_calls_with_namespaced_identity(
    graph: tuple[ModuleType, Path],
) -> None:
    module, _ = graph
    child = _WaypointChild(module.cli)
    children: dict[str, Any] = {"waypoint": child}
    state = _discover_all({"waypoint": {}}, children)
    gateway = _GatewayHandler({"waypoint": {}}, state, children)
    gateway.initialize(_ui_capabilities())

    tool = next(
        item for item in gateway.list_tools({})["tools"] if item["name"] == "waypoint.attempt-graph"
    )
    uri = tool["_meta"]["ui"]["resourceUri"]
    assert uri.startswith("ui://milo-gateway/waypoint/")
    resources = gateway.list_resources({})["resources"]
    assert any(item["uri"] == uri and item["mimeType"] == MCP_APPS_MIME_TYPE for item in resources)
    content = gateway.read_resource({"uri": uri})["contents"][0]
    assert content["uri"] == uri
    assert "siblingTool(toolName" in content["text"]
    called = gateway.call_tool(
        {"name": "waypoint.attempt-graph", "arguments": {"intent_id": "race"}}
    )
    assert len(called["structuredContent"]["attempts"]) == 2


def test_waypoint_passes_all_mcp_apps_verifier_identities() -> None:
    report = verify(str(_APP_PATH), timeout=10.0)
    assert report.exit_code == 0, report.format()
    checks = {check.name: check for check in report.checks}
    for name in ("mcp_apps_in_process", "mcp_apps_gateway", "mcp_apps_transport"):
        assert checks[name].status == "ok"
        assert "1 tool link(s)" in checks[name].message
        assert "1 UI resource(s)" in checks[name].message
