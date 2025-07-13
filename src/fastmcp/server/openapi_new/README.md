# OpenAPI Server Implementation (New)

This directory contains the next-generation FastMCP server implementation for OpenAPI integration, designed to replace the legacy implementation in `/server/openapi.py`.

## Architecture Overview

The new implementation uses a **hybrid approach** combining automatic code generation with fallback compatibility, providing robust OpenAPI support while maintaining backward compatibility.

### Core Components

1. **`server.py`** - `FastMCPOpenAPI` main server class with hybrid routing
2. **`components.py`** - Callable-based and fallback component implementations
3. **`routing.py`** - Route mapping and component selection logic

### Key Architecture Principles

#### 1. Hybrid Strategy
- **Primary Path**: Use generated callables from `openapi-python-client` 
- **Fallback Path**: Use legacy HTTP request building when callables unavailable
- **Seamless Integration**: Same public API regardless of implementation path

#### 2. Component Duality
Each MCP component type has two implementations:
- **Callable-based**: Uses generated client functions (preferred)
- **Legacy-based**: Uses manual HTTP construction (fallback)

#### 3. Automatic Selection
- Server automatically chooses best implementation per operation
- Logs which implementation is used for monitoring
- Graceful degradation ensures reliability

## Component Classes

### Callable-Based Components (Preferred)

#### `CallableTool`
- Executes operations using generated callable functions
- Automatic parameter validation and serialization
- Built-in error handling and response processing
- **Advantages**: Robust, tested, comprehensive OpenAPI support

#### `CallableResource` / `CallableResourceTemplate`  
- Provides resource access using generated callables
- Automatic response caching and validation
- Support for complex parameter patterns
- **Advantages**: Better error handling, performance optimizations

### Fallback Components

#### `OpenAPITool` / `OpenAPIResource` / `OpenAPIResourceTemplate`
- Imported from legacy implementation
- Used when callable generation fails or is unavailable
- Same interface as callable-based components
- **Purpose**: Ensure backward compatibility and reliability

## Server Implementation

### `FastMCPOpenAPI` Class

The main server class orchestrates the hybrid approach:

```python
class FastMCPOpenAPI(FastMCP):
    def __init__(self, openapi_spec: dict, client: httpx.AsyncClient, **kwargs):
        # 1. Parse OpenAPI spec to HTTP routes
        self._routes = parse_openapi_to_http_routes(openapi_spec)
        
        # 2. Attempt callable generation
        try:
            factory = OASCallableFactory(openapi_spec, base_url=base_url)
            self._callables_map = factory.build()
        except Exception:
            self._callables_map = {}  # Fallback to legacy
            
        # 3. Create components using hybrid approach
        self._create_components()
```

### Component Selection Logic

```python
def _create_tool(self, route: HTTPRoute) -> Tool:
    # Try callable-based first
    callable_fn = self._callables_map.get(route.operation_id)
    if callable_fn:
        return CallableTool(callable=callable_fn, route=route, ...)
    
    # Fallback to legacy
    return OpenAPITool(client=self._client, route=route, ...)
```

## Data Flow

### Successful Callable Path

```
OpenAPI Spec → OASCallableFactory → Generated Client → CallableTool → HTTP Request → Structured Response
```

1. **Spec Parsing**: OpenAPI spec parsed to `HTTPRoute` models
2. **Client Generation**: `openapi-python-client` generates Python client
3. **Callable Extraction**: Extract operation functions by `operationId`
4. **Component Creation**: Create `CallableTool` with bound callable
5. **Request Execution**: Execute callable with validated parameters
6. **Response Processing**: Return structured MCP response

### Fallback Path

```
OpenAPI Spec → HTTPRoute → OpenAPITool → Manual HTTP Request → Response Processing
```

1. **Spec Parsing**: Same as callable path
2. **Legacy Creation**: Create `OpenAPITool` with HTTP client
3. **Manual Construction**: Build HTTP request manually
4. **Response Handling**: Process response with legacy logic

## Key Features

### 1. Enhanced Parameter Handling

#### Parameter Collision Resolution
- **Automatic Suffixing**: Colliding parameters get location-based suffixes
- **Example**: `id` in path and body becomes `id__path` and `id`
- **Transparent**: LLMs see suffixed parameters, implementation routes correctly

#### DeepObject Style Support
- **Native Support**: Generated client handles all deepObject variations
- **Explode Handling**: Proper support for explode=true/false
- **Complex Objects**: Nested object serialization works correctly

### 2. Robust Error Handling

#### HTTP Error Mapping
- **Status Code Mapping**: HTTP errors mapped to appropriate MCP errors
- **Structured Responses**: Error details preserved in tool results
- **Timeout Handling**: Network timeouts handled gracefully

#### Fallback Error Handling
- **Generation Failures**: Client generation errors don't break server
- **Runtime Failures**: Callable execution errors fall back to legacy
- **Logging**: All fallback usage logged for monitoring

### 3. Performance Optimizations

#### Efficient Client Reuse
- **Connection Pooling**: HTTP connections reused across requests
- **Client Caching**: Generated clients cached for performance
- **Async Support**: Full async/await throughout

#### Smart Fallback
- **Per-Operation**: Fallback decisions made per operation, not globally
- **Caching**: Fallback decisions cached to avoid repeated attempts
- **Monitoring**: Fallback usage tracked for optimization

## Configuration

### Server Options

```python
server = FastMCPOpenAPI(
    openapi_spec=spec,           # Required: OpenAPI specification
    client=httpx_client,         # Required: HTTP client instance
    name="API Server",           # Optional: Server name
    route_map=custom_routes,     # Optional: Custom route mappings
    force_fallback=False,        # Optional: Force legacy implementation
    enable_caching=True,         # Optional: Enable response caching
)
```

### Route Mapping Customization

```python
from fastmcp.server.openapi_new.routing import RouteMap

custom_routes = RouteMap({
    "GET:/users": "tool",        # Force specific operations to be tools
    "GET:/status": "resource",   # Force specific operations to be resources
})
```

## Testing Strategy

### Test Structure

Tests are organized by functionality:
- `test_server.py` - Server integration and hybrid behavior
- `test_components.py` - Component behavior with callables
- `test_parameter_collisions.py` - Parameter collision handling
- `test_deepobject_style.py` - DeepObject parameter style support
- `test_openapi_features.py` - General OpenAPI feature compliance

### Testing Philosophy

1. **Real Integration**: Test with real OpenAPI specs and HTTP clients
2. **Minimal Mocking**: Only mock external API endpoints
3. **Behavioral Focus**: Test behavior, not implementation details
4. **Fallback Coverage**: Test both callable and fallback paths

### Example Test Pattern

```python
async def test_callable_with_fallback():
    """Test that server works with both callable and fallback paths."""
    
    # Test with working callable generation
    server = FastMCPOpenAPI(spec=valid_spec, client=client)
    # Verify callable path works
    
    # Test with forced fallback
    server = FastMCPOpenAPI(spec=valid_spec, client=client, force_fallback=True)
    # Verify fallback path works with same behavior
```

## Migration Benefits

### From Legacy Implementation

1. **Better OpenAPI Compliance**: Generated client handles all OpenAPI features correctly
2. **Fewer Bugs**: Eliminate manual parameter serialization errors
3. **Enhanced Features**: Support for more OpenAPI parameter styles and patterns
4. **Future-proof**: Automatic updates when OpenAPI spec evolves
5. **Performance**: Better connection handling and response processing

### Backward Compatibility

- **Same Interface**: Public API unchanged from legacy implementation
- **Graceful Degradation**: Fallback ensures existing functionality preserved
- **No Breaking Changes**: Existing code works without modification

## Monitoring and Debugging

### Logging

```python
# Enable debug logging to see implementation choices
import logging
logging.getLogger("fastmcp.server.openapi_new").setLevel(logging.DEBUG)
```

### Key Log Messages
- **Callable Generation**: Success/failure of client generation
- **Component Selection**: Which implementation chosen per operation
- **Fallback Usage**: When and why fallback path is used
- **Performance Metrics**: Request timing and error rates

### Debugging Common Issues

1. **Client Generation Fails**
   - Check OpenAPI spec validity
   - Verify `openapi-python-client` installation
   - Review generation error logs

2. **Parameter Issues**
   - Enable debug logging for parameter processing
   - Check for parameter collision warnings
   - Verify OpenAPI spec parameter definitions

3. **Performance Issues**
   - Monitor callable vs fallback usage ratios
   - Check HTTP client configuration
   - Review response processing timing

## Future Enhancements

### Planned Features

1. **Advanced Caching**: Intelligent response caching with TTL
2. **Streaming Support**: Handle streaming API responses
3. **Batch Operations**: Optimize multiple operation calls
4. **Enhanced Monitoring**: Detailed metrics and health checks
5. **Configuration Management**: Dynamic configuration updates

### Performance Improvements

1. **Lazy Loading**: Generate clients on-demand
2. **Parallel Processing**: Concurrent operation execution
3. **Memory Optimization**: Efficient client storage and cleanup
4. **Request Optimization**: Smart request batching and deduplication

## Related Documentation

- `/utilities/openapi_new/README.md` - Utility implementation details
- `/server/openapi/README.md` - Legacy implementation reference
- `/tests/server/openapi_new/` - Comprehensive test suite
- Project documentation on OpenAPI integration patterns