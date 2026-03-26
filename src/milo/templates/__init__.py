"""Built-in templates and template environment factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_TEMPLATE_DIR = Path(__file__).parent


def get_env(**kwargs: Any) -> Any:
    """Create a kida Environment with the built-in template loader.

    Returns a kida Environment with a chained loader:
    user templates -> milo built-in templates -> kida components.
    """
    from kida import Environment, FileSystemLoader

    loaders = []

    # User-provided loader
    if "loader" in kwargs:
        user_loader = kwargs.pop("loader")
        if user_loader is not None:
            loaders.append(user_loader)

    # Built-in milo templates
    loaders.append(FileSystemLoader(str(_TEMPLATE_DIR)))

    if len(loaders) == 1:
        loader = loaders[0]
    else:
        from kida import ChoiceLoader

        loader = ChoiceLoader(loaders)

    return Environment(loader=loader, **kwargs)
