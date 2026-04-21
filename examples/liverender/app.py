"""LiveRenderer outside the App harness — a one-shot progress view.

Use :mod:`milo.live` when you have a straight-line script or subroutine that
wants in-place terminal updates without the ceremony of a reducer-driven
:class:`milo.App`. For keyboard input, message filters, or state that persists
beyond the task, use :class:`milo.App` + :class:`milo.TickCmd` instead.

    uv run python examples/liverender/app.py
"""

from __future__ import annotations

import time

from milo.live import LiveRenderer, terminal_env

TEMPLATE = """\
{{- spinner() }} {{ label }}
  progress {{ (progress * 100)|round|int }}%
"""

STEPS = (
    ("Resolving dependencies", 0.15),
    ("Fetching packages", 0.45),
    ("Compiling", 0.80),
    ("Finalizing", 1.00),
)


def main() -> None:
    env = terminal_env()
    tpl = env.from_string(TEMPLATE, name="liverender")

    with LiveRenderer(tpl, refresh_rate=0.08) as live:
        live.start_auto(label="Starting", progress=0.0)
        for label, progress in STEPS:
            live.update(label=label, progress=progress)
            time.sleep(0.6)
        live.stop_auto()

    print("done.")


if __name__ == "__main__":
    main()
