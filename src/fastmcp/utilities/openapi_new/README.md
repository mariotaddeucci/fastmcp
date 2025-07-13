# OpenAPI Utilities (New Implementation)

This directory contains the next-generation OpenAPI integration utilities for FastMCP, designed to replace the legacy `openapi.py` implementation.

## Architecture Overview

The new implementation follows a **code generation strategy** using `openapi-python-client` to automatically generate callable functions from OpenAPI specifications, eliminating the need for manual HTTP request construction.

### Core Components

1. **`callables.py`** - `OASCallableFactory` for generating callable functions
2. **`parser.py`** - OpenAPI spec parsing and route extraction  
3. **`schemas.py`** - Schema processing and validation utilities
4. **`models.py`** - Data models and intermediate representations
5. **`formatters.py`** - Response formatting and processing utilities

### Key Architecture Principles

#### 1. Code Generation Strategy
- Uses `openapi-python-client` CLI to generate Python client code
- Extracts callable functions from generated client
- Offloads OpenAPI compliance to a robust, well-tested library

#### 2. Hybrid Approach  
- **Primary**: Use generated callables when available
- **Fallback**: Fall back to legacy HTTP request building for edge cases
- **Backward Compatibility**: Maintains compatibility with existing code

#### 3. Separation of Concerns
- **Callable Generation**: `OASCallableFactory` handles client generation
- **Component Integration**: Components in `/server/openapi_new/` handle MCP integration
- **Utility Functions**: Shared utilities for schema processing and formatting

## Data Flow

### Client Generation Process

```
OpenAPI Spec → OASCallableFactory → openapi-python-client CLI → Generated Client → Extracted Callables
```

1. **Input**: Raw OpenAPI specification (dict)
2. **Generation**: CLI generates Python client in temporary directory
3. **Import**: Dynamically import generated client module
4. **Extraction**: Extract callable functions by operation ID
5. **Binding**: Create bound callables with proper error handling

### Request Processing

```
MCP Tool Call → Callable Function → HTTP Request → API Response → Structured Output
```

1. **Tool Invocation**: FastMCP receives tool call with parameters
2. **Callable Execution**: Execute appropriate generated callable
3. **Response Processing**: Parse response into structured format
4. **Error Handling**: Convert HTTP errors to MCP-compatible formats

## Key Features

### 1. Automatic OpenAPI Compliance
- All parameter serialization handled by generated client
- Supports all OpenAPI parameter styles (form, deepObject, etc.)
- Automatic request body formatting
- Built-in response validation

### 2. Enhanced Error Handling
- HTTP status code mapping to MCP errors
- Structured error responses
- Timeout and connection error handling

### 3. Robust Parameter Handling
- **Parameter Collisions**: Automatic suffixing for name collisions
- **DeepObject Style**: Native support via generated client
- **Complex Schemas**: Handles nested objects and arrays
- **Validation**: Input validation via Pydantic models

### 4. Performance Optimizations
- **Caching**: Generated clients are cached
- **Async Support**: Full async/await support
- **Connection Pooling**: Reuses HTTP connections

## Component Integration

### Server Components (`/server/openapi_new/`)

1. **`CallableTool`** - Tool implementation using generated callables
2. **`CallableResource`** - Resource implementation using callables  
3. **`CallableResourceTemplate`** - Resource template with callables
4. **`FastMCPOpenAPI`** - Main server class with hybrid approach

### Fallback Strategy

When callables are not available:
- Falls back to legacy `OpenAPITool` implementation
- Maintains full backward compatibility
- Logs fallback usage for monitoring

## Usage Examples

### Basic Server Setup

```python
import httpx
from fastmcp.server.openapi_new import FastMCPOpenAPI

# OpenAPI spec (can be loaded from file/URL)
openapi_spec = {...}

# Create HTTP client
async with httpx.AsyncClient() as client:
    # Create server with automatic callable generation
    server = FastMCPOpenAPI(
        openapi_spec=openapi_spec,
        client=client,
        name="My API Server"
    )
    
    # Server automatically generates callables and creates tools
```

### Custom Callable Factory

```python
from fastmcp.utilities.openapi_new.callables import OASCallableFactory

# Generate callables manually
factory = OASCallableFactory(openapi_spec, base_url="https://api.example.com")
callables_map = factory.build()

# Use specific callable
get_user = callables_map.get("get_user")
if get_user:
    result = await get_user(user_id=123)
```

## Testing Strategy

Tests are located in `/tests/utilities/openapi_new/` and `/tests/server/openapi_new/`:

### Test Categories

1. **Unit Tests**
   - `test_callables.py` - Callable factory functionality
   - `test_components.py` - Component behavior with callables
   - `test_server.py` - Server integration and fallback logic

2. **Feature Tests**  
   - `test_parameter_collisions.py` - Parameter name collision handling
   - `test_deepobject_style.py` - DeepObject parameter style support
   - `test_openapi_features.py` - General OpenAPI feature support

### Testing Philosophy

- **Real Objects**: Use real Pydantic models and callable functions
- **Minimal Mocking**: Only mock external API calls
- **Behavioral Testing**: Focus on behavior rather than implementation details
- **Integration Focus**: Test complete request/response cycles

## Migration Guide

### From Legacy Implementation

1. **Import Changes**:
   ```python
   # Old
   from fastmcp.server.openapi import FastMCPOpenAPI
   
   # New  
   from fastmcp.server.openapi_new import FastMCPOpenAPI
   ```

2. **Constructor**: Same interface, no changes needed

3. **Automatic Benefits**: 
   - Better OpenAPI compliance
   - Fewer parameter serialization bugs
   - Support for more OpenAPI features

### Gradual Migration

- Both implementations can coexist
- Migrate individual services incrementally
- Fallback ensures no breaking changes

## Future Enhancements

### Planned Features

1. **Client Caching**: Persistent client generation caching
2. **Streaming Support**: Handle streaming responses
3. **Authentication**: Enhanced auth provider integration
4. **Metrics**: Request/response metrics and monitoring
5. **Validation**: Enhanced input/output validation

### Performance Improvements

1. **Lazy Generation**: Generate clients on-demand
2. **Parallel Generation**: Generate multiple clients concurrently
3. **Memory Optimization**: Optimize client storage and cleanup

## Troubleshooting

### Common Issues

1. **Client Generation Fails**
   - Check OpenAPI spec validity
   - Verify `openapi-python-client` installation
   - Check for unsupported OpenAPI features

2. **Import Errors**
   - Ensure generated client directory is accessible
   - Check for Python path issues
   - Verify temporary directory permissions

3. **Runtime Errors**
   - Check network connectivity
   - Verify API endpoint availability  
   - Review parameter validation errors

### Debugging

- Enable debug logging: `logger.setLevel(logging.DEBUG)`
- Check callable generation logs
- Review fallback usage patterns
- Monitor API response patterns

## Dependencies

- `openapi-python-client` - Client code generation
- `httpx` - HTTP client library
- `pydantic` - Data validation and serialization
- `tempfile` - Temporary directory management for generation