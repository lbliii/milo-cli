---
title: Interactive Forms
nav_title: Forms
description: Text, select, confirm, and password fields with validation and TTY fallback.
weight: 40
draft: false
lang: en
tags: [forms, fields, input, validation]
keywords: [forms, fields, text, select, confirm, password, validation]
category: usage
icon: textbox
---

Milo includes a built-in form system for collecting structured input. Define fields declaratively with `FieldSpec`, then run `form()` to get a dictionary of responses.

## Quick example

```python
from milo import form, FieldSpec, FieldType

result = form(
    FieldSpec("name", "Your name"),
    FieldSpec("env", "Environment", field_type=FieldType.SELECT,
              choices=("dev", "staging", "prod")),
    FieldSpec("confirm", "Deploy?", field_type=FieldType.CONFIRM),
)
# result = {"name": "Alice", "env": "prod", "confirm": True}
```

## Field types

:::{tab-set}
:::{tab-item} Text
:badge: Default

The default field type. Supports cursor movement (arrows, Home, End), insert, delete, and backspace.

```python
FieldSpec("name", "Your name")
FieldSpec("email", "Email", placeholder="user@example.com")
```

:::{/tab-item}

:::{tab-item} Password

Same as text, but input is masked.

```python
FieldSpec("token", "API Token", field_type=FieldType.PASSWORD)
```

:::{/tab-item}

:::{tab-item} Select

Cycle through choices with Up/Down arrow keys. Renders as a radio-style list with `[x]` / `[ ]` indicators.

```python
FieldSpec("region", "Region", field_type=FieldType.SELECT,
          choices=("us-east-1", "eu-west-1", "ap-southeast-1"))
```

:::{/tab-item}

:::{tab-item} Confirm

Yes/No toggle. Use Y/N keys or Left/Right arrows.

```python
FieldSpec("proceed", "Continue?", field_type=FieldType.CONFIRM,
          default=True)
```

:::{/tab-item}
:::{/tab-set}

## Validation

Pass a validator function to `FieldSpec`. It receives the field value and returns `None` (valid) or an error message string.

```python
def validate_email(value):
    if "@" not in value:
        return "Must be a valid email address"
    return None

FieldSpec("email", "Email", validator=validate_email)
```

:::{warning}
Validators run on every keystroke for text fields. Keep them fast — avoid network calls or file I/O. For async validation, use a [[docs/usage/sagas|saga]] on form submission instead.
:::

## Keyboard navigation

| Key | Action |
|-----|--------|
| Tab / Shift+Tab | Move between fields |
| Enter | Submit form (or advance to next field) |
| Up / Down | Cycle select choices |
| Left / Right | Toggle confirm fields |
| Home / End | Jump to start/end of text |
| Ctrl+C | Cancel form |

## TTY fallback

When stdin is not a TTY (piped input, CI environments), `form()` falls back to plain `input()` prompts automatically. No code changes needed.

:::{tip}
This means forms work in CI pipelines — pipe answers via stdin or set environment variables and read them in your reducer as defaults.
:::

## Using form_reducer directly

For full control, use `form_reducer` directly in an `App` instead of the `form()` helper:

```python
from milo import App
from milo.form import form_reducer

specs = [FieldSpec("name", "Name"), FieldSpec("age", "Age")]
app = App(template="form.txt", reducer=form_reducer, initial_state={"specs": specs})
final = app.run()
```

:::{dropdown} When to use form() vs form_reducer
:icon: info

**Use `form()`** for standalone data collection — it creates its own `App`, runs it, and returns the result dict. Good for scripts and CLI tools.

**Use `form_reducer`** when forms are part of a larger app — embed form state in a [[docs/usage/flows|Flow]] screen, combine with other reducers, or add custom middleware.

:::
