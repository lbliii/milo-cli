# Milo CLI — development tasks (Python 3.14t, uv)

PYTHON_VERSION ?= 3.14t
VENV_DIR ?= .venv

.PHONY: all help setup install test test-cov lint format ty bench ci clean build

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
	@echo "  make bench     - pytest-benchmark (benchmarks/)"
	@echo "  make lint      - ruff check"
	@echo "  make format    - ruff format"
	@echo "  make ty        - ty type checker"
	@echo "  make ci        - lint + format check + ty + tests + coverage"
	@echo "  make clean     - remove build artifacts"
	@echo "  make build     - uv build"

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

lint:
	uv run ruff check src/ tests/ benchmarks/

format:
	uv run ruff format src/ tests/ benchmarks/

ty:
	uv run ty check src/milo/

ci: lint
	uv run ruff format src/ tests/ benchmarks/ --check
	$(MAKE) ty
	$(MAKE) test-cov

clean:
	rm -rf dist/ .pytest_cache .coverage coverage.xml htmlcov/

build:
	uv build
