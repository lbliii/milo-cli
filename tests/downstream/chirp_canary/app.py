"""Chirp-shaped CLI registered only through released Milo public APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from milo import CLI

_ROOT = Path(__file__).resolve().parent
CONTRACT = cast(dict[str, Any], json.loads((_ROOT / "contract.json").read_text(encoding="utf-8")))


def _version_report() -> str:
    versions = CONTRACT["versions"]
    return f"chirp {versions['chirp']} canary on milo {versions['milo']}"


cli = CLI(
    name="chirp",
    description="Released Chirp command contract expressed through Milo.",
    version=CONTRACT["versions"]["chirp"],
    version_flags=("-V", "--version"),
    version_report=_version_report,
)

for command_name, command in CONTRACT["commands"].items():
    cli.lazy_command(
        command_name,
        f"chirp_canary.handlers:{command_name.replace('-', '_')}",
        description=command["description"],
        schema=command["schema"],
        surfaces=command["surfaces"],
        annotations=command.get("annotations"),
    )


if __name__ == "__main__":
    cli.run()
