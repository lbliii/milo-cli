# Milo CLI — development tasks (Python 3.14t, uv)

PYTHON_VERSION ?= 3.14t
VENV_DIR ?= .venv

.PHONY: all help setup install test test-cov showcase-test chirp-canary lint format ty bench docs-test ci clean build release-status gh-release changelog changelog-draft

all: help

help:
	@echo "milo-cli development"
	@echo "===================="
	@echo "Python: $(PYTHON_VERSION)"
	@echo ""
	@echo "  make setup     - uv venv with $(PYTHON_VERSION)"
	@echo "  make install   - uv sync --group dev"
	@echo "  make test      - pytest (tests/ only)"
	@echo "  make test-cov  - pytest + coverage (fail under 80%)"
	@echo "  make showcase-test - Waypoint tests + Milo verifier"
	@echo "  make chirp-canary - exact released Milo/Chirp downstream contract"
	@echo "  make bench     - pytest-benchmark (benchmarks/)"
	@echo "  make lint      - ruff check"
	@echo "  make format    - ruff format"
	@echo "  make ty        - ty type checker"
	@echo "  make ci        - lint + format check + ty + tests + coverage"
	@echo "  make docs-test - verify templates and tagged docs snippets"
	@echo "  make clean     - remove build artifacts"
	@echo "  make build     - uv build"
	@echo "  make release-status - verify release version/tag/changelog alignment"
	@echo "  make changelog  - compile changelog.d/ fragments into CHANGELOG.md"
	@echo "  make changelog-draft - preview changelog without writing"
	@echo "  make gh-release - create GitHub release → triggers PyPI publish"

setup:
	uv venv --python $(PYTHON_VERSION) $(VENV_DIR)

install:
	uv sync --group dev

test:
	PYTHON_GIL=0 uv run pytest tests/ -q --tb=short --timeout=120

test-cov:
	PYTHON_GIL=0 uv run pytest tests/ -q --tb=short --timeout=120 \
		--cov=milo --cov-report=term-missing --cov-fail-under=80

bench:
	PYTHON_GIL=0 uv run pytest benchmarks/ --benchmark-only -q

docs-test:
	uv run python scripts/check_templates.py
	uv run python scripts/check_docs_snippets.py

showcase-test:
	PYTHON_GIL=0 uv run pytest tests/test_waypoint*.py -q --tb=short --timeout=120
	uv run milo verify showcase/waypoint/app.py

chirp-canary:
	PYTHON_GIL=0 uv run --no-project --isolated --python 3.14t \
		--with milo-cli==0.4.1 --with bengal-chirp==0.10.0 \
		python scripts/check_chirp_canary.py --require-free-threaded

lint:
	uv run ruff check src/ tests/ benchmarks/ showcase/waypoint/

format:
	uv run ruff format src/ tests/ benchmarks/ showcase/waypoint/

ty:
	uv run ty check src/milo/

ci: lint
	uv run ruff format src/ tests/ benchmarks/ showcase/waypoint/ --check
	$(MAKE) ty
	$(MAKE) test-cov
	$(MAKE) showcase-test

clean:
	rm -rf dist/ .pytest_cache .coverage coverage.xml htmlcov/

build:
	uv build

release-status:
	uv run python scripts/release_status.py --remote

changelog:
	uv run towncrier build --yes

changelog-draft:
	uv run towncrier build --draft

# Create GitHub release from site release notes; triggers python-publish workflow → PyPI
# Strips YAML frontmatter (--- ... ---) from notes before passing to gh
gh-release:
	uv run python scripts/release_status.py --remote --pypi
	@VERSION=$$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	PROJECT=$$(grep -m1 '^name = ' pyproject.toml | sed 's/name = "\(.*\)"/\1/'); \
	NOTES="site/content/releases/$$VERSION.md"; \
	if [ ! -f "$$NOTES" ]; then echo "Error: $$NOTES not found"; exit 1; fi; \
	echo "Creating release v$$VERSION for $$PROJECT..."; \
	git push origin main 2>/dev/null || true; \
	git push origin v$$VERSION 2>/dev/null || true; \
	awk '/^---$$/{c++;next}c>=2' "$$NOTES" | gh release create v$$VERSION \
		--title "$$PROJECT $$VERSION" \
		-F -; \
	echo "✓ GitHub release v$$VERSION created (PyPI publish will run via workflow)"
