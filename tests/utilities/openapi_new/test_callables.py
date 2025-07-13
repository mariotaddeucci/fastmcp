"""Unit tests for OASCallableFactory."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from fastmcp.utilities.openapi_new.callables import OASCallableFactory


class TestOASCallableFactory:
    """Test the OpenAPI callable factory."""
    
    def test_init(self):
        """Test factory initialization."""
        spec = {"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}}
        base_url = "https://api.example.com"
        
        factory = OASCallableFactory(spec, base_url)
        
        assert factory.spec == spec
        assert factory.base_url == base_url
    
    def test_init_default_base_url(self):
        """Test factory initialization with default base URL."""
        spec = {"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}}
        
        factory = OASCallableFactory(spec)
        
        assert factory.spec == spec
        assert factory.base_url == "http://localhost"
    
    @patch('subprocess.run')
    def test_build_client_generation_failure(self, mock_run):
        """Test that build handles client generation failures gracefully."""
        spec = {"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}}
        factory = OASCallableFactory(spec)
        
        # Mock subprocess failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Generation failed"
        mock_run.return_value = mock_result
        
        with pytest.raises(RuntimeError, match="Client generation failed"):
            factory.build()
    
    @patch('subprocess.run')
    def test_build_timeout_handling(self, mock_run):
        """Test that build handles subprocess timeouts."""
        from subprocess import TimeoutExpired
        
        spec = {"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}}
        factory = OASCallableFactory(spec)
        
        # Mock subprocess timeout
        mock_run.side_effect = TimeoutExpired("cmd", 60)
        
        with pytest.raises(RuntimeError, match="Client generation timed out"):
            factory.build()
    
    def test_operation_id_to_func_name(self):
        """Test operation ID to function name conversion."""
        factory = OASCallableFactory({})
        
        # Test various operation ID formats
        assert factory._operation_id_to_func_name("getUserById") == "getuserbyid"
        assert factory._operation_id_to_func_name("get-user-by-id") == "get_user_by_id"
        assert factory._operation_id_to_func_name("get user by id") == "get_user_by_id"
        assert factory._operation_id_to_func_name("getUser") == "getuser"
    
    def test_get_operation_id_from_function_attributes(self):
        """Test extracting operation ID from function attributes."""
        factory = OASCallableFactory({})
        
        # Mock function with operation_id attribute
        mock_func = Mock()
        mock_func.operation_id = "getUserById"
        
        result = factory._get_operation_id(mock_func, "get_user_by_id")
        assert result == "getUserById"
    
    def test_get_operation_id_from_docstring(self):
        """Test extracting operation ID from function docstring."""
        factory = OASCallableFactory({})
        
        # Create a real function object for proper docstring handling
        def mock_func():
            """Get user by ID.
            
            operation_id: getUserById
            """
            pass
        
        # Remove operation_id attribute if it exists
        if hasattr(mock_func, 'operation_id'):
            delattr(mock_func, 'operation_id')
        
        result = factory._get_operation_id(mock_func, "get_user_by_id")
        assert result == "getUserById"
    
    def test_get_operation_id_from_spec_matching(self):
        """Test extracting operation ID by matching with OpenAPI spec."""
        spec = {
            "paths": {
                "/users/{id}": {
                    "get": {
                        "operationId": "getUserById"
                    }
                }
            }
        }
        factory = OASCallableFactory(spec)
        
        # Create a real function object without attributes or helpful docstring
        def mock_func():
            """Just a function."""
            pass
        
        # Ensure no operation_id attribute
        if hasattr(mock_func, 'operation_id'):
            delattr(mock_func, 'operation_id')
        
        result = factory._get_operation_id(mock_func, "getuserbyid")
        assert result == "getUserById"
    
    def test_get_operation_id_fallback_to_function_name(self):
        """Test fallback to function name when no operation ID found."""
        factory = OASCallableFactory({})
        
        # Create a real function object without any operation ID info
        def mock_func():
            """Just a function."""
            pass
        
        # Ensure no operation_id attribute
        if hasattr(mock_func, 'operation_id'):
            delattr(mock_func, 'operation_id')
        
        result = factory._get_operation_id(mock_func, "get_user_by_id")
        assert result == "get_user_by_id"
    
    @pytest.mark.asyncio
    async def test_create_bound_callable(self):
        """Test creating bound callables with client injection."""
        factory = OASCallableFactory({})
        
        # Mock original function and client
        async def mock_api_func(client, user_id):
            return f"User {user_id} from {client.base_url}"
        
        mock_client = Mock()
        mock_client.base_url = "https://api.example.com"
        
        # Create bound callable
        bound_callable = factory._create_bound_callable(mock_api_func, mock_client)
        
        # Test that it works with just the parameter (client is injected)
        result = await bound_callable(user_id=123)
        assert result == "User 123 from https://api.example.com"
        
        # Test that it filters out FastMCP context
        result = await bound_callable(user_id=456, context="should_be_filtered")
        assert result == "User 456 from https://api.example.com"
    
    def test_create_bound_callable_preserves_metadata(self):
        """Test that bound callables preserve original function metadata."""
        factory = OASCallableFactory({})
        
        def original_func():
            """Original function docstring."""
            pass
        
        original_func.__name__ = "original_name"
        
        mock_client = Mock()
        bound_callable = factory._create_bound_callable(original_func, mock_client)
        
        assert bound_callable.__name__ == "original_name"
        assert bound_callable.__doc__ == "Original function docstring."