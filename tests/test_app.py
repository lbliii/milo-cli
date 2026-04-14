"""Tests for app.py — App lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from milo._errors import AppError
from milo._types import RenderTarget
from milo.app import App, render_html, run


@dataclass(frozen=True, slots=True)
class SimpleState:
    value: int = 0
    submitted: bool = False


def simple_reducer(state, action):
    if state is None:
        return SimpleState()
    return state


class TestApp:
    def test_requires_reducer_or_flow(self):
        with pytest.raises(AppError):
            App(template="test.kida", initial_state=0)

    def test_from_flow(self):
        from milo.flow import FlowScreen

        def r(s, a):
            return s or 0

        a = FlowScreen("a", "a.kida", r)
        b = FlowScreen("b", "b.kida", r)
        app = App.from_flow(a >> b)
        assert app._flow is not None

    def test_default_attributes(self):
        app = App(template="t.kida", reducer=simple_reducer, initial_state=SimpleState())
        assert app._tick_rate == 0.0
        assert app._transient is False
        assert app._target == RenderTarget.TERMINAL

    def test_html_target_skips_tty(self):
        """HTML target goes straight to _render_once without TTY check."""
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("hello {{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        app = App(
            template="t.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(value=42),
            target=RenderTarget.HTML,
            env=env,
        )
        with patch("sys.stdout"):
            result = app.run()
        assert isinstance(result, SimpleState)

    def test_non_tty_calls_render_once(self):
        """Non-TTY stdin triggers the single render path."""
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("val={{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        app = App(
            template="t.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(value=7),
            env=env,
        )
        with patch("milo.app.is_tty", return_value=False), patch("sys.stdout"):
            result = app.run()
        assert isinstance(result, SimpleState)

    def test_get_template_name_no_flow(self):
        app = App(template="my.kida", reducer=simple_reducer, initial_state=None)
        assert app._get_template_name(SimpleState()) == "my.kida"

    def test_get_template_name_with_flow(self):
        from milo.flow import FlowScreen, FlowState

        def r(s, a):
            return s or 0

        a = FlowScreen("screen_a", "a.kida", r)
        b = FlowScreen("screen_b", "b.kida", r)
        app = App.from_flow(a >> b)

        flow_state = FlowState(current_screen="screen_a", screen_states={})
        assert app._get_template_name(flow_state) == "a.kida"

        flow_state_b = FlowState(current_screen="screen_b", screen_states={})
        assert app._get_template_name(flow_state_b) == "b.kida"

    def test_get_env_uses_provided(self):
        fake_env = MagicMock()
        app = App(template="t.kida", reducer=simple_reducer, initial_state=None, env=fake_env)
        assert app._get_env() is fake_env

    def test_get_env_creates_default(self):
        app = App(template="t.kida", reducer=simple_reducer, initial_state=None)
        env = app._get_env()
        assert env is not None

    def test_render_state_logs_errors_to_stderr(self):
        """_render_state should log errors to stderr, not raise."""
        bad_env = MagicMock()
        bad_env.get_template.side_effect = Exception("template error")
        app = App(template="t.kida", reducer=simple_reducer, initial_state=None, env=bad_env)
        with patch("sys.stderr") as mock_stderr:
            app._render_state(SimpleState(), bad_env, None)
            mock_stderr.write.assert_called_once()
            assert "template error" in mock_stderr.write.call_args[0][0]

    def test_render_once_logs_errors_to_stderr(self):
        """_render_once should log errors to stderr, not raise."""
        bad_env = MagicMock()
        bad_env.get_template.side_effect = Exception("template error")
        app = App(template="t.kida", reducer=simple_reducer, initial_state=None, env=bad_env)
        with patch("sys.stderr") as mock_stderr:
            app._render_once(SimpleState())
            mock_stderr.write.assert_called_once()
            assert "template error" in mock_stderr.write.call_args[0][0]

    def test_render_once_writes_output(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("output={{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        app = App(
            template="t.kida", reducer=simple_reducer, initial_state=SimpleState(value=9), env=env
        )

        written = []
        mock_stdout = MagicMock()
        mock_stdout.write = lambda s: written.append(s)
        with patch("sys.stdout", mock_stdout):
            app._render_once(SimpleState(value=9))
        assert any("output=9" in s for s in written)

    def test_render_state_with_renderer(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("val={{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl
        renderer = MagicMock()

        app = App(template="t.kida", reducer=simple_reducer, initial_state=None, env=env)
        app._render_state(SimpleState(value=3), env, renderer)
        renderer.update.assert_called_once()

    def test_render_state_with_renderer_content(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("val={{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        app = App(template="t.kida", reducer=simple_reducer, initial_state=None, env=env)
        renderer = MagicMock()
        app._render_state(SimpleState(value=5), env, renderer)
        renderer.update.assert_called_once()
        assert "val=5" in renderer.update.call_args[0][0]

    def test_render_once_with_flow_state(self):
        """_render_once extracts screen state from FlowState."""
        from kida import Environment

        from milo.flow import FlowState

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("s={{ state }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        def r(s, a):
            return s or 0

        from milo.flow import FlowScreen

        a = FlowScreen("a", "a.kida", r)
        b = FlowScreen("b", "b.kida", r)
        app = App.from_flow(a >> b, env=env)

        flow_state = FlowState(
            current_screen="a",
            screen_states={"a": "screen_a_state", "b": "screen_b_state"},
        )
        written = []
        mock_stdout = MagicMock()
        mock_stdout.write = lambda s: written.append(s)
        with patch("sys.stdout", mock_stdout):
            app._render_once(flow_state)
        assert any("screen_a_state" in s for s in written)


class TestFromDir:
    def test_from_dir_with_templates(self, tmp_path):
        """from_dir discovers templates/ relative to caller file."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "hello.kida").write_text("hello={{ state.value }}")
        caller = tmp_path / "app.py"
        caller.touch()

        app = App.from_dir(
            str(caller),
            template="hello.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(value=10),
        )
        with patch("milo.app.is_tty", return_value=False):
            written = []
            mock_stdout = MagicMock()
            mock_stdout.write = lambda s: written.append(s)
            with patch("sys.stdout", mock_stdout):
                result = app.run()
        assert isinstance(result, SimpleState)
        assert any("hello=10" in s for s in written)

    def test_from_dir_missing_templates_raises(self, tmp_path):
        """from_dir raises AppError when templates/ does not exist."""
        caller = tmp_path / "app.py"
        caller.touch()

        with pytest.raises(AppError, match="Templates directory not found"):
            App.from_dir(
                str(caller),
                template="t.kida",
                reducer=simple_reducer,
            )

    def test_from_dir_custom_templates_dir(self, tmp_path):
        """from_dir supports a custom templates directory name."""
        tpl_dir = tmp_path / "views"
        tpl_dir.mkdir()
        (tpl_dir / "page.kida").write_text("page={{ state.value }}")
        caller = tmp_path / "app.py"
        caller.touch()

        app = App.from_dir(
            str(caller),
            template="page.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(value=5),
            templates_dir="views",
        )
        assert app._template_name == "page.kida"

    def test_from_dir_with_flow(self, tmp_path):
        """from_dir works with a Flow."""
        from milo.flow import FlowScreen

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "a.kida").write_text("screen a")
        (tpl_dir / "b.kida").write_text("screen b")
        caller = tmp_path / "app.py"
        caller.touch()

        def r(s, a):
            return s or 0

        a = FlowScreen("a", "a.kida", r)
        b = FlowScreen("b", "b.kida", r)
        app = App.from_dir(str(caller), flow=a >> b)
        assert app._flow is not None

    def test_from_dir_rejects_env_kwarg(self, tmp_path):
        """from_dir raises AppError if env is passed."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "t.kida").write_text("x")
        caller = tmp_path / "app.py"
        caller.touch()

        with pytest.raises(AppError, match="does not accept an 'env' argument"):
            App.from_dir(
                str(caller),
                template="t.kida",
                reducer=simple_reducer,
                env=MagicMock(),
            )


class TestExitTemplate:
    def test_exit_template_renders_after_run(self):
        """exit_template renders the final state after the app loop ends."""
        from kida import Environment

        tmpl_env = Environment()
        main_tmpl = tmpl_env.from_string("main={{ state.value }}")
        exit_tmpl = tmpl_env.from_string("bye={{ state.value }}")

        env = MagicMock()

        def get_template(name):
            if name == "exit.kida":
                return exit_tmpl
            return main_tmpl

        env.get_template.side_effect = get_template

        app = App(
            template="t.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(value=42),
            target=RenderTarget.HTML,
            env=env,
            exit_template="exit.kida",
        )
        written = []
        mock_stdout = MagicMock()
        mock_stdout.write = lambda s: written.append(s)
        with patch("sys.stdout", mock_stdout):
            app.run()
        assert any("bye=42" in s for s in written)

    def test_no_exit_template_by_default(self):
        """Without exit_template, nothing extra is rendered."""
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("main")

        env = MagicMock()
        env.get_template.return_value = tmpl

        app = App(
            template="t.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(),
            target=RenderTarget.HTML,
            env=env,
        )
        with patch("sys.stdout"):
            app.run()
        # get_template called once for the main render, not twice
        assert env.get_template.call_count == 1

    def test_exit_template_error_logged(self):
        """Errors in exit template render go to stderr, not raised."""
        from kida import Environment

        tmpl_env = Environment()
        main_tmpl = tmpl_env.from_string("main")

        env = MagicMock()

        def get_template(name):
            if name == "exit.kida":
                raise Exception("exit template missing")
            return main_tmpl

        env.get_template.side_effect = get_template

        app = App(
            template="t.kida",
            reducer=simple_reducer,
            initial_state=SimpleState(),
            target=RenderTarget.HTML,
            env=env,
            exit_template="exit.kida",
        )
        with patch("sys.stdout"), patch("sys.stderr") as mock_stderr:
            app.run()  # should not raise
            mock_stderr.write.assert_called_once()

    def test_render_classmethod(self):
        """App.render does a one-shot template render."""
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("hello={{ state.value }}")

        env = MagicMock()
        env.get_template.return_value = tmpl

        result = App.render("t.kida", SimpleState(value=5), env=env)
        assert result == "hello=5"


class TestRun:
    def test_run_shorthand_non_tty(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("{{ state }}")
        env = MagicMock()
        env.get_template.return_value = tmpl

        with patch("milo.app.is_tty", return_value=False), patch("sys.stdout"):
            result = run(
                template="t.kida",
                reducer=simple_reducer,
                initial_state=SimpleState(),
                env=env,
            )
        assert isinstance(result, SimpleState)


class TestRenderHtml:
    def test_basic_html(self):
        from milo.templates import get_env

        get_env()

        # Create a simple template string
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("Hello {{ state.name }}")

        @dataclass(frozen=True, slots=True)
        class State:
            name: str = "World"

        html = render_html(State(), tmpl, title="Test")
        assert "Hello World" in html
        assert "<title>Test</title>" in html
        assert "<!DOCTYPE html>" in html

    def test_render_html_with_string_template(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("body={{ state }}")
        env = MagicMock()
        env.get_template.return_value = tmpl

        html = render_html("my_state", "t.kida", env=env)
        assert "<!DOCTYPE html>" in html
        assert "body=my_state" in html

    def test_render_html_custom_css(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("x")
        env = MagicMock()
        env.get_template.return_value = tmpl

        html = render_html("state", tmpl, css="body{color:red}")
        assert "body{color:red}" in html

    def test_render_html_default_css(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("x")

        html = render_html("state", tmpl)
        # default css includes background
        assert "background" in html

    def test_render_html_with_title(self):
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("content")
        html = render_html("state", tmpl, title="My App")
        assert "<title>My App</title>" in html

    def test_render_html_no_env_creates_one(self):
        """When env=None render_html creates an env with autoescape=True."""
        from kida import Environment

        tmpl_env = Environment()
        tmpl = tmpl_env.from_string("hello")
        # pass template object so no template lookup needed
        html = render_html("s", tmpl)
        assert "<!DOCTYPE html>" in html
