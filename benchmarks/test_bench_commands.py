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


def _make_large_lazy_cli(size: int = 100) -> CLI:
    cli = CLI(name="large")
    for index in range(size):
        cli.lazy_command(
            f"command-{index}",
            "json:dumps",
            description=f"Command {index}",
            schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
            },
        )
    return cli


def test_bench_large_lazy_navigation_parser(benchmark) -> None:
    """Build metadata-only navigation for a large lazy command registry."""
    cli = _make_large_lazy_cli()
    benchmark(cli._build_navigation_parser)


def test_bench_large_lazy_full_parser(benchmark) -> None:
    """Retain the explicit full-tree parser baseline for conflict/tooling work."""
    cli = _make_large_lazy_cli()
    benchmark(cli.build_parser)


def test_bench_large_lazy_selected_parser(benchmark) -> None:
    """Build only one selected leaf parser in a large lazy registry."""
    cli = _make_large_lazy_cli()
    navigation = cli._build_navigation_parser()
    args, _ = navigation.parse_known_args(["command-50", "--value", "ok"])
    selected = cli._selected_command_path(args)
    assert selected is not None
    benchmark(cli._build_selected_parser, *selected)
