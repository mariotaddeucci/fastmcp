"""Unit tests for OpenAPI callable components."""

import json
from unittest.mock import AsyncMock

import pydantic
import pytest

from fastmcp.server.openapi_new.components import (
    CallableResource,
    CallableResourceTemplate,
    CallableTool,
)
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.openapi_new import HTTPRoute


def create_test_route(method="GET", path="/test", operation_id="test_op"):
    """Create a real HTTPRoute for testing."""
    return HTTPRoute(
        path=path,
        method=method,
        operation_id=operation_id,
        summary="Test operation",
        description="Test description",
        tags=["test"],
        parameters=[],
        request_body=None,
        responses={"200": {"description": "Success"}},
        schema_definitions={},
        extensions={}
    )


class TestCallableTool:
    """Test the CallableTool component."""
    
    def test_init(self):
        """Test CallableTool initialization."""
        async def test_callable():
            return {"result": "success"}
        
        route = create_test_route()
        
        tool = CallableTool(
            callable_func=test_callable,
            route=route,
            name="test_tool",
            description="Test tool",
            parameters={"type": "object"},
            output_schema={"type": "object"},
            tags={"test"}
        )
        
        assert tool.name == "test_tool"
        assert tool.description == "Test tool"
        assert tool.parameters == {"type": "object"}
        assert tool.output_schema == {"type": "object"}
        assert tool.tags == {"test"}
        assert tool._callable == test_callable
        assert tool._route == route
    
    def test_repr(self):
        """Test CallableTool string representation."""
        async def test_callable():
            return {"result": "success"}
        
        route = create_test_route(method="GET", path="/users/{id}")
        
        tool = CallableTool(
            callable_func=test_callable,
            route=route,
            name="get_user",
            description="Get user",
            parameters={"type": "object"}
        )
        
        repr_str = repr(tool)
        assert "CallableTool" in repr_str
        assert "get_user" in repr_str
        assert "GET" in repr_str
        assert "/users/{id}" in repr_str
    
    @pytest.mark.asyncio
    async def test_run_with_pydantic_v2_model(self):
        """Test tool run with Pydantic v2 model response."""
        # Create a simple Pydantic model
        class UserResponse(pydantic.BaseModel):
            id: int
            name: str
            email: str
        
        # Real callable that returns Pydantic model
        async def get_user_callable(user_id):
            return UserResponse(id=user_id, name="John Doe", email="john@example.com")
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=get_user_callable,
            route=route,
            name="get_user",
            description="Get user",
            parameters={"type": "object"}
        )
        
        # Test the tool run
        result = await tool.run({"user_id": 1, "context": "should_be_filtered"})
        
        # Verify result structure
        assert isinstance(result, ToolResult)
        assert result.structured_content is not None
        expected_data = {"id": 1, "name": "John Doe", "email": "john@example.com"}
        assert result.structured_content == expected_data
    
    @pytest.mark.asyncio 
    async def test_run_with_attrs_model(self):
        """Test tool run with attrs model that has to_dict method."""
        # Create a real object that mimics what openapi-python-client generates
        class PostResponse:
            def __init__(self, id, title):
                self.id = id
                self.title = title
            
            def to_dict(self):
                return {"id": self.id, "title": self.title}
        
        async def get_post_callable(post_id):
            return PostResponse(id=post_id, title="Test Post")
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=get_post_callable,
            route=route,
            name="get_post",
            description="Get post",
            parameters={"type": "object"}
        )
        
        result = await tool.run({"post_id": 1})
        
        # Verify result
        assert isinstance(result, ToolResult)
        assert result.structured_content == {"id": 1, "title": "Test Post"}
    
    @pytest.mark.asyncio
    async def test_run_with_dict_response(self):
        """Test tool run with direct dict response."""
        async def create_user_callable(name):
            return {"status": "success", "data": {"id": 1, "name": name}}
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=create_user_callable,
            route=route,
            name="create_user",
            description="Create user",
            parameters={"type": "object"}
        )
        
        result = await tool.run({"name": "John"})
        
        assert isinstance(result, ToolResult)
        assert result.structured_content == {"status": "success", "data": {"id": 1, "name": "John"}}
    
    @pytest.mark.asyncio
    async def test_run_with_output_schema_wrapping(self):
        """Test tool run with output schema that requires wrapping."""
        async def get_user_id_callable(username):
            return {"user_id": 1}
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=get_user_id_callable,
            route=route,
            name="get_user_id",
            description="Get user ID",
            parameters={"type": "object"},
            output_schema={"type": "object", "x-fastmcp-wrap-result": True}
        )
        
        result = await tool.run({"username": "john"})
        
        # Should wrap the result in a "result" key
        assert isinstance(result, ToolResult)
        assert result.structured_content == {"result": {"user_id": 1}}
    
    @pytest.mark.asyncio
    async def test_run_error_handling(self):
        """Test tool run error handling."""
        async def failing_callable(param):
            raise ValueError("API error")
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=failing_callable,
            route=route,
            name="failing_tool",
            description="Failing tool",
            parameters={"type": "object"}
        )
        
        result = await tool.run({"param": "value"})
        
        # Should return error result, not raise exception
        assert isinstance(result, ToolResult)
        # Check the content (which is a list of TextContent objects)
        content_text = result.content[0].text if result.content else ""
        assert "Error executing failing_tool" in content_text
        assert "API error" in content_text
    
    @pytest.mark.asyncio
    async def test_run_with_string_fallback(self):
        """Test tool run with non-serializable response falls back to string."""
        async def number_callable():
            return 42
        
        route = create_test_route()
        tool = CallableTool(
            callable_func=number_callable,
            route=route,
            name="number_tool",
            description="Returns number",
            parameters={"type": "object"}
        )
        
        result = await tool.run({})
        
        # Should fall back to string content
        assert isinstance(result, ToolResult)
        # Check the content text
        content_text = result.content[0].text if result.content else ""
        assert content_text == "42"
        assert result.structured_content is None


class TestCallableResource:
    """Test the CallableResource component."""
    
    def test_init(self):
        """Test CallableResource initialization."""
        async def test_callable():
            return {"data": "resource data"}
        
        route = create_test_route()
        
        resource = CallableResource(
            callable_func=test_callable,
            route=route,
            uri="resource://test_resource",
            name="test_resource",
            description="Test resource",
            mime_type="application/json",
            tags={"test"}
        )
        
        assert resource.name == "test_resource"
        assert resource.description == "Test resource"
        assert str(resource.uri) == "resource://test_resource"
        assert resource.mime_type == "application/json"
        assert resource.tags == {"test"}
        assert resource._callable == test_callable
        assert resource._route == route
    
    def test_repr(self):
        """Test CallableResource string representation."""
        async def test_callable():
            return {"data": "test"}
        
        route = create_test_route(path="/api/data")
        
        resource = CallableResource(
            callable_func=test_callable,
            route=route,
            uri="resource://test_data",
            name="test_data",
            description="Test data resource"
        )
        
        repr_str = repr(resource)
        assert "CallableResource" in repr_str
        assert "test_data" in repr_str
        assert "resource://test_data" in repr_str
        assert "/api/data" in repr_str
    
    @pytest.mark.asyncio
    async def test_read_with_pydantic_model(self):
        """Test resource read with Pydantic model response."""
        class DataResponse(pydantic.BaseModel):
            id: int
            value: str
        
        async def get_data_callable():
            return DataResponse(id=1, value="test data")
        
        route = create_test_route()
        resource = CallableResource(
            callable_func=get_data_callable,
            route=route,
            uri="resource://data",
            name="data",
            description="Data resource"
        )
        
        result = await resource.read()
        
        # Should return JSON string
        assert isinstance(result, str)
        import json
        parsed = json.loads(result)
        assert parsed == {"id": 1, "value": "test data"}
    
    @pytest.mark.asyncio
    async def test_read_with_dict_response(self):
        """Test resource read with dict response."""
        async def get_data_callable():
            return {"status": "active", "items": [1, 2, 3]}
        
        route = create_test_route()
        resource = CallableResource(
            callable_func=get_data_callable,
            route=route,
            uri="resource://data",
            name="data",
            description="Data resource"
        )
        
        result = await resource.read()
        
        # Should return JSON string
        assert isinstance(result, str)
        import json
        parsed = json.loads(result)
        assert parsed == {"status": "active", "items": [1, 2, 3]}
    
    @pytest.mark.asyncio
    async def test_read_with_string_response(self):
        """Test resource read with string response."""
        async def get_text_callable():
            return "Hello, World!"
        
        route = create_test_route()
        resource = CallableResource(
            callable_func=get_text_callable,
            route=route,
            uri="resource://text",
            name="text",
            description="Text resource"
        )
        
        result = await resource.read()
        
        # Should return the string directly
        assert result == "Hello, World!"
    
    @pytest.mark.asyncio
    async def test_read_error_handling(self):
        """Test resource read error handling."""
        async def failing_callable():
            raise ConnectionError("Network error")
        
        route = create_test_route()
        resource = CallableResource(
            callable_func=failing_callable,
            route=route,
            uri="resource://failing",
            name="failing",
            description="Failing resource"
        )
        
        with pytest.raises(ValueError, match="Error reading resource failing"):
            await resource.read()


class TestCallableResourceTemplate:
    """Test the CallableResourceTemplate component."""
    
    def test_init(self):
        """Test CallableResourceTemplate initialization."""
        async def test_callable(user_id):
            return {"user_id": user_id}
        
        route = create_test_route()
        
        template = CallableResourceTemplate(
            callable_func=test_callable,
            route=route,
            uri_template="resource://users/{user_id}",
            name="user_template",
            description="User resource template",
            parameters={"type": "object", "properties": {"user_id": {"type": "integer"}}},
            tags={"users"}
        )
        
        assert template.name == "user_template"
        assert template.description == "User resource template"
        assert template.uri_template == "resource://users/{user_id}"
        assert template.tags == {"users"}
        assert template._callable == test_callable
        assert template._route == route
    
    def test_repr(self):
        """Test CallableResourceTemplate string representation."""
        async def test_callable(user_id):
            return {"user_id": user_id}
        
        route = create_test_route(path="/api/users/{id}")
        
        template = CallableResourceTemplate(
            callable_func=test_callable,
            route=route,
            uri_template="resource://users/{user_id}",
            name="user_template",
            description="User template",
            parameters={"type": "object"}
        )
        
        repr_str = repr(template)
        assert "CallableResourceTemplate" in repr_str
        assert "user_template" in repr_str
        assert "resource://users/{user_id}" in repr_str
        assert "/api/users/{id}" in repr_str
    
    @pytest.mark.asyncio
    async def test_create_resource(self):
        """Test creating a resource from template."""
        async def get_user_callable(user_id):
            return {"id": user_id, "name": f"User {user_id}"}
        
        route = create_test_route()
        template = CallableResourceTemplate(
            callable_func=get_user_callable,
            route=route,
            uri_template="resource://users/{user_id}",
            name="user_template",
            description="User template",
            parameters={"type": "object"}
        )
        
        # Create a resource instance
        resource = await template.create_resource(
            uri="resource://users/123",
            params={"user_id": 123}
        )
        
        # Verify the resource
        assert isinstance(resource, CallableResource)
        assert resource.name == "user_template-user_id=123"
        assert str(resource.uri) == "resource://users/123"
        assert resource.description == "User template"
        
        # Test that the resource works
        result = await resource.read()
        import json
        parsed = json.loads(result)
        assert parsed == {"id": 123, "name": "User 123"}