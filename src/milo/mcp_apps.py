"""Typed contracts for the stable MCP Apps UI extension."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

MCP_APPS_EXTENSION_ID = "io.modelcontextprotocol/ui"
MCP_APPS_MIME_TYPE = "text/html;profile=mcp-app"

MCPAppVisibility = Literal["model", "app"]


def _tuplify(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value for value in normalized):
        raise ValueError("MCP Apps domain entries must be non-empty strings")
    return normalized


def _validate_ui_uri(uri: str) -> None:
    if not isinstance(uri, str) or not uri.startswith("ui://") or not uri[5:]:
        raise ValueError("MCP Apps resource URIs must use the non-empty 'ui://' scheme")


@dataclass(frozen=True, slots=True, init=False)
class MCPAppCSP:
    """Origins requested by an MCP App resource's Content Security Policy."""

    connect_domains: tuple[str, ...]
    resource_domains: tuple[str, ...]
    frame_domains: tuple[str, ...]
    base_uri_domains: tuple[str, ...]

    def __init__(
        self,
        connect_domains: tuple[str, ...] | list[str] = (),
        resource_domains: tuple[str, ...] | list[str] = (),
        frame_domains: tuple[str, ...] | list[str] = (),
        base_uri_domains: tuple[str, ...] | list[str] = (),
    ) -> None:
        object.__setattr__(self, "connect_domains", _tuplify(connect_domains))
        object.__setattr__(self, "resource_domains", _tuplify(resource_domains))
        object.__setattr__(self, "frame_domains", _tuplify(frame_domains))
        object.__setattr__(self, "base_uri_domains", _tuplify(base_uri_domains))


@dataclass(frozen=True, slots=True)
class MCPAppPermissions:
    """Browser capabilities requested by an MCP App resource."""

    camera: bool = False
    microphone: bool = False
    geolocation: bool = False
    clipboard_write: bool = False


@dataclass(frozen=True, slots=True)
class MCPAppResourceMeta:
    """Security and presentation metadata attached to an MCP App resource."""

    csp: MCPAppCSP | None = None
    permissions: MCPAppPermissions | None = None
    domain: str = ""
    prefers_border: bool | None = None


@dataclass(frozen=True, slots=True, init=False)
class MCPAppToolMeta:
    """Link an MCP tool to a UI resource and declare its visibility."""

    resource_uri: str
    visibility: tuple[MCPAppVisibility, ...]

    def __init__(
        self,
        resource_uri: str,
        visibility: tuple[MCPAppVisibility, ...] | list[MCPAppVisibility] = (
            "model",
            "app",
        ),
    ) -> None:
        _validate_ui_uri(resource_uri)
        normalized = tuple(dict.fromkeys(visibility))
        invalid = set(normalized) - {"model", "app"}
        if invalid or not normalized:
            values = ", ".join(sorted(invalid)) if invalid else "empty visibility"
            raise ValueError(f"Invalid MCP Apps tool visibility: {values}")
        object.__setattr__(self, "resource_uri", resource_uri)
        object.__setattr__(self, "visibility", normalized)


@dataclass(frozen=True, slots=True)
class MCPAppResourceDef:
    """A registered HTML resource for the MCP Apps extension."""

    uri: str
    name: str
    description: str
    handler: Callable[..., str | bytes]
    meta: MCPAppResourceMeta = MCPAppResourceMeta()
    mime_type: str = MCP_APPS_MIME_TYPE

    def __post_init__(self) -> None:
        _validate_ui_uri(self.uri)
        if self.mime_type != MCP_APPS_MIME_TYPE:
            raise ValueError(f"MCP Apps resources must use {MCP_APPS_MIME_TYPE!r}")


def _resource_meta_to_protocol(meta: MCPAppResourceMeta) -> dict[str, Any]:
    """Serialize immutable resource metadata with stable MCP field names."""
    ui: dict[str, Any] = {}
    if meta.csp is not None:
        csp: dict[str, Any] = {}
        mappings = (
            ("connectDomains", meta.csp.connect_domains),
            ("resourceDomains", meta.csp.resource_domains),
            ("frameDomains", meta.csp.frame_domains),
            ("baseUriDomains", meta.csp.base_uri_domains),
        )
        for key, values in mappings:
            if values:
                csp[key] = list(values)
        ui["csp"] = csp
    if meta.permissions is not None:
        permissions = {
            key: {}
            for key, requested in (
                ("camera", meta.permissions.camera),
                ("microphone", meta.permissions.microphone),
                ("geolocation", meta.permissions.geolocation),
                ("clipboardWrite", meta.permissions.clipboard_write),
            )
            if requested
        }
        ui["permissions"] = permissions
    if meta.domain:
        ui["domain"] = meta.domain
    if meta.prefers_border is not None:
        ui["prefersBorder"] = meta.prefers_border
    return {"ui": ui} if ui else {}


def _tool_meta_to_protocol(meta: MCPAppToolMeta) -> dict[str, Any]:
    """Serialize a tool-to-resource link using the stable nested shape."""
    return {
        "ui": {
            "resourceUri": meta.resource_uri,
            "visibility": list(meta.visibility),
        }
    }
