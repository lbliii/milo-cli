"""Tests for _types.py — frozen dataclasses and enums."""

from __future__ import annotations

import pytest

from milo._types import (
    BUILTIN_ACTIONS,
    Action,
    AppStatus,
    Call,
    Delay,
    FieldSpec,
    FieldState,
    FieldType,
    Fork,
    FormState,
    Key,
    Put,
    Quit,
    ReducerResult,
    RenderTarget,
    Screen,
    Select,
    SpecialKey,
    Transition,
)


class TestKey:
    def test_default_key(self):
        k = Key()
        assert k.char == ""
        assert k.name is None
        assert k.ctrl is False
        assert k.alt is False
        assert k.shift is False

    def test_char_key(self):
        k = Key(char="a")
        assert k.char == "a"

    def test_special_key(self):
        k = Key(name=SpecialKey.ENTER)
        assert k.name == SpecialKey.ENTER

    def test_modifier_key(self):
        k = Key(char="c", ctrl=True)
        assert k.ctrl is True

    def test_frozen(self):
        k = Key(char="a")
        with pytest.raises(AttributeError):
            k.char = "b"

    def test_equality(self):
        assert Key(char="a") == Key(char="a")
        assert Key(char="a") != Key(char="b")


class TestAction:
    def test_basic(self):
        a = Action("test")
        assert a.type == "test"
        assert a.payload is None

    def test_with_payload(self):
        a = Action("test", payload=42)
        assert a.payload == 42

    def test_frozen(self):
        a = Action("test")
        with pytest.raises(AttributeError):
            a.type = "other"

    def test_builtin_actions(self):
        assert "@@INIT" in BUILTIN_ACTIONS
        assert "@@KEY" in BUILTIN_ACTIONS
        assert "@@QUIT" in BUILTIN_ACTIONS
        assert "@@SAGA_ERROR" in BUILTIN_ACTIONS
        assert "@@SAGA_CANCELLED" in BUILTIN_ACTIONS
        assert "@@CMD_ERROR" in BUILTIN_ACTIONS
        assert "@@PHASE_SKIPPED" in BUILTIN_ACTIONS
        assert "@@PHASE_RETRY" in BUILTIN_ACTIONS
        assert len(BUILTIN_ACTIONS) == 18


class TestEffects:
    def test_call(self):
        c = Call(fn=len, args=([1, 2, 3],))
        assert c.fn is len
        assert c.args == ([1, 2, 3],)

    def test_put(self):
        p = Put(action=Action("test"))
        assert p.action.type == "test"

    def test_select_default(self):
        s = Select()
        assert s.selector is None

    def test_select_with_selector(self):
        s = Select(selector=lambda x: x.count)
        assert s.selector is not None

    def test_fork(self):
        def gen():
            yield

        g = gen()
        f = Fork(saga=g)
        assert f.saga is g

    def test_delay(self):
        d = Delay(seconds=1.5)
        assert d.seconds == 1.5


class TestReducerResult:
    def test_basic(self):
        r = ReducerResult(state=42)
        assert r.state == 42
        assert r.sagas == ()

    def test_with_sagas(self):
        def saga():
            yield

        r = ReducerResult(state=42, sagas=(saga,))
        assert len(r.sagas) == 1


class TestQuit:
    def test_basic(self):
        q = Quit(state=42)
        assert q.state == 42
        assert q.code == 0
        assert q.sagas == ()

    def test_with_code(self):
        q = Quit(state=0, code=1)
        assert q.code == 1

    def test_with_sagas(self):
        def saga():
            yield

        q = Quit(state=0, sagas=(saga,))
        assert len(q.sagas) == 1

    def test_frozen(self):
        q = Quit(state=0)
        with pytest.raises(AttributeError):
            q.state = 1


class TestEnums:
    def test_app_status(self):
        assert AppStatus.IDLE.name == "IDLE"
        assert AppStatus.RUNNING.name == "RUNNING"

    def test_render_target(self):
        assert RenderTarget.TERMINAL.name == "TERMINAL"
        assert RenderTarget.HTML.name == "HTML"

    def test_field_type(self):
        assert FieldType.TEXT.name == "TEXT"
        assert FieldType.SELECT.name == "SELECT"
        assert FieldType.CONFIRM.name == "CONFIRM"
        assert FieldType.PASSWORD.name == "PASSWORD"


class TestFieldSpec:
    def test_defaults(self):
        f = FieldSpec(name="username", label="Username")
        assert f.field_type == FieldType.TEXT
        assert f.choices == ()
        assert f.validator is None

    def test_select(self):
        f = FieldSpec(
            name="env",
            label="Environment",
            field_type=FieldType.SELECT,
            choices=("dev", "staging", "prod"),
        )
        assert f.choices == ("dev", "staging", "prod")


class TestFieldState:
    def test_defaults(self):
        f = FieldState()
        assert f.value == ""
        assert f.cursor == 0
        assert f.error == ""
        assert f.focused is False

    def test_frozen(self):
        f = FieldState(value="hello")
        with pytest.raises(AttributeError):
            f.value = "world"


class TestFormState:
    def test_defaults(self):
        f = FormState()
        assert f.fields == ()
        assert f.specs == ()
        assert f.active_index == 0
        assert f.submitted is False


class TestScreen:
    def test_basic(self):
        def r(s, a):
            return s

        s = Screen(name="main", template="main.kida", reducer=r)
        assert s.name == "main"
        assert s.template == "main.kida"


class TestTransition:
    def test_basic(self):
        t = Transition(from_screen="a", to_screen="b", on_action="@@NAVIGATE")
        assert t.from_screen == "a"
        assert t.to_screen == "b"
