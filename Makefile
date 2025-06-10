.PHONY: help install install-dev test test-unit test-integration lint format type-check build clean

help:
	@echo "Available commands:"
	@echo "  install        Install the package"
	@echo "  install-dev    Install with development dependencies"
	@echo "  test           Run all tests"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  lint           Run linters"
	@echo "  format         Format code"
	@echo "  type-check     Run type checking"
	@echo "  build          Build distribution packages"
	@echo "  clean          Clean build artifacts"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,test]"
	pre-commit install

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v --cov=async_cassandra --cov-report=html

test-integration:
	docker-compose -f tests/integration/docker-compose.yml up -d
	@echo "Waiting for Cassandra to start..."
	@sleep 30
	pytest tests/integration/ -v -m integration
	docker-compose -f tests/integration/docker-compose.yml down

lint:
	black --check src/ tests/
	isort --check-only src/ tests/
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

type-check:
	mypy src/

build:
	python -m build

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