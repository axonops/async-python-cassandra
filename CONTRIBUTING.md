# Contributing to async-python-cassandra

First off, thank you for considering contributing to async-python-cassandra! It's people like you that make this project possible.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a branch** for your changes
4. **Make your changes** and commit them
5. **Push your changes** to your fork
6. **Submit a pull request**

## How Can I Contribute?

### 🐛 Reporting Bugs

Before creating bug reports, please check existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** to demonstrate the steps
- **Describe the behavior you observed**
- **Explain which behavior you expected to see instead**
- **Include Python version, Cassandra version, and OS**

### 💡 Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- **Use a clear and descriptive title**
- **Provide a step-by-step description** of the suggested enhancement
- **Provide specific examples** to demonstrate the steps
- **Describe the current behavior** and **explain which behavior you expected to see instead**
- **Explain why this enhancement would be useful**

### 🔧 Your First Code Contribution

Unsure where to begin contributing? You can start by looking through these issues:

- Issues labeled `good first issue`
- Issues labeled `help wanted`

## Development Setup

1. **Install Python 3.8+**
   ```bash
   python --version  # Should be 3.8 or higher
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the package in development mode**
   ```bash
   pip install -e ".[dev,test]"
   ```

4. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

5. **Run tests to ensure everything is working**
   ```bash
   pytest tests/unit/
   ```

## Pull Request Process

1. **Sign the CLA**: All contributors must sign our [Contributor License Agreement](CLA.md) before their PR can be merged.

2. **Update the documentation** with details of changes to the interface, new environment variables, new parameters, etc.

3. **Add tests** for any new functionality. Ensure all tests pass:
   ```bash
   pytest tests/
   ```

4. **Update the README.md** if necessary with details of changes to the API.

5. **Ensure your code follows our style guidelines** by running:
   ```bash
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   mypy src/
   ```

6. **Commit your changes** using clear and descriptive commit messages.

7. **Push your branch** to your fork and submit a pull request to the `main` branch.

8. **Wait for review**. The maintainers will review your PR and may suggest changes.

## Style Guidelines

### Python Style Guide

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with the following specifications:

- **Line length**: 100 characters
- **Use type hints** for all function signatures
- **Use docstrings** for all public modules, functions, classes, and methods
- **Use descriptive variable names**

### Code Formatting

We use the following tools to maintain code quality:

- **black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

Run all formatters with:
```bash
black src/ tests/
isort src/ tests/
```

### Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Example:
```
Add async batch execution support

- Implement BatchStatement async wrapper
- Add comprehensive tests for batch operations
- Update documentation with batch examples

Fixes #123
```

## Testing Guidelines

### Writing Tests

- Write unit tests for all new functionality
- Write integration tests for features that interact with Cassandra
- Use descriptive test names that explain what is being tested
- Use pytest fixtures for common test setup
- Mock external dependencies in unit tests

### Running Tests

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only integration tests (requires Cassandra)
pytest tests/integration/

# Run with coverage
pytest --cov=async_cassandra tests/

# Run specific test file
pytest tests/unit/test_session.py

# Run tests matching a pattern
pytest -k "test_async"
```

### Test Structure

```python
import pytest
from async_cassandra import AsyncCassandraSession


class TestAsyncCassandraSession:
    """Test cases for AsyncCassandraSession."""
    
    @pytest.fixture
    async def session(self):
        """Create a test session."""
        session = await AsyncCassandraSession.create(
            contact_points=['localhost']
        )
        yield session
        await session.close()
    
    async def test_execute_simple_query(self, session):
        """Test executing a simple query."""
        result = await session.execute("SELECT release_version FROM system.local")
        assert result is not None
```

## Documentation

### Docstring Format

We use Google-style docstrings:

```python
def execute_async(query: str, parameters: Optional[List] = None) -> Future[ResultSet]:
    """Execute a CQL query asynchronously.
    
    Args:
        query: The CQL query to execute.
        parameters: Optional list of parameters for the query.
    
    Returns:
        A Future that will contain the ResultSet when complete.
    
    Raises:
        CassandraException: If the query execution fails.
    
    Example:
        >>> result = await session.execute_async("SELECT * FROM users WHERE id = ?", [user_id])
        >>> for row in result:
        ...     print(row)
    """
```

### Updating Documentation

- Update docstrings for any changed functionality
- Update the relevant .md files in the `docs/` directory
- Add examples for new features
- Ensure all links work correctly

## Questions?

Feel free to open an issue with your question or reach out to the maintainers directly.

Thank you for contributing! 🎉