# Terminal Input Steward

This domain represents raw terminal input, key decoding, and platform-specific terminal mode behavior. It matters because a small mistake can leave a user's terminal broken or make interactive apps impossible to drive reliably.

Related docs:
- root `AGENTS.md`
- `src/milo/AGENTS.md`
- `site/content/docs/usage/input.md`
- `site/content/docs/about/architecture.md`

## Point Of View
Represent humans using interactive Milo apps on real terminals, tests simulating key streams, and app/runtime peers that need normalized `Key` objects.

## Protect
- Raw mode must be entered only for TTYs and must be restored through context-manager exit paths.
- Escape sequences, modifiers, Ctrl keys, printable characters, and unknown sequences must degrade predictably.
- Platform-specific behavior stays isolated in `_platform.py`; decoding rules stay isolated in `_sequences.py` and `_reader.py`.
- Input errors must be actionable and wrapped as Milo input errors where callers can recover or report cleanly.
- No reader path should busy-spin or block terminal cleanup.

## Advocate
- Small fixture-driven tests for new escape sequences and platform edge cases.
- More explicit docs for unsupported terminal behavior when users can act on it.
- Narrow platform abstractions instead of scattering `sys.stdin`, `termios`, or Windows-specific logic.

## Serve Peers
- Provide `App` and form flows stable `Key` semantics independent of platform.
- Help tests avoid flaky real-TTY dependencies by exposing decode-level units.
- Give docs exact key names and limitations for interactive examples.

## Do Not
- Add broad terminal libraries or curses-like dependencies.
- Treat non-TTY stdin as interactive input.
- Hide raw-mode restore failures if they prevent cleanup code from running.
- Put rendering or app state policy into the input decoder.

## Own
- `src/milo/input/_reader.py`, `_platform.py`, `_sequences.py`, and package exports.
- `tests/test_input.py` plus any platform-specific fixtures added for key parsing.
- Input sections in `site/content/docs/usage/input.md` and examples that rely on special keys.
