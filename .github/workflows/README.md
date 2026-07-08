# Milo CI Reference Patterns

Milo's workflows are the stack reference for a hard branch-coverage gate, a
GIL-on/free-threaded control matrix, runtime GIL assertions, dual-OS proof, and
per-pull-request benchmark comparisons. Copy the pattern, then adapt package
names and honest thresholds to the target repository.

These exports implement Milo's rows in the cross-stack
[hygiene baseline](https://github.com/lbliii/pounce/blob/main/docs/design/stack-hygiene-baseline.md).

## Coverage and interpreter control

The canonical implementation is [`ci.yml`](ci.yml):

```yaml
strategy:
  matrix:
    include:
      - python-version: "3.14"
        python-gil: "1"
      - python-version: "3.14t"
        python-gil: "0"

env:
  PYTHON_GIL: ${{ matrix.python-gil }}

steps:
  - run: >-
      uv run pytest tests/ --cov=PACKAGE
      --cov-fail-under=80
  - env:
      EXPECTED_GIL: ${{ matrix.python-gil }}
    run: >-
      uv run python -c "import os, sys;
      expected = os.environ['EXPECTED_GIL'] == '1';
      assert sys._is_gil_enabled() is expected"
```

Keep branch coverage enabled in the repository coverage configuration and the
floor enforced in the CI command. Repositories below 80% should set an honest
measured floor and ratchet upward; they should not copy `80` and make the job
non-blocking. Keep a Python 3.14 GIL-on control because it represents most users
and distinguishes free-threading bugs from general bugs.

Milo runs Python 3.14t on Ubuntu and macOS and the ordinary 3.14 control on
Ubuntu. Coverage comments and uploads come from one canonical 3.14t Ubuntu job
so matrix jobs do not race to publish the same report.

## Benchmark receipts

[`benchmarks.yml`](benchmarks.yml) runs committed workloads, uploads the JSON
receipt, downloads the latest `main` artifact, and comments a comparison on the
pull request. Its thresholds are diagnostic: yellow above 5%, red above 20%.
Hardware-hosted CI noise means the comment is evidence for review, not a claim
that every flagged change is a regression.

The portable workflow shape is:

```yaml
- run: >-
    uv run pytest benchmarks/ --benchmark-only
    --benchmark-json=benchmark-results.json
- uses: actions/upload-artifact@v4
  with:
    name: benchmark-results-${{ github.sha }}
    path: benchmark-results.json
- if: github.event_name == 'pull_request'
  uses: dawidd6/action-download-artifact@v6
  with:
    workflow: benchmarks.yml
    branch: main
    name: benchmark-results-*
    path: baseline/
    if_no_artifact_found: warn
- if: github.event_name == 'pull_request'
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    # Produce comment-body.md from the baseline/current JSON pair first.
    gh pr comment "${{ github.event.pull_request.number }}" \
      --body-file comment-body.md
```

See the executable workflow for Milo's stable-name matching, percentage
calculation, missing-baseline behavior, and edit-or-create comment logic.

When porting the workflow:

1. keep workload names stable;
2. record interpreter, GIL state, platform, and baseline identity;
3. state thresholds and noise caveats;
4. never invent a baseline when no artifact exists; and
5. require a focused benchmark note for changes to a claimed hot path.

## Other gates

- [`changelog.yml`](changelog.yml) requires a towncrier fragment for
  user-visible pull requests.
- [`downstream-chirp.yml`](downstream-chirp.yml) demonstrates an isolated,
  exact-version downstream canary.
- [`pages.yml`](pages.yml) builds the public documentation site from source.

These files are the executable source of truth. Update this page when their
exported pattern changes.
