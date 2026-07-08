# CLI + MCP comparison fixture

These two complete entrypoints implement the same `deploy` capability. Both
provide a human CLI command and a local stdio MCP tool. The Milo entrypoint also
provides llms.txt discovery through its built-in `--llms-txt` projection.

The comparison page counts physical source lines after excluding blank lines
and comment-only lines. Imports, docstrings, registration, presentation, and
dispatch all count. The metric is a small composition-cost illustration, not a
framework-wide productivity or performance benchmark.

Run the CLI paths:

```bash
uv run python benchmarks/comparison/milo_app.py deploy \
  --environment staging --service api
uv run --with typer==0.26.8 --with fastmcp==3.4.3 \
  python benchmarks/comparison/typer_fastmcp_app.py deploy \
  --environment staging --service api
```

Inspect the generated MCP surfaces:

```bash
uv run python benchmarks/comparison/milo_app.py --llms-txt
uv run --with fastmcp==3.4.3 fastmcp inspect \
  benchmarks/comparison/typer_fastmcp_app.py:mcp --format mcp
```

`tests/docs/test_public_claims.py` owns the line-count calculation and guards
the published totals against drift. The composed fixture was executed and
inspected with Typer 0.26.8 and FastMCP 3.4.3 on 2026-07-08; the pins keep the
reproduction tied to the implementation that was measured.
