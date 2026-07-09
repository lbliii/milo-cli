"""Dependency-free ASGI binding for modern Streamable HTTP MCP."""

from __future__ import annotations

import asyncio
import base64
import binascii
import importlib
import inspect
import ipaddress
import json
import re
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from milo._jsonrpc import (
    HEADER_MISMATCH,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
    SUPPORTED_MCP_VERSIONS,
)
from milo._mcp_router import dispatch
from milo.mcp import _classify_exception, _CLIHandler, _tool_schema, _use_notification_sink

if TYPE_CHECKING:
    from milo.commands import CLI

type ASGIMessage = dict[str, Any]
type ASGIScope = dict[str, Any]
type ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
type ASGISend = Callable[[ASGIMessage], Awaitable[None]]
type BearerTokenValidator = Callable[[str], bool | Awaitable[bool]]

_MAX_REQUEST_BYTES = 1_048_576
_BASE64_SENTINEL = re.compile(r"^=\?base64\?([A-Za-z0-9+/]*={0,2})\?=$")
_BEARER_TOKEN = re.compile(r"^[A-Za-z0-9\-._~+/]+=*$")
_HEADER_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_MISSING = object()


@dataclass(frozen=True, slots=True)
class _HTTPProblemError(Exception):
    status: int
    code: int
    message: str
    data: dict[str, Any] | None = None


class MCPASGIApp:
    """ASGI 3 application for stateless MCP 2026-07-28 requests."""

    def __init__(
        self,
        cli: CLI,
        *,
        path: str = "/mcp",
        token_validator: BearerTokenValidator | None = None,
        protected_resource_metadata: Mapping[str, Any] | None = None,
        allowed_origins: Iterable[str] = (),
        max_request_bytes: int = _MAX_REQUEST_BYTES,
    ) -> None:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("MCP ASGI path must be an absolute path without query or fragment")
        if max_request_bytes < 1:
            raise ValueError("max_request_bytes must be at least 1")
        if token_validator is not None and not callable(token_validator):
            raise TypeError("token_validator must be callable")
        if (token_validator is None) != (protected_resource_metadata is None):
            raise ValueError(
                "token_validator and protected_resource_metadata must be configured together"
            )

        self._handler = _CLIHandler(cli)
        self._cli = cli
        self.path = path.rstrip("/") or "/"
        self._token_validator = token_validator
        self._allowed_origins = frozenset(_validate_origins(allowed_origins))
        self._max_request_bytes = max_request_bytes
        self._metadata: dict[str, Any] | None = None
        self._metadata_path = ""
        self._metadata_url = ""
        if protected_resource_metadata is not None:
            metadata = _validate_resource_metadata(protected_resource_metadata)
            self._metadata = metadata
            self._metadata_url, self._metadata_path = _resource_metadata_location(
                metadata["resource"]
            )

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope_type != "http":
            await _send_empty(send, 404)
            return

        path = scope.get("path", "")
        method = str(scope.get("method", "GET")).upper()
        headers = _collect_headers(scope.get("headers", ()))
        try:
            self._validate_origin(headers)
        except _HTTPProblemError as problem:
            await self._send_problem(send, request_id=None, problem=problem)
            return
        if self._metadata is not None and path == self._metadata_path:
            if method != "GET":
                await _send_empty(send, 405, headers=((b"allow", b"GET"),))
                return
            await _send_json(send, 200, self._metadata)
            return
        if path != self.path:
            await _send_empty(send, 404)
            return
        if method != "POST":
            await _send_empty(send, 405, headers=((b"allow", b"POST"),))
            return

        request: dict[str, Any] | None = None
        try:
            await self._authorize(headers)
            _validate_media_headers(headers)
            body = await _read_body(receive, headers, self._max_request_bytes)
            request = _parse_jsonrpc_request(body)
            _validate_mirrored_headers(headers, request, self._cli)
        except _HTTPProblemError as problem:
            request_id = request.get("id") if request is not None else None
            await self._send_problem(send, request_id=request_id, problem=problem)
            return

        request_id = request.get("id")
        method_name = request["method"]
        params = request["params"]
        is_notification = "id" not in request
        dispatch_task, notifications = self._start_dispatch(method_name, params)
        if is_notification:
            # JSON-RPC notifications never receive a JSON-RPC response, even
            # when dispatch fails. The HTTP request itself was accepted.
            await dispatch_task
            await _send_empty(send, 202)
            return

        first_notification = asyncio.create_task(notifications.get())
        done, _ = await asyncio.wait(
            {dispatch_task, first_notification},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if first_notification in done:
            await _send_sse_start(send)
            await _send_sse_event(send, first_notification.result(), more_body=True)
            while not dispatch_task.done():
                next_notification = asyncio.create_task(notifications.get())
                done, _ = await asyncio.wait(
                    {dispatch_task, next_notification},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if next_notification in done:
                    await _send_sse_event(send, next_notification.result(), more_body=True)
                else:
                    next_notification.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_notification
            result, error = await dispatch_task
            # Worker callbacks are queued before the worker future completes.
            await asyncio.sleep(0)
            while not notifications.empty():
                await _send_sse_event(send, notifications.get_nowait(), more_body=True)
            final = _jsonrpc_response(request_id, result=result, error=error)
            await _send_sse_event(send, final, more_body=False)
            return

        first_notification.cancel()
        with suppress(asyncio.CancelledError):
            await first_notification
        result, error = await dispatch_task
        # Drain notification callbacks queued immediately before completion.
        await asyncio.sleep(0)
        if not notifications.empty():
            pending: list[dict[str, Any]] = []
            while not notifications.empty():
                pending.append(notifications.get_nowait())
            final = _jsonrpc_response(request_id, result=result, error=error)
            await _send_sse(send, [*pending, final])
        elif error is not None:
            await self._send_exception(send, request_id=request_id, error=error)
        else:
            await _send_json(send, 200, _jsonrpc_response(request_id, result=result))

    def _start_dispatch(
        self,
        method: str,
        params: dict[str, Any],
    ) -> tuple[
        asyncio.Task[tuple[dict[str, Any] | None, Exception | None]],
        asyncio.Queue[dict[str, Any]],
    ]:
        """Run synchronous handlers in worker threads for true 3.14t parallelism."""
        loop = asyncio.get_running_loop()
        notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def emit(message: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(notifications.put_nowait, message)

        def run() -> tuple[dict[str, Any] | None, Exception | None]:
            try:
                with _use_notification_sink(emit):
                    return dispatch(self._handler, method, params), None
            except Exception as exc:
                return None, exc

        return asyncio.create_task(asyncio.to_thread(run)), notifications

    def _validate_origin(self, headers: dict[bytes, list[bytes]]) -> None:
        raw = _single_header(headers, b"origin", status=403)
        if raw is None:
            return
        try:
            origin = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise _HTTPProblemError(403, -32600, "Invalid Origin header") from exc
        parsed = urlsplit(origin)
        canonical = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or canonical not in self._allowed_origins
        ):
            raise _HTTPProblemError(403, -32600, "Origin is not allowed")

    async def _authorize(self, headers: dict[bytes, list[bytes]]) -> None:
        if self._token_validator is None:
            return
        raw = _single_header(headers, b"authorization", status=401)
        if raw is None:
            raise _HTTPProblemError(401, -32600, "Bearer token required")
        try:
            scheme, token = raw.decode("ascii").split(" ", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise _HTTPProblemError(401, -32600, "Malformed Authorization header") from exc
        if scheme.lower() != "bearer" or not token or not _BEARER_TOKEN.fullmatch(token):
            raise _HTTPProblemError(401, -32600, "Malformed bearer token")
        try:
            valid = await asyncio.to_thread(self._token_validator, token)
            if inspect.isawaitable(valid):
                valid = await valid
        except Exception as exc:
            sys.stderr.write(f"MCP bearer token validator failed: {type(exc).__name__}\n")
            raise _HTTPProblemError(500, -32603, "Bearer token validation failed") from exc
        if valid is not True:
            raise _HTTPProblemError(401, -32600, "Bearer token is invalid or expired")

    async def _send_problem(
        self,
        send: ASGISend,
        *,
        request_id: Any,
        problem: _HTTPProblemError,
    ) -> None:
        headers: tuple[tuple[bytes, bytes], ...] = ()
        if problem.status == 401 and self._metadata_url:
            challenge = f'Bearer resource_metadata="{self._metadata_url}"'.encode("ascii")
            headers = ((b"www-authenticate", challenge),)
        payload = _jsonrpc_error(request_id, problem.code, problem.message, problem.data)
        await _send_json(send, problem.status, payload, headers=headers)

    async def _send_exception(
        self,
        send: ASGISend,
        *,
        request_id: Any,
        error: Exception,
    ) -> None:
        code, data = _classify_exception(error)
        if code == -32601:
            status = 404
        elif code in {-32600, -32602, -32020, -32021, -32022}:
            status = 400
        else:
            status = 500
        await _send_json(send, status, _jsonrpc_error(request_id, code, str(error), data))

    async def _lifespan(self, receive: ASGIReceive, send: ASGISend) -> None:
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message_type == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


def _collect_headers(raw_headers: Iterable[tuple[bytes, bytes]]) -> dict[bytes, list[bytes]]:
    headers: dict[bytes, list[bytes]] = {}
    for raw_name, raw_value in raw_headers:
        name = bytes(raw_name).lower()
        headers.setdefault(name, []).append(bytes(raw_value))
    return headers


def _single_header(
    headers: dict[bytes, list[bytes]],
    name: bytes,
    *,
    status: int = 400,
) -> bytes | None:
    values = headers.get(name, [])
    if len(values) > 1:
        label = name.decode("ascii", errors="replace")
        raise _HTTPProblemError(status, HEADER_MISMATCH, f"Duplicate {label} header")
    return values[0] if values else None


def _validate_media_headers(headers: dict[bytes, list[bytes]]) -> None:
    content_type = _single_header(headers, b"content-type")
    if content_type is None or content_type.decode("latin-1").split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise _HTTPProblemError(415, -32600, "Content-Type must be application/json")
    accept = _single_header(headers, b"accept")
    if accept is None:
        raise _HTTPProblemError(
            406,
            -32600,
            "Accept must include application/json and text/event-stream",
        )
    accepted = {
        item.split(";", 1)[0].strip().lower() for item in accept.decode("latin-1").split(",")
    }
    if not {"application/json", "text/event-stream"}.issubset(accepted):
        raise _HTTPProblemError(
            406,
            -32600,
            "Accept must include application/json and text/event-stream",
        )


async def _read_body(
    receive: ASGIReceive,
    headers: dict[bytes, list[bytes]],
    limit: int,
) -> bytes:
    content_length = _single_header(headers, b"content-length")
    declared: int | None = None
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise _HTTPProblemError(400, -32600, "Content-Length must be an integer") from exc
        if declared < 0:
            raise _HTTPProblemError(400, -32600, "Content-Length must not be negative")
        if declared > limit:
            raise _HTTPProblemError(413, -32600, f"Request body exceeds {limit} bytes")

    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        message_type = message.get("type")
        if message_type == "http.disconnect":
            raise _HTTPProblemError(400, -32600, "Client disconnected before request completed")
        if message_type != "http.request":
            raise _HTTPProblemError(400, -32600, "Invalid ASGI request event")
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise _HTTPProblemError(400, -32600, "ASGI request body must be bytes")
        size += len(chunk)
        if size > limit:
            raise _HTTPProblemError(413, -32600, f"Request body exceeds {limit} bytes")
        chunks.append(chunk)
        if not message.get("more_body", False):
            if declared is not None and declared != size:
                raise _HTTPProblemError(
                    400,
                    -32600,
                    f"Content-Length declared {declared} bytes but received {size}",
                )
            return b"".join(chunks)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _parse_jsonrpc_request(body: bytes) -> dict[str, Any]:
    try:
        request = json.loads(body, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _HTTPProblemError(400, -32700, "Parse error") from exc
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        raise _HTTPProblemError(400, -32600, "Invalid Request")
    method = request.get("method")
    if not isinstance(method, str) or not method:
        raise _HTTPProblemError(400, -32600, "Invalid Request")
    if "id" in request:
        request_id = request["id"]
        if isinstance(request_id, bool) or not isinstance(
            request_id, (str, int, float, type(None))
        ):
            raise _HTTPProblemError(400, -32600, "Invalid Request")
    params = request.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise _HTTPProblemError(400, -32602, "Invalid params")
    normalized = dict(request)
    normalized["params"] = params
    return normalized


def _validate_mirrored_headers(
    headers: dict[bytes, list[bytes]],
    request: dict[str, Any],
    cli: CLI,
) -> None:
    if b"mcp-session-id" in headers:
        raise _HTTPProblemError(
            400,
            HEADER_MISMATCH,
            "Mcp-Session-Id is not supported by the stateless 2026-07-28 transport",
        )
    params = request["params"]
    meta = params.get("_meta")
    body_version = meta.get(MCP_PROTOCOL_VERSION_META_KEY) if isinstance(meta, dict) else None
    header_version = _decoded_header(headers, b"mcp-protocol-version", "MCP-Protocol-Version")
    if not isinstance(body_version, str) or header_version != body_version:
        raise _header_mismatch("MCP-Protocol-Version", header_version, body_version)
    if body_version != MCP_VERSION:
        raise _HTTPProblemError(
            400,
            -32022,
            f"Unsupported protocol version: {body_version}",
            {"supported": list(SUPPORTED_MCP_VERSIONS), "requested": body_version},
        )

    method = request["method"]
    header_method = _decoded_header(headers, b"mcp-method", "Mcp-Method")
    if header_method != method:
        raise _header_mismatch("Mcp-Method", header_method, method)

    body_name = _request_name(method, params)
    if method in {"tools/call", "resources/read", "prompts/get"}:
        header_name = _decoded_header(headers, b"mcp-name", "Mcp-Name", encoded=True)
        if body_name is _MISSING or not isinstance(body_name, str) or header_name != body_name:
            raise _header_mismatch("Mcp-Name", header_name, body_name)
    elif b"mcp-name" in headers:
        raise _header_mismatch("Mcp-Name", _decoded_header(headers, b"mcp-name", "Mcp-Name"), None)

    if method == "tools/call" and isinstance(body_name, str):
        _validate_tool_parameter_headers(headers, cli, body_name, params.get("arguments", {}))


def _request_name(method: str, params: dict[str, Any]) -> object:
    if method in {"tools/call", "prompts/get"}:
        return params.get("name", _MISSING)
    if method == "resources/read":
        return params.get("uri", _MISSING)
    return _MISSING


def _decoded_header(
    headers: dict[bytes, list[bytes]],
    name: bytes,
    label: str,
    *,
    encoded: bool = False,
) -> str | None:
    raw = _single_header(headers, name)
    if raw is None:
        return None
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _HTTPProblemError(400, HEADER_MISMATCH, f"{label} is not ASCII or Base64") from exc
    return _decode_header_value(value, label) if encoded else value


def _decode_header_value(value: str, label: str) -> str:
    match = _BASE64_SENTINEL.fullmatch(value)
    if match is not None:
        try:
            return base64.b64decode(match.group(1), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise _HTTPProblemError(400, HEADER_MISMATCH, f"{label} has invalid Base64") from exc
    if value.startswith("=?base64?") or value.endswith("?="):
        raise _HTTPProblemError(400, HEADER_MISMATCH, f"{label} has malformed Base64 sentinel")
    if value != value.strip(" \t") or any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        raise _HTTPProblemError(400, HEADER_MISMATCH, f"{label} must use Base64 encoding")
    return value


def _header_mismatch(label: str, header: Any, body: Any) -> _HTTPProblemError:
    return _HTTPProblemError(
        400,
        HEADER_MISMATCH,
        f"Header mismatch: {label} value {header!r} does not match body value {body!r}",
    )


def _validate_tool_parameter_headers(
    headers: dict[bytes, list[bytes]],
    cli: CLI,
    tool_name: str,
    arguments: Any,
) -> None:
    schema = _tool_schema(cli, tool_name)
    if schema is None or not isinstance(arguments, dict):
        return
    try:
        annotations = _header_annotations(schema)
    except ValueError as exc:
        raise _HTTPProblemError(500, -32603, f"Invalid tool header configuration: {exc}") from exc
    for header_name, path, schema_type in annotations:
        field_name = f"mcp-param-{header_name}".encode("ascii")
        raw = _single_header(headers, field_name)
        body_value = _value_at_path(arguments, path)
        label = f"Mcp-Param-{header_name}"
        if body_value is _MISSING or body_value is None:
            if raw is not None:
                raise _header_mismatch(label, _decode_raw_header_value(raw, label), None)
            continue
        if raw is None:
            raise _header_mismatch(label, None, body_value)
        decoded = _decode_raw_header_value(raw, label)
        if not _header_value_matches(decoded, body_value, schema_type):
            raise _header_mismatch(label, decoded, body_value)


def _decode_raw_header_value(raw: bytes, label: str) -> str:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _HTTPProblemError(400, HEADER_MISMATCH, f"{label} is not ASCII or Base64") from exc
    return _decode_header_value(value, label)


def _header_annotations(
    schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[str, tuple[str, ...], str]]:
    if not path:
        _reject_unreachable_header_annotations(schema)
    found: list[tuple[str, tuple[str, ...], str]] = []
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return found
    seen: set[str] = set()
    for property_name, property_schema in properties.items():
        if not isinstance(property_name, str) or not isinstance(property_schema, dict):
            continue
        child_path = (*path, property_name)
        annotation = property_schema.get("x-mcp-header")
        if annotation is not None:
            if not isinstance(annotation, str) or not _HEADER_TOKEN.fullmatch(annotation):
                raise ValueError(f"Invalid x-mcp-header annotation at {'.'.join(child_path)}")
            normalized = annotation.lower()
            if normalized in seen:
                raise ValueError(f"Duplicate x-mcp-header annotation: {annotation}")
            schema_type = property_schema.get("type")
            if schema_type not in {"string", "integer", "boolean"}:
                raise ValueError(
                    f"x-mcp-header at {'.'.join(child_path)} must use string, integer, or boolean"
                )
            seen.add(normalized)
            found.append((normalized, child_path, schema_type))
        nested = _header_annotations(property_schema, child_path)
        for nested_name, nested_path, nested_type in nested:
            if nested_name in seen:
                raise ValueError(f"Duplicate x-mcp-header annotation: {nested_name}")
            seen.add(nested_name)
            found.append((nested_name, nested_path, nested_type))
    return found


def _reject_unreachable_header_annotations(schema: dict[str, Any]) -> None:
    """Reject x-mcp-header outside a direct chain of object properties."""

    def walk(node: Any, *, is_property: bool, reachable: bool) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, is_property=False, reachable=False)
            return
        if not isinstance(node, dict):
            return
        if "x-mcp-header" in node and (not is_property or not reachable):
            raise ValueError("x-mcp-header must be on a statically reachable property")
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for child in value.values():
                    walk(child, is_property=True, reachable=reachable)
            elif key != "x-mcp-header":
                walk(value, is_property=False, reachable=False)

    walk(schema, is_property=False, reachable=True)


def _value_at_path(arguments: dict[str, Any], path: tuple[str, ...]) -> object:
    current: object = arguments
    for component in path:
        if not isinstance(current, dict) or component not in current:
            return _MISSING
        current = current[component]
    return current


def _header_value_matches(header: str, body: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(body, str) and header == body
    if schema_type == "boolean":
        return isinstance(body, bool) and header == ("true" if body else "false")
    if schema_type == "integer":
        if isinstance(body, bool) or not isinstance(body, int):
            return False
        try:
            return int(header) == body
        except ValueError:
            return False
    return False


def _validate_origins(origins: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for origin in origins:
        if not isinstance(origin, str) or not origin:
            raise ValueError("allowed_origins entries must be non-empty strings")
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid allowed Origin: {origin!r}")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(
                f"Allowed Origin must not contain a path, query, or fragment: {origin!r}"
            )
        canonical = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def _validate_resource_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = json.loads(json.dumps(dict(metadata)))
    except (TypeError, ValueError) as exc:
        raise ValueError("protected_resource_metadata must be JSON serializable") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("protected_resource_metadata must be an object")
    resource = snapshot.get("resource")
    if not isinstance(resource, str):
        raise ValueError("protected_resource_metadata.resource must be an absolute URI")
    _validate_https_uri(resource, field="resource", allow_loopback_http=True)
    authorization_servers = snapshot.get("authorization_servers")
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise ValueError("protected_resource_metadata.authorization_servers must be non-empty")
    for server in authorization_servers:
        if not isinstance(server, str):
            raise ValueError("authorization_servers entries must be absolute HTTPS URIs")
        _validate_https_uri(server, field="authorization_servers", allow_loopback_http=False)
    return snapshot


def _validate_https_uri(value: str, *, field: str, allow_loopback_http: bool) -> None:
    parsed = urlsplit(value)
    if not parsed.netloc or parsed.fragment:
        raise ValueError(f"{field} must be an absolute URI without a fragment")
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and allow_loopback_http and _is_loopback_host(parsed.hostname or ""):
        return
    raise ValueError(f"{field} must use HTTPS")


def _resource_metadata_location(resource: str) -> tuple[str, str]:
    parsed = urlsplit(resource)
    resource_path = parsed.path.rstrip("/")
    metadata_path = "/.well-known/oauth-protected-resource" + resource_path
    metadata_url = urlunsplit((parsed.scheme, parsed.netloc, metadata_path, "", ""))
    return metadata_url, metadata_path


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _jsonrpc_response(
    request_id: Any,
    *,
    result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    if error is not None:
        code, data = _classify_exception(error)
        return _jsonrpc_error(request_id, code, str(error), data)
    return {"jsonrpc": "2.0", "id": request_id, "result": result or {}}


def _jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


async def _send_json(
    send: ASGISend,
    status: int,
    payload: Mapping[str, Any],
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response_headers = (
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        *headers,
    )
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _send_empty(
    send: ASGISend,
    status: int,
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": ((b"content-length", b"0"), *headers),
        }
    )
    await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _send_sse(send: ASGISend, messages: Iterable[Mapping[str, Any]]) -> None:
    await _send_sse_start(send)
    items = list(messages)
    for index, message in enumerate(items):
        await _send_sse_event(send, message, more_body=index < len(items) - 1)


async def _send_sse_start(send: ASGISend) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": (
                (b"content-type", b"text/event-stream"),
                (b"cache-control", b"no-cache"),
                (b"x-accel-buffering", b"no"),
            ),
        }
    )


async def _send_sse_event(
    send: ASGISend,
    message: Mapping[str, Any],
    *,
    more_body: bool,
) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    body = b"event: message\ndata: " + payload + b"\n\n"
    await send({"type": "http.response.body", "body": body, "more_body": more_body})


def run_mcp_http_server(
    cli: CLI,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    allow_unauthenticated: bool = False,
) -> None:
    """Run the optional standalone Uvicorn adapter for a Milo CLI."""
    if not 1 <= port <= 65_535:
        raise ValueError("--port must be between 1 and 65535")
    if not _is_loopback_host(host) and not allow_unauthenticated:
        raise ValueError(
            "Refusing an unauthenticated non-loopback MCP bind. Use cli.asgi_app() "
            "with a bearer token validator, or pass --allow-unauthenticated explicitly."
        )
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Standalone MCP HTTP requires the optional HTTP extra. "
            "Install with: pip install 'milo-cli[http]'"
        ) from exc
    uvicorn.run(cli.asgi_app(), host=host, port=port)
