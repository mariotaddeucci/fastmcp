"""OpenAPI component implementations: Tool, Resource, and ResourceTemplate classes."""

import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx
import pydantic
from mcp.types import ToolAnnotations
from pydantic.networks import AnyUrl

try:
    import pydantic.v1 as pydantic_v1
except ImportError:
    pydantic_v1 = None

from fastmcp.exceptions import ToolError
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.server.dependencies import get_http_headers
from fastmcp.tools.tool import Tool, ToolResult
from fastmcp.utilities.logging import get_logger

# Import from our new utilities
from fastmcp.utilities.openapi_new import (
    HTTPRoute,
    format_array_parameter,
    format_deep_object_parameter,
)

if TYPE_CHECKING:
    from fastmcp.server import Context

logger = get_logger(__name__)


class OpenAPITool(Tool):
    """Tool implementation for OpenAPI endpoints."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        route: HTTPRoute,
        name: str,
        description: str,
        parameters: dict[str, Any],
        output_schema: dict[str, Any] | None = None,
        tags: set[str] | None = None,
        timeout: float | None = None,
        annotations: ToolAnnotations | None = None,
        serializer: Callable[[Any], str] | None = None,
    ):
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
            output_schema=output_schema,
            tags=tags or set(),
            annotations=annotations,
            serializer=serializer,
        )
        self._client = client
        self._route = route
        self._timeout = timeout

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"OpenAPITool(name={self.name!r}, method={self._route.method}, path={self._route.path})"

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the HTTP request based on the route configuration."""

        # Create mapping from suffixed parameter names back to original names and locations
        # This handles parameter collisions where suffixes were added during schema generation
        param_mapping = {}  # suffixed_name -> (original_name, location)

        # First, check if we have request body properties to detect collisions
        body_props = set()
        if self._route.request_body and self._route.request_body.content_schema:
            content_type = next(iter(self._route.request_body.content_schema))
            body_schema = self._route.request_body.content_schema[content_type]
            body_props = set(body_schema.get("properties", {}).keys())

        # Build parameter mapping for potentially suffixed parameters
        for param in self._route.parameters:
            original_name = param.name
            suffixed_name = f"{param.name}__{param.location}"

            # If parameter name collides with body property, it would have been suffixed
            if param.name in body_props:
                param_mapping[suffixed_name] = (original_name, param.location)
            # Also map original name for backward compatibility when no collision
            param_mapping[original_name] = (original_name, param.location)

        # Prepare URL
        path = self._route.path

        # Replace path parameters with values from arguments
        # Look for both original and suffixed parameter names
        path_params = {}
        for p in self._route.parameters:
            if p.location == "path":
                # Try suffixed name first, then original name
                suffixed_name = f"{p.name}__{p.location}"
                if (
                    suffixed_name in arguments
                    and arguments.get(suffixed_name) is not None
                ):
                    path_params[p.name] = arguments[suffixed_name]
                elif p.name in arguments and arguments.get(p.name) is not None:
                    path_params[p.name] = arguments[p.name]

        # Ensure all path parameters are provided
        required_path_params = {
            p.name
            for p in self._route.parameters
            if p.location == "path" and p.required
        }
        missing_params = required_path_params - path_params.keys()
        if missing_params:
            raise ToolError(f"Missing required path parameters: {missing_params}")

        for param_name, param_value in path_params.items():
            # Handle array path parameters with style 'simple' (comma-separated)
            # In OpenAPI, 'simple' is the default style for path parameters
            param_info = next(
                (p for p in self._route.parameters if p.name == param_name), None
            )

            if param_info and isinstance(param_value, list):
                # Check if schema indicates an array type
                schema = param_info.schema_
                is_array = schema.get("type") == "array"

                if is_array:
                    # Format array values as comma-separated string
                    # This follows the OpenAPI 'simple' style (default for path)
                    formatted_value = format_array_parameter(
                        param_value, param_name, is_query_parameter=False
                    )
                    path = path.replace(f"{{{param_name}}}", str(formatted_value))
                    continue

            # Default handling for non-array parameters or non-array schemas
            path = path.replace(f"{{{param_name}}}", str(param_value))

        # Prepare query parameters - filter out None and empty strings
        query_params = {}
        for p in self._route.parameters:
            if p.location == "query":
                # Try suffixed name first, then original name
                suffixed_name = f"{p.name}__{p.location}"
                param_value = None

                suffixed_value = arguments.get(suffixed_name)
                if (
                    suffixed_name in arguments
                    and suffixed_value is not None
                    and suffixed_value != ""
                    and not (
                        isinstance(suffixed_value, list | dict)
                        and len(suffixed_value) == 0
                    )
                ):
                    param_value = arguments[suffixed_name]
                else:
                    name_value = arguments.get(p.name)
                    if (
                        p.name in arguments
                        and name_value is not None
                        and name_value != ""
                        and not (
                            isinstance(name_value, list | dict) and len(name_value) == 0
                        )
                    ):
                        param_value = arguments[p.name]

                if param_value is not None:
                    # Handle different parameter styles and types
                    param_style = (
                        p.style or "form"
                    )  # Default style for query parameters is "form"
                    param_explode = (
                        p.explode if p.explode is not None else True
                    )  # Default explode for query is True

                    # Handle deepObject style for object parameters
                    if (
                        param_style == "deepObject"
                        and isinstance(param_value, dict)
                        and len(param_value) > 0
                    ):
                        if param_explode:
                            # deepObject with explode=true: object properties become separate parameters
                            # e.g., target[id]=123&target[type]=user
                            deep_obj_params = format_deep_object_parameter(
                                param_value, p.name
                            )
                            query_params.update(deep_obj_params)
                        else:
                            # deepObject with explode=false is not commonly used, fallback to JSON
                            logger.warning(
                                f"deepObject style with explode=false for parameter '{p.name}' is not standard. "
                                f"Using JSON serialization fallback."
                            )
                            query_params[p.name] = json.dumps(param_value)
                    # Handle array parameters with form style (default)
                    elif (
                        isinstance(param_value, list)
                        and p.schema_.get("type") == "array"
                        and len(param_value) > 0
                    ):
                        if param_explode:
                            # When explode=True, we pass the array directly, which HTTPX will serialize
                            # as multiple parameters with the same name
                            query_params[p.name] = param_value
                        else:
                            # Format array as comma-separated string when explode=False
                            formatted_value = format_array_parameter(
                                param_value, p.name, is_query_parameter=True
                            )
                            query_params[p.name] = formatted_value
                    else:
                        # Non-array, non-deepObject parameters are passed as is
                        query_params[p.name] = param_value

        # Prepare headers - fix typing by ensuring all values are strings
        headers = {}

        # Start with OpenAPI-defined header parameters
        openapi_headers = {}
        for p in self._route.parameters:
            if p.location == "header":
                # Try suffixed name first, then original name
                suffixed_name = f"{p.name}__{p.location}"
                param_value = None

                if (
                    suffixed_name in arguments
                    and arguments.get(suffixed_name) is not None
                ):
                    param_value = arguments[suffixed_name]
                elif p.name in arguments and arguments.get(p.name) is not None:
                    param_value = arguments[p.name]

                if param_value is not None:
                    openapi_headers[p.name.lower()] = str(param_value)
        headers.update(openapi_headers)

        # Add headers from the current MCP client HTTP request (these take precedence)
        mcp_headers = get_http_headers()
        headers.update(mcp_headers)

        # Prepare request body
        json_data = None
        if self._route.request_body and self._route.request_body.content_schema:
            # Extract body parameters with collision-aware logic
            # Exclude all parameter names that belong to path/query/header locations
            params_to_exclude = set()

            for p in self._route.parameters:
                if (
                    p.name in body_props
                ):  # This parameter had a collision, so it was suffixed
                    params_to_exclude.add(f"{p.name}__{p.location}")
                else:  # No collision, parameter keeps original name but should still be excluded from body
                    params_to_exclude.add(p.name)

            body_params = {
                k: v
                for k, v in arguments.items()
                if k not in params_to_exclude and k != "context"
            }

            if body_params:
                json_data = body_params

        # Execute the request
        try:
            response = await self._client.request(
                method=self._route.method,
                url=path,
                params=query_params,
                headers=headers,
                json=json_data,
                timeout=self._timeout,
            )

            # Raise for 4xx/5xx responses
            response.raise_for_status()

            # Try to parse as JSON first
            try:
                result = response.json()

                # Handle structured content based on output schema, if any
                structured_output = None
                if self.output_schema is not None:
                    if self.output_schema.get("x-fastmcp-wrap-result"):
                        # Schema says wrap - always wrap in result key
                        structured_output = {"result": result}
                    else:
                        structured_output = result
                # If no output schema, use fallback logic for backward compatibility
                elif not isinstance(result, dict):
                    structured_output = {"result": result}
                else:
                    structured_output = result

                return ToolResult(structured_content=structured_output)
            except json.JSONDecodeError:
                return ToolResult(content=response.text)

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors (4xx, 5xx)
            error_message = (
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
            )
            try:
                error_data = e.response.json()
                error_message += f" - {error_data}"
            except (json.JSONDecodeError, ValueError):
                if e.response.text:
                    error_message += f" - {e.response.text}"

            raise ValueError(error_message)

        except httpx.RequestError as e:
            # Handle request errors (connection, timeout, etc.)
            raise ValueError(f"Request error: {str(e)}")


class OpenAPIResource(Resource):
    """Resource implementation for OpenAPI endpoints."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        route: HTTPRoute,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "application/json",
        tags: set[str] = set(),
        timeout: float | None = None,
    ):
        super().__init__(
            uri=AnyUrl(uri),  # Convert string to AnyUrl
            name=name,
            description=description,
            mime_type=mime_type,
            tags=tags,
        )
        self._client = client
        self._route = route
        self._timeout = timeout

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"OpenAPIResource(name={self.name!r}, uri={self.uri!r}, path={self._route.path})"

    async def read(self) -> str | bytes:
        """Fetch the resource data by making an HTTP request."""
        try:
            # Extract path parameters from the URI if present
            path = self._route.path
            resource_uri = str(self.uri)

            # If this is a templated resource, extract path parameters from the URI
            if "{" in path and "}" in path:
                # Extract the resource ID from the URI (the last part after the last slash)
                parts = resource_uri.split("/")

                if len(parts) > 1:
                    # Find all path parameters in the route path
                    path_params = {}

                    # Find the path parameter names from the route path
                    param_matches = re.findall(r"\{([^}]+)\}", path)
                    if param_matches:
                        # Reverse sorting from creation order (traversal is backwards)
                        param_matches.sort(reverse=True)
                        # Number of sent parameters is number of parts -1 (assuming first part is resource identifier)
                        expected_param_count = len(parts) - 1
                        # Map parameters from the end of the URI to the parameters in the path
                        # Last parameter in URI (parts[-1]) maps to last parameter in path, and so on
                        for i, param_name in enumerate(param_matches):
                            # Ensure we don't use resource identifier as parameter
                            if i < expected_param_count:
                                # Get values from the end of parts
                                param_value = parts[-1 - i]
                                path_params[param_name] = param_value

                    # Replace path parameters with their values
                    for param_name, param_value in path_params.items():
                        path = path.replace(f"{{{param_name}}}", str(param_value))

            # Filter any query parameters - get query parameters and filter out None/empty values
            query_params = {}
            for param in self._route.parameters:
                if param.location == "query" and hasattr(self, f"_{param.name}"):
                    value = getattr(self, f"_{param.name}")
                    if value is not None and value != "":
                        query_params[param.name] = value

            # Prepare headers from MCP client request if available
            headers = {}
            mcp_headers = get_http_headers()
            headers.update(mcp_headers)

            response = await self._client.request(
                method=self._route.method,
                url=path,
                params=query_params,
                headers=headers,
                timeout=self._timeout,
            )

            # Raise for 4xx/5xx responses
            response.raise_for_status()

            # Determine content type and return appropriate format
            content_type = response.headers.get("content-type", "").lower()

            if "application/json" in content_type:
                result = response.json()
                return json.dumps(result)
            elif any(ct in content_type for ct in ["text/", "application/xml"]):
                return response.text
            else:
                return response.content

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors (4xx, 5xx)
            error_message = (
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
            )
            try:
                error_data = e.response.json()
                error_message += f" - {error_data}"
            except (json.JSONDecodeError, ValueError):
                if e.response.text:
                    error_message += f" - {e.response.text}"

            raise ValueError(error_message)

        except httpx.RequestError as e:
            # Handle request errors (connection, timeout, etc.)
            raise ValueError(f"Request error: {str(e)}")


class OpenAPIResourceTemplate(ResourceTemplate):
    """Resource template implementation for OpenAPI endpoints."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        route: HTTPRoute,
        uri_template: str,
        name: str,
        description: str,
        parameters: dict[str, Any],
        tags: set[str] = set(),
        timeout: float | None = None,
    ):
        super().__init__(
            uri_template=uri_template,
            name=name,
            description=description,
            parameters=parameters,
            tags=tags,
        )
        self._client = client
        self._route = route
        self._timeout = timeout

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"OpenAPIResourceTemplate(name={self.name!r}, uri_template={self.uri_template!r}, path={self._route.path})"

    async def create_resource(
        self,
        uri: str,
        params: dict[str, Any],
        context: "Context | None" = None,
    ) -> Resource:
        """Create a resource with the given parameters."""
        # Generate a URI for this resource instance
        uri_parts = []
        for key, value in params.items():
            uri_parts.append(f"{key}={value}")

        # Create and return a resource
        return OpenAPIResource(
            client=self._client,
            route=self._route,
            uri=uri,
            name=f"{self.name}-{'-'.join(uri_parts)}",
            description=self.description or f"Resource for {self._route.path}",
            mime_type="application/json",
            tags=set(self._route.tags or []),
            timeout=self._timeout,
        )


class CallableTool(Tool):
    """Tool implementation that wraps a generated OpenAPI callable."""

    def __init__(
        self,
        callable_func: Callable[..., Any],
        route: HTTPRoute,
        name: str,
        description: str,
        parameters: dict[str, Any],
        output_schema: dict[str, Any] | None = None,
        tags: set[str] | None = None,
        annotations: ToolAnnotations | None = None,
        serializer: Callable[[Any], str] | None = None,
    ):
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
            output_schema=output_schema,
            tags=tags or set(),
            annotations=annotations,
            serializer=serializer,
        )
        self._callable = callable_func
        self._route = route

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"CallableTool(name={self.name!r}, method={self._route.method}, path={self._route.path})"

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the callable function based on the route configuration."""
        try:
            # Remove FastMCP-specific arguments that the generated callable won't expect
            clean_arguments = {k: v for k, v in arguments.items() if k != 'context'}
            
            # Call the generated function
            response = await self._callable(**clean_arguments)
            
                
            # Handle the response from the generated client
            if hasattr(response, 'parsed') and response.parsed is not None:
                # Generated client returned a structured response
                structured_output = response.parsed
                
                # Handle output schema wrapping if needed
                if self.output_schema is not None:
                    if self.output_schema.get("x-fastmcp-wrap-result"):
                        # Schema says wrap - always wrap in result key
                        structured_output = {"result": structured_output}
                # If no output schema, use fallback logic for backward compatibility
                elif not isinstance(structured_output, dict):
                    structured_output = {"result": structured_output}
                
                return ToolResult(structured_content=structured_output)
            elif hasattr(response, 'content'):
                # Response has raw content
                return ToolResult(content=response.content)
            else:
                # Response is likely a Pydantic model from openapi-python-client
                # Convert to dict for structured output
                if isinstance(response, pydantic.BaseModel):
                    # Pydantic v2 model
                    structured_output = response.model_dump()
                elif pydantic_v1 and isinstance(response, pydantic_v1.BaseModel):
                    # Pydantic v1 model
                    structured_output = response.dict()
                elif hasattr(response, 'to_dict'):
                    # Generated client model with to_dict method (attrs or other)
                    structured_output = response.to_dict()
                elif isinstance(response, dict):
                    structured_output = response
                else:
                    # Fallback to string content
                    return ToolResult(content=str(response))
                
                # Handle output schema wrapping if needed
                if self.output_schema is not None:
                    if self.output_schema.get("x-fastmcp-wrap-result"):
                        # Schema says wrap - always wrap in result key
                        structured_output = {"result": structured_output}
                # If no output schema, use fallback logic for backward compatibility
                elif not isinstance(structured_output, dict):
                    structured_output = {"result": structured_output}
                
                return ToolResult(structured_content=structured_output)

        except Exception as e:
            # Handle errors gracefully
            logger.error(f"Error in callable tool {self.name}: {e}")
            return ToolResult(content=f"Error executing {self.name}: {str(e)}")


class CallableResource(Resource):
    """Resource implementation that wraps a generated OpenAPI callable."""

    def __init__(
        self,
        callable_func: Callable[..., Any],
        route: HTTPRoute,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "application/json",
        tags: set[str] = set(),
    ):
        super().__init__(
            uri=AnyUrl(uri),  # Convert string to AnyUrl
            name=name,
            description=description,
            mime_type=mime_type,
            tags=tags,
        )
        self._callable = callable_func
        self._route = route

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"CallableResource(name={self.name!r}, uri={self.uri!r}, path={self._route.path})"

    async def read(self) -> str | bytes:
        """Fetch the resource data by calling the generated function."""
        try:
            # Call the generated function (no parameters for basic resources)
            response = await self._callable()

            # Handle the response content
            if hasattr(response, 'parsed') and response.parsed is not None:
                # Return JSON-serialized parsed content
                return json.dumps(response.parsed)
            elif hasattr(response, 'content'):
                # Return raw content
                if isinstance(response.content, bytes):
                    return response.content
                else:
                    return str(response.content)
            else:
                # Response is likely a Pydantic model from openapi-python-client
                if isinstance(response, pydantic.BaseModel):
                    # Pydantic v2 model
                    return json.dumps(response.model_dump())
                elif pydantic_v1 and isinstance(response, pydantic_v1.BaseModel):
                    # Pydantic v1 model
                    return json.dumps(response.dict())
                elif hasattr(response, 'to_dict'):
                    # Generated client model with to_dict method (attrs or other)
                    return json.dumps(response.to_dict())
                elif isinstance(response, dict | list):
                    return json.dumps(response)
                else:
                    return str(response)

        except Exception as e:
            logger.error(f"Error in callable resource {self.name}: {e}")
            raise ValueError(f"Error reading resource {self.name}: {str(e)}")


class CallableResourceTemplate(ResourceTemplate):
    """Resource template implementation that wraps a generated OpenAPI callable."""

    def __init__(
        self,
        callable_func: Callable[..., Any],
        route: HTTPRoute,
        uri_template: str,
        name: str,
        description: str,
        parameters: dict[str, Any],
        tags: set[str] = set(),
    ):
        super().__init__(
            uri_template=uri_template,
            name=name,
            description=description,
            parameters=parameters,
            tags=tags,
        )
        self._callable = callable_func
        self._route = route

    def __repr__(self) -> str:
        """Custom representation to prevent recursion errors when printing."""
        return f"CallableResourceTemplate(name={self.name!r}, uri_template={self.uri_template!r}, path={self._route.path})"

    async def create_resource(
        self,
        uri: str,
        params: dict[str, Any],
        context: "Context | None" = None,
    ) -> Resource:
        """Create a resource with the given parameters."""
        from functools import partial

        # Create a bound callable with the provided parameters
        bound_callable = partial(self._callable, **params)

        # Create and return a CallableResource instance
        return CallableResource(
            callable_func=bound_callable,
            route=self._route,
            uri=uri,
            name=f"{self.name}-{'-'.join(f'{k}={v}' for k, v in params.items())}",
            description=self.description or f"Resource for {self._route.path}",
            mime_type="application/json",
            tags=set(self._route.tags or []),
        )


# Export public symbols
__all__ = [
    "OpenAPITool",
    "OpenAPIResource", 
    "OpenAPIResourceTemplate",
    "CallableTool",
    "CallableResource",
    "CallableResourceTemplate",
]
