# Milo 85-Second Launch Demo

This is the recording runbook for issue #88. The story is one operation, two
audiences: Claude calls a typed tool, then a human runs the same command and
receives an interactive confirmation.

## Preflight

- Record at 1440p or higher with a terminal font readable at mobile width.
- Use a fresh directory with no virtual environment and no Milo checkout above
  it in the directory tree.
- Install `uv` and Claude Code; sign in to Claude before recording.
- Use the release candidate version in every `--with` and `--from` argument if
  the final release is not yet on PyPI.
- Run the full sequence once off-camera. `milo verify` must report zero
  failures.
- Keep the final recording between 60 and 90 seconds. Cut package-download and
  agent-thinking pauses; do not fake command output.
- Prepare a separate clean Milo checkout for the final Waypoint shot and run
  `uv run python showcase/waypoint/replay.py` once before recording it.

## Function to Type

After scaffolding, replace `app.py` with this prepared snippet:

```python milo-docs:compile
from typing import Annotated

from milo import CLI, Context, MinLen

cli = CLI(name="deployer", description="Deploy services", version="0.1")


@cli.command(
    "deploy",
    description="Deploy a service",
    annotations={"destructiveHint": True},
)
def deploy(
    environment: Annotated[str, MinLen(1)],
    service: Annotated[str, MinLen(1)],
    ctx: Context = None,
) -> dict[str, str]:
    """Deploy a service.

    Args:
        environment: Target environment.
        service: Service to deploy.
        ctx: Milo's injected context.
    """
    if ctx and ctx.is_interactive and not ctx.confirm(
        f"Deploy {service} to {environment}?"
    ):
        return {"status": "cancelled"}
    return {"status": "deployed", "service": service, "environment": environment}


if __name__ == "__main__":
    cli.run()
```

## Shot List

| Time | Screen action | Narration |
|---|---|---|
| 0–6s | `uvx --python 3.14 --from milo-cli milo new deployer` | “Start with a normal Python CLI.” |
| 6–22s | Open `deployer/app.py`; type or paste the prepared function | “Types, constraints, and a docstring are the contract.” |
| 22–31s | Run `uv run --python 3.14 --with milo-cli milo verify deployer/app.py` | “Milo verifies the schema and a real MCP handshake before an agent sees it.” |
| 31–39s | Register the stdio command shown below | “The same file is the MCP server.” |
| 39–55s | In Claude, ask: `Deploy api to staging using the deploy tool.` | “Claude discovers the generated schema and calls the function.” |
| 55–69s | Run the command by hand; answer `y` at the confirmation | “A human gets an interactive safety gate.” |
| 69–75s | Split-screen the Claude result and terminal result | “One function. Two audiences. No adapter schema.” |
| 75–85s | Cut to the Waypoint replay's three-attempt DAG and picked winner | “The same contract scales: hook to CLI, agent to MCP, human to TUI and Apps. CLI for depth, MCP for reach.” |

## Commands on Screen

Run these from the fresh parent directory:

```bash milo-docs:skip reason=requires-clean-machine-and-claude-registration
uvx --python 3.14 --from milo-cli milo new deployer
uv run --python 3.14 --with milo-cli milo verify deployer/app.py

claude mcp add --transport stdio deployer -- \
  uv run --python 3.14 --with milo-cli python "$PWD/deployer/app.py" --mcp

uv run --python 3.14 --with milo-cli python deployer/app.py deploy \
  --environment staging --service api
```

After registration, `claude mcp get deployer` should show a connected stdio
server. Remove a rehearsal registration with `claude mcp remove deployer`
before recording the final take.

Record the closing shot from the clean Milo checkout prepared in preflight:

```bash milo-docs:run cwd=.
uv run python showcase/waypoint/replay.py
```

Frame the final `DAG view` and `pick [destructiveHint]` lines together. The
script uses a real stdio MCP exchange and leaves its fixture path in the last
line; do not substitute hand-authored output.

## Acceptance Review

- The scaffold command visibly succeeds on a clean machine.
- The verifier output is readable and reports zero failures.
- Claude visibly selects `deploy`; the result is not pasted prose.
- The human invocation visibly asks for confirmation.
- The exact same `app.py` path is used by Claude and the terminal.
- The Waypoint closing shot visibly contains three attempts, a picked winner,
  and the MCP Apps resource URI.
- No token, home-directory path, username, or unrelated MCP server is visible.
- Captions include “CLI”, “MCP tool”, and “same typed function”.
