"""Tests for the theme system."""

from __future__ import annotations

import pytest

from milo.theme import (
    _RESET,
    DEFAULT_THEME,
    ThemeProxy,
    ThemeStyle,
    make_style_filter,
)

# ---------------------------------------------------------------------------
# ThemeStyle
# ---------------------------------------------------------------------------


class TestThemeStyle:
    def test_empty_style_no_sgr(self):
        s = ThemeStyle()
        assert s.sgr_prefix() == ""

    def test_fg_only(self):
        s = ThemeStyle(fg="red")
        assert s.sgr_prefix() == "\033[31m"

    def test_bold_only(self):
        s = ThemeStyle(bold=True)
        assert s.sgr_prefix() == "\033[1m"

    def test_dim_only(self):
        s = ThemeStyle(dim=True)
        assert s.sgr_prefix() == "\033[2m"

    def test_italic_only(self):
        s = ThemeStyle(italic=True)
        assert s.sgr_prefix() == "\033[3m"

    def test_combined_fg_bold(self):
        s = ThemeStyle(fg="cyan", bold=True)
        prefix = s.sgr_prefix()
        assert "\033[" in prefix
        assert "36" in prefix
        assert "1" in prefix

    def test_unknown_fg_ignored(self):
        s = ThemeStyle(fg="neon_purple")
        # Unknown color names produce no fg code, but other attrs still work
        assert s.sgr_prefix() == ""

    def test_frozen(self):
        s = ThemeStyle(fg="red")
        with pytest.raises(AttributeError):
            s.fg = "blue"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ThemeProxy
# ---------------------------------------------------------------------------


class TestThemeProxy:
    def test_known_style_returns_sgr(self):
        proxy = ThemeProxy(DEFAULT_THEME, color=True)
        result = proxy.primary
        assert "\033[" in result

    def test_reset(self):
        proxy = ThemeProxy(DEFAULT_THEME, color=True)
        assert proxy.reset == _RESET

    def test_no_color_returns_empty(self):
        proxy = ThemeProxy(DEFAULT_THEME, color=False)
        assert proxy.primary == ""
        assert proxy.reset == ""

    def test_unknown_style_raises(self):
        proxy = ThemeProxy(DEFAULT_THEME, color=True)
        with pytest.raises(AttributeError, match="Unknown theme style"):
            _ = proxy.nonexistent

    def test_custom_theme(self):
        custom = {"brand": ThemeStyle(fg="magenta", bold=True)}
        proxy = ThemeProxy(custom, color=True)
        assert "\033[" in proxy.brand


# ---------------------------------------------------------------------------
# make_style_filter
# ---------------------------------------------------------------------------


class TestStyleFilter:
    def test_applies_color(self):
        f = make_style_filter(DEFAULT_THEME, color=True)
        result = f("hello", "error")
        assert result.startswith("\033[")
        assert result.endswith(_RESET)
        assert "hello" in result

    def test_no_color_returns_plain(self):
        f = make_style_filter(DEFAULT_THEME, color=False)
        result = f("hello", "error")
        assert result == "hello"
        assert "\033[" not in result

    def test_unknown_style_raises(self):
        f = make_style_filter(DEFAULT_THEME, color=True)
        with pytest.raises(ValueError, match="Unknown theme style"):
            f("hello", "nope")

    def test_empty_style_passthrough(self):
        theme = {"plain": ThemeStyle()}
        f = make_style_filter(theme, color=True)
        result = f("hello", "plain")
        assert result == "hello"


# ---------------------------------------------------------------------------
# DEFAULT_THEME coverage
# ---------------------------------------------------------------------------


class TestDefaultTheme:
    def test_all_styles_have_sgr(self):
        """Every default style should produce a non-empty SGR prefix."""
        for name, style in DEFAULT_THEME.items():
            assert style.sgr_prefix(), f"Style {name!r} produces no SGR"

    def test_expected_keys(self):
        expected = {"primary", "secondary", "success", "error", "warning", "muted", "emphasis"}
        assert set(DEFAULT_THEME) == expected


# ---------------------------------------------------------------------------
# Integration: get_env() with theme
# ---------------------------------------------------------------------------


class TestGetEnvTheme:
    def test_default_theme_registered(self):
        from milo.templates import get_env

        env = get_env()
        assert "style" in env._filters
        assert "theme" in env.globals

    def test_custom_theme_registered(self):
        from milo.templates import get_env

        custom = {**DEFAULT_THEME, "brand": ThemeStyle(fg="magenta")}
        env = get_env(theme=custom)
        assert "style" in env._filters

    def test_style_filter_works_in_template(self):
        from milo.templates import get_env

        env = get_env()
        tmpl = env.from_string('{{ "hi" | style("primary") }}')
        result = tmpl.render()
        assert "hi" in result
