"""Side-effect-free representative handlers loaded only after command selection."""

from __future__ import annotations

from typing import Any


def _result(command: str, values: dict[str, Any]) -> dict[str, Any]:
    return {"command": command, "status": "ok", **values}


def new(
    name: str,
    minimal: bool = False,
    stream: bool = False,
    sse: bool = False,
    shell: bool = False,
    ai: bool = False,
    with_chirpui: bool = False,
) -> dict[str, Any]:
    return _result("new", dict(locals()))


def run(
    app: str,
    host: str | None = None,
    port: int | None = None,
    production: bool = False,
    workers: int | None = None,
    metrics: bool = False,
    rate_limit: bool = False,
    queue: bool = False,
    sentry_dsn: str | None = None,
) -> dict[str, Any]:
    return _result("run", dict(locals()))


def dev(
    app: str,
    host: str | None = None,
    port: int | None = None,
    production: bool = False,
    workers: int | None = None,
    metrics: bool = False,
    rate_limit: bool = False,
    queue: bool = False,
    sentry_dsn: str | None = None,
) -> dict[str, Any]:
    return _result("dev", dict(locals()))


def check(
    app: str,
    warnings_as_errors: bool = False,
    coverage: bool = False,
    deploy: bool = False,
    json: bool = False,
    baseline: str | None = None,
    include_info: bool = False,
) -> dict[str, Any]:
    if app == "missing_canary_app:app":
        raise ValueError("Could not import missing_canary_app")
    return _result("check", dict(locals()))


def diff(
    app: str,
    base: str,
    json: bool = False,
    warnings_as_errors: bool = False,
    deploy: bool = False,
    include_info: bool = False,
) -> dict[str, Any]:
    return _result("diff", dict(locals()))


def routes(app: str) -> dict[str, Any]:
    return _result("routes", dict(locals()))


def security_check(app: str) -> dict[str, Any]:
    return _result("security-check", dict(locals()))


def freeze(app: str, output: str, exclude: list[str] | None = None) -> dict[str, Any]:
    return _result("freeze", dict(locals()))


def makemigrations(
    db: str,
    schema: str,
    migrations_dir: str = "migrations",
) -> dict[str, Any]:
    return _result("makemigrations", dict(locals()))


def migrate(db: str, migrations_dir: str = "migrations") -> dict[str, Any]:
    return _result("migrate", dict(locals()))


def shapes_codegen(
    path: str = ".",
    dry_run: bool = False,
    audit: bool = False,
    migrations: str = "migrations",
) -> dict[str, Any]:
    return _result("shapes-codegen", dict(locals()))
