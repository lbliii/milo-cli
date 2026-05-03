from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCS_DIR = _REPO_ROOT / "site" / "content" / "docs"


def test_docs_top_level_sections_match_reader_intent_model():
    sections = sorted(
        path.name for path in _DOCS_DIR.iterdir() if path.is_dir() and not path.name.startswith(".")
    )

    assert sections == [
        "about",
        "applied-tutorials",
        "build-apps",
        "build-clis",
        "examples",
        "get-started",
        "quality",
        "reference",
    ]


def test_old_feature_bucket_sections_do_not_return():
    retired = ["migrate", "tutorials", "usage"]
    existing = [name for name in retired if (_DOCS_DIR / name).exists()]

    assert not existing, f"Retired docs section(s) should stay removed: {existing}"


def _local_card_links(path: Path) -> list[str]:
    links: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(":link:"):
            target = stripped.removeprefix(":link:").strip()
            if not target.startswith(("http://", "https://", "#")):
                links.append(target)
    return links


def _resolve_card_link(source: Path, target: str) -> Path:
    base = source.parent
    clean_target = target.split("#", 1)[0].rstrip("/")
    resolved = (base / clean_target).resolve()

    if resolved.is_dir():
        return resolved / "_index.md"
    if resolved.suffix:
        return resolved
    return resolved.with_suffix(".md")


def test_local_card_links_resolve_to_existing_docs_pages():
    missing: dict[str, list[str]] = {}
    for path in sorted(_DOCS_DIR.rglob("*.md")):
        for target in _local_card_links(path):
            resolved = _resolve_card_link(path, target)
            if not resolved.exists():
                missing.setdefault(str(path.relative_to(_REPO_ROOT)), []).append(target)

    assert not missing
