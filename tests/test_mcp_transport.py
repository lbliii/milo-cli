"""Transport-level JSON-RPC behavior for leaf MCP server."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from milo.commands import CLI
from milo.mcp import run_mcp_server


def _run_server(input_text: str) -> list[dict]:
    cli = CLI(name="transport", description="")
    stdin = io.StringIO(input_text)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
        run_mcp_server(cli)
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def test_non_object_json_gets_invalid_request_error() -> None:
    responses = _run_server("[]\n")
    assert responses[0]["error"]["code"] == -32600


def test_unknown_method_gets_method_not_found_error() -> None:
    responses = _run_server('{"jsonrpc":"2.0","id":1,"method":"nope"}\n')
    assert responses[0]["id"] == 1
    assert responses[0]["error"]["code"] == -32601


def test_server_discover_lists_supported_versions() -> None:
    responses = _run_server('{"jsonrpc":"2.0","id":1,"method":"server/discover"}\n')
    assert responses[0]["result"]["supportedVersions"] == ["2026-07-28", "2025-11-25"]
    assert responses[0]["result"]["resultType"] == "complete"
    assert responses[0]["result"]["serverInfo"]["name"] == "transport"


def test_explicit_unsupported_protocol_version_returns_repair_data() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}},
    }
    responses = _run_server(json.dumps(request) + "\n")
    error = responses[0]["error"]
    assert error["code"] == -32022
    assert error["data"]["supported"] == ["2026-07-28", "2025-11-25"]
    assert error["data"]["requested"] == "1900-01-01"


def test_json_rpc_notification_gets_no_response() -> None:
    responses = _run_server('{"jsonrpc":"2.0","method":"tools/list"}\n')
    assert responses == []
