"""Template rendering benchmarks — kida render and terminal update costs."""

from __future__ import annotations

import io

from milo.templates import get_env

# ---------------------------------------------------------------------------
# Template fixtures (inline strings to avoid file I/O in benchmarks)
# ---------------------------------------------------------------------------

SMALL_TEMPLATE = """\
{{ title | bold }}

Status: {{ status }}
Count: {{ count }}
"""

MEDIUM_TEMPLATE = """\
{{ title | bold }}

{% for item in items %}
  {% if item.active %}{{ item.name | bold }}{% else %}{{ item.name | dim }}{% endif %} - {{ item.description }}
{% endfor %}

Total: {{ items | length }} items
Active: {{ items | selectattr("active") | list | length }}
"""

LARGE_TEMPLATE = """\
{{ title | bold }}
{{ description }}

{% for group in groups %}
{{ group.name | bold }}:
{% for cmd in group.commands %}  {{ cmd.name }}    {{ cmd.help }}{% if cmd.default %} ({{ cmd.default }}){% endif %}
{% endfor %}
{% endfor %}

{% if examples %}
Examples:
{% for ex in examples %}  $ {{ ex.command }}
    {{ ex.description }}
{% endfor %}
{% endif %}
"""


# ---------------------------------------------------------------------------
# State fixtures
# ---------------------------------------------------------------------------


def _small_state():
    return {"title": "My App", "status": "running", "count": 42}


def _medium_state():
    return {
        "title": "Task Manager",
        "items": [
            {"name": f"task-{i}", "active": i % 3 != 0, "description": f"Task number {i}"}
            for i in range(15)
        ],
    }


def _large_state():
    return {
        "title": "myapp",
        "description": "A comprehensive CLI tool",
        "groups": [
            {
                "name": f"Group {g}",
                "commands": [
                    {
                        "name": f"cmd-{g}-{c}",
                        "help": f"Help text for command {c}",
                        "default": f"val{c}" if c % 2 == 0 else None,
                    }
                    for c in range(8)
                ],
            }
            for g in range(4)
        ],
        "examples": [
            {"command": f"myapp cmd-0-{i} --flag", "description": f"Example {i}"} for i in range(5)
        ],
    }


# ---------------------------------------------------------------------------
# Template rendering throughput
# ---------------------------------------------------------------------------


def test_bench_render_small(benchmark) -> None:
    """Render a 4-line template with simple variable substitution."""
    env = get_env()
    tmpl = env.from_string(SMALL_TEMPLATE, name="bench_small")
    state = _small_state()
    benchmark(tmpl.render, **state)


def test_bench_render_medium(benchmark) -> None:
    """Render a template with loop (15 items) + conditionals."""
    env = get_env()
    tmpl = env.from_string(MEDIUM_TEMPLATE, name="bench_medium")
    state = _medium_state()
    benchmark(tmpl.render, **state)


def test_bench_render_large(benchmark) -> None:
    """Render a help-page-style template (4 groups x 8 commands + examples)."""
    env = get_env()
    tmpl = env.from_string(LARGE_TEMPLATE, name="bench_large")
    state = _large_state()
    benchmark(tmpl.render, **state)


# ---------------------------------------------------------------------------
# Environment creation cost
# ---------------------------------------------------------------------------


def test_bench_get_env(benchmark) -> None:
    """Cost of creating a kida Environment (loader + theme registration)."""
    benchmark(get_env)


# ---------------------------------------------------------------------------
# Built-in template loading
# ---------------------------------------------------------------------------


def test_bench_load_help_template(benchmark) -> None:
    """Cost of loading the built-in help.kida template (file I/O + parse)."""
    env = get_env()

    def load():
        return env.get_template("help.kida")

    benchmark(load)


def test_bench_load_form_template(benchmark) -> None:
    """Cost of loading the built-in form.kida template."""
    env = get_env()

    def load():
        return env.get_template("form.kida")

    benchmark(load)


# ---------------------------------------------------------------------------
# Terminal renderer simulation (write to StringIO instead of stdout)
# ---------------------------------------------------------------------------


def test_bench_terminal_update_small(benchmark) -> None:
    """Simulate _TerminalRenderer.update() with 5-line output."""
    output = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
    cols = 80
    buf = io.StringIO()

    def update():
        lines = output.split("\n")
        buf.seek(0)
        buf.write("\033[H")
        for line in lines:
            buf.write(line[:cols])
            buf.write("\033[K\n")
        buf.truncate()

    benchmark(update)


def test_bench_terminal_update_large(benchmark) -> None:
    """Simulate _TerminalRenderer.update() with 40-line output (full screen)."""
    output = "\n".join(f"{'x' * 60} line {i}" for i in range(40))
    cols = 80
    buf = io.StringIO()

    def update():
        lines = output.split("\n")
        buf.seek(0)
        buf.write("\033[H")
        for line in lines:
            buf.write(line[:cols])
            buf.write("\033[K\n")
        buf.truncate()

    benchmark(update)
