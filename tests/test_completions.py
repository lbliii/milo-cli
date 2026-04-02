"""Tests for the completions module."""

from __future__ import annotations

from milo.commands import CLI


class TestCompletionsModule:
    def test_generate_bash(self):
        from milo.completions import generate_bash_completion

        cli = CLI(name="myapp")

        @cli.command("test", description="Test")
        def test_cmd() -> str:
            return "ok"

        script = generate_bash_completion(cli)
        assert "_myapp_completions" in script
        assert "complete -F" in script

    def test_generate_zsh(self):
        from milo.completions import generate_zsh_completion

        cli = CLI(name="myapp")

        @cli.command("test", description="Test")
        def test_cmd() -> str:
            return "ok"

        script = generate_zsh_completion(cli)
        assert "#compdef myapp" in script

    def test_generate_fish(self):
        from milo.completions import generate_fish_completion

        cli = CLI(name="myapp")

        @cli.command("test", description="Test")
        def test_cmd() -> str:
            return "ok"

        script = generate_fish_completion(cli)
        assert "complete -c myapp" in script

    def test_install_completions_auto_detect(self):
        from milo.completions import install_completions

        cli = CLI(name="myapp")

        @cli.command("test", description="Test")
        def test_cmd() -> str:
            return "ok"

        # Should not crash regardless of $SHELL
        result = install_completions(cli)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_powershell(self):
        from milo.completions import generate_powershell_completion

        cli = CLI(name="myapp")

        @cli.command("test", description="Test")
        def test_cmd() -> str:
            return "ok"

        script = generate_powershell_completion(cli)
        assert "Register-ArgumentCompleter" in script
        assert "-CommandName 'myapp'" in script

    def test_install_completions_unsupported_shell(self):
        from milo.completions import install_completions

        cli = CLI(name="myapp")
        result = install_completions(cli, shell="nushell")
        assert "Unsupported shell" in result
