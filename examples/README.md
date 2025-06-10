# async-cassandra Examples

This directory contains examples demonstrating how to use async-cassandra in various scenarios.

## Available Examples

### 1. [FastAPI Integration](fastapi_app/)

A complete REST API example showing:
- Async CRUD operations
- Connection pooling and lifecycle management
- Performance benchmarking endpoints
- Error handling best practices
- Docker/Podman support for Cassandra

To run:
```bash
cd fastapi_app
./start-cassandra.sh  # Start Cassandra with Docker/Podman
pip install -r requirements.txt
python main.py
```

### 2. Basic Usage (Coming Soon)

Simple examples demonstrating:
- Basic connection and queries
- Prepared statements
- Batch operations
- Error handling

### 3. Advanced Patterns (Coming Soon)

Advanced usage patterns:
- Connection monitoring
- Rate limiting
- Circuit breakers
- Retry strategies

## Running the Examples

All examples require:
1. Python 3.8+
2. A running Cassandra instance (2.1+ recommended)
3. Installation of async-cassandra:
   ```bash
   pip install async-cassandra
   ```

## Contributing Examples

We welcome example contributions! Please ensure your examples:
- Include clear documentation
- Follow the project's coding standards
- Include error handling
- Are tested and working

## Questions?

- GitHub Issues: https://github.com/axonops/async-python-cassandra/issues
- Email: community@axonops.com
- Website: https://axonops.com