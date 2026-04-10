# Benchmarks

Hot-path performance benchmarks using [pytest-benchmark](https://pytest-benchmark.readthedocs.io/).

## Running

```bash
# All benchmarks
make bench

# Or directly
PYTHON_GIL=0 uv run pytest benchmarks/ --benchmark-only -q

# Specific file
uv run pytest benchmarks/test_bench_store.py --benchmark-only -q

# With comparison to saved baseline
uv run pytest benchmarks/ --benchmark-only --benchmark-compare
```

## Reading Results

Each benchmark reports:

| Column | Meaning |
|--------|---------|
| **Min** | Fastest single iteration (best case) |
| **Mean** | Average across all iterations |
| **StdDev** | Standard deviation — high values signal instability |
| **Median** | Middle value (more robust than mean for skewed distributions) |
| **OPS** | Operations per second (1/Mean) |
| **Rounds** | How many times the benchmark ran |

For regression detection, compare **Median** values — they're most resistant to outliers.

## Benchmark Categories

| File | Category | What It Measures |
|------|----------|-----------------|
| `test_bench_store.py` | Store dispatch | Reducer execution, state size scaling, recording overhead |
| `test_bench_contention.py` | Lock contention | Multi-thread dispatch throughput, listener overhead, lock fairness |
| `test_bench_reducer.py` | Reducer complexity | Cmd/Batch/Sequence costs, combine_reducers scaling, listener notification |
| `test_bench_saga.py` | Saga executor | End-to-end saga latency, pool saturation, blocking call impact |
| `test_bench_render.py` | Rendering | Kida template render by size, env creation, terminal update simulation |
| `test_bench_mcp.py` | MCP protocol | JSON-RPC parse/serialize, router dispatch, tools/list generation, full round-trip |
| `test_bench_schema.py` | Schema generation | function_to_schema by param count, type complexity, Annotated constraints |
| `test_bench_gateway.py` | Gateway | Discovery cost, proxied tools/call, tool routing, scaling with N children |

## Adding a Benchmark

1. Create `benchmarks/test_bench_<area>.py`
2. Use fixtures from `conftest.py` (e.g., `store_factory`, `cli_factory`)
3. Follow the naming convention: `test_bench_<what_you_measure>`
4. Each benchmark function should measure one thing

```python
def test_bench_my_operation(benchmark, store_factory) -> None:
    """One-line description of what this measures."""
    store = store_factory(some_reducer, initial_state)
    action = Action("my_action")
    benchmark(store.dispatch, action)
```

## Stability

Benchmarks should produce < 10% variance across consecutive runs on the same machine. If a benchmark is flaky:

- Check for GC interference (pytest-benchmark handles warmup automatically)
- Ensure no background processes are competing for CPU
- Consider increasing `--benchmark-min-rounds`

## CI Integration

CI runs benchmarks via `.github/workflows/benchmarks.yml` with `PYTHON_GIL=0` (free-threading mode):

- **Weekly** (Sunday 3am UTC): full run, results uploaded as artifact
- **On PRs** (when `src/`, `benchmarks/`, or `pyproject.toml` change): runs benchmarks, compares against latest main baseline, posts a comment with regression/improvement summary
- Regressions >20% are flagged with a warning in the PR comment
