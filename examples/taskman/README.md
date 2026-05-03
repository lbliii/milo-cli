# taskman - commands plus MCP resources

`taskman` is a compact stateful CLI that exposes both tools and read-only resources. It is useful when an agent should mutate state through commands but inspect current state through resource URIs.

## Run

```bash
rm -f examples/taskman/.tasks.json
```

```bash milo-docs:run cwd=.
trap 'rm -f examples/taskman/.tasks.json' EXIT
uv run python examples/taskman/app.py add --title "Write docs" --priority high
uv run python examples/taskman/app.py list --format json
uv run python examples/taskman/app.py stats
uv run python examples/taskman/app.py --llms-txt
uv run milo verify examples/taskman/app.py
```

The example writes `examples/taskman/.tasks.json`. Remove that file when you want a fresh local run.

## MCP Probe

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"resources/list"}' \
  | uv run python examples/taskman/app.py --mcp
```

## Copy This When

- Agents need read-only resource snapshots such as `tasks://pending`.
- Human users still need normal CLI commands and output formats.
- You want aliases, hidden commands, tags, and `--format json` in one small app.
