"""MCP 2026-07-28 release-candidate conformance and legacy parity."""

from __future__ import annotations

import pytest

from milo import CLI, Context
from milo._jsonrpc import (
    LEGACY_MCP_VERSION,
    MCP_CLIENT_CAPABILITIES_META_KEY,
    MCP_CLIENT_INFO_META_KEY,
    MCP_PROTOCOL_VERSION_META_KEY,
    MCP_VERSION,
    SUPPORTED_MCP_VERSIONS,
)
from milo._mcp_router import InvalidRequestMetadataError, MethodNotFoundError, dispatch
from milo.mcp import _classify_exception, _CLIHandler


def _modern_meta(*, capabilities: dict | None = None, **extra: str) -> dict:
    return {
        MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION,
        MCP_CLIENT_INFO_META_KEY: {"name": "conformance-client", "version": "1.0"},
        MCP_CLIENT_CAPABILITIES_META_KEY: capabilities or {},
        **extra,
    }


@pytest.fixture
def cli() -> CLI:
    app = CLI(name="conformance", description="MCP conformance fixture", version="1.0")

    @app.command("trace")
    def trace(ctx: Context = None) -> str:
        return ctx.globals["mcp"]["traceparent"]

    @app.resource("config://app")
    def config() -> str:
        return "ok"

    @app.prompt("review")
    def review() -> str:
        return "Review this"

    return app


def test_supported_versions_are_modern_first_with_legacy_fallback() -> None:
    assert MCP_VERSION == "2026-07-28"
    assert LEGACY_MCP_VERSION == "2025-11-25"
    assert SUPPORTED_MCP_VERSIONS == (MCP_VERSION, LEGACY_MCP_VERSION)


def test_legacy_initialize_and_requests_keep_legacy_shape(cli: CLI) -> None:
    handler = _CLIHandler(cli)

    initialized = dispatch(handler, "initialize", {"protocolVersion": LEGACY_MCP_VERSION})
    listed = dispatch(handler, "tools/list", {})

    assert initialized == {
        "protocolVersion": LEGACY_MCP_VERSION,
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "serverInfo": {
            "name": "conformance",
            "version": "1.0",
            "title": "MCP conformance fixture",
        },
        "instructions": "MCP conformance fixture",
    }
    assert "resultType" not in listed
    assert "ttlMs" not in listed
    assert "cacheScope" not in listed


@pytest.mark.parametrize("method", ["tools/list", "resources/list", "prompts/list"])
def test_modern_list_results_have_result_and_cache_metadata(cli: CLI, method: str) -> None:
    result = dispatch(_CLIHandler(cli), method, {"_meta": _modern_meta()})

    assert result is not None
    assert result["resultType"] == "complete"
    assert result["ttlMs"] >= 0
    assert result["cacheScope"] in {"public", "private"}


def test_modern_resource_read_is_private_and_immediately_stale(cli: CLI) -> None:
    result = dispatch(
        _CLIHandler(cli),
        "resources/read",
        {"uri": "config://app", "_meta": _modern_meta()},
    )

    assert result is not None
    assert result["resultType"] == "complete"
    assert result["ttlMs"] == 0
    assert result["cacheScope"] == "private"


def test_server_discover_advertises_both_eras_and_complete_result(cli: CLI) -> None:
    result = dispatch(_CLIHandler(cli), "server/discover", {"_meta": _modern_meta()})

    assert result is not None
    assert result["supportedVersions"] == [MCP_VERSION, LEGACY_MCP_VERSION]
    assert result["resultType"] == "complete"


def test_modern_requests_require_identity_and_capability_metadata(cli: CLI) -> None:
    params = {"_meta": {MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION}}

    with pytest.raises(InvalidRequestMetadataError) as caught:
        dispatch(_CLIHandler(cli), "tools/list", params)

    assert caught.value.missing == [MCP_CLIENT_INFO_META_KEY, MCP_CLIENT_CAPABILITIES_META_KEY]
    code, data = _classify_exception(caught.value)
    assert code == -32602
    assert data is not None
    assert data["missing"] == caught.value.missing


@pytest.mark.parametrize(
    ("meta", "invalid_field"),
    [
        (
            {
                MCP_CLIENT_INFO_META_KEY: {"name": "client", "version": "1.0"},
                MCP_CLIENT_CAPABILITIES_META_KEY: {},
            },
            MCP_PROTOCOL_VERSION_META_KEY,
        ),
        (
            {
                MCP_PROTOCOL_VERSION_META_KEY: MCP_VERSION,
                MCP_CLIENT_INFO_META_KEY: {"name": "client"},
                MCP_CLIENT_CAPABILITIES_META_KEY: {},
            },
            f"{MCP_CLIENT_INFO_META_KEY}.version",
        ),
    ],
)
def test_modern_request_metadata_rejects_incomplete_identity(
    cli: CLI,
    meta: dict,
    invalid_field: str,
) -> None:
    with pytest.raises(InvalidRequestMetadataError) as caught:
        dispatch(_CLIHandler(cli), "tools/list", {"_meta": meta})

    assert invalid_field in caught.value.missing


@pytest.mark.parametrize("method", ["initialize", "notifications/initialized"])
def test_modern_protocol_rejects_removed_handshake(cli: CLI, method: str) -> None:
    with pytest.raises(MethodNotFoundError, match="not part of modern MCP"):
        dispatch(
            _CLIHandler(cli),
            method,
            {"_meta": _modern_meta()},
        )


def test_trace_context_is_available_to_handler_context(cli: CLI) -> None:
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    result = dispatch(
        _CLIHandler(cli),
        "tools/call",
        {
            "name": "trace",
            "arguments": {},
            "_meta": _modern_meta(traceparent=traceparent, tracestate="vendor=value"),
        },
    )

    assert result is not None
    assert result["resultType"] == "complete"
    assert result["content"][0]["text"] == traceparent


def test_tool_order_is_deterministic(cli: CLI) -> None:
    @cli.command("second")
    def second() -> None:
        return None

    params = {"_meta": _modern_meta()}
    handler = _CLIHandler(cli)

    first = dispatch(handler, "tools/list", params)
    second_result = dispatch(handler, "tools/list", params)

    assert first is not None
    assert second_result is not None
    assert [tool["name"] for tool in first["tools"]] == ["trace", "second"]
    assert second_result["tools"] == first["tools"]
