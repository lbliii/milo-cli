"""Parser construction benchmarks for public command presentation metadata."""

from __future__ import annotations

from typing import Annotated

from milo import CLI, MinLen, Option, Positional


def _make_chirp_shaped_cli() -> CLI:
    cli = CLI(
        name="chirp",
        version_flags=("-V", "--version"),
        version_report=lambda: "chirp 0.8.2\nkida 1.4.0",
    )

    @cli.command("check")
    def check(
        app: Annotated[str, Positional("APP")],
        include: Annotated[list[str] | None, Option(aliases=("-i",)), MinLen(1)] = None,
        strict: bool = False,
    ) -> dict[str, object]:
        return {"app": app, "include": include or [], "strict": strict}

    for name in ("run", "dev"):
        cli.lazy_command(
            name,
            "chirp.cli.server:run",
            surfaces=("cli",),
            schema={
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "x-milo-cli": {"kind": "positional", "metavar": "APP"},
                    }
                },
                "required": ["app"],
            },
        )
    return cli


def test_bench_chirp_shaped_parser_construction(benchmark) -> None:
    """Build a parser with positionals, aliases, surfaces, and lazy schemas."""
    cli = _make_chirp_shaped_cli()
    benchmark(cli.build_parser)
