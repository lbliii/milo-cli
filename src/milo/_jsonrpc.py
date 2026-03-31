"""Shared JSON-RPC output helpers for mcp.py and gateway.py."""

from __future__ import annotations

import json
import sys
from typing import Any

MCP_VERSION = "2025-11-25"


def _write_result(req_id: Any, result: dict[str, Any]) -> None:
    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _write_error(req_id: Any, code: int, message: str) -> None:
    response = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _stderr(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
