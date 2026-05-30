"""Shared JSON-RPC output helpers for mcp.py and gateway.py."""

from __future__ import annotations

import json
import sys
from typing import Any

MCP_VERSION = "2025-11-25"
SUPPORTED_MCP_VERSIONS = (MCP_VERSION,)
MCP_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
UNSUPPORTED_PROTOCOL_VERSION = -32004


def _parse_request(line: str) -> tuple[Any, str, dict[str, Any], bool] | None:
    """Parse and validate one JSON-RPC request line.

    Returns ``(id, method, params, is_notification)`` or ``None`` after writing
    a JSON-RPC error response for malformed input.
    """
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        _write_error(None, -32700, "Parse error")
        return None

    if not isinstance(request, dict):
        _write_error(None, -32600, "Invalid Request")
        return None

    method = request.get("method")
    if not isinstance(method, str) or not method:
        _write_error(request.get("id"), -32600, "Invalid Request")
        return None

    params = request.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        _write_error(request.get("id"), -32602, "Invalid params")
        return None

    return request.get("id"), method, params, "id" not in request


def _write_result(req_id: Any, result: dict[str, Any]) -> None:
    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _write_error(
    req_id: Any, code: int, message: str, *, data: dict[str, Any] | None = None
) -> None:
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    response = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": error_obj,
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _write_notification(method: str, params: dict[str, Any]) -> None:
    """Write a JSON-RPC notification (no id field, no response expected)."""
    notification = {"jsonrpc": "2.0", "method": method, "params": params}
    sys.stdout.write(json.dumps(notification) + "\n")
    sys.stdout.flush()


def _stderr(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
