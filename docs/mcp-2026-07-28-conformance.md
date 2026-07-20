# MCP 2026-07-28 conformance audit

Status: **release-candidate implementation, final validation pending**.

Milo's stdio server and gateway implement the locked MCP 2026-07-28 release
candidate while retaining the 2025-11-25 handshake for legacy clients. The
final specification is scheduled for July 28, 2026. This matrix must be
revalidated against the final schema and conformance suite before issue #105
can close or the docs call support final.

Authoritative inputs:

- [2026-07-28 release-candidate announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
- [draft specification](https://modelcontextprotocol.io/specification/draft)
- [changes from 2025-11-25](https://modelcontextprotocol.io/specification/draft/changelog)
- [versioning and compatibility](https://modelcontextprotocol.io/specification/draft/basic/versioning)
- [stdio and Streamable HTTP transports](https://modelcontextprotocol.io/specification/draft/basic/transports)
- [MCP Apps extension](https://modelcontextprotocol.io/extensions/apps/overview)

## Revision and result matrix

| Contract | 2026-07-28 stdio | 2025-11-25 stdio | Evidence / status |
|---|---|---|---|
| Version discovery | `server/discover` advertises modern first, then legacy | A probe may precede fallback | Router, child, gateway, verifier, and conformance tests: implemented |
| Lifecycle | No `initialize` or `notifications/initialized` | Existing two-message handshake preserved | Modern removed methods reject with `-32601`; legacy regression tests unchanged |
| Request identity | Every request requires protocol version, client info, and client capabilities in `_meta` | Metadata remains optional | Missing modern fields reject with `-32602`; implemented |
| Unsupported revision | `-32022` with requested and supported revisions | Same when an explicit unsupported revision is supplied | Implemented |
| Result discrimination | Every ordinary result carries `resultType: "complete"` | Older response shape preserved | Implemented; Milo does not emit `input_required` because it exposes no server-to-client request API |
| Cache hints | List results use `ttlMs: 30000`, `cacheScope: "private"`; resource reads use `ttlMs: 0`, private | Cache fields omitted | Implemented for every cacheable method Milo advertises |
| Resource not found | `-32602` Invalid params | `-32602` | Implemented and verified through leaf and gateway paths |
| Tool ordering | Registration order is deterministic | Same | Implemented and regression-tested |
| Trace context | `traceparent`, `tracestate`, and `baggage` remain in request context and cross the gateway | Preserved when supplied | Implemented; Milo creates no OpenTelemetry spans itself |
| Client capability scope | Read from each request; no connection-scoped modern state | Captured during `initialize` | Implemented; MCP Apps has concurrent no-leak proof under `PYTHON_GIL=0` |

## Feature audit

| RC feature | Milo decision | Status |
|---|---|---|
| `subscriptions/listen` | Milo advertises no list-change or resource-subscription capability, so it has no subscription stream to migrate. | Not advertised; not applicable to current surface |
| Multi round-trip requests | Milo has no elicitation, sampling, or roots request API and therefore never returns `input_required`. | Not advertised; no legacy behavior to migrate |
| Roots, Sampling, Logging | Milo did not implement these deprecated capabilities. Stdio diagnostics continue on stderr. | No deprecated dependency |
| MCP Apps | Keep official extension ID `io.modelcontextprotocol/ui`; negotiate per request in modern mode and during `initialize` in legacy mode. | Implemented in leaf server, gateway, verifier, example, and tests |
| Tasks extension | Do not fold long-running job semantics into the core revision migration. | Tracked separately in [#108](https://github.com/lbliii/milo-cli/issues/108) |
| JSON Schema 2020-12 | Generated schemas and structured results already cover Milo's typed command surface, including local `$defs`/`$ref` and `anyOf`. Milo's handwritten validator does not yet implement every 2020-12 composition and conditional keyword accepted by arbitrary lazy-command schemas. | **Remaining #105 blocker**; do not claim full 2020-12 conformance |
| Streamable HTTP headers and errors | `Mcp-Method`, `Mcp-Name`, `MCP-Protocol-Version`, header/body mismatch `-32020`, Origin checks, and HTTP status mapping do not apply to stdio. | Deferred to HTTP transport [#106](https://github.com/lbliii/milo-cli/issues/106) |
| HTTP authorization | The specification says stdio should obtain credentials from the environment rather than use the HTTP authorization flow. | Deferred to [#106](https://github.com/lbliii/milo-cli/issues/106) |

## Stdio mapping decision

Modern stdio uses one JSON-RPC object per line exactly as before, but each
request is self-contained. A client should send a modern `server/discover`
probe with the required metadata. If the server returns Method not found, the
client falls back on the same process to the 2025-11-25 `initialize` handshake.
After modern selection, Milo does not retain protocol version, client identity,
or capabilities as connection state; the request `_meta` envelope is the
authority.

The gateway follows the same probe/fallback algorithm for each child. Modern
child requests use gateway identity metadata and preserve incoming trace
context. Legacy children keep their initialized connection behavior.

## Closure checklist

- [x] Modern and legacy routing, discovery, error, result, cache, trace, and extension tests
- [x] `milo verify` checks modern discovery/cache metadata and a real legacy fallback
- [x] Scaffold and examples run through the verifier
- [x] Free-threaded concurrent MCP Apps capability-isolation proof
- [ ] Full JSON Schema 2020-12 acceptance and bounded validation decision
- [ ] Re-run the audit against the July 28 final schema and official conformance suite
- [ ] Remove the release-candidate qualifier only after both blockers pass

