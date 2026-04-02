"""Tests for CLI middleware integration."""

from __future__ import annotations

from milo.commands import CLI


class TestMiddlewareIntegration:
    def test_middleware_runs_in_run(self):
        """Middleware executes when a command is dispatched via CLI.run()."""
        log = []

        cli = CLI(name="test", description="test")

        @cli.middleware
        def logger(ctx, call, next_fn):
            log.append(f"before:{call.name}")
            result = next_fn(call)
            log.append(f"after:{call.name}")
            return result

        @cli.command("greet", description="Greet")
        def greet(name: str = "world") -> str:
            return f"Hello, {name}!"

        result = cli.invoke(["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "before:greet" in log
        assert "after:greet" in log

    def test_middleware_runs_in_call(self):
        """Middleware executes when a command is called programmatically."""
        log = []

        cli = CLI(name="test", description="test")

        @cli.middleware
        def logger(ctx, call, next_fn):
            log.append(f"called:{call.name}")
            return next_fn(call)

        @cli.command("add", description="Add numbers")
        def add(a: int = 0, b: int = 0) -> int:
            return a + b

        result = cli.call("add", a=1, b=2)
        assert result == 3
        assert "called:add" in log

    def test_call_provides_context_to_middleware(self):
        """CLI.call() provides a non-None Context to middleware."""
        ctx_seen = []

        cli = CLI(name="test", description="test")

        @cli.middleware
        def capture(ctx, call, next_fn):
            ctx_seen.append(ctx)
            return next_fn(call)

        @cli.command("noop", description="No-op")
        def noop() -> str:
            return "ok"

        cli.call("noop")
        assert len(ctx_seen) == 1
        assert ctx_seen[0] is not None

    def test_before_hook_error_handling(self):
        """Before-command hook errors are caught and exit with code 1."""
        cli = CLI(name="test", description="test")

        @cli.before_command
        def bad_hook(ctx, command_name, kwargs):
            raise RuntimeError("hook failed")

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hello"

        result = cli.invoke(["greet"])
        assert result.exit_code == 1
        assert "hook failed" in result.stderr

    def test_after_hook_error_handling(self):
        """After-command hook errors are caught (command still succeeds)."""
        cli = CLI(name="test", description="test")

        @cli.after_command
        def bad_hook(ctx, command_name, result):
            raise RuntimeError("after hook failed")

        @cli.command("greet", description="Greet")
        def greet() -> str:
            return "hello"

        result = cli.invoke(["greet"])
        # Command itself succeeded; hook error is logged
        assert "after hook failed" in result.stderr
