# Output Gallery

Advanced Milo output examples for CLIs that need to summarize complex work without
dumping noisy logs. The fixtures are static-site flavored so Bengal can copy the
shapes directly: broken links, failed markdown directives, publish warnings,
phase timelines, and next-step footers.

```bash
uv run python examples/outputgallery/app.py audit
uv run python examples/outputgallery/app.py audit --limit 0
uv run python examples/outputgallery/app.py audit --depth summary
uv run python examples/outputgallery/app.py audit --focus LNK001
uv run python examples/outputgallery/app.py audit --style ascii
uv run python examples/outputgallery/app.py audit --format json
uv run python examples/outputgallery/app.py atlas
uv run python examples/outputgallery/app.py catalog
uv run python examples/outputgallery/app.py directive
uv run python examples/outputgallery/app.py graph
uv run python examples/outputgallery/app.py grammar
uv run python examples/outputgallery/app.py heat
uv run python examples/outputgallery/app.py cache
uv run python examples/outputgallery/app.py layout --width narrow
uv run python examples/outputgallery/app.py spark
uv run python examples/outputgallery/app.py timeline
uv run python examples/outputgallery/app.py warnings
```

Patterns shown:

- Outcome headers that make the command verdict obvious.
- A visual grammar with Unicode and ASCII-safe equivalents.
- Grouped diagnostics with file, line, target, and repair hint.
- Character maps, severity rails, branch diagrams, and score panels.
- Bengal-style diagnostic views for broken links, directives, and warnings.
- Progressive disclosure through bounded issue lists and an expansion flag.
- Summary and focus views for drilldown workflows.
- Phase timelines that explain where time and risk accumulated.
- Build telemetry views for heat, trends, cache reuse, and fingerprints.
- Width and capability adaptation examples for wide, narrow, ASCII, CI, and JSON output.
- Structured JSON for agents, CI annotations, dashboards, and MCP calls.

Research basis:

- [Command Line Interface Guidelines](https://clig.dev/) for stdout/stderr
  separation, color discipline, progress behavior, and concise defaults.
- [The CLI Spec](https://clispec.dev/) for agent-friendly structured output,
  bounded output, and schema introspection.
- [AWS CLI output formats](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-output-format.html)
  and [Azure CLI output formats](https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli)
  for explicit human and machine output modes.
- [PatternFly CLI handbook](https://www.patternfly.org/developer-resources/cli-handbook/writing-guidelines)
  for success, warning, and error message shape.
