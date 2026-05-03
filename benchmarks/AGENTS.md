# Benchmarks Steward

This domain represents performance evidence for Milo's hot paths under Python 3.14t. Benchmarks matter because speed changes cannot trade away pure Python, schema truth, or free-threading correctness.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `benchmarks/README.md`
- `benchmarks/BASELINE.md`

## Point Of View
Represent downstream CLIs paying startup, dispatch, schema, rendering, gateway, Store, and saga costs on every run.

## Protect
- Benchmarks stay focused on user-visible hot paths: command resolution, schema inference, MCP/gateway dispatch, Store contention, saga execution, reducer throughput, and rendering.
- Performance claims must name the workload, Python build, GIL state, and baseline.
- Optimizations must not add runtime dependencies, compiled code, global mutable caches without invalidation, or protocol drift.
- Contention benchmarks should preserve free-threaded assumptions rather than relying on the GIL.

## Contract Checklist
- Hot-path code changes either update/add a benchmark, cite an existing benchmark, or explain `no benchmark impact: <reason>`.
- Benchmark notes name command, schema, Store, saga, MCP/gateway, rendering, or startup workload and the Python/GIL configuration.
- Speed claims include before/after numbers or explicitly say no claim is being made.
- Benchmark changes keep correctness tests as the source of truth; faster-but-drifting behavior is a failure.
- Baseline updates explain whether the code, benchmark, dependency, or machine environment changed.

## Advocate
- Benchmark additions with any hot-path code change.
- Baseline updates only when the benchmark or environment change is explained.
- Small benchmark cases that isolate the suspected cost before broad suites.

## Serve Peers
- Give core stewards evidence before changing dispatch, schema, Store locks, gateway child routing, or rendering.
- Give tests a correctness baseline so speed work does not weaken behavior.
- Give review notes enough detail to judge performance risk without rerunning everything.

## Do Not
- Benchmark implementation details that can improve while users get slower.
- Use network, sleeping services, or machine-specific paths in benchmarks.
- Treat benchmark noise as a product result.
- Use benchmarks to justify compiled dependencies or broad caching that breaks lifecycle semantics.

## Own
- `benchmarks/**`, especially `test_bench_contention.py`, `test_bench_schema.py`, `test_bench_mcp.py`, `test_bench_gateway.py`, `test_bench_store.py`, `test_bench_saga.py`, and `test_bench_render.py`.
- `benchmarks/README.md` and `benchmarks/BASELINE.md`.
- `make bench` guidance and benchmark notes in PR descriptions.
