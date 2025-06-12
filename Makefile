.PHONY: help install install-dev test test-unit test-integration test-integration-keep test-stress test-all lint format type-check build clean container-start container-stop container-status

help:
	@echo "Available commands:"
	@echo "  install        Install the package"
	@echo "  install-dev    Install with development dependencies"
	@echo "  test           Run all tests (excluding stress tests)"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests (auto-manages containers)"
	@echo "  test-integration-keep Run integration tests (keeps containers running)"
	@echo "  test-stress    Run stress tests"
	@echo "  test-all       Run ALL tests (unit, integration, and stress)"
	@echo "  container-start Start Cassandra container manually"
	@echo "  container-stop  Stop Cassandra container"
	@echo "  container-status Check if Cassandra container is running"
	@echo "  lint           Run linters"
	@echo "  format         Format code"
	@echo "  type-check     Run type checking"
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

test:
	pytest tests/ -v -m "not stress"

test-unit:
	pytest tests/unit/ -v --cov=async_cassandra --cov-report=html

test-integration:
	@echo "Running integration tests with automatic container management..."
	pytest tests/integration/ -v -m integration
	@echo "Integration tests completed."

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

build:
	python -m build

test-integration-keep:
	@echo "Running integration tests (keeping containers after tests)..."
	KEEP_CONTAINERS=1 pytest tests/integration/ -v -m integration
	@echo "Integration tests completed. Containers are still running."

test-stress:
	@echo "Running stress tests..."
	pytest tests/integration/ -v -m stress
	@echo "Stress tests completed."

test-all:
	@echo "Running all tests (unit, integration, and stress)..."
	make test-unit
	make test-integration
	make test-stress
	@echo "All tests completed."

container-start:
	@echo "Starting test containers..."
	@cd tests/integration && python container_manager.py start

container-stop:
	@echo "Stopping test containers..."
	@cd tests/integration && python container_manager.py stop

container-status:
	@cd tests/integration && python container_manager.py status

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete