from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
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


def test_help_template_docs_mark_unpopulated_fields_as_reserved():
    text = (_DOCS_DIR / "build-clis" / "help.md").read_text(encoding="utf-8")
    assert "| `state.epilog` | `str` | Reserved; currently empty by default |" in text
    assert "| `state.usage` | `str` | Reserved; currently empty by default |" in text


def test_form_docs_match_the_bundled_select_indicator():
    forms = (_DOCS_DIR / "build-apps" / "forms.md").read_text(encoding="utf-8")
    templates = (_DOCS_DIR / "build-apps" / "templates.md").read_text(encoding="utf-8")
    assert "theme's check icon" in forms
    assert "themed check icon" in templates
    assert "`[x]` / `[ ]`" not in forms
    assert "`[x]` / `[ ]`" not in templates


def test_platform_data_paths_cover_unix_and_windows():
    commands = (_DOCS_DIR / "build-clis" / "commands.md").read_text(encoding="utf-8")
    mcp = (_DOCS_DIR / "build-clis" / "mcp.md").read_text(encoding="utf-8")

    assert "~/.milo/cache/" in commands
    assert "%LOCALAPPDATA%\\milo\\cache\\" in commands
    assert "~/.milo/registry.json" in mcp
    assert "%LOCALAPPDATA%\\milo\\registry.json" in mcp


def test_version_check_snippet_imports_sys_for_stderr():
    commands = (_DOCS_DIR / "build-clis" / "commands.md").read_text(encoding="utf-8")
    snippet = commands.split("## Version checking", maxsplit=1)[1]
    snippet = snippet.split("```", maxsplit=2)[1]
    assert "import sys" in snippet
    assert "file=sys.stderr" in snippet


def test_readme_front_door_is_clean_machine_and_verify_first():
    text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    front_door = text.split("## What is Milo?", maxsplit=1)[0]
    normalized = " ".join(front_door.split())

    assert "uvx --python 3.14 --from milo-cli milo new hello_milo" in front_door
    assert "--with milo-cli milo verify hello_milo/app.py" in front_door
    assert "claude mcp add --transport stdio hello_milo" in front_door
    assert front_door.index("milo verify") < front_door.index("claude mcp add")
    assert "Do not register a new tool until it reports zero failures" in normalized


def test_comparison_page_names_honest_decision_boundaries_and_sources():
    text = (_DOCS_DIR / "about" / "comparisons.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "What FastMCP and Typer Do Better" in text
    assert "Same Deploy App, Complete Entrypoints" in text
    assert "The Verification Difference" in text
    assert "https://gofastmcp.com/getting-started/welcome" in text
    assert "https://gofastmcp.com/cli/inspecting" in text
    assert "https://typer.tiangolo.com/" in text
    assert "not currently the broadest remote MCP platform" in normalized
    assert "Parallel HTTP Proof Is Still Pending" in text
    assert "issues/106" in text


def test_launch_assets_are_public_safe_and_share_one_demo_contract():
    post = (_REPO_ROOT / "docs" / "launch-post.md").read_text(encoding="utf-8")
    runbook = (_REPO_ROOT / "docs" / "launch-demo-script.md").read_text(encoding="utf-8")

    for text in (post, runbook):
        assert 'CLI(name="deployer"' in text
        assert 'annotations={"destructiveHint": True}' in text
        assert "milo verify" in text
        assert "/Users/" not in text

    assert "60 and 90 seconds" in runbook
    assert "same `app.py` path is used by Claude and the terminal" in runbook


def test_chirp_adoption_contract_is_source_pinned_and_executable():
    text = (_REPO_ROOT / "docs" / "chirp-adoption-contract.md").read_text(encoding="utf-8")

    assert "9d2279fc6f30b4b4c61e8bc658adf9296afd1e17" in text
    assert "eleven flat subcommands" in text
    assert "Nine of eleven commands use at least one positional" in text
    assert "tests/test_chirp_adoption_contract.py" in text
    assert "Positional and Option Presentation" in text
    assert "Per-Surface Command Visibility" in text
    assert "Lazy Resolution Must Fail Nonzero" in text
    assert "Root Version Contract" in text
    assert "Terminal Presentation Without Protocol Prints" in text
    assert "five generic contracts approved and implemented" in text
    assert "release required before downstream migration" in text
    assert "M-CMD-004" in text
