# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of async-python-cassandra
- AsyncCluster and AsyncCassandraSession for async/await support
- Streaming support for large result sets
- Connection monitoring and health checks
- Metrics collection (in-memory and Prometheus)
- Comprehensive test suite
- FastAPI integration example
- Full documentation

### Fixed
- Thread safety issues in async wrapper
- Memory leaks in streaming implementation
- Proper error propagation from driver to async layer

### Changed
- Improved connection pool management
- Better timeout handling
- Enhanced error messages

[Unreleased]: https://github.com/axonops/async-python-cassandra/compare/main...HEAD