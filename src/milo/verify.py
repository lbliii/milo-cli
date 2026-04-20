"""Self-diagnosis for agent-built milo CLIs (`milo verify`).

Answers "is this CLI correctly built?" via six checks:

1. **Imports** — the file (or module) loads without error.
2. **CLI located** — a ``milo.CLI`` instance is reachable in the module.
3. **Commands registered** — at least one ``@cli.command`` has been attached.
4. **Schemas generate** — ``function_to_schema`` succeeds for every command;
   missing docstring ``Args:`` sections surface as warnings.
5. **In-process MCP list** — ``_list_tools(cli)`` returns a well-formed list
   with one entry per command.
6. **Subprocess MCP transport** — running ``python <file> --mcp`` responds to
   ``initialize`` and ``tools/list`` over JSON-RPC. (Skipped for module:attr
   inputs since there's no standalone entry point.)

The report distinguishes pass/warn/fail; `milo verify` exits non-zero only on
failures, not warnings.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

    from milo.commands import CLI

_MCP_PROTOCOL_VERSION = "2025-06-18"
_ICONS = {"ok": "✓", "warn": "⚠", "fail": "✗", "skip": "∙"}


@dataclass(frozen=True, slots=True)
class VerifyCheck:
    """A single diagnostic check result."""

    name: str
    status: str  # "ok" | "warn" | "fail" | "skip"
    message: str
    details: str = ""


@dataclass(frozen=True, slots=True)
class VerifyReport:
    """Aggregated verify report."""

    target: str
    checks: tuple[VerifyCheck, ...]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "ok")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failures(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.status == "skip")

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def format(self) -> str:
        """Render the report for terminal output."""
        lines = [f"milo verify {self.target}", ""]
        for c in self.checks:
            icon = _ICONS.get(c.status, "?")
            lines.append(f"  {icon} {c.name}: {c.message}")
            if c.details:
                lines.extend(f"      {detail}" for detail in c.details.splitlines())
        lines.append("")
        summary = (
            f"{self.passed} passed, {self.warnings} warning(s), "
            f"{self.failures} failure(s), {self.skipped} skipped"
        )
        lines.append(summary)
        return "\n".join(lines)


def verify(target: str, *, timeout: float = 5.0) -> VerifyReport:
    """Run all verify checks against ``target``.

    Args:
        target: Either a filesystem path ending in ``.py`` or a ``module:attr``
            reference. File paths are imported via ``importlib.util`` so no
            ``sys.path`` pollution is required; module:attr is resolved via
            the standard import machinery with the cwd added to ``sys.path``.
        timeout: Seconds to wait for the subprocess MCP handshake.

    Returns:
        A :class:`VerifyReport` with every check attached. The report's
        ``exit_code`` is 1 iff any check failed (warnings do not fail the
        report).
    """
    checks: list[VerifyCheck] = []

    # --- Check 1: imports ---
    module, file_path, import_check = _load_target(target)
    checks.append(import_check)
    if import_check.status == "fail" or module is None:
        return VerifyReport(target=target, checks=tuple(checks))

    # --- Check 2: locate CLI instance ---
    cli = _find_cli_instance(module, target)
    if isinstance(cli, VerifyCheck):
        checks.append(cli)
        return VerifyReport(target=target, checks=tuple(checks))
    checks.append(
        VerifyCheck(
            name="cli_located",
            status="ok",
            message=f"found CLI instance (name={cli.name!r})",
        )
    )

    # --- Check 3: commands registered ---
    command_list = list(cli.walk_commands())
    if not command_list:
        checks.append(
            VerifyCheck(
                name="commands_registered",
                status="fail",
                message="no commands registered",
                details="Add at least one @cli.command(...) function.",
            )
        )
        return VerifyReport(target=target, checks=tuple(checks))
    checks.append(
        VerifyCheck(
            name="commands_registered",
            status="ok",
            message=f"{len(command_list)} command(s) registered",
            details=", ".join(path for path, _ in command_list),
        )
    )

    # --- Check 4: schemas generate ---
    checks.append(_check_schemas(command_list))

    # --- Check 5: in-process MCP list ---
    expected_visible = sum(1 for _, cmd in command_list if not getattr(cmd, "hidden", False))
    checks.append(_check_in_process_mcp(cli, expected_visible))

    # --- Check 6: subprocess MCP transport ---
    if file_path is None:
        checks.append(
            VerifyCheck(
                name="mcp_transport",
                status="skip",
                message="subprocess transport check skipped for module:attr input",
            )
        )
    else:
        checks.append(_check_subprocess_mcp(file_path, timeout=timeout))

    return VerifyReport(target=target, checks=tuple(checks))


def _load_target(target: str) -> tuple[ModuleType | None, Path | None, VerifyCheck]:
    """Import the target and return ``(module, file_path, import_check)``.

    ``file_path`` is ``None`` for module:attr inputs. On failure the first
    element is ``None`` and ``import_check`` carries the diagnosis.
    """
    if target.endswith(".py") and Path(target).is_file():
        path = Path(target).resolve()
        mod_name = f"_verify_{path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return (
                None,
                None,
                VerifyCheck(
                    name="imports",
                    status="fail",
                    message=f"could not create import spec for {path}",
                ),
            )
        module = importlib.util.module_from_spec(spec)
        # Register before exec_module so @dataclass etc. can resolve
        # ``sys.modules[cls.__module__]`` during class construction (Py 3.14).
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(mod_name, None)
            return (
                None,
                None,
                VerifyCheck(
                    name="imports",
                    status="fail",
                    message=f"import failed: {type(e).__name__}: {e}",
                ),
            )
        return module, path, VerifyCheck(name="imports", status="ok", message=f"loaded {path.name}")

    if ":" in target:
        module_path, _, _ = target.partition(":")
        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)
        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            return (
                None,
                None,
                VerifyCheck(
                    name="imports",
                    status="fail",
                    message=f"import failed: {type(e).__name__}: {e}",
                ),
            )
        return (
            module,
            None,
            VerifyCheck(name="imports", status="ok", message=f"loaded module {module_path!r}"),
        )

    return (
        None,
        None,
        VerifyCheck(
            name="imports",
            status="fail",
            message=(f"target {target!r} is neither a .py file path nor a module:attr reference"),
        ),
    )


def _find_cli_instance(module: ModuleType, target: str) -> CLI | VerifyCheck:
    """Find the CLI instance in ``module``.

    For ``module:attr`` targets, look up the named attribute. For file-path
    targets, scan the module for exactly one ``CLI`` instance.
    """
    from milo.commands import CLI

    if ":" in target and not target.endswith(".py"):
        _, _, attr = target.partition(":")
        obj = getattr(module, attr, None)
        if obj is None:
            return VerifyCheck(
                name="cli_located",
                status="fail",
                message=f"attribute {attr!r} not found on module",
            )
        if not isinstance(obj, CLI):
            return VerifyCheck(
                name="cli_located",
                status="fail",
                message=f"{attr!r} is {type(obj).__name__}, not milo.CLI",
            )
        return obj

    instances = [
        (name, obj)
        for name, obj in vars(module).items()
        if isinstance(obj, CLI) and not name.startswith("_")
    ]
    if not instances:
        return VerifyCheck(
            name="cli_located",
            status="fail",
            message="no milo.CLI instance found at module top level",
            details="Assign one: `cli = CLI(name=..., ...)`",
        )
    if len(instances) > 1:
        names = ", ".join(n for n, _ in instances)
        return VerifyCheck(
            name="cli_located",
            status="fail",
            message=f"multiple CLI instances found: {names}",
            details="Use the module:attr form to disambiguate.",
        )
    return instances[0][1]


def _check_schemas(command_list: list[tuple[str, Any]]) -> VerifyCheck:
    """Generate schemas for every command; surface docstring coverage gaps.

    Coverage gaps come from ``function_to_schema(..., warn_missing_docs=True)``
    so verify sees the same undocumented-param judgement as production schema
    generation would, were it opted in.
    """
    import warnings as _warnings

    from milo.schema import function_to_schema

    failures: list[str] = []
    doc_warnings: list[str] = []

    for path, cmd in command_list:
        handler = getattr(cmd, "handler", None)
        if handler is None:
            failures.append(f"{path}: no handler")
            continue
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            try:
                function_to_schema(handler, warn_missing_docs=True)
            except Exception as e:
                failures.append(f"{path}: {type(e).__name__}: {e}")
                continue
        for w in caught:
            if not issubclass(w.category, UserWarning):
                continue
            msg = str(w.message)
            # Only surface missing-docs warnings here. Other UserWarnings
            # (unrecognized type fallbacks, unresolved forward refs) belong
            # to schema generation itself, not docstring coverage.
            if "no description" in msg:
                doc_warnings.append(f"{path}: {msg}")

    if failures:
        return VerifyCheck(
            name="schemas_generate",
            status="fail",
            message=f"{len(failures)} schema generation failure(s)",
            details="\n".join(failures),
        )
    if doc_warnings:
        return VerifyCheck(
            name="schemas_generate",
            status="warn",
            message=(
                f"schemas generate ({len(command_list)}), "
                f"but {len(doc_warnings)} parameter(s) lack descriptions"
            ),
            details="\n".join(doc_warnings),
        )
    return VerifyCheck(
        name="schemas_generate",
        status="ok",
        message=f"{len(command_list)} schema(s) generated; all params documented",
    )


def _check_in_process_mcp(cli: CLI, expected_count: int) -> VerifyCheck:
    """Call ``_list_tools(cli)`` and validate shape."""
    from milo.mcp import _list_tools

    try:
        tools = _list_tools(cli)
    except Exception as e:
        return VerifyCheck(
            name="mcp_list_tools",
            status="fail",
            message=f"_list_tools raised: {type(e).__name__}: {e}",
        )

    if len(tools) != expected_count:
        return VerifyCheck(
            name="mcp_list_tools",
            status="fail",
            message=(
                f"expected {expected_count} tool(s), got {len(tools)} — "
                f"some commands did not reach the MCP surface"
            ),
        )
    for tool in tools:
        if "name" not in tool or "inputSchema" not in tool:
            return VerifyCheck(
                name="mcp_list_tools",
                status="fail",
                message=f"malformed tool entry: {tool!r}",
            )
    return VerifyCheck(
        name="mcp_list_tools",
        status="ok",
        message=f"{len(tools)} tool(s) listed with valid inputSchema",
    )


def _check_subprocess_mcp(path: Path, *, timeout: float) -> VerifyCheck:
    """Start `python <path> --mcp`, handshake, verify tools/list response."""
    proc = subprocess.Popen(
        [sys.executable, str(path), "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": _MCP_PROTOCOL_VERSION, "capabilities": {}},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        try:
            stdout, stderr = proc.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return VerifyCheck(
                name="mcp_transport",
                status="fail",
                message=f"subprocess did not respond within {timeout}s",
                details='Check that the file ends with `if __name__ == "__main__": cli.run()`.',
            )

        responses: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(json.JSONDecodeError):
                responses.append(json.loads(line))

        if len(responses) < 2:
            return VerifyCheck(
                name="mcp_transport",
                status="fail",
                message=f"expected 2 JSON-RPC responses, got {len(responses)}",
                details=(stderr or "no stderr").strip()[:500],
            )

        init_resp, tools_resp = responses[0], responses[1]
        if "result" not in init_resp or "protocolVersion" not in init_resp.get("result", {}):
            return VerifyCheck(
                name="mcp_transport",
                status="fail",
                message="initialize response missing protocolVersion",
                details=json.dumps(init_resp)[:300],
            )
        if "result" not in tools_resp or "tools" not in tools_resp.get("result", {}):
            return VerifyCheck(
                name="mcp_transport",
                status="fail",
                message="tools/list response missing tools list",
                details=json.dumps(tools_resp)[:300],
            )

        tool_count = len(tools_resp["result"]["tools"])
        return VerifyCheck(
            name="mcp_transport",
            status="ok",
            message=f"subprocess handshake succeeded; {tool_count} tool(s) over JSON-RPC",
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
