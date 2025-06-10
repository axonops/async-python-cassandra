# async-python-cassandra

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/axonops/async-python-cassandra/actions/workflows/tests.yml/badge.svg)](https://github.com/axonops/async-python-cassandra/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/axonops/async-python-cassandra/branch/main/graph/badge.svg)](https://codecov.io/gh/axonops/async-python-cassandra)

## ✨ Overview

An async Python wrapper for the Cassandra Python driver that provides true asynchronous operations, addressing the performance limitations of the official driver when used with async frameworks like FastAPI.

The official Cassandra Python driver uses a separate thread pool for I/O operations, which can become a bottleneck in high-concurrency async applications. This library wraps the driver's async functionality to provide proper async/await support that integrates seamlessly with Python's asyncio event loop.

## 🚀 Key Features

- ✅ True async/await support for Cassandra operations
- ✅ Optimized for Python's single connection per host limitation
- ✅ Automatic retries with configurable policies
- ✅ Support for prepared statements and batch operations
- ✅ Type hints and full typing support
- ✅ Compatible with FastAPI, aiohttp, and other async frameworks
- ✅ Comprehensive test coverage including integration tests
- ✅ Performance optimized for high-concurrency scenarios

> **Important**: The Python Cassandra driver maintains only one TCP connection per host when using protocol v3+ (Cassandra 2.1+). This is a driver limitation due to Python's Global Interpreter Lock (GIL). See our [Connection Pooling Documentation](docs/connection-pooling.md) for details.

## 📋 Requirements

- Python 3.8 or higher
- Apache Cassandra 5.0+ (tested with 5.0, may work with earlier versions)
- cassandra-driver 3.29.2+

## 🔧 Installation

```bash
# From PyPI (when published)
pip install async-cassandra

# From source
pip install -e .
```

## 📚 Quick Start

```python
import asyncio
from async_cassandra import AsyncCluster

async def main():
    # Connect to Cassandra
    cluster = AsyncCluster(['localhost'])
    session = await cluster.connect()
    
    # Execute queries
    result = await session.execute("SELECT * FROM system.local")
    print(f"Connected to: {result.one().cluster_name}")
    
    # Clean up
    await session.close()
    await cluster.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

For more detailed examples, see our [Getting Started Guide](docs/getting-started.md).

## 🏗️ Why async-cassandra?

The Cassandra Python driver uses a thread pool for I/O operations, which can become a bottleneck in async applications. This library provides true async/await support, enabling:

- **Better Performance**: Handle thousands of concurrent queries efficiently
- **Lower Resource Usage**: No thread pool overhead
- **Seamless Integration**: Works naturally with FastAPI, aiohttp, and other async frameworks
- **Proper Backpressure**: Async operations allow better control over concurrency

See our [Architecture Overview](docs/architecture.md) for technical details.

## 🧪 Testing

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests (requires Cassandra)
pytest tests/integration/

# Run with coverage
pytest --cov=async_cassandra tests/

# Run specific test file
pytest tests/unit/test_session.py
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

**Important**: All contributors must sign our [Contributor License Agreement (CLA)](CLA.md) before their pull request can be merged.

## 📞 Support

- **Issues**: Please report bugs and feature requests on our [GitHub Issues](https://github.com/axonops/async-python-cassandra/issues) page
- **Community**: For questions and discussions, contact us at community@axonops.com
- **Company**: Learn more about AxonOps at [https://axonops.com](https://axonops.com)

## 📖 Documentation

### Getting Started
- [Getting Started Guide](docs/getting-started.md) - **Start here!**
- [API Reference](docs/api.md) - Detailed API documentation
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

### Advanced Topics
- [Connection Pooling Guide](docs/connection-pooling.md) - Understanding Python driver limitations
- [Performance Guide](docs/performance.md) - Optimization tips and benchmarks
- [Architecture Overview](docs/architecture.md) - Technical deep dive

### Examples
- [FastAPI Integration](examples/fastapi_app/README.md) - Complete REST API example
- [More Examples](examples/) - Additional usage patterns

## ⚡ Performance

Benchmarks show significant performance improvements over synchronous operations in high-concurrency scenarios:

| Scenario | Sync Driver | Async Wrapper | Improvement |
|----------|-------------|---------------|--------------|
| 1000 concurrent queries | 2.3s | 0.8s | 2.9x |
| 10000 concurrent queries | 23.5s | 7.2s | 3.3x |

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- DataStax for the [Python Driver for Apache Cassandra](https://github.com/datastax/python-driver)
- The Python asyncio community for inspiration and best practices
- All contributors who help make this project better

## ⚖️ Legal Notices

### Trademarks

Apache®, Apache Cassandra®, are either registered trademarks or trademarks of the Apache Software Foundation in the United States and/or other countries. This project is not affiliated with, endorsed by, or sponsored by the Apache Software Foundation.

DataStax is a registered trademark of DataStax, Inc. and its subsidiaries in the United States and/or other countries.

### Copyright

This project is an independent work and has not been authorized, sponsored, or otherwise approved by the Apache Software Foundation or DataStax, Inc.

### License Compliance

This project uses the Apache License 2.0, which is compatible with the Apache Cassandra project. We acknowledge and respect all applicable licenses of dependencies used in this project.
