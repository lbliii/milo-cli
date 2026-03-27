"""Persistent child process for MCP gateway communication."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any


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
    ) -> None:
        self.name = name
        self.command = command
        self.idle_timeout = idle_timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._last_use = time.monotonic()
        self._request_id = 0
        self._initialized = False

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
        self._request_id = 0

    def _ensure_initialized(self) -> None:
        """Send initialize if not already done."""
        if self._initialized:
            return
        self._request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
        }
        self._write_line(json.dumps(req))
        self._read_line()  # consume initialize response
        # Send notifications/initialized
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._write_line(json.dumps(notif))
        self._initialized = True

    def ensure_alive(self) -> None:
        """Spawn or reconnect if the child process is dead."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._spawn()
                self._ensure_initialized()

    def send_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result. Thread-safe."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._spawn()
                self._ensure_initialized()

            self._request_id += 1
            req_id = self._request_id
            request = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
            self._write_line(json.dumps(request))
            response_line = self._read_line()
            self._last_use = time.monotonic()

            if not response_line:
                return {"error": {"code": -32603, "message": f"No response from {self.name}"}}

            try:
                response = json.loads(response_line)
            except json.JSONDecodeError:
                return {"error": {"code": -32700, "message": "Parse error from child"}}

            if "error" in response:
                return response
            return response.get("result", {})

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
            if self._proc is not None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    import contextlib

                    with contextlib.suppress(ProcessLookupError):
                        self._proc.kill()
                self._proc = None
                self._initialized = False

    def _write_line(self, line: str) -> None:
        """Write a line to the child's stdin."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _read_line(self) -> str:
        """Read a line from the child's stdout."""
        assert self._proc is not None
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        return line.strip()
