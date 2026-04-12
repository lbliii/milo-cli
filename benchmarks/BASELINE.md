# Benchmark Baseline — v0.2.2-dev

**Date**: 2026-04-12
**Platform**: macOS Darwin 25.3.0, Apple Silicon
**Python**: CPython 3.14.3
**Suite**: 74 benchmarks across 7 files

---

## Store Dispatch

Core dispatch path: acquire lock → run reducer → unwrap result → compute record hash → release lock → append record → notify listeners → schedule effects.

| Benchmark | Median | OPS | Notes |
|---|---|---|---|
| noop reducer | 292ns | 3.3M | Floor: lock + return |
| dict merge | 309ns | 3.0M | Typical app pattern |
| ReducerResult unwrap | 708ns | 1.4M | 2.4x noop — isinstance checks + field extraction |
| + Cmd | 2.8μs | 209K | ThreadPoolExecutor.submit() cost |
| + Sequence(4) | 3.7μs | 173K | Single submit for serial chain |
| + Batch(4) | 8.7μs | 63K | Bulk task accounting + 4 executor submits |
| state-5 keys | 300ns | 3.1M | Dict spread cost |
| state-50 keys | 433ns | 2.2M | +44% vs 5 keys |
| state-500 keys | 1.3μs | 711K | 4.5x vs 5 keys (dict copy dominates) |
| recording (small) | 708ns | 1.2M | Merkle chain: hash(f-string) — O(1) per dispatch |
| recording (200 keys) | 1.3μs | 663K | Same O(1) — state size does not affect recording cost |

**Note**: Recording uses an action-based Merkle chain (`hash(f"{prev}:{type}:{payload}")`), not `repr(state)`. The hash is computed inside the lock to maintain chain ordering; the append and timestamp are deferred outside the lock.

### Listeners

| Listeners | Median | vs 0 |
|---|---|---|
| 0 | 292ns | 1x |
| 4 | 292ns | 1x |
| 16 | 500ns | 1.7x |

### combine_reducers

| Slices | Median | vs 2 slices |
|---|---|---|
| 2 | 594ns | 1x |
| 5 | 871ns | 1.5x |
| 10 | 1.5μs | 2.5x |

---

## Lock Contention

200 dispatches per thread to the same store, measuring total wall-clock time.

| Threads | Noop median | Dict-merge median | Scaling factor |
|---|---|---|---|
| 1 | 116μs | 139μs | 1.0x |
| 2 | 182μs | 210μs | 1.5x |
| 4 | 325μs | 382μs | 2.7x |
| 8 | 596μs | 701μs | 5.0x |

4 listeners on top of 4 threads: 435μs (1.1x overhead vs no listeners).
Lock fairness check passes — no thread starvation observed.

### Lock hold time (8 threads, recording + 4 listeners)

| Metric | Value |
|---|---|
| Hold time (median) | 542ns |
| Wait time (median) | 42ns |
| Hold/wait ratio | 12.9x |

---

## Saga Executor

End-to-end: dispatch action → saga runs on thread pool → result action dispatched.

| Pattern | Median | Notes |
|---|---|---|
| Simple (1 Call + 1 Put) | 45μs | Pool submit + generator step |
| Chain (5 Call + 6 Put) | 48μs | Generator stepping is cheap (~0.5μs/step) |
| Select (read state) | 47μs | Lock-free state read |
| Fork (1 parent + 4 children) | 174μs | 4 additional pool submissions |

### Pool Saturation (4-worker pool)

| Concurrent sagas | Median | vs pool-size |
|---|---|---|
| 4 (= pool) | 155μs | 1x |
| 8 (2x) | 562μs | 3.6x |
| 16 (4x) | 943μs | 6.1x |
| 32 (8x) | 987μs | 6.4x |

Sub-linear scaling — queueing overhead is modest for lightweight sagas.

### Blocking Impact

| Scenario | Median |
|---|---|
| 100 dispatches, no blockers | 26μs |
| 100 dispatches + 3 blocking sagas (50ms) | **55ms** |

Blocking sagas don't slow dispatch itself (dispatch doesn't use the pool), but total wall-clock includes waiting for pool drain on shutdown.

---

## Template Rendering

| Operation | Median | Notes |
|---|---|---|
| Terminal update (5 lines) | 418ns | StringIO write loop |
| Terminal update (40 lines) | 3.8μs | Linear: ~88ns/line |
| Render small (4 vars) | 4.1μs | Kida template overhead floor |
| Render medium (15-item loop) | 15.6μs | 3.8x small |
| Render large (32 cmds + examples) | 25.3μs | 6.2x small |
| Load template (help.kida) | 4.2μs | File parse |
| Load template (form.kida) | 4.0μs | Similar complexity |
| **get_env() (cached)** | **125ns** | Singleton cache hit |

**Note**: `get_env()` is now cached as a module-level singleton. First call costs ~125μs (loader chain + theme registration); subsequent default-args calls return the cached instance in ~125ns.

---

## MCP Protocol

| Operation | Median | Notes |
|---|---|---|
| JSON parse (request) | 1.1μs | stdlib json.loads |
| JSON serialize (small) | 1.3μs | Simple dict |
| JSON serialize (100 items) | 17.5μs | Scales with payload |
| Router dispatch (initialize) | 233ns | Match statement |
| Router dispatch (tools/list, cached) | 2.6μs | Returns pre-built list |
| Router dispatch (tools/call) | 9.4μs | Command lookup + execution |
| **Full round-trip** | **13.1μs** | Parse + route + call + serialize |

### _list_tools Generation

| Commands | Median | Per-command |
|---|---|---|
| 5 | 79μs | 15.8μs |
| 20 | 316μs | 15.8μs |
| 50 | **794μs** | 15.9μs |

Linear scaling at ~15.8μs per command (dominated by schema generation).

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
| initialize | 459ns | Static dict |

### Discovery

| Children | Median | Notes |
|---|---|---|
| 1 | 71μs | ThreadPoolExecutor overhead |
| 4 | 196μs | 2.8x (parallel) |
| 8 | 271μs | 3.8x (parallel) |
| 4 x 20 tools | 510μs | Namespace merging cost |

---

## Key Findings

1. **`get_env()` cache now works**: 125ns cached vs 125μs uncached — 1,000x improvement from fixing the singleton cache-write condition.

2. **Recording overhead is minimal**: Action-based Merkle chain costs ~700ns regardless of state size. The previous `repr(state) + SHA256` approach was replaced with `hash(f-string)` — O(1) per dispatch.

3. **Lock hold time is 542ns** with recording hash deferred outside the lock (previously 834ns). The hash is computed inside the lock (for chain ordering) using Python's built-in `hash()` instead of SHA256.

4. **Schema generation at ~16μs/command** drives `_list_tools` cost. For 50 commands, that's ~800μs per uncached call. The tool cache is essential.

5. **Batch submission uses bulk task accounting**: One `_tasks_lock` acquisition for the entire batch instead of per-Cmd, with individual executor submits for concurrency.

6. **Saga generator stepping is free** — chain (5 steps) costs the same as simple (1 step). The overhead is in pool submission, not generator protocol.

7. **Gateway adds ~2.5μs per proxied call** — negligible compared to the child process I/O in production.
