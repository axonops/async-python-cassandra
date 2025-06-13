.PHONY: help install install-dev test test-quick test-core test-critical test-progressive test-all test-unit test-integration test-integration-keep test-stress test-bdd lint format type-check build clean container-start container-stop container-status

help:
	@echo "Available commands:"
	@echo ""
	@echo "Installation:"
	@echo "  install        Install the package"
	@echo "  install-dev    Install with development dependencies"
	@echo ""
	@echo "Quick Test Commands (New):"
	@echo "  test-quick     Run quick validation tests (~30s)"
	@echo "  test-core      Run core functionality tests only (~1m)"
	@echo "  test-critical  Run critical tests (core + FastAPI) (~2m)"
	@echo "  test-progressive Run tests in fail-fast order"
	@echo ""
	@echo "Test Suites:"
	@echo "  test           Run all tests (excluding stress tests)"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests (auto-manages containers)"
	@echo "  test-integration-keep Run integration tests (keeps containers running)"
	@echo "  test-stress    Run stress tests"
	@echo "  test-bdd       Run BDD acceptance tests"
	@echo "  test-all       Run ALL tests (unit, integration, stress, and BDD)"
	@echo ""
	@echo "Test Categories:"
	@echo "  test-resilience Run error handling and resilience tests"
	@echo "  test-features  Run advanced feature tests"
	@echo "  test-fastapi   Run FastAPI integration tests"
	@echo "  test-performance Run performance and benchmark tests"
	@echo ""
	@echo "Container Management:"
	@echo "  container-start Start Cassandra container manually"
	@echo "  container-stop  Stop Cassandra container"
	@echo "  container-status Check if Cassandra container is running"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Run linters"
	@echo "  format         Format code"
	@echo "  type-check     Run type checking"
	@echo ""
	@echo "Build:"
	@echo "  build          Build distribution packages"
	@echo "  clean          Clean build artifacts"
	@echo ""
	@echo "Environment variables:"
	@echo "  SKIP_INTEGRATION_TESTS=1  Skip integration tests"
	@echo "  KEEP_CONTAINERS=1         Keep containers running after tests"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,test]"
	pre-commit install

# Quick validation (30s)
test-quick:
	@echo "Running quick validation tests..."
	pytest tests/_core -v --fail-fast -m "quick"

# Core tests only (1m)
test-core:
	@echo "Running core functionality tests..."
	pytest tests/_core tests/_resilience -v --fail-fast

# Critical path (per CLAUDE.md)
test-critical:
	@echo "Running critical tests (including FastAPI)..."
	pytest tests/_core -v --fail-fast -m "critical"
	pytest tests/fastapi -v
	cd examples/fastapi_app && pytest tests/ -v
	pytest tests/bdd -m "critical" -v

# Progressive execution
test-progressive:
	@echo "Running tests in fail-fast order..."
	@pytest tests/_core -v --fail-fast || exit 1
	@pytest tests/_resilience -v --fail-fast || exit 1
	@pytest tests/_features -v || exit 1
	@pytest tests/integration -v || exit 1
	@pytest tests/fastapi -v || exit 1
	@pytest tests/bdd -m "critical" -v || exit 1

# Test suite commands
test-resilience:
	@echo "Running resilience tests..."
	pytest tests/_resilience -v

test-features:
	@echo "Running feature tests..."
	pytest tests/_features -v

test-fastapi:
	@echo "Running FastAPI integration tests..."
	pytest tests/fastapi -v
	cd examples/fastapi_app && pytest tests/ -v

test-performance:
	@echo "Running performance tests..."
	pytest tests/performance -v

# BDD tests
test-bdd:
	@echo "Running BDD acceptance tests..."
	pytest tests/bdd -v --cucumber-json=reports/bdd.json

# Legacy test commands (for compatibility)
test:
	pytest tests/ -v -m "not stress"

test-unit:
	pytest tests/unit/ tests/_core/ tests/_resilience/ tests/_features/ -v --cov=async_cassandra --cov-report=html

test-integration:
	@echo "Running integration tests with automatic container management..."
	pytest tests/integration/ -v -m integration
	@echo "Integration tests completed."

test-integration-keep:
	@echo "Running integration tests (keeping containers after tests)..."
	KEEP_CONTAINERS=1 pytest tests/integration/ -v -m integration
	@echo "Integration tests completed. Containers are still running."

test-stress:
	@echo "Running stress tests..."
	pytest tests/integration/ tests/performance/ -v -m stress
	@echo "Stress tests completed."

# Full test suite
test-all: lint
	@echo "Running complete test suite..."
	$(MAKE) test-progressive
	pytest tests/performance -v
	pytest tests/bdd -v

# Code quality
lint:
	ruff check src/ tests/
	black --check src/ tests/
	isort --check-only src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

# Build
build:
	python -m build

# Container management
container-start:
	@echo "Starting test containers..."
	@cd tests/integration && python container_manager.py start

container-stop:
	@echo "Stopping test containers..."
	@cd tests/integration && python container_manager.py stop

container-status:
	@cd tests/integration && python container_manager.py status

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf reports/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete