"""Tests for template component primitives."""

from __future__ import annotations

import pytest

from milo.templates import get_env


@pytest.fixture
def env():
    return get_env()


def _render(env, body: str, **ctx) -> str:
    """Render a template string with component imports."""
    prefix = '{% from "components/_defs.txt" import section, status_line, kv_pair, kv_list, def_list, example_block, tag_list, breadcrumb, command_row, header, header_box, key_hints %}'
    tmpl = env.from_string(prefix + body, name="test")
    return tmpl.render(**ctx)


class TestSection:
    def test_default_color(self, env):
        out = _render(env, '{{ section("Options") }}')
        assert "Options" in out

    def test_renders_colon(self, env):
        out = _render(env, '{{ section("Flags") }}')
        # Strip ANSI, check structure
        assert ":" in out


class TestStatusLine:
    def test_success(self, env):
        out = _render(env, '{{ status_line("success", "Done") }}')
        assert "Done" in out

    def test_error_with_detail(self, env):
        out = _render(env, '{{ status_line("error", "Failed", "exit 1") }}')
        assert "Failed" in out
        assert "exit 1" in out

    def test_warning(self, env):
        out = _render(env, '{{ status_line("warning", "Deprecated") }}')
        assert "Deprecated" in out

    def test_info(self, env):
        out = _render(env, '{{ status_line("info", "Note") }}')
        assert "Note" in out


class TestKvPair:
    def test_basic(self, env):
        out = _render(env, '{{ kv_pair("Name", "Alice") }}')
        assert "Name" in out
        assert "Alice" in out

    def test_custom_width(self, env):
        out = _render(env, '{{ kv_pair("X", "Y", width=20) }}')
        assert "X" in out
        assert "Y" in out


class TestKvList:
    def test_multiple_items(self, env):
        items = [{"label": "Host", "value": "localhost"}, {"label": "Port", "value": 8080}]
        out = _render(env, "{{ kv_list(items) }}", items=items)
        assert "Host" in out
        assert "localhost" in out
        assert "Port" in out
        assert "8080" in out


class TestDefList:
    def test_renders_terms(self, env):
        items = [
            {"term": "init", "description": "Initialize project"},
            {"term": "build", "description": "Compile app"},
        ]
        out = _render(env, "{{ def_list(items) }}", items=items)
        assert "init" in out
        assert "Initialize project" in out
        assert "build" in out


class TestExampleBlock:
    def test_renders_commands(self, env):
        examples = [
            {"description": "Create project", "command": "milo init my-app"},
        ]
        out = _render(env, "{{ example_block(examples) }}", examples=examples)
        assert "Create project" in out
        assert "milo init my-app" in out
        assert "$" in out


class TestTagList:
    def test_string_tags(self, env):
        out = _render(env, '{{ tag_list(["required", "beta"]) }}')
        assert "[required]" in out
        assert "[beta]" in out

    def test_dict_tags(self, env):
        tags = [{"label": "stable", "color": "green"}, {"label": "beta", "color": "yellow"}]
        out = _render(env, "{{ tag_list(tags) }}", tags=tags)
        assert "[stable]" in out
        assert "[beta]" in out


class TestBreadcrumb:
    def test_renders_parts(self, env):
        out = _render(env, '{{ breadcrumb(["app", "config", "db"]) }}')
        assert "app" in out
        assert "config" in out
        assert "db" in out

    def test_separator(self, env):
        out = _render(env, '{{ breadcrumb(["a", "b"], sep=" / ") }}')
        assert "/" in out


class TestCommandRow:
    def test_basic(self, env):
        out = _render(env, '{{ command_row("init", "Start a project") }}')
        assert "init" in out
        assert "Start a project" in out

    def test_with_aliases_and_tags(self, env):
        out = _render(env, '{{ command_row("init", "Start", ["i", "new"], ["core"]) }}')
        assert "init" in out
        assert "(i, new)" in out
        assert "[core]" in out


class TestHeader:
    def test_name_only(self, env):
        out = _render(env, '{{ header("myapp") }}')
        assert "myapp" in out

    def test_full(self, env):
        out = _render(env, '{{ header("myapp", "v1.0", "A tool") }}')
        assert "myapp" in out
        assert "v1.0" in out
        assert "A tool" in out


class TestHeaderBox:
    def test_renders_box(self, env):
        out = _render(env, '{{ header_box("myapp", "v1.0", "A CLI tool") }}')
        assert "myapp" in out
        assert "v1.0" in out

    def test_no_description(self, env):
        out = _render(env, '{{ header_box("myapp") }}')
        assert "myapp" in out


class TestComposites:
    def test_help_page(self, env):
        tmpl = env.get_template("components/help_page.txt")
        out = tmpl.render(
            name="myapp",
            version="v1.0",
            description="A tool",
            commands=[{"name": "init", "description": "Start"}],
            flags=[{"flags": ["-v", "--verbose"], "description": "Verbose"}],
            examples=[{"description": "Run it", "command": "myapp init"}],
        )
        assert "myapp" in out
        assert "init" in out
        assert "--verbose" in out
        assert "$ myapp init" in out


class TestKeyHints:
    def test_basic_hints(self, env):
        out = _render(
            env,
            '{{ key_hints([{"key": "enter", "action": "confirm"}, {"key": "esc", "action": "cancel"}]) }}',
        )
        assert "enter" in out
        assert "confirm" in out
        assert "esc" in out
        assert "cancel" in out

    def test_single_hint(self, env):
        out = _render(
            env,
            '{{ key_hints([{"key": "q", "action": "quit"}]) }}',
        )
        assert "q" in out
        assert "quit" in out


class TestCompositeTemplates:
    def test_command_list(self, env):
        tmpl = env.get_template("components/command_list.txt")
        out = tmpl.render(
            commands=[
                {"name": "new", "description": "Create"},
                {"name": "list", "description": "Show all", "aliases": ["ls"]},
            ],
        )
        assert "Commands" in out
        assert "new" in out
        assert "(ls)" in out
