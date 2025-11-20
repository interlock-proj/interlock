.PHONY: format lint typecheck test test-unit test-integration quality check ci clean help

help:
	@echo "Available targets:"
	@echo "  format           - Auto-fix formatting and linting issues with Ruff"
	@echo "  lint             - Check code quality with Ruff"
	@echo "  typecheck        - Run mypy type checker"
	@echo "  test             - Run all tests with coverage"
	@echo "  test-unit        - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  quality          - Run lint and typecheck (no tests)"
	@echo "  check            - Run all quality checks and tests"
	@echo "  ci               - Full CI suite (same as check)"
	@echo "  clean            - Remove generated files"

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy interlock

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v

quality: lint typecheck
	@echo "✓ Code quality checks passed!"

check: quality test
	@echo "✓ All checks passed!"

ci: check
	@echo "✓ CI checks complete!"

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
