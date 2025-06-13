"""
Configuration for acceptance tests.
"""

import sys
from pathlib import Path

# Add the examples directory to Python path so we can import the FastAPI app
examples_path = Path(__file__).parent.parent.parent / "examples"
sys.path.insert(0, str(examples_path))


def pytest_configure(config):
    """Configure pytest for acceptance tests."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "acceptance: mark test as an acceptance test following BDD patterns"
    )
