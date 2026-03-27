"""Tests for milo.streaming — generator-based streaming."""

from __future__ import annotations

import pytest

from milo.streaming import Progress, consume_generator, is_generator_result


class TestProgress:
    def test_frozen(self) -> None:
        p = Progress(status="Building", step=1, total=3)
        with pytest.raises(AttributeError):
            p.status = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        p = Progress(status="Working")
        assert p.step == 0
        assert p.total == 0


class TestIsGeneratorResult:
    def test_generator_detected(self) -> None:
        def gen():
            yield 1

        assert is_generator_result(gen()) is True

    def test_non_generator(self) -> None:
        assert is_generator_result("hello") is False
        assert is_generator_result(42) is False
        assert is_generator_result(None) is False
        assert is_generator_result([1, 2, 3]) is False


class TestConsumeGenerator:
    def test_collects_progress(self) -> None:
        def gen():
            yield Progress(status="Step 1", step=1, total=2)
            yield Progress(status="Step 2", step=2, total=2)
            return "done"

        progress, final = consume_generator(gen())
        assert len(progress) == 2
        assert progress[0].status == "Step 1"
        assert progress[1].status == "Step 2"
        assert final == "done"

    def test_no_return_value(self) -> None:
        def gen():
            yield Progress(status="Working")

        progress, final = consume_generator(gen())
        assert len(progress) == 1
        assert final is None

    def test_empty_generator(self) -> None:
        def gen():
            return "immediate"
            yield  # make it a generator

        progress, final = consume_generator(gen())
        assert progress == []
        assert final == "immediate"

    def test_non_progress_yields_ignored(self) -> None:
        def gen():
            yield Progress(status="real")
            yield "not a progress"
            yield 42
            return "final"

        progress, final = consume_generator(gen())
        assert len(progress) == 1
        assert progress[0].status == "real"
        assert final == "final"

    def test_return_structured_data(self) -> None:
        def gen():
            yield Progress(status="Building")
            return {"status": "ok", "count": 5}

        _progress, final = consume_generator(gen())
        assert final == {"status": "ok", "count": 5}
