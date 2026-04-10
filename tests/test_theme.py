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

    # -- 256-color support ---------------------------------------------------

    def test_fg_256_color(self):
        s = ThemeStyle(fg=33)
        assert s.sgr_prefix() == "\033[38;5;33m"

    def test_fg_256_color_zero(self):
        s = ThemeStyle(fg=0)
        assert s.sgr_prefix() == "\033[38;5;0m"

    def test_fg_256_color_255(self):
        s = ThemeStyle(fg=255)
        assert s.sgr_prefix() == "\033[38;5;255m"

    def test_fg_256_with_bold(self):
        s = ThemeStyle(fg=33, bold=True)
        prefix = s.sgr_prefix()
        assert "38;5;33" in prefix
        assert "1" in prefix

    # -- Truecolor support ---------------------------------------------------

    def test_fg_truecolor(self):
        s = ThemeStyle(fg="#ff6600")
        assert s.sgr_prefix() == "\033[38;2;255;102;0m"

    def test_fg_truecolor_black(self):
        s = ThemeStyle(fg="#000000")
        assert s.sgr_prefix() == "\033[38;2;0;0;0m"

    def test_fg_truecolor_white(self):
        s = ThemeStyle(fg="#ffffff")
        assert s.sgr_prefix() == "\033[38;2;255;255;255m"

    def test_fg_truecolor_with_decorations(self):
        s = ThemeStyle(fg="#aabbcc", bold=True, italic=True)
        prefix = s.sgr_prefix()
        assert "38;2;170;187;204" in prefix
        assert "1" in prefix
        assert "3" in prefix

    # -- Background color support --------------------------------------------

    def test_bg_named(self):
        s = ThemeStyle(bg="red")
        assert s.sgr_prefix() == "\033[41m"

    def test_bg_256_color(self):
        s = ThemeStyle(bg=220)
        assert s.sgr_prefix() == "\033[48;5;220m"

    def test_bg_truecolor(self):
        s = ThemeStyle(bg="#112233")
        assert s.sgr_prefix() == "\033[48;2;17;34;51m"

    def test_fg_and_bg_combined(self):
        s = ThemeStyle(fg="red", bg="blue")
        prefix = s.sgr_prefix()
        assert "31" in prefix
        assert "44" in prefix

    def test_fg_256_bg_truecolor(self):
        s = ThemeStyle(fg=33, bg="#ff0000")
        prefix = s.sgr_prefix()
        assert "38;5;33" in prefix
        assert "48;2;255;0;0" in prefix

    def test_bg_unknown_named_ignored(self):
        s = ThemeStyle(bg="neon_purple")
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
