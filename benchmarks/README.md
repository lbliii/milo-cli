# Benchmarks

Hot-path checks using [pytest-benchmark](https://pytest-benchmark.readthedocs.io/).

```bash
make bench
# or
uv run pytest benchmarks/ --benchmark-only -q
```

CI runs weekly and on manual dispatch via `.github/workflows/benchmarks.yml` (not on every PR).
