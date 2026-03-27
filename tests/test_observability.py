"""Tests for milo.observability — request logging and stats."""

from __future__ import annotations

import threading
import time

import pytest

from milo.observability import (
    RequestLog,
    RequestLogger,
    correlation_id,
    log_request,
    new_correlation_id,
)


class TestRequestLog:
    def test_frozen(self) -> None:
        entry = RequestLog(correlation_id="abc", method="tools/call", name="greet", latency_ms=10.0)
        with pytest.raises(AttributeError):
            entry.method = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        entry = RequestLog(correlation_id="abc", method="tools/call", name="greet", latency_ms=10.0)
        assert entry.error == ""
        assert entry.cli_name == ""
        assert entry.timestamp == 0.0


class TestCorrelationId:
    def test_new_correlation_id(self) -> None:
        cid = new_correlation_id()
        assert len(cid) == 12
        assert correlation_id.get() == cid

    def test_default_empty(self) -> None:
        # Reset to default
        token = correlation_id.set("")
        assert correlation_id.get() == ""
        correlation_id.reset(token)


class TestRequestLogger:
    def test_record_and_recent(self) -> None:
        logger = RequestLogger(max_size=100)
        for i in range(5):
            logger.record(
                RequestLog(
                    correlation_id=f"id-{i}",
                    method="tools/call",
                    name=f"tool-{i}",
                    latency_ms=float(i),
                )
            )
        recent = logger.recent(3)
        assert len(recent) == 3
        assert recent[0].name == "tool-2"
        assert recent[2].name == "tool-4"

    def test_ring_buffer_max_size(self) -> None:
        logger = RequestLogger(max_size=3)
        for i in range(10):
            logger.record(
                RequestLog(correlation_id="id", method="m", name=f"t-{i}", latency_ms=1.0)
            )
        recent = logger.recent(100)
        assert len(recent) == 3
        assert recent[0].name == "t-7"

    def test_stats_empty(self) -> None:
        logger = RequestLogger()
        stats = logger.stats()
        assert stats["total"] == 0
        assert stats["errors"] == 0
        assert stats["avg_latency_ms"] == 0.0
        assert stats["p99_latency_ms"] == 0.0

    def test_stats_with_data(self) -> None:
        logger = RequestLogger()
        for i in range(100):
            logger.record(
                RequestLog(
                    correlation_id="id",
                    method="m",
                    name="t",
                    latency_ms=float(i + 1),
                    error="err" if i % 10 == 0 else "",
                )
            )
        stats = logger.stats()
        assert stats["total"] == 100
        assert stats["errors"] == 10
        assert stats["avg_latency_ms"] > 0
        assert stats["p99_latency_ms"] > 0

    def test_thread_safety(self) -> None:
        logger = RequestLogger(max_size=1000)
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(50):
                    logger.record(
                        RequestLog(
                            correlation_id=f"t{thread_id}",
                            method="m",
                            name=f"t-{thread_id}-{i}",
                            latency_ms=1.0,
                        )
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert logger.stats()["total"] == 200


class TestLogRequest:
    def test_creates_and_records(self) -> None:
        logger = RequestLogger()
        start = time.monotonic()
        entry = log_request(logger, "tools/call", "greet", start, cli_name="myapp")
        assert entry.method == "tools/call"
        assert entry.name == "greet"
        assert entry.cli_name == "myapp"
        assert entry.latency_ms >= 0
        assert logger.stats()["total"] == 1
