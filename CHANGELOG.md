# Changelog

All notable changes to async-cassandra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive Getting Started guide (`docs/getting-started.md`)
- Troubleshooting guide (`docs/troubleshooting.md`) with common issues and solutions
- Connection pooling documentation explaining Python driver limitations
- Connection monitoring utilities (`async_cassandra.monitoring`)
- Rate-limited session wrapper for connection protection
- Base classes to reduce code duplication (`async_cassandra.base`)
- Examples README for better navigation

### Changed
- Updated all organization references to AxonOps (GitHub, email, website)
- Restructured documentation for better user adoption
- Improved README with clearer structure and better onboarding
- Refactored cluster and session classes to use common base classes
- Removed redundant code through new abstractions
- Updated all references from "DataStax driver" to "Cassandra Python driver" (except in acknowledgments)

### Fixed
- Archive security improvements document to proper location
- Consistent error handling patterns across the codebase
- Proper idempotent close/shutdown operations with locking

### Security
- All security fixes from previous audit are maintained

## [0.1.0] - 2024-XX-XX

### Added
- Initial release of async-cassandra
- True async/await support for Cassandra operations
- Connection pooling optimized for async workloads
- Automatic retries with configurable policies
- Support for prepared statements and batch operations
- Type hints and full typing support
- FastAPI integration example
- Comprehensive test coverage (97%+)

### Security
- CQL injection prevention in `set_keyspace()`
- Thread-safe shutdown operations
- Proper exception handling for Cassandra-specific errors

[Unreleased]: https://github.com/axonops/async-python-cassandra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/axonops/async-python-cassandra/releases/tag/v0.1.0