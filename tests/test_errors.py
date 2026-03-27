"""Tests for _errors.py — error hierarchy, format_compact, error templates."""

from __future__ import annotations

import pytest

from milo._errors import (
    AppError,
    DevError,
    ErrorCode,
    FlowError,
    FormError,
    InputError,
    MiloError,
    StateError,
    format_error,
    format_render_error,
)


class TestMiloError:
    def test_code_and_message(self):
        e = MiloError(ErrorCode.APP_LIFECYCLE, "test message")
        assert e.code == ErrorCode.APP_LIFECYCLE
        assert e.message == "test message"
        assert "[M-APP-001]" in str(e)

    def test_format_compact(self):
        e = MiloError(ErrorCode.STA_REDUCER, "Reducer exploded")
        assert e.format_compact() == "M-STA-001: Reducer exploded"

    def test_subclasses_have_format_compact(self):
        for cls, code in [
            (InputError, ErrorCode.INP_RAW_MODE),
            (StateError, ErrorCode.STA_SAGA),
            (FormError, ErrorCode.FRM_VALIDATION),
            (AppError, ErrorCode.APP_RENDER),
            (FlowError, ErrorCode.FLW_SCREEN),
            (DevError, ErrorCode.DEV_WATCH),
        ]:
            e = cls(code, "msg")
            assert code.value in e.format_compact()


class TestFormatError:
    def test_milo_error_uses_format_compact(self):
        e = AppError(ErrorCode.APP_RENDER, "bad template")
        result = format_error(e)
        assert "M-APP-002" in result
        assert "bad template" in result

    def test_kida_error_uses_format_compact(self):
        """Kida TemplateErrors also have format_compact()."""
        from kida import Environment

        env = Environment()
        try:
            env.from_string("{% if x %}unclosed", name="test.kida")
            pytest.fail("Should have raised")
        except Exception as e:
            result = format_error(e)
            assert "K-" in result or "unclosed" in result.lower()

    def test_plain_exception_fallback(self):
        result = format_error(ValueError("something broke"))
        assert "ValueError" in result
        assert "something broke" in result


class TestFormatRenderError:
    def test_without_env_returns_compact(self):
        e = AppError(ErrorCode.APP_RENDER, "missing template")
        result = format_render_error(e)
        assert "M-APP-002" in result

    def test_with_env_renders_error_template(self):
        from milo.templates import get_env

        env = get_env()
        e = AppError(ErrorCode.APP_TEMPLATE, "not found")
        result = format_render_error(e, template_name="counter.kida", env=env)
        assert "not found" in result
        assert "counter.kida" in result

    def test_with_kida_error(self):
        from kida import Environment

        env = Environment()
        try:
            env.from_string("{{ foo.bar }}", name="test.kida").render()
            pytest.fail("Should have raised")
        except Exception as e:
            result = format_render_error(e, template_name="test.kida")
            # Should contain something useful
            assert len(result) > 0

    def test_bad_env_falls_back(self):
        """If error template itself fails, fall back to format_error()."""
        from unittest.mock import MagicMock

        bad_env = MagicMock()
        bad_env.get_template.side_effect = Exception("meta-error")

        e = AppError(ErrorCode.APP_RENDER, "original problem")
        result = format_render_error(e, env=bad_env)
        assert "original problem" in result
