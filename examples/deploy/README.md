# deploy - dual-mode CLI and MCP tool

`deploy` is the flagship example for commands that humans run from a terminal and agents call through MCP. It demonstrates typed constraints, destructive/read-only annotations, progress events, resources, prompts, and an interactive confirmation path.

## Run

```bash milo-docs:run cwd=.
uv run python examples/deploy/app.py environments
uv run python examples/deploy/app.py status --environment staging --service api
uv run python examples/deploy/app.py --llms-txt
uv run milo verify examples/deploy/app.py
```

The `deploy` and `rollback` commands are intentionally annotated as destructive. In a real CLI, keep those annotations close to the function that performs the side effect so CLI docs, MCP tools/list, and llms.txt stay aligned.

## MCP Probe

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"status","arguments":{"environment":"staging","service":"api"}}}' \
  | uv run python examples/deploy/app.py --mcp
```

## Copy This When

- A command needs both human confirmation and structured agent output.
- MCP clients need progress notifications while the command works.
- The CLI exposes read-only resources or reusable prompts alongside tools.
- You need schema constraints from `Annotated[...]` to be visible in MCP.
