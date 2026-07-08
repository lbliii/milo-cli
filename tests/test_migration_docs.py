from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATE_DIR = _REPO_ROOT / "site" / "content" / "docs" / "get-started" / "migrate-existing-cli"
_INDEX = _MIGRATE_DIR / "_index.md"
_FRAMEWORK_GUIDE = _MIGRATE_DIR / "framework-adoption.md"


def _recipe_pages() -> list[Path]:
    return sorted(path for path in _MIGRATE_DIR.glob("from-*.md") if path.name != "_index.md")


def test_migration_index_links_all_recipe_pages():
    index = _INDEX.read_text(encoding="utf-8")
    missing = [
        path.stem
        for path in _recipe_pages()
        if f"docs/get-started/migrate-existing-cli/{path.stem}" not in index
    ]
    assert not missing, f"Migration index does not link recipe page(s): {missing}"


def test_migration_recipes_include_source_mapping_and_watchouts():
    missing: dict[str, list[str]] = {}
    for path in _recipe_pages():
        text = path.read_text(encoding="utf-8")
        required = {
            "official reference": "Official reference" in text or "Official references" in text,
            "mapping": "## Mapping" in text,
            "watchouts": "## What To Watch" in text,
        }
        failed = [name for name, ok in required.items() if not ok]
        if failed:
            missing[path.name] = failed

    assert not missing


def test_migration_index_links_official_sources():
    text = _INDEX.read_text(encoding="utf-8")
    expected = [
        "https://docs.python.org/3/library/argparse.html",
        "https://click.palletsprojects.com/en/stable/commands-and-groups/",
        "https://typer.tiangolo.com/tutorial/first-steps/",
        "https://google.github.io/python-fire/guide/",
        "https://cobra.dev/docs/tutorials/getting-started/",
    ]
    missing = [url for url in expected if url not in text]
    assert not missing, f"Migration index is missing official source URL(s): {missing}"


def test_framework_adoption_guide_covers_the_release_gate_with_public_apis():
    text = _FRAMEWORK_GUIDE.read_text(encoding="utf-8")

    required = [
        "Freeze the compatibility inventory",
        "CLI.lazy_command",
        "terminal_renderer",
        'surfaces=("cli",)',
        "Context",
        "exit `0`/`1`/`2`",
        "MCPClient",
        "generate_llms_txt",
        "milo verify",
        "PYTHON_GIL=0",
        "Option(aliases=...)",
        "exact released versions",
        "Chirp issue #572",
    ]
    missing = [item for item in required if item not in text]
    assert not missing, f"Framework adoption guide omitted: {missing}"
    assert "from milo.mcp import _call_tool" not in text
    assert "argparse.Namespace" in text
    assert "do not pass an `argparse.namespace`" in text.lower()


def test_migration_index_and_readme_link_the_framework_guide():
    index = _INDEX.read_text(encoding="utf-8")
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "migrate-existing-cli/framework-adoption" in index
    assert "mature-CLI adoption guide" in readme
