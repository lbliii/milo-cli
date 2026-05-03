from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATE_DIR = _REPO_ROOT / "site" / "content" / "docs" / "migrate"
_INDEX = _MIGRATE_DIR / "_index.md"


def _recipe_pages() -> list[Path]:
    return sorted(path for path in _MIGRATE_DIR.glob("from-*.md") if path.name != "_index.md")


def test_migration_index_links_all_recipe_pages():
    index = _INDEX.read_text(encoding="utf-8")
    missing = [path.stem for path in _recipe_pages() if f"docs/migrate/{path.stem}" not in index]
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
