"""Tests for template component primitives."""

from __future__ import annotations

import pytest

from milo.templates import get_env


@pytest.fixture
def env():
    return get_env()


def _render(env, body: str, **ctx) -> str:
    """Render a template string with component imports."""
    prefix = '{% from "components/_defs.kida" import section, status_line, kv_pair, kv_list, def_list, example_block, tag_list, breadcrumb, command_row, header, header_box, key_hints %}'
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

    def test_empty_version(self, env):
        out = _render(env, '{{ header("myapp", "") }}')
        assert "myapp" in out

    def test_none_version(self, env):
        out = _render(env, '{{ header("myapp", none) }}')
        assert "myapp" in out


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
        tmpl = env.get_template("components/help_page.kida")
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

    def test_help_page_minimal(self, env):
        """Only name provided — all optional fields default via ??=."""
        tmpl = env.get_template("components/help_page.kida")
        out = tmpl.render(name="myapp")
        assert "myapp" in out
        assert "Usage" not in out
        assert "Commands" not in out
        assert "Options" not in out
        assert "Examples" not in out

    def test_help_page_no_commands(self, env):
        tmpl = env.get_template("components/help_page.kida")
        out = tmpl.render(name="myapp", version="v2.0", usage="myapp [cmd]")
        assert "myapp" in out
        assert "v2.0" in out
        assert "Usage" in out
        assert "Commands" not in out

    def test_help_page_none_fields(self, env):
        """Explicitly None values are coalesced to defaults by ??=."""
        tmpl = env.get_template("components/help_page.kida")
        out = tmpl.render(
            name="myapp",
            version=None,
            description=None,
            commands=None,
            flags=None,
        )
        assert "myapp" in out
        assert "Commands" not in out
        assert "Options" not in out

    def test_help_page_with_epilog(self, env):
        tmpl = env.get_template("components/help_page.kida")
        out = tmpl.render(name="myapp", epilog="See docs for more.")
        assert "myapp" in out
        assert "See docs for more." in out


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


class TestPipelineProgress:
    def _render_pipeline(self, env, state):
        prefix = '{% from "components/_defs.kida" import pipeline_progress %}'
        tmpl = env.from_string(prefix + "{{ pipeline_progress(state) }}", name="test_pipeline")
        return tmpl.render(state=state)

    def test_all_pending(self, env):
        from milo.pipeline import PhaseStatus, PipelineState

        state = PipelineState(
            name="build",
            phases=(PhaseStatus(name="a"), PhaseStatus(name="b")),
            status="pending",
        )
        out = self._render_pipeline(env, state)
        assert "a" in out
        assert "b" in out

    def test_running_phase(self, env):
        from milo.pipeline import PhaseStatus, PipelineState

        state = PipelineState(
            name="build",
            phases=(
                PhaseStatus(name="a", status="completed", elapsed=0.05),
                PhaseStatus(name="b", status="running"),
            ),
            status="running",
            progress=0.5,
        )
        out = self._render_pipeline(env, state)
        assert "a" in out
        assert "b" in out
        # Progress bar should show ~50%
        assert "50%" in out

    def test_completed_pipeline(self, env):
        from milo.pipeline import PhaseStatus, PipelineState

        state = PipelineState(
            name="build",
            phases=(
                PhaseStatus(name="a", status="completed", elapsed=0.05),
                PhaseStatus(name="b", status="completed", elapsed=0.10),
            ),
            status="completed",
            progress=1.0,
            elapsed=0.15,
        )
        out = self._render_pipeline(env, state)
        assert "done" in out

    def test_failed_pipeline(self, env):
        from milo.pipeline import PhaseStatus, PipelineState

        state = PipelineState(
            name="build",
            phases=(
                PhaseStatus(name="a", status="completed", elapsed=0.05),
                PhaseStatus(name="b", status="failed", error="boom"),
            ),
            status="failed",
        )
        out = self._render_pipeline(env, state)
        assert "boom" in out
        assert "failed" in out


class TestCompositeTemplates:
    def test_command_list(self, env):
        tmpl = env.get_template("components/command_list.kida")
        out = tmpl.render(
            commands=[
                {"name": "new", "description": "Create"},
                {"name": "list", "description": "Show all", "aliases": ["ls"]},
            ],
        )
        assert "Commands" in out
        assert "new" in out
        assert "(ls)" in out


class TestPhaseDetail:
    def _render_detail(self, env, phase, log_scroll=0, log_height=10, auto_follow=True):
        prefix = '{% from "components/_defs.kida" import phase_detail %}'
        tmpl = env.from_string(
            prefix
            + "{{ phase_detail(phase, log_scroll=log_scroll, log_height=log_height, auto_follow=auto_follow) }}",
            name="test_detail",
        )
        return tmpl.render(
            phase=phase, log_scroll=log_scroll, log_height=log_height, auto_follow=auto_follow
        )

    def test_empty_logs_no_capture(self, env):
        from milo.pipeline import PhaseStatus

        phase = PhaseStatus(name="build", status="completed", elapsed=1.0)
        out = self._render_detail(env, phase)
        assert "No output captured." in out
        assert "build" in out

    def test_with_logs(self, env):
        from milo.pipeline import PhaseLog, PhaseStatus

        phase = PhaseStatus(
            name="parse",
            status="running",
            logs=(
                PhaseLog(line="Parsing config..."),
                PhaseLog(line="Found 10 files"),
            ),
        )
        out = self._render_detail(env, phase)
        assert "Parsing config..." in out
        assert "Found 10 files" in out
        assert "parse" in out

    def test_failed_phase_with_error(self, env):
        from milo.pipeline import PhaseStatus

        phase = PhaseStatus(name="build", status="failed", error="YAML parse error")
        out = self._render_detail(env, phase)
        assert "FAILED" in out
        assert "YAML parse error" in out

    def test_failed_with_logs_shows_error(self, env):
        from milo.pipeline import PhaseLog, PhaseStatus

        phase = PhaseStatus(
            name="build",
            status="failed",
            error="boom",
            logs=(PhaseLog(line="starting..."),),
        )
        out = self._render_detail(env, phase)
        assert "starting..." in out
        assert "boom" in out
        assert "FAILED" in out

    def test_scrolling_overflow_indicators(self, env):
        from milo.pipeline import PhaseLog, PhaseStatus

        logs = tuple(PhaseLog(line=f"line {i}") for i in range(20))
        phase = PhaseStatus(name="a", status="running", logs=logs)
        out = self._render_detail(env, phase, log_scroll=5, log_height=5)
        assert "more above" in out
        assert "more below" in out
        assert "line 5" in out

    def test_auto_follow_indicator(self, env):
        from milo.pipeline import PhaseLog, PhaseStatus

        phase = PhaseStatus(
            name="a", status="running", logs=(PhaseLog(line="hello"),)
        )
        out = self._render_detail(env, phase, auto_follow=True)
        assert "AUTO" in out


class TestPipelineDetail:
    def _render_detail(self, env, state):
        prefix = '{% from "components/_defs.kida" import pipeline_detail %}'
        tmpl = env.from_string(
            prefix + "{{ pipeline_detail(state) }}", name="test_pipeline_detail"
        )
        return tmpl.render(state=state)

    def test_overview_mode(self, env):
        from milo.pipeline import PhaseStatus, PipelineState, PipelineViewState

        ps = PipelineState(
            name="build",
            phases=(
                PhaseStatus(name="a", status="completed", elapsed=0.5),
                PhaseStatus(name="b", status="running"),
                PhaseStatus(name="c"),
            ),
            status="running",
            progress=0.33,
        )
        vs = PipelineViewState(pipeline=ps, selected_phase=1)
        out = self._render_detail(env, vs)
        assert "a" in out
        assert "b" in out
        assert "c" in out
        assert "expand" in out  # key hints
        assert "select" in out

    def test_detail_mode_key_hints(self, env):
        from milo.pipeline import PhaseStatus, PipelineState, PipelineViewState

        ps = PipelineState(
            name="build",
            phases=(PhaseStatus(name="a", status="completed", elapsed=0.5),),
            status="completed",
            progress=1.0,
            elapsed=0.5,
        )
        vs = PipelineViewState(pipeline=ps, selected_phase=0, expanded=True)
        out = self._render_detail(env, vs)
        assert "scroll" in out
        assert "collapse" in out
        assert "follow" in out

    def test_expanded_shows_detail_pane(self, env):
        from milo.pipeline import PhaseLog, PhaseStatus, PipelineState, PipelineViewState

        ps = PipelineState(
            name="build",
            phases=(
                PhaseStatus(
                    name="a",
                    status="running",
                    logs=(PhaseLog(line="working..."),),
                ),
            ),
            status="running",
            progress=0.0,
        )
        vs = PipelineViewState(pipeline=ps, selected_phase=0, expanded=True)
        out = self._render_detail(env, vs)
        assert "working..." in out
