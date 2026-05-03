from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "check_docs_snippets.py"
_SPEC = importlib.util.spec_from_file_location("check_docs_snippets", _SCRIPT)
assert _SPEC is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
check_paths = _MODULE.check_paths


def test_tagged_shell_snippet_runs(tmp_path: Path):
    doc = tmp_path / "README.md"
    doc.write_text(
        """
```bash milo-docs:run
printf 'ok\\n'
```
""",
        encoding="utf-8",
    )

    assert check_paths([doc], repo_root=tmp_path) == []


def test_skip_snippet_requires_reason(tmp_path: Path):
    doc = tmp_path / "README.md"
    doc.write_text(
        """
```bash milo-docs:skip
external-service command
```
""",
        encoding="utf-8",
    )

    errors = check_paths([doc], repo_root=tmp_path)

    assert len(errors) == 1
    assert "requires reason" in errors[0]


def test_python_snippet_compile_errors_are_reported(tmp_path: Path):
    doc = tmp_path / "README.md"
    doc.write_text(
        """
```python milo-docs:compile
def nope(:
    pass
```
""",
        encoding="utf-8",
    )

    errors = check_paths([doc], repo_root=tmp_path)

    assert len(errors) == 1
    assert "Python snippet does not compile" in errors[0]


def test_missing_path_is_reported(tmp_path: Path):
    missing = tmp_path / "missing.md"
    errors = check_paths([missing], repo_root=tmp_path)

    assert len(errors) == 1
    assert "path does not exist" in errors[0]


def test_indented_tagged_fence_is_checked(tmp_path: Path):
    doc = tmp_path / "README.md"
    doc.write_text(
        """
   ```python milo-docs:compile
def nope(:
    pass
   ```
""",
        encoding="utf-8",
    )

    errors = check_paths([doc], repo_root=tmp_path)

    assert len(errors) == 1
    assert "Python snippet does not compile" in errors[0]
