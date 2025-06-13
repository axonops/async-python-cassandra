# BDD Tests Status

The BDD tests are currently not fully implemented due to complexity with pytest-bdd and async functions.

## Issues:
1. pytest-bdd has limited support for async/await in step definitions
2. The existing step definitions need to be rewritten to work with pytest-bdd's fixture system
3. Complex fixture dependencies between steps need proper implementation

## TODO:
1. Rewrite step definitions to use synchronous wrappers around async code
2. Implement proper fixture sharing between steps
3. Create helper functions to handle async operations in BDD context
4. Consider using pytest-asyncio markers for async scenarios

## Temporary Solution:
The core functionality is thoroughly tested in:
- tests/_core/ - Core async wrapper tests
- tests/_resilience/ - Error handling and resilience tests  
- tests/_features/ - Advanced feature tests
- tests/unit/ - Comprehensive unit tests
- tests/fastapi/ - Integration tests with FastAPI

These tests provide comprehensive coverage of all functionality described in the BDD scenarios.