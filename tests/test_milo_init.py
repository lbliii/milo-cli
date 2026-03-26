"""Tests for milo/__init__.py — lazy imports and __getattr__."""

from __future__ import annotations

import pytest


class TestLazyImports:
    def test_action_accessible(self):
        import milo

        Action = milo.Action
        from milo._types import Action as RealAction

        assert Action is RealAction

    def test_key_accessible(self):
        import milo

        Key = milo.Key
        from milo._types import Key as RealKey

        assert Key is RealKey

    def test_special_key_accessible(self):
        import milo

        assert milo.SpecialKey is not None

    def test_app_status_accessible(self):
        import milo
        from milo._types import AppStatus

        assert milo.AppStatus is AppStatus

    def test_render_target_accessible(self):
        import milo
        from milo._types import RenderTarget

        assert milo.RenderTarget is RenderTarget

    def test_field_type_accessible(self):
        import milo
        from milo._types import FieldType

        assert milo.FieldType is FieldType

    def test_field_spec_accessible(self):
        import milo
        from milo._types import FieldSpec

        assert milo.FieldSpec is FieldSpec

    def test_field_state_accessible(self):
        import milo
        from milo._types import FieldState

        assert milo.FieldState is FieldState

    def test_form_state_accessible(self):
        import milo
        from milo._types import FormState

        assert milo.FormState is FormState

    def test_screen_accessible(self):
        import milo
        from milo._types import Screen

        assert milo.Screen is Screen

    def test_transition_accessible(self):
        import milo
        from milo._types import Transition

        assert milo.Transition is Transition

    def test_reducer_result_accessible(self):
        import milo
        from milo._types import ReducerResult

        assert milo.ReducerResult is ReducerResult

    def test_call_accessible(self):
        import milo
        from milo._types import Call

        assert milo.Call is Call

    def test_put_accessible(self):
        import milo
        from milo._types import Put

        assert milo.Put is Put

    def test_select_accessible(self):
        import milo
        from milo._types import Select

        assert milo.Select is Select

    def test_fork_accessible(self):
        import milo
        from milo._types import Fork

        assert milo.Fork is Fork

    def test_delay_accessible(self):
        import milo
        from milo._types import Delay

        assert milo.Delay is Delay

    def test_builtin_actions_accessible(self):
        import milo
        from milo._types import BUILTIN_ACTIONS

        assert milo.BUILTIN_ACTIONS is BUILTIN_ACTIONS

    def test_milo_error_accessible(self):
        import milo
        from milo._errors import MiloError

        assert milo.MiloError is MiloError

    def test_input_error_accessible(self):
        import milo
        from milo._errors import InputError

        assert milo.InputError is InputError

    def test_state_error_accessible(self):
        import milo
        from milo._errors import StateError

        assert milo.StateError is StateError

    def test_form_error_accessible(self):
        import milo
        from milo._errors import FormError

        assert milo.FormError is FormError

    def test_app_error_accessible(self):
        import milo
        from milo._errors import AppError

        assert milo.AppError is AppError

    def test_flow_error_accessible(self):
        import milo
        from milo._errors import FlowError

        assert milo.FlowError is FlowError

    def test_error_code_accessible(self):
        import milo
        from milo._errors import ErrorCode

        assert milo.ErrorCode is ErrorCode

    def test_store_accessible(self):
        import milo
        from milo.state import Store

        assert milo.Store is Store

    def test_combine_reducers_accessible(self):
        import milo
        from milo.state import combine_reducers

        assert milo.combine_reducers is combine_reducers

    def test_app_accessible(self):
        import milo
        from milo.app import App

        assert milo.App is App

    def test_run_accessible(self):
        import milo
        from milo.app import run

        assert milo.run is run

    def test_render_html_accessible(self):
        import milo
        from milo.app import render_html

        assert milo.render_html is render_html

    def test_flow_screen_accessible(self):
        import milo
        from milo.flow import FlowScreen

        assert milo.FlowScreen is FlowScreen

    def test_flow_accessible(self):
        import milo
        from milo.flow import Flow

        assert milo.Flow is Flow

    def test_flow_state_accessible(self):
        import milo
        from milo.flow import FlowState

        assert milo.FlowState is FlowState

    def test_form_accessible(self):
        import importlib

        import milo

        # Verify __getattr__ resolves "form" to the function from milo.form module
        form_fn = importlib.import_module("milo.form").form
        # milo.form attribute should be callable (function), not a module
        result = milo.__getattr__("form")
        assert callable(result)
        assert result is form_fn

    def test_form_reducer_accessible(self):
        import milo
        from milo.form import form_reducer

        assert milo.form_reducer is form_reducer

    def test_help_renderer_accessible(self):
        import milo
        from milo.help import HelpRenderer

        assert milo.HelpRenderer is HelpRenderer

    def test_dev_server_accessible(self):
        import milo
        from milo.dev import DevServer

        assert milo.DevServer is DevServer

    def test_unknown_attribute_raises(self):
        import milo

        with pytest.raises(AttributeError, match="module 'milo' has no attribute"):
            _ = milo.NonExistentAttribute12345

    def test_version(self):
        import milo

        assert milo.__version__ == "0.1.0"

    def test_py_mod_gil(self):
        import milo

        assert milo._Py_mod_gil() == 0

    def test_all_contains_expected(self):
        import milo

        assert "Action" in milo.__all__
        assert "App" in milo.__all__
        assert "Store" in milo.__all__
