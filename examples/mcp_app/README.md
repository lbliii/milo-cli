# MCP Apps Resource

One typed `forecast()` function is a human CLI command, an MCP tool, an
`llms.txt` entry, and the data source for an interactive MCP App. The app is a
static HTML string with a tiny vanilla-JavaScript JSON-RPC bridge—no web
framework, npm package, CDN, or runtime dependency.

```bash milo-docs:run cwd=.
uv run python examples/mcp_app/app.py forecast --city Boston --format json
uv run python examples/mcp_app/app.py --llms-txt
uv run milo verify examples/mcp_app/app.py
```

Run the same file as a stdio MCP server when registering it with a host:

```bash milo-docs:skip reason=long-running-json-rpc-server
uv run python examples/mcp_app/app.py --mcp
```

Clients that negotiate `io.modelcontextprotocol/ui` with the
`text/html;profile=mcp-app` MIME type receive the tool link and UI resource.
Other clients receive the same text/structured tool result without UI metadata.
The view performs the stable `ui/initialize` handshake, renders
`ui/notifications/tool-result`, and lets a user change the city and request a
fresh result through `tools/call`. It derives the tool name from host context so
direct and gateway-namespaced tools both work.

Milo transports the resource; the host owns iframe sandboxing and CSP
enforcement. The example intentionally keeps all application HTML and browser
behavior beside the command in `app.py`, not in Milo core.

## When a web framework owns the HTML

Keep this static pattern for a small standalone CLI. If a framework such as
[Chirp](https://github.com/lbliii/chirp) already owns templates, assets, auth,
or mutation semantics, let that framework produce the HTML resource and use
Milo only for the typed command, schema, MCP metadata, and structured fallback.
Do not move framework rendering or browser policy into Milo core.
