"""CLI entry point — milo dev, milo replay."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _load_app(app_path: str):
    """Load an App instance from a module:attribute path like 'myapp:app'."""
    if ":" not in app_path:
        sys.stderr.write(f"Error: expected format 'module:attribute', got '{app_path}'\n")
        sys.exit(1)

    module_path, attr_name = app_path.rsplit(":", 1)

    # Add cwd to sys.path so local modules can be found
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        sys.stderr.write(f"Error: could not import '{module_path}': {e}\n")
        sys.exit(1)

    try:
        app = getattr(module, attr_name)
    except AttributeError:
        sys.stderr.write(f"Error: '{module_path}' has no attribute '{attr_name}'\n")
        sys.exit(1)

    return app


def _cmd_dev(args: argparse.Namespace) -> None:
    """Run the dev server with hot-reload."""
    from milo.dev import DevServer

    app = _load_app(args.app)
    watch_dirs = tuple(args.watch) if args.watch else ()
    server = DevServer(app, watch_dirs=watch_dirs, poll_interval=args.poll)
    server.run()


def _cmd_verify(args: argparse.Namespace) -> None:
    """Run diagnostic checks against an agent-built milo CLI."""
    from milo.verify import verify

    report = verify(args.target, timeout=args.timeout)
    sys.stdout.write(report.format() + "\n")
    sys.exit(report.exit_code)


def _cmd_new(args: argparse.Namespace) -> None:
    """Scaffold a new milo CLI project."""
    from milo._scaffold import ScaffoldError, scaffold

    try:
        project_dir = scaffold(args.name, Path(args.dir))
    except ScaffoldError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    sys.stdout.write(
        f"Created {project_dir}\n"
        f"\n"
        f"Next steps:\n"
        f"  cd {project_dir}\n"
        f"  uv run python app.py greet --name Alice\n"
        f"  uv run pytest tests/\n"
    )


def _cmd_components(args: argparse.Namespace) -> None:
    """List bundled and user-defined template components."""
    from milo.components_cli import run

    paths = tuple(Path(p) for p in args.path or ())
    sys.exit(run(paths=paths, as_json=args.json))


def _cmd_replay(args: argparse.Namespace) -> None:
    """Replay a recorded session."""
    from milo.testing._record import load_recording
    from milo.testing._replay import replay

    recording = load_recording(args.session)

    def default_reducer(state, _action):
        return state

    reducer = default_reducer

    # Try to load a reducer if specified
    if args.reducer:
        reducer = _load_app(args.reducer)

    def on_state(state, action):
        if args.diff:
            sys.stdout.write(f"[{action.type}] -> {state!r}\n")

    final = replay(
        recording,
        reducer,
        speed=args.speed,
        step=args.step,
        on_state=on_state if args.diff else None,
        assert_hashes=args.assert_hashes,
    )

    if args.assert_hashes:
        sys.stderr.write("All state hashes match.\n")
    else:
        sys.stdout.write(f"Replay complete. Final state: {final!r}\n")


_MIN_PYTHON = (3, 14)


def _preflight_python_version() -> None:
    """Exit with an actionable message when running under an unsupported Python.

    Runs before any milo module import that relies on 3.14+ features, so the
    user sees a fix-it message instead of a `SyntaxError` or `ImportError`.
    """
    if sys.version_info < _MIN_PYTHON:
        have = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        want = f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}"
        sys.stderr.write(
            f"milo requires Python {want}+ (you have {have}).\n"
            f"Install with: uv python install {want}\n"
        )
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    _preflight_python_version()

    parser = argparse.ArgumentParser(
        prog="milo",
        description="Template-driven CLI applications for free-threaded Python",
    )
    from milo import __version__

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # milo new
    new_parser = subparsers.add_parser("new", help="Scaffold a new milo CLI project")
    new_parser.add_argument("name", help="Project name (lowercase, underscores)")
    new_parser.add_argument(
        "--dir", "-d", default=".", help="Parent directory for the project (default: cwd)"
    )

    # milo verify
    verify_parser = subparsers.add_parser(
        "verify", help="Self-diagnose a milo CLI (schema, dispatch, MCP)"
    )
    verify_parser.add_argument("target", help="Path to app.py or 'module:attr' reference")
    verify_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for the subprocess MCP handshake (default: 5.0)",
    )

    # milo dev
    dev_parser = subparsers.add_parser("dev", help="Run app with hot-reload")
    dev_parser.add_argument("app", help="App path as 'module:attribute'")
    dev_parser.add_argument(
        "--watch", "-w", action="append", default=[], help="Directories to watch for changes"
    )
    dev_parser.add_argument(
        "--poll", type=float, default=0.5, help="Poll interval in seconds (default: 0.5)"
    )

    # milo components
    components_parser = subparsers.add_parser(
        "components", help="List bundled + user template components (defs)"
    )
    components_parser.add_argument(
        "--path",
        "-p",
        action="append",
        default=[],
        help="Extra templates dir to scan (repeatable)",
    )
    components_parser.add_argument(
        "--json", action="store_true", help="Emit full def metadata as JSON"
    )

    # milo replay
    replay_parser = subparsers.add_parser("replay", help="Replay a recorded session")
    replay_parser.add_argument("session", help="Path to session JSONL file")
    replay_parser.add_argument("--reducer", "-r", help="Reducer path as 'module:attribute'")
    replay_parser.add_argument(
        "--speed", "-s", type=float, default=1.0, help="Playback speed multiplier (default: 1.0)"
    )
    replay_parser.add_argument(
        "--step", action="store_true", help="Step-by-step mode (press Enter to advance)"
    )
    replay_parser.add_argument(
        "--diff", "-d", action="store_true", help="Show state diff between transitions"
    )
    replay_parser.add_argument(
        "--assert",
        dest="assert_hashes",
        action="store_true",
        help="Exit non-zero if state hashes don't match (CI use)",
    )

    args = parser.parse_args(argv)

    if args.command == "new":
        _cmd_new(args)
    elif args.command == "verify":
        _cmd_verify(args)
    elif args.command == "dev":
        _cmd_dev(args)
    elif args.command == "components":
        _cmd_components(args)
    elif args.command == "replay":
        _cmd_replay(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
