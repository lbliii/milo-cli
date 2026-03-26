"""CLI entry point — milo dev, milo replay."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _load_app(app_path: str):
    """Load an App instance from a module:attribute path like 'myapp:app'."""
    if ":" not in app_path:
        print(f"Error: expected format 'module:attribute', got '{app_path}'", file=sys.stderr)
        sys.exit(1)

    module_path, attr_name = app_path.rsplit(":", 1)

    # Add cwd to sys.path so local modules can be found
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        print(f"Error: could not import '{module_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        app = getattr(module, attr_name)
    except AttributeError:
        print(f"Error: '{module_path}' has no attribute '{attr_name}'", file=sys.stderr)
        sys.exit(1)

    return app


def _cmd_dev(args: argparse.Namespace) -> None:
    """Run the dev server with hot-reload."""
    from milo.dev import DevServer

    app = _load_app(args.app)
    watch_dirs = tuple(args.watch) if args.watch else ()
    server = DevServer(app, watch_dirs=watch_dirs, poll_interval=args.poll)
    server.run()


def _cmd_replay(args: argparse.Namespace) -> None:
    """Replay a recorded session."""
    from milo.testing._record import load_recording
    from milo.testing._replay import replay

    recording = load_recording(args.session)

    def default_reducer(state, action):
        return state

    reducer = default_reducer

    # Try to load a reducer if specified
    if args.reducer:
        reducer = _load_app(args.reducer)

    def on_state(state, action):
        if args.diff:
            print(f"[{action.type}] -> {state!r}")

    final = replay(
        recording,
        reducer,
        speed=args.speed,
        step=args.step,
        on_state=on_state if args.diff else None,
        assert_hashes=args.assert_hashes,
    )

    if args.assert_hashes:
        print("All state hashes match.", file=sys.stderr)
    else:
        print(f"Replay complete. Final state: {final!r}")


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="milo",
        description="Template-driven CLI applications for free-threaded Python",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.1.0"
    )
    subparsers = parser.add_subparsers(dest="command")

    # milo dev
    dev_parser = subparsers.add_parser("dev", help="Run app with hot-reload")
    dev_parser.add_argument("app", help="App path as 'module:attribute'")
    dev_parser.add_argument(
        "--watch", "-w", action="append", default=[], help="Directories to watch for changes"
    )
    dev_parser.add_argument(
        "--poll", type=float, default=0.5, help="Poll interval in seconds (default: 0.5)"
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
        "--assert", dest="assert_hashes", action="store_true",
        help="Exit non-zero if state hashes don't match (CI use)"
    )

    args = parser.parse_args(argv)

    if args.command == "dev":
        _cmd_dev(args)
    elif args.command == "replay":
        _cmd_replay(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
