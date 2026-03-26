"""Form fields and form reducer."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from milo._types import (
    Action,
    FieldSpec,
    FieldState,
    FieldType,
    FormState,
    Key,
    SpecialKey,
)
from milo.input._platform import is_tty


def _make_initial_fields(specs: tuple[FieldSpec, ...]) -> tuple[FieldState, ...]:
    """Create initial field states from specs."""
    fields = []
    for i, spec in enumerate(specs):
        default = spec.default if spec.default is not None else ""
        if spec.field_type == FieldType.CONFIRM:
            default = spec.default if spec.default is not None else False
        elif spec.field_type == FieldType.SELECT:
            default = spec.default if spec.default is not None else 0
        fields.append(
            FieldState(
                value=default,
                cursor=len(str(default)) if isinstance(default, str) else 0,
                focused=(i == 0),
            )
        )
    return tuple(fields)


def form_reducer(state: FormState | None, action: Action) -> FormState:
    """Reducer for form state."""
    if state is None:
        return FormState()

    if state.submitted:
        return state

    if action.type == "@@INIT" and action.payload and isinstance(action.payload, tuple):
        specs = action.payload
        return FormState(
            fields=_make_initial_fields(specs),
            specs=specs,
            active_index=0,
        )

    if action.type != "@@KEY":
        return state

    key: Key = action.payload
    if not isinstance(key, Key):
        return state

    idx = state.active_index
    if idx >= len(state.fields) or idx >= len(state.specs):
        return state

    field = state.fields[idx]
    spec = state.specs[idx]

    # Tab / Enter: move to next field or submit
    if key.name == SpecialKey.TAB or key.name == SpecialKey.ENTER:
        if key.name == SpecialKey.ENTER and spec.field_type != FieldType.TEXT:
            pass  # Enter confirms select/confirm fields too
        # Validate current field
        if spec.validator:
            ok, err = spec.validator(field.value)
            if not ok:
                new_field = replace(field, error=err)
                fields = _replace_field(state.fields, idx, new_field)
                return replace(state, fields=fields)

        if idx < len(state.fields) - 1:
            # Move to next field
            fields = _replace_field(
                state.fields,
                idx,
                replace(field, focused=False, error=""),
            )
            next_field = replace(state.fields[idx + 1], focused=True)
            fields = _replace_field(fields, idx + 1, next_field)
            return replace(state, fields=fields, active_index=idx + 1)
        else:
            # Submit
            return replace(state, submitted=True)

    # Shift+Tab: move to previous field
    if key.name == SpecialKey.TAB and key.shift:
        if idx > 0:
            fields = _replace_field(state.fields, idx, replace(field, focused=False))
            prev_field = replace(state.fields[idx - 1], focused=True)
            fields = _replace_field(fields, idx - 1, prev_field)
            return replace(state, fields=fields, active_index=idx - 1)
        return state

    # Field-type specific handling
    match spec.field_type:
        case FieldType.TEXT | FieldType.PASSWORD:
            new_field = _handle_text_key(field, key)
        case FieldType.SELECT:
            new_field = _handle_select_key(field, key, spec)
        case FieldType.CONFIRM:
            new_field = _handle_confirm_key(field, key)
        case _:
            new_field = field

    if new_field is not field:
        fields = _replace_field(state.fields, idx, new_field)
        return replace(state, fields=fields)

    return state


def _handle_text_key(field: FieldState, key: Key) -> FieldState:
    """Handle keypress for text/password fields."""
    value = str(field.value)
    cursor = field.cursor

    if key.name == SpecialKey.BACKSPACE:
        if cursor > 0:
            value = value[: cursor - 1] + value[cursor:]
            cursor -= 1
        else:
            return field
    elif key.name == SpecialKey.DELETE:
        if cursor < len(value):
            value = value[:cursor] + value[cursor + 1 :]
        else:
            return field
    elif key.name == SpecialKey.LEFT:
        cursor = max(0, cursor - 1)
    elif key.name == SpecialKey.RIGHT:
        cursor = min(len(value), cursor + 1)
    elif key.name == SpecialKey.HOME:
        cursor = 0
    elif key.name == SpecialKey.END:
        cursor = len(value)
    elif key.char and key.char.isprintable() and not key.ctrl and not key.alt:
        value = value[:cursor] + key.char + value[cursor:]
        cursor += 1
    else:
        return field

    return replace(field, value=value, cursor=cursor, error="")


def _handle_select_key(field: FieldState, key: Key, spec: FieldSpec) -> FieldState:
    """Handle keypress for select fields."""
    idx = field.selected_index
    count = len(spec.choices)

    if key.name == SpecialKey.UP:
        idx = (idx - 1) % count if count else 0
    elif key.name == SpecialKey.DOWN:
        idx = (idx + 1) % count if count else 0
    else:
        return field

    return replace(field, selected_index=idx, value=spec.choices[idx] if spec.choices else "")


def _handle_confirm_key(field: FieldState, key: Key) -> FieldState:
    """Handle keypress for confirm fields."""
    if key.char in ("y", "Y"):
        return replace(field, value=True)
    elif key.char in ("n", "N"):
        return replace(field, value=False)
    elif key.name in (SpecialKey.LEFT, SpecialKey.RIGHT):
        return replace(field, value=not field.value)
    return field


def _replace_field(
    fields: tuple[FieldState, ...], index: int, new: FieldState
) -> tuple[FieldState, ...]:
    """Return a new tuple with one field replaced."""
    lst = list(fields)
    lst[index] = new
    return tuple(lst)


def form(
    *specs: FieldSpec,
    env: Any = None,
) -> dict[str, Any]:
    """Run an interactive form, return field values.

    Falls back to input() if not a TTY.
    """
    if not is_tty():
        return _form_fallback(specs)

    from milo.app import App

    initial = FormState(
        fields=_make_initial_fields(specs),
        specs=specs,
        active_index=0,
    )
    # Focus the first field
    if initial.fields:
        fields = list(initial.fields)
        fields[0] = replace(fields[0], focused=True)
        initial = replace(initial, fields=tuple(fields))

    app = App(
        template="form.txt",
        reducer=form_reducer,
        initial_state=initial,
        env=env,
    )
    final: FormState = app.run()
    return {spec.name: field.value for spec, field in zip(specs, final.fields, strict=False)}


def _form_fallback(specs: tuple[FieldSpec, ...] | tuple) -> dict[str, Any]:
    """Non-TTY fallback using input()."""
    values: dict[str, Any] = {}
    for spec in specs:
        match spec.field_type:
            case FieldType.CONFIRM:
                raw = input(f"{spec.label} (y/n): ").strip().lower()
                values[spec.name] = raw in ("y", "yes")
            case FieldType.SELECT:
                print(f"{spec.label}:")
                for i, choice in enumerate(spec.choices):
                    print(f"  {i + 1}. {choice}")
                raw = input("Choice: ").strip()
                try:
                    idx = int(raw) - 1
                    values[spec.name] = spec.choices[idx]
                except ValueError, IndexError:
                    values[spec.name] = spec.choices[0] if spec.choices else ""
            case _:
                values[spec.name] = input(f"{spec.label}: ").strip()
    return values
