"""Persistent child process for MCP gateway communication."""

from __future__ import annotations

import contextlib
import json
import subprocess
import threading
import time
from typing import Any

from milo._jsonrpc import MCP_PROTOCOL_VERSION_META_KEY, MCP_VERSION, UNSUPPORTED_PROTOCOL_VERSION


def _gateway_client_capabilities() -> dict[str, Any]:
    """Capabilities the gateway can faithfully proxy from child servers."""
    from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

    return {
        "extensions": {
            MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
        }
    }


def _client_meta(protocol_version: str) -> dict[str, Any]:
    return {
        MCP_PROTOCOL_VERSION_META_KEY: protocol_version,
        "io.modelcontextprotocol/clientInfo": {"name": "milo-gateway", "version": "unknown"},
        "io.modelcontextprotocol/clientCapabilities": _gateway_client_capabilities(),
    }


class ChildProcess:
    """A persistent child process that speaks JSON-RPC on stdin/stdout.

    Thread-safe: a lock serializes all calls to the same child.
    Auto-reconnects if the child process dies.
    """

    def __init__(
        self,
        name: str,
        command: list[str],
        *,
        idle_timeout: float = 300.0,
        request_timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.command = command
        self.idle_timeout = idle_timeout
        self.request_timeout = request_timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._last_use = time.monotonic()
        self._request_id = 0
        self._initialized = False
        self._protocol_mode = "unknown"
        self._stateless_protocol_version: str | None = None
        self._protocol_version: str | None = None
        self._last_error = ""

    def _spawn(self) -> None:
        """Start the child process with persistent pipes."""
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        self._initialized = False
        self._protocol_mode = "unknown"
        self._stateless_protocol_version = None
        self._protocol_version = None
        self._last_error = ""
        self._request_id = 0

    def _ensure_initialized(self) -> None:
        """Negotiate enough protocol context for child calls.

        Milo still speaks the initialization-based 2025-11-25 protocol, but
        newer MCP revisions probe with ``server/discover`` and may omit
        ``initialize`` entirely. The gateway can therefore talk to both eras.
        """
        if self._initialized:
            return

        probe = self._send_request(
            "server/discover",
            {"_meta": _client_meta(MCP_VERSION)},
        )
        if self._try_stateless_from_discover(probe):
            return

        response = self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_VERSION,
                "capabilities": _gateway_client_capabilities(),
                "clientInfo": {"name": "milo-gateway", "version": "unknown"},
            },
        )
        result = response.get("result")
        if isinstance(result, dict):
            protocol_version = result.get("protocolVersion")
            self._protocol_version = str(protocol_version) if protocol_version else MCP_VERSION
        else:
            self._protocol_version = MCP_VERSION
        self._protocol_mode = "legacy"
        # Send notifications/initialized
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._write_line(json.dumps(notif))
        self._initialized = True

    def _try_stateless_from_discover(self, response: dict[str, Any]) -> bool:
        error = response.get("error")
        if isinstance(error, dict) and error.get("code") == UNSUPPORTED_PROTOCOL_VERSION:
            data = error.get("data", {})
            supported = data.get("supported", []) if isinstance(data, dict) else []
            if supported:
                self._set_stateless_protocol(str(supported[0]))
                self._initialized = True
                return True
            return False

        result = response.get("result")
        if not isinstance(result, dict):
            return False
        supported = result.get("supportedVersions")
        if not isinstance(supported, list) or not supported:
            return False
        if MCP_VERSION in supported:
            return False
        self._set_stateless_protocol(str(supported[0]))
        self._initialized = True
        return True

    def _set_stateless_protocol(self, protocol_version: str) -> None:
        self._protocol_mode = "stateless"
        self._protocol_version = protocol_version
        self._stateless_protocol_version = protocol_version

    @property
    def protocol_mode(self) -> str:
        """Return the negotiated child protocol mode for diagnostics."""
        return self._protocol_mode

    @property
    def protocol_version(self) -> str | None:
        """Return the negotiated child protocol version, if known."""
        return self._protocol_version

    @property
    def last_error(self) -> str:
        """Return the last child JSON-RPC or transport error seen by the gateway."""
        return self._last_error

    def ensure_alive(self) -> None:
        """Spawn or reconnect if the child process is dead."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._spawn()
                self._ensure_initialized()

    def send_call(
        self, method: str, params: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result. Thread-safe.

        *timeout* overrides the instance ``request_timeout`` for this call.
        """
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._spawn()
                self._ensure_initialized()

            request_params = params
            if self._stateless_protocol_version is not None:
                request_params = dict(params)
                request_params.setdefault("_meta", _client_meta(self._stateless_protocol_version))
            response = self._send_request(method, request_params, timeout=timeout)
            self._last_use = time.monotonic()

            if "error" in response:
                self._record_error_response(response)
                return response
            self._last_error = ""
            return response.get("result", {})

    def _send_request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self._request_id += 1
        req_id = self._request_id
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        self._write_line(json.dumps(request))
        effective_timeout = timeout if timeout is not None else self.request_timeout
        return self._read_response(req_id, timeout=effective_timeout)

    def _record_error_response(self, response: dict[str, Any]) -> None:
        error = response.get("error", {})
        if isinstance(error, dict):
            message = error.get("message")
            code = error.get("code")
            if message:
                self._last_error = f"{code}: {message}" if code is not None else str(message)
                return
        self._last_error = "Unknown child error"

    def fetch_tools(self) -> list[dict[str, Any]]:
        """Fetch tools/list from the child process."""
        result = self.send_call("tools/list", {})
        return result.get("tools", [])

    def is_idle(self) -> bool:
        """Check if the child has been idle longer than idle_timeout."""
        return (time.monotonic() - self._last_use) > self.idle_timeout

    def kill(self) -> None:
        """Kill the child process."""
        with self._lock:
            self._graceful_kill()

    def _graceful_kill(self) -> None:
        """SIGTERM with grace period, then SIGKILL if needed.

        Must be called while holding ``self._lock``.
        """
        if self._proc is None:
            return
        try:
            self._proc.terminate()  # SIGTERM
            self._proc.wait(timeout=5)  # Grace period
        except ProcessLookupError:
            pass  # Already dead
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()  # SIGKILL
        self._proc = None
        self._initialized = False

    def _write_line(self, line: str) -> None:
        """Write a line to the child's stdin."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _read_response(self, req_id: int, *, timeout: float | None = None) -> dict[str, Any]:
        """Read frames until the response matching *req_id* arrives."""
        effective_timeout = timeout if timeout is not None else self.request_timeout
        deadline = time.monotonic() + effective_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._graceful_kill()
                return self._transport_error("child_timeout", f"No response from {self.name}")

            response_line = self._read_line(timeout=remaining)
            if response_line is None:
                return self._transport_error("child_timeout", f"No response from {self.name}")
            if not response_line:
                return self._transport_error(
                    "child_disconnected", f"Child {self.name} disconnected"
                )

            try:
                response = json.loads(response_line)
            except json.JSONDecodeError:
                return {
                    "error": {
                        "code": -32700,
                        "message": "Parse error from child",
                        "data": {"reason": "child_parse_error", "child": self.name},
                    }
                }

            # Notifications have no id and may be interleaved with streaming tool
            # results. They are intentionally ignored by the gateway transport.
            if "id" not in response:
                continue
            if response.get("id") == req_id:
                return response

    def _transport_error(self, reason: str, message: str) -> dict[str, Any]:
        return {
            "error": {
                "code": -32603,
                "message": message,
                "data": {"reason": reason, "child": self.name},
            }
        }

    def _read_line(self, *, timeout: float | None = None) -> str | None:
        """Read a line from the child's stdout with timeout.

        Uses a background thread so we can enforce a deadline even
        when the child blocks without writing a newline.
        """
        effective_timeout = timeout if timeout is not None else self.request_timeout
        assert self._proc is not None
        stdout = self._proc.stdout
        assert stdout is not None
        result: list[str] = []
        reader = threading.Thread(
            target=lambda: result.append(stdout.readline()),
            daemon=True,
        )
        reader.start()
        reader.join(timeout=effective_timeout)
        if reader.is_alive():
            # Timed out — graceful shutdown: SIGTERM → grace → SIGKILL
            self._graceful_kill()
            return None
        return result[0].strip() if result else ""
