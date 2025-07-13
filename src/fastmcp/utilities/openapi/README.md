# OpenAPI Utilities (Legacy)

This directory contains the original OpenAPI integration utilities for FastMCP. This is the **legacy implementation** that will eventually be replaced by `openapi_new/`.

## Architecture Overview

### Core Components

1. **`openapi.py`** - Main utility module containing:
   - OpenAPI spec parsing using `openapi-pydantic`
   - Intermediate Representation (IR) models for HTTP routes
   - Parameter formatting functions for different OpenAPI styles
   - Schema combination and validation utilities

### Key Features

- **Manual HTTP Request Building**: Constructs HTTP requests manually based on OpenAPI specifications
- **Parameter Style Support**: Handles various OpenAPI parameter styles:
  - `form` style for query parameters
  - `deepObject` style with explode=true/false
  - Array parameter formatting
- **Schema Validation**: Uses Pydantic models for OpenAPI spec validation
- **Response Processing**: Extracts and formats response schemas

### Data Flow

1. **Parse OpenAPI Spec** → `HTTPRoute` IR models
2. **Manual Parameter Processing** → Format according to OpenAPI style rules
3. **HTTP Request Construction** → Build requests using `httpx`
4. **Response Handling** → Parse and validate responses

### Limitations

- **Manual Implementation**: All OpenAPI compliance is manually implemented
- **Maintenance Overhead**: Need to keep up with OpenAPI specification changes
- **Bug-prone**: Easy to introduce bugs in parameter serialization
- **Limited Features**: Not all OpenAPI features are supported

## Related Files

- `/server/openapi.py` - Server implementation using these utilities
- `/tests/server/openapi/` - Test suite for legacy implementation

## Migration Status

🚨 **This implementation is being replaced by `openapi_new/`**

The new implementation uses `openapi-python-client` for automatic code generation, which:
- Offloads OpenAPI compliance to a robust, well-tested library
- Reduces maintenance burden
- Provides better feature coverage
- Eliminates manual parameter serialization bugs

## Usage Guidelines

- **New Development**: Use `openapi_new/` for all new features
- **Bug Fixes**: Only critical fixes should be applied here
- **Migration**: Existing code should be migrated to `openapi_new/` when possible

## Key Functions

### Parameter Formatting
- `format_array_parameter()` - Format array parameters for HTTP requests
- `format_deep_object_parameter()` - Handle deepObject style parameters

### Schema Processing  
- `_combine_schemas()` - Merge parameter and request body schemas
- `extract_output_schema_from_responses()` - Extract response schemas

### Parsing
- `parse_openapi_to_http_routes()` - Convert OpenAPI spec to internal IR models

## Testing

Legacy tests are in `/tests/server/openapi/` and focus on:
- Parameter collision handling
- DeepObject style serialization
- Request/response processing
- Schema validation