# MCP Apps Resource

This minimal example links a normal structured Milo command to a predeclared
`ui://` HTML resource using the stable MCP Apps 2026-01-26 metadata shape.

```bash
uv run python examples/mcp_app/app.py forecast --city Boston --format json
uv run python examples/mcp_app/app.py --mcp
```

Clients that negotiate `io.modelcontextprotocol/ui` with the
`text/html;profile=mcp-app` MIME type receive the tool link and UI resource.
Other clients receive the same text/structured tool result without UI metadata.
Milo serves the resource; the host owns iframe sandboxing and CSP enforcement.
