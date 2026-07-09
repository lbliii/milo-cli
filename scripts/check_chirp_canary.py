"""Verify released Chirp CLI evidence against a released Milo-shaped canary."""

# This executable prints one machine-readable CI receipt.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DOWNSTREAM = ROOT / "tests" / "downstream"
CANARY = DOWNSTREAM / "chirp_canary"
CONTRACT_PATH = CANARY / "contract.json"
HANDLER_MODULE = "chirp_canary.handlers"


class CanaryError(RuntimeError):
    """Raised when a released or representative contract drifts."""


def _contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))


def _run(
    command: tuple[str, ...],
    *,
    input_text: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CanaryError(f"Command timed out: {' '.join(command)}") from error


def _require(
    condition: bool,
    message: str,
    completed: subprocess.CompletedProcess[str] | None = None,
) -> None:
    if condition:
        return
    if completed is not None:
        message = (
            f"{message}\nexit={completed.returncode}\n"
            f"stdout={completed.stdout!r}\nstderr={completed.stderr!r}"
        )
    raise CanaryError(message)


def _help_heading(output: str) -> str:
    lines = output.splitlines()
    _require(bool(lines) and bool(lines[0].strip()), "help output omitted heading")
    return lines[0].strip()


def _check_installed_versions(contract: dict[str, Any]) -> None:
    versions = contract["versions"]
    installed = {
        "milo": importlib.metadata.version("milo-cli"),
        "chirp": importlib.metadata.version("bengal-chirp"),
    }
    _require(
        installed == {"milo": versions["milo"], "chirp": versions["chirp"]},
        (f"Canary must use exact released versions {versions}; installed {installed}"),
    )

    milo_location = Path(str(importlib.metadata.distribution("milo-cli").locate_file(""))).resolve()
    chirp_location = Path(
        str(importlib.metadata.distribution("bengal-chirp").locate_file(""))
    ).resolve()
    _require(not milo_location.is_relative_to(ROOT), "Canary imported Milo from this checkout")
    _require(not chirp_location.is_relative_to(ROOT), "Canary imported Chirp from a checkout")


def _check_free_threaded(*, required: bool) -> bool:
    checker = getattr(sys, "_is_gil_enabled", None)
    gil_enabled = True if checker is None else bool(checker())
    if required:
        _require(not gil_enabled, "Canary requires Python 3.14t with PYTHON_GIL=0")
    return not gil_enabled


def _check_released_chirp(contract: dict[str, Any]) -> dict[str, float]:
    started = time.perf_counter()
    commands = contract["commands"]

    root_help = _run((sys.executable, "-m", "chirp.cli", "--help"))
    _require(
        root_help.returncode == 0 and not root_help.stderr, "Chirp root help failed", root_help
    )
    _require(
        _help_heading(root_help.stdout) == contract["root_help_heading"],
        "Released Chirp root help drifted; advance the pin and manifest explicitly",
        root_help,
    )
    command_offsets = [root_help.stdout.index(f"  {name}") for name in commands]
    _require(
        command_offsets == sorted(command_offsets),
        "Released Chirp root command order drifted",
        root_help,
    )
    for command_name, command in commands.items():
        result = _run((sys.executable, "-m", "chirp.cli", command_name, "--help"))
        _require(
            result.returncode == 0 and not result.stderr, f"{command_name} help failed", result
        )
        _require(
            _help_heading(result.stdout) == command["help_heading"],
            f"Released Chirp {command_name} help drifted; update the versioned contract",
            result,
        )
        for property_name, prop in command["schema"]["properties"].items():
            presentation = prop.get("x-milo-cli", {})
            if presentation.get("kind") == "positional":
                _require(
                    f"  {property_name} " in result.stdout,
                    f"Released Chirp {command_name} help omitted positional {property_name}",
                    result,
                )
                continue
            flags = [
                f"--{property_name.replace('_', '-')}",
                *presentation.get("aliases", []),
            ]
            _require(
                any(flag in result.stdout for flag in flags),
                f"Released Chirp {command_name} help omitted {flags}",
                result,
            )

    no_command = _run((sys.executable, "-m", "chirp.cli"))
    _require(
        no_command.returncode == 0 and bool(no_command.stdout) and not no_command.stderr,
        "Chirp no-command stdout/exit contract drifted",
        no_command,
    )
    version = _run((sys.executable, "-m", "chirp.cli", "--version"))
    _require(
        version.returncode == 0
        and version.stdout.startswith(f"chirp {contract['versions']['chirp']}")
        and not version.stderr,
        "Chirp version stdout contract drifted",
        version,
    )
    parse_error = _run((sys.executable, "-m", "chirp.cli", "--not-a-chirp-option"))
    _require(
        parse_error.returncode == 2
        and not parse_error.stdout
        and "usage:" in parse_error.stderr
        and "error:" in parse_error.stderr,
        "Chirp parse-error channel or exit code drifted",
        parse_error,
    )
    resolution_error = _run((sys.executable, "-m", "chirp.cli", "check", "missing_canary_app:app"))
    _require(
        resolution_error.returncode == 1
        and not resolution_error.stdout
        and resolution_error.stderr.startswith("Error:")
        and "missing_canary_app" in resolution_error.stderr,
        "Chirp resolution-error channel or exit code drifted",
        resolution_error,
    )

    handler_names = [
        "_new",
        "_run",
        "_check",
        "_diff",
        "_routes",
        "_security_check",
        "_freeze",
        "_makemigrations",
        "_migrate",
        "_shapes_codegen",
        "_version",
    ]
    lazy_script = (
        "import contextlib, io, json, sys; import chirp.cli as cli; "
        "sink=io.StringIO(); "
        "\nwith contextlib.redirect_stdout(sink):\n"
        " try:\n  cli.main(['--help'])\n except SystemExit:\n  pass\n"
        f"print(json.dumps([name for name in {handler_names!r} "
        "if 'chirp.cli.' + name in sys.modules]))"
    )
    lazy = _run((sys.executable, "-c", lazy_script))
    _require(
        lazy.returncode == 0 and json.loads(lazy.stdout) == [],
        "Released Chirp root help eagerly imported command handlers",
        lazy,
    )
    return {"released_chirp_ms": round((time.perf_counter() - started) * 1000, 2)}


def _fixture_env() -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    pythonpath = str(DOWNSTREAM) if not existing else os.pathsep.join((str(DOWNSTREAM), existing))
    return {"PYTHONPATH": pythonpath}


def _check_milo_fixture(contract: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    sys.path.insert(0, str(DOWNSTREAM))
    try:
        from milo import generate_llms_txt
        from milo.testing import MCPClient

        cli = importlib.import_module("chirp_canary.app").cli
        _require(HANDLER_MODULE not in sys.modules, "Fixture eagerly imported its handlers")
        root_help = cli.invoke(["--help"])
        _require(root_help.exit_code == 0, "Milo fixture root help failed")
        _require(
            _help_heading(root_help.output) == contract["root_help_heading"],
            "Milo fixture root help heading drifted",
        )
        for command_name in contract["commands"]:
            _require(command_name in root_help.output, f"Milo root help omitted {command_name}")
        for command_name, command in contract["commands"].items():
            result = cli.invoke([command_name, "--help"])
            _require(result.exit_code == 0, f"Milo {command_name} help failed")
            _require(
                _help_heading(result.output) == command["help_heading"],
                f"Milo {command_name} help heading drifted",
            )
            for property_name, prop in command["schema"]["properties"].items():
                presentation = prop.get("x-milo-cli", {})
                if presentation.get("kind") == "positional":
                    continue
                flags = [
                    f"--{property_name.replace('_', '-')}",
                    *presentation.get("aliases", []),
                ]
                _require(
                    any(flag in result.output for flag in flags),
                    f"Milo {command_name} help omitted {flags}",
                )
        _require(HANDLER_MODULE not in sys.modules, "Help imported the fixture handler module")

        discovered = [tool.name for tool in MCPClient(cli).list_tools()]
        _require(
            discovered == ["check", "diff", "routes"],
            "In-process MCP discovery did not preserve the safe command set",
        )
        llms = generate_llms_txt(cli)
        _require(HANDLER_MODULE not in sys.modules, "Agent discovery imported fixture handlers")
        for safe in discovered:
            _require(f"**{safe}**" in llms, f"llms.txt omitted safe command {safe}")
        for cli_only in (
            "new",
            "run",
            "dev",
            "security-check",
            "freeze",
            "makemigrations",
            "migrate",
            "shapes-codegen",
        ):
            _require(f"**{cli_only}**" not in llms, f"llms.txt exposed CLI-only {cli_only}")

        structured = cli.call_raw("check", app="demo:app", json=True, include_info=True)
        _require(structured["command"] == "check", "Programmatic call lost structured output")
        _require(structured["json"] is True, "Programmatic call lost the legacy JSON selector")
        _require(HANDLER_MODULE in sys.modules, "Selected command did not resolve its lazy handler")
    finally:
        sys.path.remove(str(DOWNSTREAM))

    env = _fixture_env()
    app_path = CANARY / "app.py"
    terminal = _run(
        (
            sys.executable,
            str(app_path),
            "check",
            "demo:app",
            "--json",
            "--include-info",
            "--format",
            "json",
        ),
        extra_env=env,
    )
    _require(terminal.returncode == 0 and not terminal.stderr, "Milo fixture CLI failed", terminal)
    terminal_data = json.loads(terminal.stdout)
    _require(
        terminal_data["command"] == "check" and terminal_data["include_info"] is True,
        "Milo fixture CLI structured stdout drifted",
        terminal,
    )
    parse_error = _run(
        (sys.executable, str(app_path), "check", "demo:app", "--not-a-chirp-option"),
        extra_env=env,
    )
    _require(
        parse_error.returncode == 2
        and not parse_error.stdout
        and "usage:" in parse_error.stderr
        and "error:" in parse_error.stderr,
        "Milo fixture parse-error channel or exit code drifted",
        parse_error,
    )
    command_error = _run(
        (sys.executable, str(app_path), "check", "missing_canary_app:app"),
        extra_env=env,
    )
    _require(
        command_error.returncode == 1
        and not command_error.stdout
        and "Could not import missing_canary_app" in command_error.stderr,
        "Milo fixture command-error channel or exit code drifted",
        command_error,
    )

    rpc_payload = "".join(
        f"{json.dumps(request)}\n"
        for request in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "check",
                    "arguments": {"app": "demo:app", "include_info": True},
                },
            },
        )
    )
    rpc = _run(
        (sys.executable, str(app_path), "--mcp"),
        input_text=rpc_payload,
        extra_env=env,
    )
    _require(rpc.returncode == 0, "Milo fixture MCP process failed", rpc)
    messages = [json.loads(line) for line in rpc.stdout.splitlines() if line.strip()]
    tools_response = next(message for message in messages if message.get("id") == 2)
    call_response = next(message for message in messages if message.get("id") == 3)
    tools = tools_response["result"]["tools"]
    _require(
        [tool["name"] for tool in tools] == ["check", "diff", "routes"],
        "MCP discovery did not preserve the safe command set",
        rpc,
    )
    _require(
        all(tool["annotations"].get("readOnlyHint") for tool in tools),
        "MCP safe commands lost readOnlyHint",
        rpc,
    )
    called = call_response["result"]["structuredContent"]
    _require(
        called["command"] == "check" and called["include_info"] is True,
        "MCP call lost structured output",
        rpc,
    )
    return {
        "milo_fixture_ms": round((time.perf_counter() - started) * 1000, 2),
        "mcp_tools": [tool["name"] for tool in tools],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="Exercise the canary fixture with the current environment; skip released Chirp.",
    )
    parser.add_argument(
        "--require-free-threaded",
        action="store_true",
        help="Fail unless Python is running with the GIL disabled.",
    )
    args = parser.parse_args()
    contract = _contract()
    try:
        free_threaded = _check_free_threaded(required=args.require_free_threaded)
        timings: dict[str, float] = {}
        if not args.fixture_only:
            _check_installed_versions(contract)
            timings.update(_check_released_chirp(contract))
        fixture = _check_milo_fixture(contract)
        timings["milo_fixture_ms"] = fixture.pop("milo_fixture_ms")
    except (CanaryError, KeyError, OSError, ValueError) as error:
        print(f"Chirp canary failed: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "passed",
                "versions": contract["versions"],
                "free_threaded": free_threaded,
                "commands": len(contract["commands"]),
                **fixture,
                "timings": timings,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
