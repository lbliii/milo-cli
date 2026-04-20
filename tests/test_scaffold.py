"""Tests for the project scaffold (`milo new`).

Three layers:
  1. Pure scaffold function — file layout, substitution, error handling.
  2. End-to-end roundtrip — scaffold + import + run + run scaffolded tests.
  3. CLI entry point — `milo new` invokes the scaffold and prints next steps.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from milo._scaffold import ScaffoldError, scaffold


class TestScaffoldFunction:
    def test_creates_expected_layout(self, tmp_path):
        project = scaffold("my_cli", tmp_path)
        assert project == tmp_path / "my_cli"
        assert (project / "app.py").is_file()
        assert (project / "conftest.py").is_file()
        assert (project / "tests" / "__init__.py").is_file()
        assert (project / "tests" / "test_app.py").is_file()
        assert (project / "README.md").is_file()

    def test_substitutes_name_placeholder(self, tmp_path):
        project = scaffold("my_cli", tmp_path)
        app = (project / "app.py").read_text()
        readme = (project / "README.md").read_text()
        assert 'CLI(name="my_cli"' in app
        assert "my_cli" in readme
        assert "{{name}}" not in app
        assert "{{name}}" not in readme

    @pytest.mark.parametrize(
        "bad_name",
        ["My-CLI", "1_cli", "foo bar", "", "FOO", "_leading_underscore"],
    )
    def test_rejects_invalid_names(self, bad_name, tmp_path):
        with pytest.raises(ScaffoldError, match="Invalid project name"):
            scaffold(bad_name, tmp_path)

    def test_refuses_to_overwrite_existing_dir(self, tmp_path):
        scaffold("my_cli", tmp_path)
        with pytest.raises(ScaffoldError, match="Refusing to overwrite"):
            scaffold("my_cli", tmp_path)

    def test_no_template_placeholders_in_default_tree(self):
        from milo._scaffold import _TEMPLATE_DIR

        for path in _TEMPLATE_DIR.rglob("*.py"):
            content = path.read_text()
            assert "TODO" not in content, f"{path} contains TODO"
            assert "FIXME" not in content, f"{path} contains FIXME"
            assert "XXX" not in content, f"{path} contains XXX"


class TestScaffoldRoundtrip:
    """Scaffold → import → dispatch → run scaffolded tests."""

    def test_scaffolded_app_imports_and_dispatches(self, tmp_path):
        project = scaffold("roundtrip_cli", tmp_path)

        spec = importlib.util.spec_from_file_location("roundtrip_app", project / "app.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.cli.name == "roundtrip_cli"
        result = module.cli.invoke(["greet", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello, Alice!" in result.output

    def test_scaffolded_llms_txt_lists_greet(self, tmp_path):
        project = scaffold("llms_cli", tmp_path)
        result = subprocess.run(
            [sys.executable, str(project / "app.py"), "--llms-txt"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert "**greet**" in result.stdout
        assert "**required**" in result.stdout

    def test_scaffolded_test_suite_passes(self, tmp_path):
        project = scaffold("test_run_cli", tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(project / "tests"), "-v"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (
            f"Scaffolded tests failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "7 passed" in result.stdout


class TestMiloNewCommand:
    def test_milo_new_creates_project_and_prints_next_steps(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "-m", "milo.cli", "new", "cli_cmd_test", "--dir", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert (tmp_path / "cli_cmd_test").is_dir()
        assert (tmp_path / "cli_cmd_test" / "app.py").is_file()
        assert "Next steps:" in result.stdout
        assert "cd " in result.stdout
        assert "uv run python app.py greet --name Alice" in result.stdout

    def test_milo_new_invalid_name_exits_nonzero_with_error(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "-m", "milo.cli", "new", "Bad-Name", "--dir", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 1
        assert "Invalid project name" in result.stderr
        assert not (tmp_path / "Bad-Name").exists()

    def test_milo_new_refuses_existing_target(self, tmp_path):
        (tmp_path / "exists").mkdir()
        result = subprocess.run(
            [sys.executable, "-m", "milo.cli", "new", "exists", "--dir", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 1
        assert "Refusing to overwrite" in result.stderr
