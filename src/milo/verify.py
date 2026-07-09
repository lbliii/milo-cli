"""Self-diagnosis for agent-built milo CLIs (`milo verify`).

Answers "is this CLI correctly built?" via ten checks:

1. **Imports** — the file (or module) loads without error.
2. **CLI located** — a ``milo.CLI`` instance is reachable in the module.
3. **Commands registered** — at least one ``@cli.command`` has been attached.
4. **Schemas generate** — ``function_to_schema`` succeeds for every command;
   missing docstring ``Args:`` sections surface as warnings.
5. **In-process MCP list** — ``_list_tools(cli)`` returns a well-formed list
   with one entry per command.
6. **MCP discovery** — ``server/discover`` reports the supported protocol
   versions, capabilities, and server info used by stateless MCP clients.
7. **In-process MCP Apps** — negotiated tools, UI resources, metadata, and
   payload reads agree without interpreting application HTML.
8. **Gateway MCP Apps** — a single-child gateway preserves and rewrites every
   tool-to-resource link without dropping metadata.
9. **Subprocess MCP transport** — running ``python <file> --mcp`` responds to
   ``server/discover``, then the legacy ``initialize`` handshake, and
   ``tools/list`` over JSON-RPC. (Skipped for module:attr inputs since there's
   no standalone entry point.)
10. **Subprocess MCP Apps** — the same process negotiates the MCP Apps
    extension, lists matching tool/resource views, and reads each UI resource.

The report distinguishes pass/warn/fail; `milo verify` exits non-zero only on
failures, not warnings.
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from milo._jsonrpc import (
    LEGACY_MCP_VERSION as _LEGACY_MCP_PROTOCOL_VERSION,
)
from milo._jsonrpc import (
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
)
from milo._jsonrpc import (
    MCP_VERSION as _MCP_PROTOCOL_VERSION,
)

if TYPE_CHECKING:
    from types import ModuleType

    from milo.commands import CLI

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
    expected_visible = sum(
        1 for _, cmd in command_list if not getattr(cmd, "hidden", False) and "mcp" in cmd.surfaces
    )
    checks.append(_check_in_process_mcp(cli, expected_visible))

    # --- Check 6: MCP discovery ---
    checks.append(_check_mcp_discovery(cli))

    # --- Check 7: in-process MCP Apps conformance ---
    checks.append(_check_mcp_apps_in_process(cli))

    # --- Check 8: gateway MCP Apps projection ---
    checks.append(_check_mcp_apps_gateway(cli))

    # --- Checks 9-10: subprocess MCP transport and MCP Apps conformance ---
    if file_path is None:
        checks.extend(
            (
                VerifyCheck(
                    name="mcp_transport",
                    status="skip",
                    message="subprocess transport check skipped for module:attr input",
                ),
                VerifyCheck(
                    name="mcp_apps_transport",
                    status="skip",
                    message="subprocess MCP Apps check skipped for module:attr input",
                ),
            )
        )
    else:
        transport_checks = _check_subprocess_mcp(
            file_path,
            timeout=timeout,
            ui_resource_uris=_ui_resource_uris(cli),
        )
        checks.extend(transport_checks)

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


def _check_mcp_discovery(cli: CLI) -> VerifyCheck:
    """Verify ``server/discover`` advertises the active MCP contract."""
    from milo._mcp_router import dispatch
    from milo.mcp import _CLIHandler

    try:
        result = dispatch(
            _CLIHandler(cli),
            "server/discover",
            {"_meta": _modern_meta()},
        )
    except Exception as e:
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message=f"server/discover raised: {type(e).__name__}: {e}",
        )

    if result is None:
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message="server/discover returned no result",
        )
    supported = result.get("supportedVersions")
    if not isinstance(supported, list) or _MCP_PROTOCOL_VERSION not in supported:
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message="server/discover missing active protocol version",
            details=json.dumps(result)[:300],
        )
    if not isinstance(result.get("capabilities"), dict):
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message="server/discover missing capabilities object",
            details=json.dumps(result)[:300],
        )
    if result.get("resultType") != "complete":
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message="server/discover missing resultType=complete",
            details=json.dumps(result)[:300],
        )
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict) or not server_info.get("name"):
        return VerifyCheck(
            name="mcp_discover",
            status="fail",
            message="server/discover missing serverInfo.name",
            details=json.dumps(result)[:300],
        )
    return VerifyCheck(
        name="mcp_discover",
        status="ok",
        message=f"server/discover advertises {_MCP_PROTOCOL_VERSION}",
    )


def _mcp_apps_params() -> dict[str, Any]:
    """Return the one canonical MCP Apps client capability declaration."""
    from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

    return {
        "capabilities": {
            "extensions": {
                MCP_APPS_EXTENSION_ID: {"mimeTypes": [MCP_APPS_MIME_TYPE]},
            }
        }
    }


def _modern_meta(*, include_ui: bool = False) -> dict[str, Any]:
    """Return required per-request metadata for the active MCP revision."""
    capabilities = _mcp_apps_params()["capabilities"] if include_ui else {}
    return {
        MCP_PROTOCOL_VERSION_META_KEY: _MCP_PROTOCOL_VERSION,
        MCP_CLIENT_INFO_META_KEY: {"name": "milo-verify", "version": "1.0"},
        MCP_CLIENT_CAPABILITIES_META_KEY: capabilities,
    }


def _mcp_apps_capability_issues(result: Any, *, surface: str) -> list[str]:
    """Validate a discovery/initialize result's MCP Apps declaration."""
    from milo.mcp_apps import MCP_APPS_EXTENSION_ID, MCP_APPS_MIME_TYPE

    fix = f"Advertise {MCP_APPS_EXTENSION_ID!r} with mimeTypes containing {MCP_APPS_MIME_TYPE!r}."
    if not isinstance(result, dict):
        return [f"{surface}: expected an object result. Fix: {fix}"]
    capabilities = result.get("capabilities")
    if not isinstance(capabilities, dict):
        return [f"{surface}: capabilities must be an object. Fix: {fix}"]
    extensions = capabilities.get("extensions")
    if not isinstance(extensions, dict):
        return [f"{surface}: capabilities.extensions must be an object. Fix: {fix}"]
    ui = extensions.get(MCP_APPS_EXTENSION_ID)
    if not isinstance(ui, dict):
        return [f"{surface}: missing the {MCP_APPS_EXTENSION_ID!r} extension. Fix: {fix}"]
    mime_types = ui.get("mimeTypes")
    if (
        not isinstance(mime_types, list)
        or any(not isinstance(value, str) or not value for value in mime_types)
        or MCP_APPS_MIME_TYPE not in mime_types
    ):
        return [f"{surface}: MCP Apps mimeTypes omit {MCP_APPS_MIME_TYPE!r}. Fix: {fix}"]
    return []


def _metadata_issues(meta: Any, *, surface: str) -> list[str]:
    """Validate protocol-level MCP Apps resource metadata types."""
    if not isinstance(meta, dict):
        return [f"{surface}: _meta must be an object. Fix: pass MCPAppResourceMeta(...)."]
    if "ui" not in meta:
        return []
    ui = meta.get("ui")
    if not isinstance(ui, dict):
        return [f"{surface}: _meta.ui must be an object. Fix: pass MCPAppResourceMeta(...)."]

    issues: list[str] = []
    csp = ui.get("csp")
    if csp is not None:
        if not isinstance(csp, dict):
            issues.append(
                f"{surface}: _meta.ui.csp must be an object. "
                "Fix: pass MCPAppCSP(...) through MCPAppResourceMeta."
            )
        else:
            for field in (
                "connectDomains",
                "resourceDomains",
                "frameDomains",
                "baseUriDomains",
            ):
                if field not in csp:
                    continue
                values = csp[field]
                if not isinstance(values, list) or any(
                    not isinstance(value, str) or not value for value in values
                ):
                    issues.append(
                        f"{surface}: _meta.ui.csp.{field} must be a list of non-empty strings. "
                        "Fix: pass valid domains to MCPAppCSP."
                    )

    permissions = ui.get("permissions")
    if permissions is not None:
        if not isinstance(permissions, dict):
            issues.append(
                f"{surface}: _meta.ui.permissions must be an object. "
                "Fix: pass MCPAppPermissions(...) through MCPAppResourceMeta."
            )
        elif any(
            not isinstance(name, str) or not isinstance(value, dict)
            for name, value in permissions.items()
        ):
            issues.append(
                f"{surface}: each _meta.ui.permissions entry must map a name to an object. "
                "Fix: use MCPAppPermissions boolean fields."
            )

    if "domain" in ui and (not isinstance(ui["domain"], str) or not ui["domain"]):
        issues.append(
            f"{surface}: _meta.ui.domain must be a non-empty string. "
            "Fix: pass a non-empty domain to MCPAppResourceMeta."
        )
    if "prefersBorder" in ui and not isinstance(ui["prefersBorder"], bool):
        issues.append(
            f"{surface}: _meta.ui.prefersBorder must be a boolean. "
            "Fix: pass True or False to MCPAppResourceMeta."
        )
    return issues


def _resource_entries(
    resources: list[Any],
    *,
    surface: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Collect MCP Apps resources and report malformed protocol entries."""
    from milo.mcp_apps import MCP_APPS_MIME_TYPE

    entries: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            continue
        uri = resource.get("uri")
        mime_type = resource.get("mimeType")
        is_ui = (isinstance(uri, str) and uri.startswith("ui://")) or (
            mime_type == MCP_APPS_MIME_TYPE
        )
        if not is_ui:
            continue
        location = f"{surface} resources[{index}]"
        if not isinstance(uri, str) or not uri.startswith("ui://") or not uri[5:]:
            issues.append(
                f"{location}: MCP Apps resources require a non-empty ui:// URI. "
                "Fix: register the resource with cli.ui_resource('ui://...')."
            )
            continue
        if mime_type != MCP_APPS_MIME_TYPE:
            issues.append(
                f"{location} ({uri}): mimeType must be {MCP_APPS_MIME_TYPE!r}. "
                "Fix: use cli.ui_resource(), which supplies the required profile."
            )
        if not isinstance(resource.get("name"), str) or not resource.get("name"):
            issues.append(
                f"{location} ({uri}): name must be a non-empty string. "
                "Fix: pass name=... to cli.ui_resource()."
            )
        if "description" in resource and not isinstance(resource["description"], str):
            issues.append(
                f"{location} ({uri}): description must be a string. "
                "Fix: pass description=... to cli.ui_resource()."
            )
        if "_meta" in resource:
            issues.extend(_metadata_issues(resource["_meta"], surface=f"{location} ({uri})"))
        if uri in entries:
            issues.append(
                f"{location} ({uri}): duplicate UI resource URI. "
                "Fix: register each ui:// URI exactly once."
            )
            continue
        entries[uri] = resource
    return entries, issues


def _tool_links(
    tools: list[Any],
    *,
    surface: str,
) -> tuple[list[tuple[str, str, dict[str, Any]]], list[str]]:
    """Collect nested MCP Apps tool metadata and validate its wire shape."""
    links: list[tuple[str, str, dict[str, Any]]] = []
    issues: list[str] = []
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            continue
        if "_meta" not in tool:
            continue
        meta = tool.get("_meta")
        if not isinstance(meta, dict):
            issues.append(
                f"{surface} tools[{index}]: _meta must be an object. "
                "Fix: pass MCPAppToolMeta(...) to @cli.command(ui=...)."
            )
            continue
        if "ui" not in meta:
            continue
        name = tool.get("name")
        location = f"{surface} tools[{index}]"
        if not isinstance(name, str) or not name:
            issues.append(
                f"{location}: a tool with MCP Apps metadata needs a non-empty name. "
                "Fix: register it with @cli.command('name')."
            )
            name = f"tools[{index}]"
        ui = meta.get("ui")
        if not isinstance(ui, dict):
            issues.append(
                f"{location} ({name}): _meta.ui must be an object. "
                "Fix: pass MCPAppToolMeta(...) to @cli.command(ui=...)."
            )
            continue
        uri = ui.get("resourceUri")
        if not isinstance(uri, str) or not uri.startswith("ui://") or not uri[5:]:
            issues.append(
                f"{location} ({name}): _meta.ui.resourceUri must be a non-empty ui:// URI. "
                "Fix: pass a registered URI to MCPAppToolMeta."
            )
            continue
        visibility = ui.get("visibility")
        if (
            not isinstance(visibility, list)
            or not visibility
            or any(value not in {"model", "app"} for value in visibility)
        ):
            issues.append(
                f"{location} ({name}): _meta.ui.visibility must be a non-empty list "
                "containing only 'model' and 'app'. Fix: use MCPAppToolMeta visibility values."
            )
        elif len(visibility) != len(set(visibility)):
            issues.append(
                f"{location} ({name}): _meta.ui.visibility contains duplicates. "
                "Fix: declare each visibility value once."
            )
        links.append((name, uri, ui))
    return links, issues


def _content_issues(
    result: Any,
    *,
    uri: str,
    listed_resource: dict[str, Any],
    surface: str,
) -> list[str]:
    """Validate one resources/read result without parsing application HTML."""
    from milo.mcp_apps import MCP_APPS_MIME_TYPE

    fix = "Fix the UI resource handler to return str or bytes, then rerun milo verify."
    if not isinstance(result, dict):
        return [f"{surface} resources/read {uri}: result must be an object. Fix: {fix}"]
    contents = result.get("contents")
    if not isinstance(contents, list) or len(contents) != 1 or not isinstance(contents[0], dict):
        return [f"{surface} resources/read {uri}: expected exactly one content object. Fix: {fix}"]

    content = contents[0]
    issues: list[str] = []
    if content.get("uri") != uri:
        issues.append(
            f"{surface} resources/read {uri}: content URI is {content.get('uri')!r}. "
            "Fix: return the requested resource URI unchanged."
        )
    if content.get("mimeType") != MCP_APPS_MIME_TYPE:
        issues.append(
            f"{surface} resources/read {uri}: mimeType must be {MCP_APPS_MIME_TYPE!r}. "
            "Fix: use cli.ui_resource() for the handler."
        )
    has_text = "text" in content
    has_blob = "blob" in content
    if has_text == has_blob:
        issues.append(
            f"{surface} resources/read {uri}: content must contain exactly one of text or blob. "
            f"Fix: {fix}"
        )
    elif has_text and not isinstance(content["text"], str):
        issues.append(f"{surface} resources/read {uri}: text must be a string. Fix: {fix}")
    elif has_blob:
        blob = content["blob"]
        if not isinstance(blob, str):
            issues.append(
                f"{surface} resources/read {uri}: blob must be a base64 string. Fix: {fix}"
            )
        else:
            try:
                base64.b64decode(blob, validate=True)
            except ValueError, TypeError:
                issues.append(
                    f"{surface} resources/read {uri}: blob is not valid base64. Fix: {fix}"
                )

    listed_meta = listed_resource.get("_meta")
    content_meta = content.get("_meta")
    if listed_meta != content_meta:
        issues.append(
            f"{surface} resources/read {uri}: _meta differs from resources/list. "
            "Fix: return the registered MCPAppResourceMeta consistently."
        )
    if "_meta" in content:
        issues.extend(_metadata_issues(content["_meta"], surface=f"{surface} content {uri}"))
    return issues


def _mcp_apps_view_issues(
    tools: Any,
    resources: Any,
    *,
    surface: str,
    read_resource: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[list[str], int, int, int]:
    """Validate linked tool, resource-list, and optional resource-read views."""
    if not isinstance(tools, list):
        return (
            [f"{surface} tools/list: tools must be a list. Fix: return {{'tools': [...]}}."],
            0,
            0,
            0,
        )
    if not isinstance(resources, list):
        return (
            [
                f"{surface} resources/list: resources must be a list. "
                "Fix: return {'resources': [...]}."
            ],
            0,
            0,
            0,
        )

    resource_entries, resource_issues = _resource_entries(resources, surface=surface)
    links, link_issues = _tool_links(tools, surface=surface)
    issues = [*resource_issues, *link_issues]
    for tool_name, uri, _ui in links:
        if uri not in resource_entries:
            issues.append(
                f"{surface} tool {tool_name!r} links missing resource {uri!r}. "
                f"Fix: register {uri!r} with cli.ui_resource()."
            )

    read_count = 0
    if read_resource is not None:
        from milo._errors import format_error

        for uri, resource in resource_entries.items():
            try:
                result = read_resource(uri)
            except Exception as exc:
                issues.append(
                    f"{surface} resources/read {uri} failed: {format_error(exc)}\n"
                    "Fix: repair the UI resource handler and rerun milo verify."
                )
                continue
            read_count += 1
            issues.extend(
                _content_issues(
                    result,
                    uri=uri,
                    listed_resource=resource,
                    surface=surface,
                )
            )
    return issues, len(links), len(resource_entries), read_count


def _failed_conformance(name: str, issues: list[str]) -> VerifyCheck:
    """Build one stable failure row from actionable conformance findings."""
    return VerifyCheck(
        name=name,
        status="fail",
        message=f"{len(issues)} MCP Apps conformance issue(s)",
        details="\n".join(issues),
    )


def _registered_link_issues(cli: CLI) -> list[str]:
    """Validate links that may be app-only and therefore absent from tools/list."""
    resource_uris = {uri for uri, _resource in cli.walk_ui_resources()}
    issues: list[str] = []
    for path, command in cli.walk_commands():
        ui = getattr(command, "ui", None)
        uri = getattr(ui, "resource_uri", None)
        if isinstance(uri, str) and uri not in resource_uris:
            issues.append(
                f"M-UI-002: registered tool {path!r} links missing resource {uri!r}. "
                f"Fix: register {uri!r} with cli.ui_resource()."
            )
    return issues


def _check_mcp_apps_in_process(cli: CLI) -> VerifyCheck:
    """Validate negotiated MCP Apps views and payload reads in-process."""
    from milo._errors import format_error
    from milo._mcp_router import dispatch
    from milo.mcp import _CLIHandler

    handler = _CLIHandler(cli)
    issues = _registered_link_issues(cli)
    try:
        discovered = handler.server_discover({})
        issues.extend(_mcp_apps_capability_issues(discovered, surface="server/discover"))
        initialized = handler.initialize(_mcp_apps_params())
        issues.extend(_mcp_apps_capability_issues(initialized, surface="initialize"))
        modern_params = {"_meta": _modern_meta(include_ui=True)}
        tools_result = dispatch(handler, "tools/list", modern_params) or {}
        resources_result = dispatch(handler, "resources/list", modern_params) or {}
        tools = tools_result.get("tools")
        resources = resources_result.get("resources")
        issues.extend(_cacheable_result_issues(tools_result, method="tools/list"))
        issues.extend(_cacheable_result_issues(resources_result, method="resources/list"))
    except Exception as exc:
        issues.append(
            f"in-process MCP Apps negotiation/list failed: {format_error(exc)}\n"
            "Fix: repair the linked ui:// resource or capability declaration."
        )
        return _failed_conformance("mcp_apps_in_process", issues)

    view_issues, link_count, resource_count, read_count = _mcp_apps_view_issues(
        tools,
        resources,
        surface="in-process",
        read_resource=lambda uri: (
            dispatch(
                handler,
                "resources/read",
                {"uri": uri, "_meta": _modern_meta(include_ui=True)},
            )
            or {}
        ),
    )
    issues.extend(view_issues)
    if issues:
        return _failed_conformance("mcp_apps_in_process", issues)
    return VerifyCheck(
        name="mcp_apps_in_process",
        status="ok",
        message=(
            f"{link_count} tool link(s) and {resource_count} UI resource(s) agree; "
            f"{read_count} resource(s) readable"
        ),
    )


class _VerifyGatewayChild:
    """In-process child adapter used only to exercise the real gateway projection."""

    def __init__(self, cli: CLI) -> None:
        from milo.mcp import _CLIHandler

        self._handler = _CLIHandler(cli)
        self._handler.initialize(_mcp_apps_params())

    def fetch_tools(self) -> list[dict[str, Any]]:
        return self._handler.list_tools({})["tools"]

    def send_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        methods: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "resources/list": self._handler.list_resources,
            "resources/read": self._handler.read_resource,
            "prompts/list": self._handler.list_prompts,
        }
        handler = methods.get(method)
        if handler is None:
            raise ValueError(f"Unsupported verify gateway method: {method}")
        return handler(params)


def _check_mcp_apps_gateway(cli: CLI) -> VerifyCheck:
    """Project one CLI through the real gateway and compare every UI link."""
    from milo._errors import format_error
    from milo._mcp_router import dispatch
    from milo.gateway import _discover_all, _GatewayHandler

    child = _VerifyGatewayChild(cli)
    issues: list[str] = []
    try:
        direct_tools = child.fetch_tools()
        direct_resources = child.send_call("resources/list", {})["resources"]
        children: dict[str, Any] = {"verify": child}
        state = _discover_all({"verify": {}}, children)
        handler = _GatewayHandler({"verify": {}}, state, children)
        discovered = handler.server_discover({})
        issues.extend(_mcp_apps_capability_issues(discovered, surface="gateway server/discover"))
        initialized = handler.initialize(_mcp_apps_params())
        issues.extend(_mcp_apps_capability_issues(initialized, surface="gateway initialize"))
        modern_params = {"_meta": _modern_meta(include_ui=True)}
        gateway_tools_result = dispatch(handler, "tools/list", modern_params) or {}
        gateway_resources_result = dispatch(handler, "resources/list", modern_params) or {}
        gateway_tools = gateway_tools_result["tools"]
        gateway_resources = gateway_resources_result["resources"]
        issues.extend(_cacheable_result_issues(gateway_tools_result, method="tools/list"))
        issues.extend(_cacheable_result_issues(gateway_resources_result, method="resources/list"))
    except Exception as exc:
        issues.append(
            f"gateway MCP Apps projection failed: {format_error(exc)}\n"
            "Fix: repair the child tool/resource views and rerun milo verify."
        )
        return _failed_conformance("mcp_apps_gateway", issues)

    view_issues, link_count, resource_count, _ = _mcp_apps_view_issues(
        gateway_tools,
        gateway_resources,
        surface="gateway",
    )
    issues.extend(view_issues)

    direct_resource_entries, direct_resource_issues = _resource_entries(
        direct_resources,
        surface="gateway child",
    )
    direct_links, direct_link_issues = _tool_links(direct_tools, surface="gateway child")
    issues.extend(direct_resource_issues)
    issues.extend(direct_link_issues)
    gateway_resources_by_uri = {
        resource.get("uri"): resource
        for resource in gateway_resources
        if isinstance(resource, dict) and isinstance(resource.get("uri"), str)
    }
    gateway_tools_by_name = {
        tool.get("name"): tool
        for tool in gateway_tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    routed_resources = {
        original_uri: exposed_uri
        for exposed_uri, (child_name, original_uri) in state.resource_routing.items()
        if child_name == "verify" and original_uri in direct_resource_entries
    }

    for original_uri, direct_resource in direct_resource_entries.items():
        exposed_uri = routed_resources.get(original_uri)
        if exposed_uri is None:
            issues.append(
                f"gateway omitted child UI resource {original_uri!r}. "
                "Fix: keep the ui:// URI and MCP Apps MIME profile paired."
            )
            continue
        expected_resource = deepcopy(direct_resource)
        expected_resource["uri"] = exposed_uri
        if gateway_resources_by_uri.get(exposed_uri) != expected_resource:
            issues.append(
                f"gateway changed metadata for child UI resource {original_uri!r}. "
                "Fix: preserve the resource fields while rewriting only uri."
            )

    for tool_name, original_uri, direct_ui in direct_links:
        exposed_tool = gateway_tools_by_name.get(f"verify.{tool_name}")
        exposed_uri = routed_resources.get(original_uri)
        exposed_meta = exposed_tool.get("_meta") if isinstance(exposed_tool, dict) else None
        exposed_ui = exposed_meta.get("ui") if isinstance(exposed_meta, dict) else None
        expected_ui = deepcopy(direct_ui)
        expected_ui["resourceUri"] = exposed_uri
        if exposed_uri is None or exposed_ui != expected_ui:
            issues.append(
                f"gateway tool {'verify.' + tool_name!r} does not resolve child link "
                f"{original_uri!r}. Fix: preserve UI metadata and rewrite resourceUri to the "
                "gateway resource URI."
            )

    if link_count != len(direct_links) or resource_count != len(direct_resource_entries):
        issues.append(
            "gateway MCP Apps counts differ from the child view. "
            "Fix: do not drop valid linked tools or UI resources during discovery."
        )
    if issues:
        return _failed_conformance("mcp_apps_gateway", issues)
    return VerifyCheck(
        name="mcp_apps_gateway",
        status="ok",
        message=f"gateway preserves {link_count} tool link(s) and {resource_count} UI resource(s)",
    )


def _ui_resource_uris(cli: CLI) -> tuple[str, ...]:
    """Return deterministic registered and linked UI URIs for wire reads."""
    uris: dict[str, None] = {}
    for uri, _resource in cli.walk_ui_resources():
        if isinstance(uri, str):
            uris[uri] = None
    for _path, command in cli.walk_commands():
        ui = getattr(command, "ui", None)
        uri = getattr(ui, "resource_uri", None)
        if isinstance(uri, str):
            uris[uri] = None
    return tuple(uris)


def _check_subprocess_mcp(
    path: Path,
    *,
    timeout: float,
    ui_resource_uris: tuple[str, ...],
) -> tuple[VerifyCheck, VerifyCheck]:
    """Start ``python <path> --mcp`` and verify base plus MCP Apps transport."""
    proc = subprocess.Popen(
        [sys.executable, str(path), "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        initialize_params = {
            "protocolVersion": _LEGACY_MCP_PROTOCOL_VERSION,
            **_mcp_apps_params(),
        }
        modern_params = {"_meta": _modern_meta(include_ui=True)}
        requests: list[dict[str, Any]] = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": modern_params,
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": initialize_params,
            },
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": modern_params},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/list",
                "params": modern_params,
            },
        ]
        read_ids: dict[str, int] = {}
        for request_id, uri in enumerate(ui_resource_uris, start=5):
            read_ids[uri] = request_id
            requests.append(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "resources/read",
                    "params": {"uri": uri, **modern_params},
                }
            )
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        try:
            stdout, stderr = proc.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            transport_detail = (
                'Check that the file ends with `if __name__ == "__main__": cli.run()`.'
            )
            apps_detail = (
                f"{transport_detail} Also ensure every cli.ui_resource() handler returns "
                "within the verify timeout."
            )
            return (
                VerifyCheck(
                    name="mcp_transport",
                    status="fail",
                    message=f"subprocess did not respond within {timeout}s",
                    details=transport_detail,
                ),
                VerifyCheck(
                    name="mcp_apps_transport",
                    status="fail",
                    message=f"subprocess MCP Apps check timed out after {timeout}s",
                    details=apps_detail,
                ),
            )

        responses: dict[int, dict[str, Any]] = {}
        stdout_issues: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                stdout_issues.append(
                    f"non-JSON MCP stdout: {line[:200]!r}. Fix: write diagnostics to stderr "
                    "or Context; MCP stdout is JSON-RPC only."
                )
                continue
            if isinstance(decoded, dict) and isinstance(decoded.get("id"), int):
                responses[decoded["id"]] = decoded
            elif not isinstance(decoded, dict):
                stdout_issues.append(
                    f"malformed MCP stdout value: {decoded!r}. Fix: emit JSON-RPC objects only."
                )

        stderr_excerpt = (stderr or "").strip()[:500]
        return (
            _check_base_transport_responses(
                responses,
                stdout_issues=stdout_issues,
                stderr_excerpt=stderr_excerpt,
            ),
            _check_apps_transport_responses(
                responses,
                read_ids=read_ids,
                stdout_issues=stdout_issues,
                stderr_excerpt=stderr_excerpt,
            ),
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _response_result(
    responses: dict[int, dict[str, Any]],
    request_id: int,
    method: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return one JSON-RPC result object or an actionable transport issue."""
    response = responses.get(request_id)
    if response is None:
        return None, f"{method}: missing JSON-RPC response for request id {request_id}."
    if "error" in response:
        return (
            None,
            f"{method}: server returned {json.dumps(response['error'], sort_keys=True)[:400]}.",
        )
    result = response.get("result")
    if not isinstance(result, dict):
        return None, f"{method}: response result must be an object; got {result!r}."
    return result, None


def _check_base_transport_responses(
    responses: dict[int, dict[str, Any]],
    *,
    stdout_issues: list[str],
    stderr_excerpt: str,
) -> VerifyCheck:
    """Validate the existing discovery/initialize/tools subprocess contract."""
    issues = list(stdout_issues)
    discover, issue = _response_result(responses, 1, "server/discover")
    if issue is not None or discover is None:
        issues.append(issue or "server/discover: missing result object.")
    else:
        if _MCP_PROTOCOL_VERSION not in discover.get("supportedVersions", []):
            issues.append("server/discover: response is missing the active protocol version.")
        if discover.get("resultType") != "complete":
            issues.append("server/discover: response is missing resultType=complete.")

    initialized, issue = _response_result(responses, 2, "initialize")
    if issue is not None or initialized is None:
        issues.append(issue or "initialize: missing result object.")
    elif initialized.get("protocolVersion") != _LEGACY_MCP_PROTOCOL_VERSION:
        issues.append("initialize: response did not select the supported legacy protocol.")

    tools_result, issue = _response_result(responses, 3, "tools/list")
    tools: list[Any] = []
    if issue is not None or tools_result is None:
        issues.append(issue or "tools/list: missing result object.")
    else:
        listed_tools = tools_result.get("tools")
        if not isinstance(listed_tools, list):
            issues.append("tools/list: response is missing a tools list.")
        else:
            tools = listed_tools
        issues.extend(_cacheable_result_issues(tools_result, method="tools/list"))

    if issues:
        if stderr_excerpt:
            issues.append(f"subprocess stderr: {stderr_excerpt}")
        return VerifyCheck(
            name="mcp_transport",
            status="fail",
            message=f"{len(issues)} subprocess transport issue(s)",
            details="\n".join(issues),
        )
    return VerifyCheck(
        name="mcp_transport",
        status="ok",
        message=(
            f"subprocess modern discovery and legacy fallback succeeded; "
            f"{len(tools)} tool(s) over JSON-RPC"
        ),
    )


def _cacheable_result_issues(result: dict[str, Any], *, method: str) -> list[str]:
    """Validate modern result typing and cache hints on a cacheable method."""
    issues: list[str] = []
    if result.get("resultType") != "complete":
        issues.append(f"{method}: response is missing resultType=complete.")
    ttl = result.get("ttlMs")
    if not isinstance(ttl, int) or ttl < 0:
        issues.append(f"{method}: response ttlMs must be a non-negative integer.")
    if result.get("cacheScope") not in {"public", "private"}:
        issues.append(f"{method}: response cacheScope must be public or private.")
    return issues


def _check_apps_transport_responses(
    responses: dict[int, dict[str, Any]],
    *,
    read_ids: dict[str, int],
    stdout_issues: list[str],
    stderr_excerpt: str,
) -> VerifyCheck:
    """Validate negotiated MCP Apps lists and reads over subprocess JSON-RPC."""
    issues = list(stdout_issues)
    discover, issue = _response_result(responses, 1, "server/discover")
    if issue is not None or discover is None:
        issues.append(issue or "server/discover: missing result object.")
    else:
        issues.extend(_mcp_apps_capability_issues(discover, surface="subprocess server/discover"))

    initialized, issue = _response_result(responses, 2, "initialize")
    if issue is not None or initialized is None:
        issues.append(issue or "initialize: missing result object.")
    else:
        issues.extend(_mcp_apps_capability_issues(initialized, surface="subprocess initialize"))

    tools_result, issue = _response_result(responses, 3, "tools/list")
    if issue is not None or tools_result is None:
        issues.append(issue or "tools/list: missing result object.")
        tools: Any = []
    else:
        tools = tools_result.get("tools")
        issues.extend(_cacheable_result_issues(tools_result, method="tools/list"))

    resources_result, issue = _response_result(responses, 4, "resources/list")
    if issue is not None or resources_result is None:
        issues.append(issue or "resources/list: missing result object.")
        resources: Any = []
    else:
        resources = resources_result.get("resources")
        issues.extend(_cacheable_result_issues(resources_result, method="resources/list"))

    advertised_ui_uris = (
        {
            resource["uri"]
            for resource in resources
            if isinstance(resource, dict)
            and isinstance(resource.get("uri"), str)
            and resource["uri"].startswith("ui://")
        }
        if isinstance(resources, list)
        else set()
    )
    issues.extend(
        f"subprocess resources/list omitted registered or linked UI URI {uri!r}. "
        f"Fix: register {uri!r} with cli.ui_resource() and expose it after negotiation."
        for uri in read_ids
        if uri not in advertised_ui_uris
    )

    def read_resource(uri: str) -> dict[str, Any]:
        request_id = read_ids.get(uri)
        if request_id is None:
            raise ValueError(
                f"resources/list advertised unexpected UI URI {uri!r}; "
                "register UI resources before starting the MCP transport"
            )
        result, response_issue = _response_result(
            responses,
            request_id,
            f"resources/read {uri}",
        )
        if response_issue:
            raise ValueError(response_issue)
        if result is None:  # pragma: no cover - narrowed by response_issue
            raise ValueError(f"resources/read {uri}: missing result")
        cache_issues = _cacheable_result_issues(result, method=f"resources/read {uri}")
        if cache_issues:
            raise ValueError("; ".join(cache_issues))
        return result

    view_issues, link_count, resource_count, read_count = _mcp_apps_view_issues(
        tools,
        resources,
        surface="subprocess",
        read_resource=read_resource,
    )
    issues.extend(view_issues)
    if issues:
        if stderr_excerpt:
            issues.append(f"subprocess stderr: {stderr_excerpt}")
        return _failed_conformance("mcp_apps_transport", issues)
    return VerifyCheck(
        name="mcp_apps_transport",
        status="ok",
        message=(
            f"{link_count} tool link(s) and {resource_count} UI resource(s) agree over JSON-RPC; "
            f"{read_count} resource(s) readable"
        ),
    )
