from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEDGER = _REPO_ROOT / "public-claims.json"
_COMPARISON_FIXTURES = _REPO_ROOT / "benchmarks" / "comparison"


def _claims() -> dict[str, dict[str, object]]:
    payload = json.loads(_LEDGER.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    return {claim["id"]: claim for claim in payload["claims"]}


def _source_lines(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_public_claims_have_unique_ids_and_existing_evidence():
    claims = _claims()
    raw_claims = json.loads(_LEDGER.read_text(encoding="utf-8"))["claims"]

    assert len(claims) == len(raw_claims)
    assert claims["parallel-http-tool-calls"]["status"] == "pending"
    assert claims["parallel-http-tool-calls"]["files"] == []

    for claim in raw_claims:
        for relative_path in [*claim["files"], *claim["evidence"]]:
            assert (_REPO_ROOT / relative_path).is_file(), (
                f"{claim['id']} references missing evidence {relative_path}"
            )


def test_public_claim_patterns_are_present_on_declared_surfaces():
    for claim in _claims().values():
        files = claim["files"]
        patterns = claim["patterns"]
        corpus = "\n".join(
            (_REPO_ROOT / relative_path).read_text(encoding="utf-8") for relative_path in files
        )

        for pattern in patterns:
            assert pattern in corpus, f"{claim['id']} lost declared pattern {pattern!r}"


def test_readme_public_claims_name_their_ledger_entries():
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "evidence: one-definition-three-surfaces" in readme
    assert "evidence: verify-ten-check-conformance" in readme
    assert "evidence: free-threaded-runtime" in readme
    assert "evidence: one-runtime-dependency" in readme


def test_same_app_line_counts_match_the_comparison_page():
    milo_lines = _source_lines(_COMPARISON_FIXTURES / "milo_app.py")
    composed_lines = _source_lines(_COMPARISON_FIXTURES / "typer_fastmcp_app.py")
    comparison = (_REPO_ROOT / "site" / "content" / "docs" / "about" / "comparisons.md").read_text(
        encoding="utf-8"
    )

    assert f"| Milo | `{milo_lines}` |" in comparison
    assert f"| Typer + FastMCP | `{composed_lines}` |" in comparison
    assert composed_lines > milo_lines
