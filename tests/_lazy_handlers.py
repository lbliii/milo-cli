"""Test module for lazy command loading. Imported only when resolved."""

IMPORT_COUNT = 0


def greet(name: str, loud: bool = False) -> str:
    """Say hello."""
    global IMPORT_COUNT
    IMPORT_COUNT += 1
    msg = f"Hello, {name}!"
    return msg.upper() if loud else msg


def add(a: int, b: int = 0) -> int:
    """Add two numbers."""
    return a + b


def deploy(target: str, verbose: bool = True) -> str:
    """Deploy to target."""
    return f"deploy {target} verbose={verbose}"
