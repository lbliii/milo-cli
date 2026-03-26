"""Shared test fixtures."""

from __future__ import annotations

import pytest

from milo._types import Action


@pytest.fixture
def action_init():
    return Action("@@INIT")


@pytest.fixture
def action_key():
    from milo._types import Key
    return Action("@@KEY", payload=Key(char="a"))


@pytest.fixture
def action_quit():
    return Action("@@QUIT")
