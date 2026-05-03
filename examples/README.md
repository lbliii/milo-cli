# Milo Examples

These examples are copy paths, not side demos. Every example directory has a runnable `app.py`; focused READMEs exist for the examples that are best starting points for new projects.

## Fastest Starting Points

| Start here when you need | Example | Why |
|---|---|---|
| The smallest typed CLI | [greet](greet) | One command, tests for schema, CLI dispatch, llms.txt, and MCP dispatch |
| A human CLI that is also an MCP tool | [deploy](deploy) | Typed constraints, destructive tool annotations, progress, resources, prompts, and interactive confirmation |
| An agent-readable task CLI | [taskman](taskman) | Commands plus MCP resources over application state |
| Polished terminal output patterns | [outputgallery](outputgallery) | Human summaries, CI-safe output, JSON mode, and Kida output primitives |

## Run A CLI Example

```bash milo-docs:run cwd=.
uv run python examples/greet/app.py greet --name Alice
uv run python examples/greet/app.py greet --name Alice --loud
uv run python examples/greet/app.py --llms-txt
uv run pytest examples/greet/tests/ -q
uv run milo verify examples/greet/app.py
```

## Example Map

| Category | Examples |
|---|---|
| Typed CLI and MCP | [greet](greet), [deploy](deploy), [ctxdemo](ctxdemo), [groups](groups), [lazyapp](lazyapp), [devtool](devtool), [taskman](taskman), [outputgallery](outputgallery) |
| Configuration, plugins, pipelines | [configapp](configapp), [pluggable](pluggable), [buildpipe](buildpipe) |
| Interactive apps | [counter](counter), [todo](todo), [stopwatch](stopwatch), [filepicker](filepicker), [wizard](wizard) |
| Async work | [fetcher](fetcher), [downloader](downloader), [spinner](spinner), [liverender](liverender) |

## Copy Rules

- Start with `greet` unless you already know you need state, progress, resources, or templates.
- Use `deploy` when the command has real-world side effects and needs agent-visible annotations.
- Use `taskman` when an MCP client needs both tools and read-only resources.
- Use `outputgallery` when output quality is the feature, especially for diagnostics, CI summaries, or site tooling.
- Run `uv run milo verify path/to/app.py` after adapting an example.
