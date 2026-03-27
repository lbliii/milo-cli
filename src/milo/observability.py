"""Observability for MCP requests — logging, stats, correlation IDs."""

from __future__ import annotations

import contextvars
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any

# Correlation ID for request tracing
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "milo_correlation_id", default=""
)


def new_correlation_id() -> str:
    """Generate and set a new correlation ID. Returns the ID."""
    cid = uuid.uuid4().hex[:12]
    correlation_id.set(cid)
    return cid


@dataclass(frozen=True, slots=True)
class RequestLog:
    """A single MCP request log entry."""

    correlation_id: str
    method: str
    name: str
    latency_ms: float
    error: str = ""
    cli_name: str = ""
    timestamp: float = 0.0


class RequestLogger:
    """Thread-safe ring buffer for MCP request logs with stats computation."""

    def __init__(self, max_size: int = 1000) -> None:
        self._buffer: deque[RequestLog] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._total: int = 0
        self._errors: int = 0

    def record(self, log: RequestLog) -> None:
        """Record a request log entry."""
        with self._lock:
            self._buffer.append(log)
            self._total += 1
            if log.error:
                self._errors += 1

    def recent(self, n: int = 20) -> list[RequestLog]:
        """Return the N most recent log entries."""
        with self._lock:
            items = list(self._buffer)
        return items[-n:]

    def stats(self) -> dict[str, Any]:
        """Compute aggregate statistics."""
        with self._lock:
            items = list(self._buffer)
            total = self._total
            errors = self._errors

        if not items:
            return {
                "total": total,
                "errors": errors,
                "avg_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
            }

        latencies = sorted(log.latency_ms for log in items)
        avg = sum(latencies) / len(latencies)
        p99_idx = max(0, int(len(latencies) * 0.99) - 1)

        return {
            "total": total,
            "errors": errors,
            "avg_latency_ms": round(avg, 2),
            "p99_latency_ms": round(latencies[p99_idx], 2),
        }


def log_request(
    logger: RequestLogger,
    method: str,
    name: str,
    start_time: float,
    *,
    error: str = "",
    cli_name: str = "",
) -> RequestLog:
    """Create and record a request log entry. Returns the log."""
    elapsed = (time.monotonic() - start_time) * 1000
    cid = correlation_id.get("")
    entry = RequestLog(
        correlation_id=cid,
        method=method,
        name=name,
        latency_ms=round(elapsed, 2),
        error=error,
        cli_name=cli_name,
        timestamp=time.time(),
    )
    logger.record(entry)
    return entry
