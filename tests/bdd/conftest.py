"""Pytest configuration for BDD tests."""

import asyncio
import sys
from pathlib import Path

import pytest

from tests.bdd.steps.common_steps import *  # noqa: E402, F403
from tests.bdd.steps.given_steps import *  # noqa: E402, F403
from tests.bdd.steps.then_steps import *  # noqa: E402, F403
from tests.bdd.steps.when_steps import *  # noqa: E402, F403

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for async tests."""
    return "asyncio"


# BDD-specific configuration
def pytest_bdd_step_error(request, feature, scenario, step, step_func, step_func_args, exception):
    """Enhanced error reporting for BDD steps."""
    print(f"\n{'='*60}")
    print(f"STEP FAILED: {step.keyword} {step.name}")
    print(f"Feature: {feature.name}")
    print(f"Scenario: {scenario.name}")
    print(f"Error: {exception}")
    print(f"{'='*60}\n")


# Markers for BDD tests
def pytest_configure(config):
    """Configure custom markers for BDD tests."""
    config.addinivalue_line("markers", "bdd: mark test as BDD test")
    config.addinivalue_line("markers", "critical: mark test as critical for production")
    config.addinivalue_line("markers", "smoke: mark test as smoke test")
    config.addinivalue_line("markers", "concurrency: mark test as concurrency test")
    config.addinivalue_line("markers", "error_handling: mark test as error handling test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "resilience: mark test as resilience test")
    config.addinivalue_line("markers", "fastapi: mark test as FastAPI integration test")


# Automatically mark all BDD tests
def pytest_collection_modifyitems(items):
    """Automatically add markers to BDD tests."""
    for item in items:
        # Mark all tests in bdd directory
        if "bdd" in str(item.fspath):
            item.add_marker(pytest.mark.bdd)

        # Add markers based on tags in feature files
        if hasattr(item, "scenario"):
            for tag in item.scenario.tags:
                if hasattr(pytest.mark, tag.lstrip("@")):
                    marker = getattr(pytest.mark, tag.lstrip("@"))
                    item.add_marker(marker)
