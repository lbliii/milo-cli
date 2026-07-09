"""Dependency-free ASGI MCP request and concurrent batch benchmarks."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from conftest import _build_cli

from milo._jsonrpc import (
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
)


def _request(request_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "cmd-0",
            "arguments": {"value": "bench", "count": 1},
            "_meta": {
                MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION,
                MCP_CLIENT_INFO_META_KEY: {"name": "benchmark", "version": "1.0"},
                MCP_CLIENT_CAPABILITIES_META_KEY: {},
            },
        },
    }


async def _exchange(app: Any, request: dict[str, Any]) -> bytes:
    body = json.dumps(request).encode()
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": (
                (b"content-type", b"application/json"),
                (b"accept", b"application/json, text/event-stream"),
                (b"mcp-protocol-version", MCP_VERSION.encode()),
                (b"mcp-method", b"tools/call"),
                (b"mcp-name", b"cmd-0"),
            ),
        },
        receive,
        send,
    )
    return b"".join(message.get("body", b"") for message in sent[1:])


def test_bench_mcp_http_tool_call(benchmark) -> None:
    """One ASGI POST: parse, validate headers, thread dispatch, serialize."""
    app = _build_cli(5).asgi_app()
    request = _request()
    runner = asyncio.Runner()
    try:
        benchmark(lambda: runner.run(_exchange(app, request)))
    finally:
        runner.close()


def test_bench_mcp_http_parallel_8(benchmark) -> None:
    """Eight independent ASGI tool calls scheduled on the worker pool."""
    app = _build_cli(5).asgi_app()
    requests = tuple(_request(index) for index in range(1, 9))

    async def batch() -> list[bytes]:
        return await asyncio.gather(*(_exchange(app, request) for request in requests))

    runner = asyncio.Runner()
    try:
        benchmark(lambda: runner.run(batch()))
    finally:
        runner.close()
