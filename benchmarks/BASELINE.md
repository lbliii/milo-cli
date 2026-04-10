# Benchmark Baseline — v0.2.0-dev

**Date**: 2026-04-09
**Platform**: macOS Darwin 25.3.0, Apple Silicon
**Python**: CPython 3.14.3
**Suite**: 74 benchmarks across 7 files

---

## Store Dispatch

Core dispatch path: acquire lock → run reducer → unwrap result → record (optional) → notify listeners → schedule effects.

| Benchmark | Median | OPS | Notes |
|---|---|---|---|
| noop reducer | 225ns | 4.4M | Floor: lock + return |
| dict merge | 287ns | 3.4M | Typical app pattern |
| ReducerResult unwrap | 619ns | 1.5M | 2.7x noop — isinstance checks + field extraction |
| + Cmd | 2.5μs | 209K | ThreadPoolExecutor.submit() cost |
| + Sequence(4) | 3.1μs | 173K | Single submit for serial chain |
| + Batch(4) | 8.2μs | 65K | 4 concurrent submits |
| state-5 keys | 300ns | 3.1M | Dict spread cost |
| state-50 keys | 400ns | 2.4M | +33% vs 5 keys |
| state-500 keys | 1.3μs | 747K | 5.8x vs 5 keys (dict copy dominates) |
| recording (small) | 661ns | 1.3M | SHA256 of repr(0) |
| recording (200 keys) | **46.8μs** | 21K | **167x noop** — repr + SHA256 of large state |

### Listeners

| Listeners | Median | vs 0 |
|---|---|---|
| 0 | 227ns | 1x |
| 4 | 289ns | 1.3x |
| 16 | 446ns | 2.0x |

### combine_reducers

| Slices | Median | vs 1 slice |
|---|---|---|
| 2 | 563ns | 1x |
| 5 | 817ns | 1.5x |
| 10 | 1.3μs | 2.4x |

---

## Lock Contention

200 dispatches per thread to the same store, measuring total wall-clock time.

| Threads | Noop median | Dict-merge median | Scaling factor |
|---|---|---|---|
| 1 | 109μs | 116μs | 1.0x |
| 2 | 190μs | 190μs | 1.7x |
| 4 | 312μs | 356μs | 3.1x |
| 8 | 566μs | 661μs | 5.7x |

4 listeners on top of 4 threads: 405μs (1.3x overhead vs no listeners).
Lock fairness check passes — no thread starvation observed.

---

## Saga Executor

End-to-end: dispatch action → saga runs on thread pool → result action dispatched.

| Pattern | Median | Notes |
|---|---|---|
| Simple (1 Call + 1 Put) | 39μs | Pool submit + generator step |
| Chain (5 Call + 6 Put) | 42μs | Generator stepping is cheap (~0.5μs/step) |
| Select (read state) | 38μs | Lock-free state read |
| Fork (1 parent + 4 children) | 140μs | 4 additional pool submissions |

### Pool Saturation (4-worker pool)

| Concurrent sagas | Median | vs pool-size |
|---|---|---|
| 4 (= pool) | 135μs | 1x |
| 8 (2x) | 222μs | 1.6x |
| 16 (4x) | 311μs | 2.3x |
| 32 (8x) | 373μs | 2.8x |

Sub-linear scaling — queueing overhead is modest for lightweight sagas.

### Blocking Impact

| Scenario | Median |
|---|---|
| 100 dispatches, no blockers | 23μs |
| 100 dispatches + 3 blocking sagas (50ms) | **54ms** |

Blocking sagas don't slow dispatch itself (dispatch doesn't use the pool), but total wall-clock includes waiting for pool drain on shutdown.

---

## Template Rendering

| Operation | Median | Notes |
|---|---|---|
| Terminal update (5 lines) | 384ns | StringIO write loop |
| Terminal update (40 lines) | 3.5μs | Linear: ~88ns/line |
| Render small (4 vars) | 4.2μs | Kida template overhead floor |
| Render medium (15-item loop) | 15.2μs | 3.6x small |
| Render large (32 cmds + examples) | 24.7μs | 5.9x small |
| Load template (help.kida) | 3.8μs | File parse |
| Load template (form.kida) | 3.7μs | Similar complexity |
| **get_env() creation** | **122μs** | Loader chain + theme registration |

---

## MCP Protocol

| Operation | Median | Notes |
|---|---|---|
| JSON parse (request) | 1.0μs | stdlib json.loads |
| JSON serialize (small) | 1.3μs | Simple dict |
| JSON serialize (100 items) | 17.4μs | Scales with payload |
| Router dispatch (initialize) | 233ns | Match statement |
| Router dispatch (tools/list, cached) | 2.6μs | Returns pre-built list |
| Router dispatch (tools/call) | 9.5μs | Command lookup + execution |
| **Full round-trip** | **13.0μs** | Parse + route + call + serialize |

### _list_tools Generation

| Commands | Median | Per-command |
|---|---|---|
| 5 | 78μs | 15.6μs |
| 20 | 312μs | 15.6μs |
| 50 | **792μs** | 15.8μs |

Linear scaling at ~15.6μs per command (dominated by schema generation).

---

## Schema Generation

| Function | Median | Notes |
|---|---|---|
| 0 params | 8.7μs | Baseline: inspect + get_type_hints |
| 2 params (simple) | 21.3μs | +6.3μs per simple param |
| 10 params (complex) | 102.6μs | ~9.4μs per param with mixed types |
| 5 params (Annotated) | 85.1μs | ~15.3μs per Annotated param |
| 3 params (nested generics) | 49.6μs | Recursive type resolution |

---

## Gateway

| Operation | Median | Notes |
|---|---|---|
| Tool routing lookup | 37ns | Dict lookup |
| tools/list (cached) | 89ns | Returns pre-built list |
| tools/call (proxied) | 1.5μs | Route + mock child |
| Full round-trip | 3.9μs | Parse + route + proxy + serialize |
| initialize | 414ns | Static dict |

### Discovery

| Children | Median | Notes |
|---|---|---|
| 1 | 71μs | ThreadPoolExecutor overhead |
| 4 | 194μs | 2.7x (parallel) |
| 8 | 314μs | 4.4x (parallel) |
| 4 x 20 tools | 527μs | Namespace merging cost |

---

## Key Findings

1. **Recording is the worst offender**: 46.8μs for 200-key state vs 225ns without — 208x overhead from `repr() + SHA256`. This is the single biggest optimization target.

2. **Schema generation at ~15μs/command** drives `_list_tools` cost. For 50 commands, that's 792μs per uncached call. The tool cache is essential.

3. **`get_env()` at 122μs** should be called once and reused, not per-render.

4. **Lock contention scales 5.7x at 8 threads** — the 27-line critical section (reducer + unwrap + record) is the bottleneck.

5. **Batch(4) at 8.2μs is 36x noop** — each Cmd submits to the ThreadPoolExecutor separately. A batch-submit API could reduce this.

6. **Saga generator stepping is free** — chain (5 steps) costs the same as simple (1 step). The overhead is in pool submission, not generator protocol.

7. **Gateway adds ~2.5μs per proxied call** — negligible compared to the child process I/O in production.
