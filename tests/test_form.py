"""Tests for form.py — form reducer and field handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from milo._types import (
    Action,
    FieldSpec,
    FieldState,
    FieldType,
    FormState,
    Key,
    SpecialKey,
)
from milo.form import (
    _form_fallback,
    _handle_confirm_key,
    _handle_select_key,
    _handle_text_key,
    _make_initial_fields,
    form_reducer,
    make_form_reducer,
)


class TestMakeInitialFields:
    def test_text_field(self):
        specs = (FieldSpec(name="name", label="Name"),)
        fields = _make_initial_fields(specs)
        assert len(fields) == 1
        assert fields[0].value == ""
        assert fields[0].focused is True  # First field is focused

    def test_select_field(self):
        specs = (
            FieldSpec(
                name="env",
                label="Environment",
                field_type=FieldType.SELECT,
                choices=("dev", "prod"),
            ),
        )
        fields = _make_initial_fields(specs)
        assert fields[0].value == 0  # Default index

    def test_confirm_field(self):
        specs = (FieldSpec(name="ok", label="Continue?", field_type=FieldType.CONFIRM),)
        fields = _make_initial_fields(specs)
        assert fields[0].value is False

    def test_default_values(self):
        specs = (FieldSpec(name="name", label="Name", default="Alice"),)
        fields = _make_initial_fields(specs)
        assert fields[0].value == "Alice"


class TestHandleTextKey:
    def test_char_input(self):
        field = FieldState(value="", cursor=0)
        result = _handle_text_key(field, Key(char="a"))
        assert result.value == "a"
        assert result.cursor == 1

    def test_char_insert_middle(self):
        field = FieldState(value="ac", cursor=1)
        result = _handle_text_key(field, Key(char="b"))
        assert result.value == "abc"
        assert result.cursor == 2

    def test_backspace(self):
        field = FieldState(value="ab", cursor=2)
        result = _handle_text_key(field, Key(name=SpecialKey.BACKSPACE))
        assert result.value == "a"
        assert result.cursor == 1

    def test_backspace_at_start(self):
        field = FieldState(value="a", cursor=0)
        result = _handle_text_key(field, Key(name=SpecialKey.BACKSPACE))
        assert result is field

    def test_delete(self):
        field = FieldState(value="ab", cursor=0)
        result = _handle_text_key(field, Key(name=SpecialKey.DELETE))
        assert result.value == "b"

    def test_left_right(self):
        field = FieldState(value="abc", cursor=1)
        left = _handle_text_key(field, Key(name=SpecialKey.LEFT))
        assert left.cursor == 0
        right = _handle_text_key(field, Key(name=SpecialKey.RIGHT))
        assert right.cursor == 2

    def test_home_end(self):
        field = FieldState(value="abc", cursor=1)
        home = _handle_text_key(field, Key(name=SpecialKey.HOME))
        assert home.cursor == 0
        end = _handle_text_key(field, Key(name=SpecialKey.END))
        assert end.cursor == 3


class TestHandleConfirmKey:
    def test_yes(self):
        field = FieldState(value=False)
        result = _handle_confirm_key(field, Key(char="y"))
        assert result.value is True

    def test_no(self):
        field = FieldState(value=True)
        result = _handle_confirm_key(field, Key(char="n"))
        assert result.value is False

    def test_toggle(self):
        field = FieldState(value=False)
        result = _handle_confirm_key(field, Key(name=SpecialKey.LEFT))
        assert result.value is True


class TestFormReducer:
    def test_init_returns_empty(self):
        state = form_reducer(None, Action("@@INIT"))
        assert state == FormState()

    def test_submitted_is_terminal(self):
        state = FormState(submitted=True)
        result = form_reducer(state, Action("@@KEY", payload=Key(char="a")))
        assert result.submitted is True

    def test_text_input(self):
        specs = (FieldSpec(name="name", label="Name"),)
        state = FormState(
            fields=(FieldState(value="", cursor=0, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(char="a")))
        assert result.fields[0].value == "a"

    def test_tab_moves_to_next(self):
        specs = (
            FieldSpec(name="a", label="A"),
            FieldSpec(name="b", label="B"),
        )
        state = FormState(
            fields=(
                FieldState(value="x", cursor=1, focused=True),
                FieldState(value="", cursor=0, focused=False),
            ),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.TAB)))
        assert result.active_index == 1
        assert result.fields[0].focused is False
        assert result.fields[1].focused is True

    def test_enter_on_last_submits(self):
        specs = (FieldSpec(name="a", label="A"),)
        state = FormState(
            fields=(FieldState(value="x", cursor=1, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.ENTER)))
        assert result.submitted is True

    def test_validator_blocks_advance(self):
        def must_not_empty(val):
            return (bool(val), "Required")

        specs = (
            FieldSpec(name="a", label="A", validator=must_not_empty),
            FieldSpec(name="b", label="B"),
        )
        state = FormState(
            fields=(
                FieldState(value="", cursor=0, focused=True),
                FieldState(value="", cursor=0, focused=False),
            ),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.TAB)))
        assert result.active_index == 0
        assert result.fields[0].error == "Required"


class TestHandleSelectKey:
    def test_down_increments(self):
        spec = FieldSpec(
            name="env", label="Env", field_type=FieldType.SELECT, choices=("a", "b", "c")
        )
        field = FieldState(value="a", selected_index=0)
        result = _handle_select_key(field, Key(name=SpecialKey.DOWN), spec)
        assert result.selected_index == 1
        assert result.value == "b"

    def test_up_decrements(self):
        spec = FieldSpec(
            name="env", label="Env", field_type=FieldType.SELECT, choices=("a", "b", "c")
        )
        field = FieldState(value="b", selected_index=1)
        result = _handle_select_key(field, Key(name=SpecialKey.UP), spec)
        assert result.selected_index == 0
        assert result.value == "a"

    def test_wraps_around_down(self):
        spec = FieldSpec(name="env", label="Env", field_type=FieldType.SELECT, choices=("a", "b"))
        field = FieldState(value="b", selected_index=1)
        result = _handle_select_key(field, Key(name=SpecialKey.DOWN), spec)
        assert result.selected_index == 0
        assert result.value == "a"

    def test_wraps_around_up(self):
        spec = FieldSpec(name="env", label="Env", field_type=FieldType.SELECT, choices=("a", "b"))
        field = FieldState(value="a", selected_index=0)
        result = _handle_select_key(field, Key(name=SpecialKey.UP), spec)
        assert result.selected_index == 1
        assert result.value == "b"

    def test_unrelated_key_returns_same_field(self):
        spec = FieldSpec(name="env", label="Env", field_type=FieldType.SELECT, choices=("a", "b"))
        field = FieldState(value="a", selected_index=0)
        result = _handle_select_key(field, Key(char="x"), spec)
        assert result is field

    def test_empty_choices(self):
        spec = FieldSpec(name="env", label="Env", field_type=FieldType.SELECT, choices=())
        field = FieldState(value="", selected_index=0)
        result = _handle_select_key(field, Key(name=SpecialKey.DOWN), spec)
        assert result.selected_index == 0


class TestFormReducerSelectAndPassword:
    def test_select_field_dispatch(self):
        specs = (
            FieldSpec(
                name="env", label="Env", field_type=FieldType.SELECT, choices=("dev", "prod")
            ),
        )
        state = FormState(
            fields=(FieldState(value="dev", selected_index=0, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.DOWN)))
        assert result.fields[0].selected_index == 1
        assert result.fields[0].value == "prod"

    def test_password_field_accepts_chars(self):
        specs = (FieldSpec(name="pw", label="Password", field_type=FieldType.PASSWORD),)
        state = FormState(
            fields=(FieldState(value="", cursor=0, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(char="s")))
        assert result.fields[0].value == "s"

    def test_non_key_action_returns_same_state(self):
        specs = (FieldSpec(name="a", label="A"),)
        state = FormState(
            fields=(FieldState(value="x", cursor=1, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@TICK"))
        assert result is state

    def test_init_with_payload_builds_fields(self):
        specs = (
            FieldSpec(name="name", label="Name"),
            FieldSpec(name="age", label="Age"),
        )
        # Must pass a non-None state with payload to trigger the @@INIT+payload branch
        initial = FormState()
        state = form_reducer(initial, Action("@@INIT", payload=specs))
        assert len(state.fields) == 2

    def test_invalid_payload_type_ignored(self):
        specs = (FieldSpec(name="a", label="A"),)
        state = FormState(
            fields=(FieldState(value="x", cursor=1, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload="not a key"))
        assert result is state

    def test_out_of_bounds_index_returns_state(self):
        """If active_index >= len(fields), return state unchanged."""
        specs = (FieldSpec(name="a", label="A"),)
        state = FormState(
            fields=(),
            specs=specs,
            active_index=5,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(char="x")))
        assert result is state

    def test_confirm_field_dispatch(self):
        specs = (FieldSpec(name="ok", label="OK?", field_type=FieldType.CONFIRM),)
        state = FormState(
            fields=(FieldState(value=False, focused=True),),
            specs=specs,
            active_index=0,
        )
        result = form_reducer(state, Action("@@KEY", payload=Key(char="y")))
        assert result.fields[0].value is True

    def test_no_change_returns_same_state(self):
        """Keys that don't change anything return the same state object."""
        specs = (FieldSpec(name="ok", label="OK?", field_type=FieldType.CONFIRM),)
        state = FormState(
            fields=(FieldState(value=False, focused=True),),
            specs=specs,
            active_index=0,
        )
        # Unrecognized key for confirm field — returns same field, so same state
        result = form_reducer(state, Action("@@KEY", payload=Key(char="z")))
        assert result is state


class TestMakeFormReducer:
    def test_initializes_with_fields(self):
        specs = (
            FieldSpec(name="name", label="Name"),
            FieldSpec(name="age", label="Age"),
        )
        reducer = make_form_reducer(*specs)
        state = reducer(None, Action("@@INIT"))
        assert len(state.fields) == 2
        assert state.specs == specs

    def test_handles_key_input(self):
        specs = (FieldSpec(name="name", label="Name"),)
        reducer = make_form_reducer(*specs)
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("@@KEY", payload=Key(char="a")))
        assert state.fields[0].value == "a"

    def test_submit_on_enter(self):
        specs = (FieldSpec(name="name", label="Name"),)
        reducer = make_form_reducer(*specs)
        state = reducer(None, Action("@@INIT"))
        state = reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.ENTER)))
        assert state.submitted is True

    def test_navigate_on_submit(self):
        from milo._types import ReducerResult

        specs = (FieldSpec(name="name", label="Name"),)
        reducer = make_form_reducer(*specs, navigate_on_submit=True)
        state = reducer(None, Action("@@INIT"))
        result = reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.ENTER)))
        assert isinstance(result, ReducerResult)
        assert result.state.submitted is True
        assert len(result.sagas) == 1

    def test_navigate_on_submit_false_by_default(self):
        specs = (FieldSpec(name="name", label="Name"),)
        reducer = make_form_reducer(*specs)
        state = reducer(None, Action("@@INIT"))
        result = reducer(state, Action("@@KEY", payload=Key(name=SpecialKey.ENTER)))
        # Plain FormState, not ReducerResult
        assert isinstance(result, FormState)


class TestFormFallback:
    def test_text_field(self):
        specs = (FieldSpec(name="name", label="Name"),)
        with patch("builtins.input", return_value="Alice"):
            result = _form_fallback(specs)
        assert result == {"name": "Alice"}

    def test_confirm_field_yes(self):
        specs = (FieldSpec(name="ok", label="OK?", field_type=FieldType.CONFIRM),)
        with patch("builtins.input", return_value="y"):
            result = _form_fallback(specs)
        assert result == {"ok": True}

    def test_confirm_field_no(self):
        specs = (FieldSpec(name="ok", label="OK?", field_type=FieldType.CONFIRM),)
        with patch("builtins.input", return_value="n"):
            result = _form_fallback(specs)
        assert result == {"ok": False}

    def test_confirm_field_yes_long(self):
        specs = (FieldSpec(name="ok", label="OK?", field_type=FieldType.CONFIRM),)
        with patch("builtins.input", return_value="yes"):
            result = _form_fallback(specs)
        assert result == {"ok": True}

    def test_select_field_valid(self, capsys):
        specs = (
            FieldSpec(
                name="env", label="Env", field_type=FieldType.SELECT, choices=("dev", "prod")
            ),
        )
        with patch("builtins.input", return_value="2"):
            result = _form_fallback(specs)
        assert result == {"env": "prod"}

    def test_select_field_invalid_falls_back_to_first(self, capsys):
        specs = (
            FieldSpec(
                name="env", label="Env", field_type=FieldType.SELECT, choices=("dev", "prod")
            ),
        )
        with patch("builtins.input", return_value="99"):
            result = _form_fallback(specs)
        assert result == {"env": "dev"}

    def test_select_field_non_numeric_falls_back_to_first(self, capsys):
        specs = (
            FieldSpec(
                name="env", label="Env", field_type=FieldType.SELECT, choices=("dev", "prod")
            ),
        )
        with patch("builtins.input", return_value="abc"):
            result = _form_fallback(specs)
        assert result == {"env": "dev"}

    def test_select_empty_choices(self, capsys):
        specs = (FieldSpec(name="env", label="Env", field_type=FieldType.SELECT, choices=()),)
        with patch("builtins.input", return_value="1"):
            result = _form_fallback(specs)
        assert result == {"env": ""}

    def test_non_tty_calls_fallback(self):
        """form() should call _form_fallback when not a TTY."""
        from milo.form import form

        specs = (FieldSpec(name="name", label="Name"),)
        with patch("milo.form.is_tty", return_value=False):
            with patch("builtins.input", return_value="Bob"):
                result = form(*specs)
        assert result == {"name": "Bob"}


class TestFormTimeout:
    """Tests for form timeout behavior."""

    def test_timeout_raises_on_slow_input(self):
        """Form should raise TimeoutError when timeout expires."""
        import signal
        import sys

        if sys.platform == "win32" or not hasattr(signal, "SIGALRM"):
            pytest.skip("SIGALRM not available on this platform")

        def slow_input(prompt: str = "") -> str:
            import time

            time.sleep(5)
            return "never"

        specs = (FieldSpec(name="name", label="Name"),)

        with pytest.raises(TimeoutError, match="timed out"):
            with patch("builtins.input", side_effect=slow_input):
                _form_fallback(specs, timeout=1)

    def test_timeout_none_no_alarm(self):
        """No timeout should not set an alarm."""
        specs = (FieldSpec(name="name", label="Name"),)
        with patch("builtins.input", return_value="Bob"):
            result = _form_fallback(specs, timeout=None)
        assert result == {"name": "Bob"}

    def test_non_tty_auto_timeout(self):
        """Non-TTY form() should use default timeout."""
        from milo.form import _NON_TTY_DEFAULT_TIMEOUT, form

        with patch("milo.form.is_tty", return_value=False):
            with patch("milo.form._form_fallback") as mock_fb:
                mock_fb.return_value = {"name": "test"}
                specs = (FieldSpec(name="name", label="Name"),)
                form(*specs)
                mock_fb.assert_called_once()
                _, kwargs = mock_fb.call_args
                assert kwargs["timeout"] == _NON_TTY_DEFAULT_TIMEOUT

    def test_explicit_timeout_overrides_default(self):
        """Explicit timeout should override the non-TTY default."""
        from milo.form import form

        with patch("milo.form.is_tty", return_value=False):
            with patch("milo.form._form_fallback") as mock_fb:
                mock_fb.return_value = {"name": "test"}
                specs = (FieldSpec(name="name", label="Name"),)
                form(*specs, timeout=5.0)
                _, kwargs = mock_fb.call_args
                assert kwargs["timeout"] == 5.0
