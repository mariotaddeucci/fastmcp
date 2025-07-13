# OpenAPI Server Implementation (Legacy)

This directory contains the legacy FastMCP server implementation for OpenAPI integration. This implementation manually constructs HTTP requests based on OpenAPI specifications.

## Architecture Overview

### Core Components

1. **`openapi.py`** - Main server implementation containing:
   - `FastMCPOpenAPI` server class
   - `OpenAPITool`, `OpenAPIResource`, `OpenAPIResourceTemplate` components
   - Manual HTTP request construction logic
   - Parameter collision handling (limited)

### Key Features

- **Manual Request Building**: Constructs HTTP requests using raw `httpx` calls
- **Basic Parameter Support**: Handles path, query, header, and body parameters
- **Limited Style Support**: Basic support for OpenAPI parameter styles
- **Schema Integration**: Integrates with FastMCP's schema system

### Data Flow

1. **OpenAPI Spec Parsing** → `/utilities/openapi.py` parses to `HTTPRoute` models
2. **Component Creation** → Creates MCP tools/resources from routes
3. **Request Handling** → Manual HTTP request construction in `OpenAPITool.run()`
4. **Response Processing** → Basic response handling and error mapping

### Limitations

#### Parameter Handling Issues
- **Collision Problems**: Limited handling of parameter name collisions between different locations (path, query, body)
- **DeepObject Support**: Manual implementation that may not cover all edge cases
- **Array Parameters**: Basic array handling with potential serialization issues

#### Maintenance Challenges
- **Manual Implementation**: All OpenAPI compliance manually coded
- **Bug-prone**: Easy to introduce parameter serialization bugs
- **Feature Gaps**: Missing support for many OpenAPI features
- **Test Coverage**: Difficult to test all parameter combinations

## Component Classes

### OpenAPITool
- Executes HTTP requests for OpenAPI operations
- Handles parameter extraction and formatting
- Maps HTTP responses to MCP tool results
- **Issues**: Parameter collision handling, complex parameter styles

### OpenAPIResource / OpenAPIResourceTemplate
- Provides read-only access to API resources
- Uses GET requests to fetch resource data
- **Issues**: Limited parameter support, no caching

## Key Functions

### Parameter Processing
- `_combine_schemas()` - Merges parameter schemas (collision-prone)
- Parameter extraction and formatting in `run()` methods
- Manual query string and request body construction

### Request Construction
- Manual URL building with path parameter substitution  
- Query parameter serialization
- Request body formatting
- Header management

## Known Issues

### 1. Parameter Collisions
**Problem**: When parameters have the same name in different locations (e.g., `id` in both path and request body), the current implementation excludes one of them.

**Example**:
```python
# API spec has: /users/{id} with body containing {"id": ...}
# Current behavior: body "id" is excluded, causing API errors
```

**Impact**: API calls fail due to missing required parameters

### 2. DeepObject Serialization
**Problem**: Manual implementation of deepObject style may not handle all edge cases correctly.

**Example**:
```python
# Should produce: ?target[id]=123&target[type]=org
# May produce incorrect serialization in some cases
```

### 3. Schema Combination Logic
**Problem**: `_combine_schemas()` has complex logic that's hard to maintain and debug.

**Issues**:
- Parameter precedence rules unclear
- Error handling incomplete
- Schema validation gaps

## Testing

Tests are located in `/tests/server/openapi/`:

### Test Coverage
- `test_parameter_collisions.py` - Documents collision issues
- `test_deepobject_style.py` - Tests deepObject parameter handling
- Basic request/response cycle tests

### Test Strategy
- Uses mocks for HTTP client interaction
- Focuses on parameter serialization correctness
- Tests error handling and edge cases

## Migration Path

### Why Migrate?
1. **Reduced Maintenance**: Offload OpenAPI compliance to `openapi-python-client`
2. **Better Coverage**: Support for all OpenAPI features
3. **Fewer Bugs**: Eliminate manual parameter serialization issues
4. **Future-proof**: Stay current with OpenAPI specification evolution

### Migration Steps
1. **Replace Imports**: Change from `server.openapi` to `server.openapi_new`
2. **Test Compatibility**: Verify existing functionality works
3. **Gradual Rollout**: Migrate services incrementally
4. **Monitor Performance**: Track any performance differences

### Backward Compatibility
- New implementation provides fallback to legacy behavior
- Same public API interface maintained
- Existing tests continue to pass

## Usage Guidelines

### Current Usage (Discouraged)
```python
from fastmcp.server.openapi import FastMCPOpenAPI

# This still works but is discouraged for new development
server = FastMCPOpenAPI(openapi_spec=spec, client=client)
```

### Recommended Migration
```python
from fastmcp.server.openapi_new import FastMCPOpenAPI

# New implementation with automatic callable generation
server = FastMCPOpenAPI(openapi_spec=spec, client=client)
```

## Deprecation Timeline

### Phase 1: Feature Freeze (Current)
- No new features added to legacy implementation
- Only critical bug fixes applied
- New development uses `openapi_new`

### Phase 2: Migration Period
- Encourage migration to new implementation
- Provide migration tooling and documentation
- Monitor usage patterns

### Phase 3: Deprecation
- Mark legacy implementation as deprecated
- Add deprecation warnings
- Update documentation to recommend new implementation

### Phase 4: Removal
- Remove legacy implementation after migration period
- Clean up deprecated code and tests

## Related Files

- `/utilities/openapi.py` - Core utilities used by this implementation
- `/server/openapi_new/` - New implementation replacing this one
- `/tests/server/openapi/` - Test suite for legacy implementation

## Support

For issues with the legacy implementation:
1. **Check Migration Path**: Can the issue be resolved by migrating to `openapi_new`?
2. **Critical Bugs Only**: Only critical production issues will be fixed
3. **Migration Assistance**: Focus on helping migrate to new implementation

For new development, use `/server/openapi_new/` instead.