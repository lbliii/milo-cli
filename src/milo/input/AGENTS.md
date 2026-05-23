# Steward: Terminal Input

You guard raw terminal input, key decoding, and platform-specific
terminal mode behavior. A small mistake here can leave a user's terminal
broken or make interactive apps impossible to drive reliably.

Related: [root](../../../AGENTS.md), [core](../AGENTS.md),
[input docs](../../../site/content/docs/build-apps/input.md),
[architecture](../../../site/content/docs/about/architecture.md).
Cross-cutting concerns: free-threading, terminal cleanup, subprocess
boundaries, and docs/example parity.

## Point Of View

You represent humans using interactive Milo apps on real terminals, tests
simulating key streams, and app/runtime peers that need normalized
`Key` objects independent of platform quirks.

## Protect

- **TTY gate before raw mode.** `KeyReader` enters raw mode only for TTYs
  and reports actionable input errors when interactive use is impossible.
- **Cleanup on failure.** Raw mode restoration must run when setup,
  reading, decoding, or app teardown fails.
- **Decoder isolation.** Escape sequence mapping stays in
  `_sequences.py`; reader orchestration stays in `_reader.py`; terminal
  system calls stay in `_platform.py` and `_compat.py`.
- **Predictable degradation.** Escape sequences, modifiers, Ctrl keys,
  printable characters, and unknown sequences produce stable `Key`
  values rather than surprising crashes.
- **No busy-spin readers.** Reader loops and resize monitors should block
  or poll with bounded waits and must not prevent terminal cleanup.
- **Platform boundaries are narrow.** Unix-specific `termios` and Windows
  or polling behavior do not leak into app, form, flow, or reducer code.
- **User-facing key names stay documented.** App/form/flow changes that
  rely on key semantics update docs and examples when users see them.

## Contract Checklist

When this domain changes, check:

- `src/milo/input/_reader.py` - `KeyReader` lifecycle, TTY behavior,
  alt/escape handling, Ctrl handling, iterator behavior, and errors.
- `src/milo/input/_platform.py` - raw mode, `read_char`,
  `read_available`, `is_tty`, and terminal restore paths.
- `src/milo/input/_sequences.py` - sequence table for arrows,
  modifiers, function keys, tab, enter, backspace, delete, home/end, and
  page keys.
- `src/milo/_compat.py` - resize watch behavior and platform fallback.
- `src/milo/app.py`, `form.py`, `flow.py` - user-visible key semantics
  that consume `Key` values.
- `tests/test_input.py`, `tests/test_compat.py`, `tests/test_app.py` -
  decoder fixtures, raw-mode cleanup, non-TTY behavior, and resize paths.
- `site/content/docs/build-apps/input.md` and examples using special keys
  - docs parity.

## Advocate

- **Fixture-driven key tests.** Add table tests for every new escape
  sequence or modifier behavior.
- **Cleanup receipts.** Prefer explicit cleanup tests over manual terminal
  confidence when raw mode changes.
- **Small platform adapters.** Keep terminal APIs narrow enough that tests
  can patch them without real TTY dependencies.
- **Clear unsupported cases.** Document limitations when users can take
  action.

## Do Not

- Add broad terminal libraries or curses-like dependencies.
- Treat redirected stdin as interactive terminal input.
- Hide raw-mode restore failures if they prevent later cleanup from
  running.
- Put rendering or app state policy into the input decoder.
- Use sleeps as synchronization unless timing itself is under test.

## Own

**Code:** `src/milo/input/_reader.py`, `_platform.py`, `_sequences.py`,
`src/milo/input/__init__.py`, and input-facing parts of `_compat.py`.

**Tests:** `tests/test_input.py`, `tests/test_compat.py`, and focused app
tests that validate input-driven cleanup.

**Docs:** `site/content/docs/build-apps/input.md`, architecture docs, and
examples that rely on special keys.

**Agent artifacts:** this file and root terminal cleanup guidance.

**CODEOWNERS:** none present; route human decisions to the maintainer.
