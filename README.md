# async-python-cassandra

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/axonops/async-python-cassandra/actions/workflows/tests.yml/badge.svg)](https://github.com/axonops/async-python-cassandra/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/axonops/async-python-cassandra/branch/main/graph/badge.svg)](https://codecov.io/gh/axonops/async-python-cassandra)

> ⚠️ **DEVELOPMENT WARNING**: This library is currently under active development and is NOT ready for production use. APIs may change without notice. Please use for testing and evaluation only.

## ✨ Overview

An async Python wrapper for the Cassandra Python driver that provides true asynchronous operations, addressing the performance limitations of the official driver when used with async frameworks like FastAPI.

The official Cassandra Python driver uses a separate thread pool for I/O operations, which can become a bottleneck in high-concurrency async applications. This library wraps the driver's async functionality to provide proper async/await support that integrates seamlessly with Python's asyncio event loop.

## 🚀 Key Features

- ✅ True async/await support for Cassandra operations
- ✅ Optimized for the Python driver's connection model
- ✅ Automatic retries with configurable policies
- ✅ Support for prepared statements and batch operations
- ✅ Type hints and full typing support
- ✅ Compatible with FastAPI, aiohttp, and other async frameworks
- ✅ Comprehensive test coverage including integration tests
- ✅ Performance optimized for high-concurrency scenarios


## 📋 Requirements

- Python 3.12 or higher
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

### 🔄 True Async Paging

The standard Cassandra driver's manual paging (`fetch_next_page()`) is synchronous, which blocks your entire async application:

```python
# ❌ With standard driver - blocks the event loop
result = await session.execute("SELECT * FROM large_table")
while result.has_more_pages:
    result.fetch_next_page()  # This blocks! Your app freezes here

# ✅ With async-cassandra streaming - truly async
result = await session.execute_stream("SELECT * FROM large_table")
async for row in result:
    await process_row(row)  # Non-blocking, other requests keep flowing
```

This is critical for web applications where blocking the event loop means all other requests stop being processed. For a detailed explanation of this issue, see our [streaming documentation](docs/streaming.md#the-async-problem-with-manual-paging).

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
- **Community**: For questions and discussions, visit our [GitHub Discussions](https://github.com/axonops/async-python-cassandra/discussions)
- **Company**: Learn more about AxonOps at [https://axonops.com](https://axonops.com)

## 📖 Documentation

### Getting Started
- [Getting Started Guide](docs/getting-started.md) - **Start here!**
- [API Reference](docs/api.md) - Detailed API documentation
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

### Advanced Topics
- [Connection Pooling Guide](docs/connection-pooling.md) - Understanding Python driver limitations
- [Performance Guide](docs/performance.md) - Optimization tips and benchmarks
- [Streaming Large Result Sets](docs/streaming.md) - Efficiently handle large datasets
- [Retry Policies](docs/retry-policies.md) - Why we have our own retry policy
- [Metrics and Monitoring](docs/metrics-monitoring.md) - Track performance and health
- [Architecture Overview](docs/architecture.md) - Technical deep dive

### Examples
- [FastAPI Integration](examples/fastapi_app/README.md) - Complete REST API example
- [More Examples](examples/) - Additional usage patterns

## ⚡ Performance

async-cassandra is designed to handle high-concurrency scenarios efficiently by leveraging Python's async/await capabilities and eliminating thread pool bottlenecks. The actual performance improvements will depend on your specific use case, query patterns, and Cassandra cluster configuration.

For performance optimization tips, see our [Performance Guide](docs/performance.md).

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- DataStax for the [Python Driver for Apache Cassandra](https://github.com/datastax/python-driver)
- The Python asyncio community for inspiration and best practices
- All contributors who help make this project better

## ⚖️ Legal Notices

*This project may contain trademarks or logos for projects, products, or services. Any use of third-party trademarks or logos are subject to those third-party's policies.*

- **AxonOps** is a registered trademark of AxonOps Limited.
- **Apache**, **Apache Cassandra**, **Cassandra**, **Apache Spark**, **Spark**, **Apache TinkerPop**, **TinkerPop**, **Apache Kafka** and **Kafka** are either registered trademarks or trademarks of the Apache Software Foundation or its subsidiaries in Canada, the United States and/or other countries.
- **DataStax** is a registered trademark of DataStax, Inc. and its subsidiaries in the United States and/or other countries.

### Copyright

This project is an independent work and has not been authorized, sponsored, or otherwise approved by the Apache Software Foundation or DataStax, Inc.

### License Compliance

This project uses the Apache License 2.0, which is compatible with the Apache Cassandra project. We acknowledge and respect all applicable licenses of dependencies used in this project.
