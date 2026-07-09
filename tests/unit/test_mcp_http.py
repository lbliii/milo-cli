"""Streamable HTTP ASGI, security, and free-threading contracts."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from milo import CLI, Progress
from milo._jsonrpc import (
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
)
from milo.mcp_http import MCPASGIApp


def _modern_params(**params: object) -> dict[str, object]:
    return {
        **params,
        "_meta": {
            MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION,
            MCP_CLIENT_INFO_META_KEY: {"name": "http-test", "version": "1.0"},
            MCP_CLIENT_CAPABILITIES_META_KEY: {},
        },
    }


def _request(
    method: str,
    *,
    params: dict[str, object] | None = None,
    request_id: int = 1,
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": _modern_params(**(params or {})),
    }


def _headers(
    method: str,
    *,
    name: str | None = None,
    extra: tuple[tuple[bytes, bytes], ...] = (),
) -> tuple[tuple[bytes, bytes], ...]:
    headers = [
        (b"content-type", b"application/json"),
        (b"accept", b"application/json, text/event-stream"),
        (b"mcp-protocol-version", MCP_VERSION.encode("ascii")),
        (b"mcp-method", method.encode("ascii")),
    ]
    if name is not None:
        try:
            encoded_name = name.encode("ascii")
        except UnicodeEncodeError:
            encoded_name = b"=?base64?" + base64.b64encode(name.encode("utf-8")) + b"?="
        headers.append((b"mcp-name", encoded_name))
    headers.extend(extra)
    return tuple(headers)


async def _asgi_exchange(
    app: MCPASGIApp,
    body: bytes,
    *,
    method: str = "POST",
    path: str = "/mcp",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    chunks: tuple[bytes, ...] | None = None,
) -> list[dict]:
    events = []
    request_chunks = chunks or (body,)
    for index, chunk in enumerate(request_chunks):
        events.append(
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(request_chunks) - 1,
            }
        )

    async def receive() -> dict:
        return events.pop(0)

    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8000),
        },
        receive,
        send,
    )
    return sent


def _exchange(
    app: MCPASGIApp,
    request: dict[str, object] | bytes,
    *,
    method: str = "POST",
    path: str = "/mcp",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    chunks: tuple[bytes, ...] | None = None,
) -> tuple[int, dict[bytes, bytes], bytes]:
    body = request if isinstance(request, bytes) else json.dumps(request).encode("utf-8")
    sent = asyncio.run(
        _asgi_exchange(
            app,
            body,
            method=method,
            path=path,
            headers=headers,
            chunks=chunks,
        )
    )
    start = sent[0]
    response_headers = dict(start.get("headers", ()))
    response_body = b"".join(message.get("body", b"") for message in sent[1:])
    return start["status"], response_headers, response_body


def _json(body: bytes) -> dict:
    return json.loads(body)


@pytest.fixture
def cli() -> CLI:
    app = CLI(name="http-test", description="HTTP test CLI", version="1.0")

    @app.command("greet")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    @app.resource("config://app")
    def config() -> str:
        return "ok"

    return app


def test_asgi_discovery_and_tool_call_match_stdio_router(cli: CLI) -> None:
    app = cli.asgi_app()
    discover = _request("server/discover")
    status, response_headers, body = _exchange(
        app,
        discover,
        headers=_headers("server/discover"),
    )

    assert status == 200
    assert response_headers[b"content-type"] == b"application/json"
    result = _json(body)["result"]
    assert result["supportedVersions"] == ["2026-07-28", "2025-11-25"]
    assert result["resultType"] == "complete"

    call = _request("tools/call", params={"name": "greet", "arguments": {"name": "Ada"}})
    status, _, body = _exchange(app, call, headers=_headers("tools/call", name="greet"))
    assert status == 200
    assert _json(body)["result"]["content"][0]["text"] == "Hello, Ada!"
    assert _json(body)["result"]["resultType"] == "complete"


def test_asgi_accepts_chunked_request_bodies(cli: CLI) -> None:
    app = cli.asgi_app()
    body = json.dumps(_request("tools/list")).encode()
    status, _, response = _exchange(
        app,
        body,
        headers=_headers("tools/list"),
        chunks=(body[:20], body[20:]),
    )
    assert status == 200
    assert _json(response)["result"]["tools"][0]["name"] == "greet"


def test_http_rejects_legacy_revision_and_header_mismatches(cli: CLI) -> None:
    app = cli.asgi_app()
    legacy = _request("tools/list")
    legacy["params"]["_meta"][MCP_PROTOCOL_VERSION_META_KEY] = "2025-11-25"
    status, _, body = _exchange(
        app,
        legacy,
        headers=(
            (b"content-type", b"application/json"),
            (b"accept", b"application/json, text/event-stream"),
            (b"mcp-protocol-version", b"2025-11-25"),
            (b"mcp-method", b"tools/list"),
        ),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32022

    status, _, body = _exchange(
        app,
        _request("tools/list"),
        headers=_headers("tools/call"),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32020

    call = _request("tools/call", params={"name": "greet", "arguments": {"name": "Ada"}})
    status, _, body = _exchange(app, call, headers=_headers("tools/call"))
    assert status == 400
    assert _json(body)["error"]["code"] == -32020


@pytest.mark.parametrize("missing", [b"mcp-protocol-version", b"mcp-method"])
def test_required_mirrored_headers_are_enforced(cli: CLI, missing: bytes) -> None:
    headers = tuple(item for item in _headers("tools/list") if item[0] != missing)
    status, _, body = _exchange(cli.asgi_app(), _request("tools/list"), headers=headers)
    assert status == 400
    assert _json(body)["error"]["code"] == -32020


def test_stateless_http_rejects_legacy_session_header(cli: CLI) -> None:
    status, _, body = _exchange(
        cli.asgi_app(),
        _request("tools/list"),
        headers=_headers(
            "tools/list",
            extra=((b"mcp-session-id", b"legacy-session"),),
        ),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32020
    assert "not supported" in _json(body)["error"]["message"]


def test_mcp_name_base64_and_resource_errors(cli: CLI) -> None:
    unicode_cli = CLI(name="unicode")

    @unicode_cli.command("héllo")
    def hello() -> str:
        return "hello"

    call = _request("tools/call", params={"name": "héllo", "arguments": {}})
    status, _, body = _exchange(
        unicode_cli.asgi_app(),
        call,
        headers=_headers("tools/call", name="héllo"),
    )
    assert status == 200
    assert _json(body)["result"]["content"][0]["text"] == "hello"

    read = _request("resources/read", params={"uri": "config://missing"})
    status, _, body = _exchange(
        cli.asgi_app(),
        read,
        headers=_headers("resources/read", name="config://missing"),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32602


def test_origin_allowlist_is_exact_and_applies_to_metadata(cli: CLI) -> None:
    accepted_token = "".join(("v", "alid"))
    metadata = {
        "resource": "https://mcp.example.test/mcp",
        "authorization_servers": ["https://auth.example.test"],
    }
    app = cli.asgi_app(
        token_validator=lambda token: token == accepted_token,
        protected_resource_metadata=metadata,
        allowed_origins=["https://host.example.test"],
    )
    request = _request("tools/list")
    denied = _headers(
        "tools/list",
        extra=(
            (b"origin", b"https://evil.example.test"),
            (b"authorization", f"Bearer {accepted_token}".encode()),
        ),
    )
    status, _, body = _exchange(app, request, headers=denied)
    assert status == 403
    assert _json(body)["error"]["message"] == "Origin is not allowed"

    allowed = _headers(
        "tools/list",
        extra=(
            (b"origin", b"https://host.example.test"),
            (b"authorization", f"Bearer {accepted_token}".encode()),
        ),
    )
    status, _, _ = _exchange(app, request, headers=allowed)
    assert status == 200

    status, _, _ = _exchange(
        app,
        b"",
        method="GET",
        path="/.well-known/oauth-protected-resource/mcp",
        headers=((b"origin", b"https://evil.example.test"),),
    )
    assert status == 403


def test_bearer_auth_and_protected_resource_metadata(cli: CLI) -> None:
    seen: list[str] = []
    accepted_token = "-".join(("good", "token"))

    async def validate(token: str) -> bool:
        seen.append(token)
        return token == accepted_token

    metadata = {
        "resource": "https://mcp.example.test/mcp",
        "authorization_servers": ["https://auth.example.test"],
        "scopes_supported": ["tools:call"],
    }
    app = cli.asgi_app(
        token_validator=validate,
        protected_resource_metadata=metadata,
    )

    status, response_headers, body = _exchange(
        app,
        _request("tools/list"),
        headers=_headers("tools/list"),
    )
    assert status == 401
    assert response_headers[b"www-authenticate"] == (
        b'Bearer resource_metadata="https://mcp.example.test/'
        b'.well-known/oauth-protected-resource/mcp"'
    )
    assert _json(body)["error"]["message"] == "Bearer token required"

    status, _, body = _exchange(
        app,
        _request("tools/list"),
        headers=_headers(
            "tools/list",
            extra=((b"authorization", f"Bearer {accepted_token}".encode()),),
        ),
    )
    assert status == 200
    assert seen == [accepted_token]

    status, _, body = _exchange(
        app,
        b"",
        method="GET",
        path="/.well-known/oauth-protected-resource/mcp",
    )
    assert status == 200
    assert _json(body) == metadata


def test_auth_configuration_requires_metadata_and_https(cli: CLI) -> None:
    with pytest.raises(ValueError, match="configured together"):
        cli.asgi_app(token_validator=lambda _token: True)
    with pytest.raises(ValueError, match="HTTPS"):
        cli.asgi_app(
            token_validator=lambda _token: True,
            protected_resource_metadata={
                "resource": "https://mcp.example.test/mcp",
                "authorization_servers": ["http://auth.example.test"],
            },
        )


@pytest.mark.parametrize(
    ("content_type", "accept", "expected_status"),
    [
        (b"text/plain", b"application/json, text/event-stream", 415),
        (b"application/json", b"application/json", 406),
    ],
)
def test_media_type_contract(
    cli: CLI,
    content_type: bytes,
    accept: bytes,
    expected_status: int,
) -> None:
    headers = tuple(
        (name, content_type if name == b"content-type" else accept if name == b"accept" else value)
        for name, value in _headers("tools/list")
    )
    status, _, _ = _exchange(cli.asgi_app(), _request("tools/list"), headers=headers)
    assert status == expected_status


def test_request_limit_and_method_boundary(cli: CLI) -> None:
    app = cli.asgi_app(max_request_bytes=16)
    status, _, body = _exchange(
        app,
        _request("tools/list"),
        headers=_headers("tools/list", extra=((b"content-length", b"999"),)),
    )
    assert status == 413
    assert "exceeds 16 bytes" in _json(body)["error"]["message"]

    status, response_headers, body = _exchange(app, b"", method="GET", path="/mcp")
    assert status == 405
    assert response_headers[b"allow"] == b"POST"
    assert body == b""


def test_body_framing_and_jsonrpc_shape_are_strict(cli: CLI) -> None:
    request = _request("tools/list")
    encoded = json.dumps(request).encode()
    status, _, body = _exchange(
        cli.asgi_app(),
        encoded,
        headers=_headers(
            "tools/list",
            extra=((b"content-length", str(len(encoded) - 1).encode()),),
        ),
    )
    assert status == 400
    assert "Content-Length declared" in _json(body)["error"]["message"]

    invalid_constant = encoded.replace(b'"id": 1', b'"id": NaN')
    status, _, body = _exchange(
        cli.asgi_app(),
        invalid_constant,
        headers=_headers("tools/list"),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32700

    request["id"] = {"not": "scalar"}
    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers("tools/list"),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32600


def test_unknown_method_uses_http_404_and_jsonrpc_error(cli: CLI) -> None:
    request = _request("unknown/method", request_id=9)
    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers("unknown/method"),
    )
    response = _json(body)
    assert status == 404
    assert response["id"] == 9
    assert response["error"]["code"] == -32601


def test_progress_uses_request_scoped_sse_without_stdout(cli: CLI, capsys) -> None:
    release = threading.Event()

    @cli.command("stream")
    def stream():
        yield Progress("half", step=1, total=2)
        assert release.wait(timeout=2), "test did not release streaming tool"
        return "done"

    request = _request("tools/call", params={"name": "stream", "arguments": {}})
    app = cli.asgi_app()

    async def exchange_while_running() -> list[dict]:
        encoded = json.dumps(request).encode()
        incoming = [{"type": "http.request", "body": encoded, "more_body": False}]
        sent: list[dict] = []
        progress_sent = asyncio.Event()

        async def receive() -> dict:
            return incoming.pop(0)

        async def send(message: dict) -> None:
            sent.append(message)
            if b"notifications/progress" in message.get("body", b""):
                progress_sent.set()

        task = asyncio.create_task(
            app(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/mcp",
                    "headers": _headers("tools/call", name="stream"),
                },
                receive,
                send,
            )
        )
        try:
            await asyncio.wait_for(progress_sent.wait(), timeout=1)
            assert not task.done(), "progress was buffered until the tool completed"
        finally:
            release.set()
        await task
        return sent

    sent = asyncio.run(exchange_while_running())
    status = sent[0]["status"]
    response_headers = dict(sent[0]["headers"])
    body = b"".join(message.get("body", b"") for message in sent[1:])
    assert status == 200
    assert response_headers[b"content-type"] == b"text/event-stream"
    events = [
        json.loads(line.removeprefix(b"data: "))
        for line in body.splitlines()
        if line.startswith(b"data: ")
    ]
    assert events[0]["method"] == "notifications/progress"
    assert events[1]["result"]["content"][0]["text"] == "done"
    assert capsys.readouterr().out == ""


def test_jsonrpc_notification_errors_are_acknowledged_without_a_response(cli: CLI) -> None:
    request = _request("unknown/method")
    request.pop("id")
    status, response_headers, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers("unknown/method"),
    )
    assert status == 202
    assert response_headers[b"content-length"] == b"0"
    assert body == b""


def test_x_mcp_header_matches_tool_argument() -> None:
    cli = CLI(name="headers")
    cli.lazy_command(
        "lookup",
        "_lazy_handlers:greet",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "x-mcp-header": "Tenant"},
            },
            "required": ["name"],
        },
    )
    request = _request("tools/call", params={"name": "lookup", "arguments": {"name": "acme"}})
    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers(
            "tools/call",
            name="lookup",
            extra=((b"mcp-param-tenant", b"other"),),
        ),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32020

    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers(
            "tools/call",
            name="lookup",
            extra=((b"mcp-param-tenant", b"acme"),),
        ),
    )
    assert status == 200
    assert _json(body)["result"]["content"][0]["text"] == "Hello, acme!"

    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers("tools/call", name="lookup"),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32020

    status, _, body = _exchange(
        cli.asgi_app(),
        request,
        headers=_headers(
            "tools/call",
            name="lookup",
            extra=((b"mcp-param-tenant", b"\xff"),),
        ),
    )
    assert status == 400
    assert _json(body)["error"]["code"] == -32020


def test_custom_path_and_lifespan_are_mountable(cli: CLI) -> None:
    app = cli.asgi_app(path="/agent/mcp")
    status, _, _ = _exchange(
        app,
        _request("tools/list"),
        path="/agent/mcp",
        headers=_headers("tools/list"),
    )
    assert status == 200

    async def lifespan() -> list[dict]:
        incoming = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        outgoing: list[dict] = []

        async def receive() -> dict:
            return incoming.pop(0)

        async def send(message: dict) -> None:
            outgoing.append(message)

        await app({"type": "lifespan"}, receive, send)
        return outgoing

    assert asyncio.run(lifespan()) == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


def test_standalone_mode_requires_extra_and_safe_bind(cli: CLI, capsys) -> None:
    with (
        patch("milo.mcp_http.importlib.import_module", side_effect=ModuleNotFoundError),
        pytest.raises(SystemExit, match="2"),
    ):
        cli.run(["--mcp-http"])
    assert "milo-cli[http]" in capsys.readouterr().err

    fake_uvicorn = type("FakeUvicorn", (), {"run": staticmethod(lambda *args, **kwargs: None)})
    public_host = ".".join(("0", "0", "0", "0"))
    with patch("milo.mcp_http.importlib.import_module", return_value=fake_uvicorn):
        with pytest.raises(SystemExit, match="2"):
            cli.run(["--mcp-http", "--host", public_host])
        cli.run(
            [
                "--mcp-http",
                "--host",
                public_host,
                "--port",
                "9000",
                "--allow-unauthenticated",
            ]
        )


def test_http_extra_is_optional_not_required() -> None:
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    assert 'dependencies = ["kida-templates>=0.11.0,<0.12.0"]' in pyproject
    assert 'http = ["uvicorn>=0.51.0,<0.52.0"]' in pyproject


def test_parallel_tool_calls_overlap_under_free_threading() -> None:
    is_gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)
    if is_gil_enabled():
        pytest.skip("requires a free-threaded runtime with PYTHON_GIL=0")

    cli = CLI(name="parallel")
    barrier = threading.Barrier(2, timeout=2)
    lock = threading.Lock()
    active = 0
    peak = 0

    @cli.command("work")
    def work(value: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        # Keep both CPU workers active after the rendezvous.
        deadline = time.monotonic() + 0.02
        while time.monotonic() < deadline:
            value += 1
        with lock:
            active -= 1
        return value

    app = cli.asgi_app()

    async def run_two() -> None:
        await asyncio.gather(
            _asgi_exchange(
                app,
                json.dumps(
                    _request("tools/call", params={"name": "work", "arguments": {"value": 1}})
                ).encode(),
                headers=_headers("tools/call", name="work"),
            ),
            _asgi_exchange(
                app,
                json.dumps(
                    _request(
                        "tools/call",
                        params={"name": "work", "arguments": {"value": 2}},
                        request_id=2,
                    )
                ).encode(),
                headers=_headers("tools/call", name="work"),
            ),
        )

    asyncio.run(run_two())
    assert peak == 2
