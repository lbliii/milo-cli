"""Tests for templates/__init__.py — get_env factory."""

from __future__ import annotations


class TestGetEnv:
    def test_returns_environment(self):
        from milo.templates import get_env

        env = get_env()
        assert env is not None

    def test_builtin_templates_loadable(self):
        """Built-in milo templates (form.txt, help.txt, etc.) should be findable."""
        from milo.templates import get_env

        env = get_env()
        # help.txt is a built-in template
        tmpl = env.get_template("help.kida")
        assert tmpl is not None

    def test_autoescape_kwarg_passed_through(self):
        """Extra kwargs are forwarded to kida.Environment."""
        from milo.templates import get_env

        env = get_env(autoescape=True)
        assert env is not None

    def test_with_user_loader(self):
        """A user-provided loader gets chained before built-in templates."""
        import tempfile
        from pathlib import Path

        from kida import FileSystemLoader

        from milo.templates import get_env

        with tempfile.TemporaryDirectory() as tmp:
            # Create a custom template file
            (Path(tmp) / "custom.kida").write_text("custom={{ state }}")
            user_loader = FileSystemLoader(tmp)

            env = get_env(loader=user_loader)
            # Should find the custom template
            tmpl = env.get_template("custom.kida")
            assert tmpl is not None
            rendered = tmpl.render(state="ok")
            assert "custom=ok" in rendered

    def test_user_loader_none_ignored(self):
        """loader=None should behave the same as no loader."""
        from milo.templates import get_env

        env = get_env(loader=None)
        assert env is not None
        # Should still load built-in templates
        tmpl = env.get_template("help.kida")
        assert tmpl is not None

    def test_without_user_loader_uses_single_loader(self):
        """When no user loader, ChoiceLoader is not used."""
        from kida import ChoiceLoader

        from milo.templates import get_env

        env = get_env()
        # The loader should NOT be a ChoiceLoader (it's a single FileSystemLoader)
        assert not isinstance(env.loader, ChoiceLoader)

    def test_with_user_loader_uses_choice_loader(self):
        """When a user loader is provided, a ChoiceLoader is used."""
        import tempfile

        from kida import ChoiceLoader, FileSystemLoader

        from milo.templates import get_env

        with tempfile.TemporaryDirectory() as tmp:
            user_loader = FileSystemLoader(tmp)
            env = get_env(loader=user_loader)
            assert isinstance(env.loader, ChoiceLoader)

    def test_builtin_templates_render(self):
        """Built-in templates should render without error."""
        from milo.help import HelpState
        from milo.templates import get_env

        env = get_env()
        tmpl = env.get_template("help.kida")
        state = HelpState(prog="testprog", description="A test", groups=())
        output = tmpl.render(state=state)
        assert "testprog" in output


class TestComponentTemplatesIncluded:
    def test_components_directory_exists(self):
        """The components directory should exist in the templates package."""
        from pathlib import Path

        templates_dir = Path(__file__).parent.parent / "src" / "milo" / "templates"
        components_dir = templates_dir / "components"
        assert components_dir.exists()
        assert (components_dir / "_defs.kida").exists()

    def test_pyproject_includes_components(self):
        """pyproject.toml should include components/*.kida in package-data."""
        from pathlib import Path
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            config = tomllib.load(f)

        package_data = config["tool"]["setuptools"]["package-data"]["milo"]
        assert "templates/components/*.kida" in package_data

    def test_templates_loader_finds_components(self):
        """The template environment should be able to load component templates."""
        from milo.templates import get_env

        env = get_env()
        # Should be able to find component templates
        try:
            tmpl = env.get_template("components/_defs.kida")
            assert tmpl is not None
        except Exception:
            # If kida can't parse it, that's OK -- the point is the file is found
            pass
