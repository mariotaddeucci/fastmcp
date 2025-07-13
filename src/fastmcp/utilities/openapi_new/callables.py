"""OpenAPI callable factory using openapi-python-client for code generation."""

import importlib.util
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class OASCallableFactory:
    """Generates executable callables from OpenAPI spec using openapi-python-client."""
    
    def __init__(self, spec: dict[str, Any], base_url: str = "http://localhost"):
        self.spec = spec
        self.base_url = base_url
        
    def build(self) -> dict[str, Callable]:
        """Generate client and return operationId -> callable mapping."""
        logger.info("Generating OpenAPI client callables...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # 1. Write spec to temp file
                spec_file = Path(temp_dir) / "openapi.json"
                with open(spec_file, 'w') as f:
                    json.dump(self.spec, f, indent=2)
                
                logger.debug(f"Wrote OpenAPI spec to {spec_file}")
                
                # 2. Generate client using CLI
                cmd = [
                    sys.executable, "-m", "openapi_python_client", "generate",
                    "--path", str(spec_file),
                    "--output-path", temp_dir,
                    "--overwrite"
                ]
                
                logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    logger.error(f"Client generation failed with code {result.returncode}")
                    logger.error(f"STDOUT: {result.stdout}")
                    logger.error(f"STDERR: {result.stderr}")
                    raise RuntimeError(f"Client generation failed: {result.stderr}")
                
                logger.debug(f"Client generation successful: {result.stdout}")
                
                # 3. Find generated package
                client_dirs = [
                    d for d in Path(temp_dir).iterdir() 
                    if d.is_dir() and not d.name.startswith('.') and d.name != "__pycache__"
                ]
                
                if not client_dirs:
                    raise RuntimeError("No client package generated")
                
                client_dir = client_dirs[0]
                logger.debug(f"Found generated client directory: {client_dir}")
                
                # 4. Dynamically import generated client
                sys.path.insert(0, str(temp_dir))
                try:
                    client_module_name = f"{client_dir.name}.client"
                    api_module_name = f"{client_dir.name}.api"
                    
                    logger.debug(f"Importing client module: {client_module_name}")
                    client_module = importlib.import_module(client_module_name)
                    
                    logger.debug(f"Importing API module: {api_module_name}")
                    # Import to ensure the module is available, though we import specific functions separately
                    importlib.import_module(api_module_name)
                    
                    # Find and import all API function modules
                    api_functions = {}
                    api_dir = client_dir / "api"
                    
                    # Look for API function files
                    for api_file in api_dir.rglob("*.py"):
                        if api_file.name == "__init__.py":
                            continue
                            
                        # Get relative path and convert to module name
                        rel_path = api_file.relative_to(client_dir)
                        module_parts = list(rel_path.with_suffix("").parts)
                        function_module_name = f"{client_dir.name}.{'.'.join(module_parts)}"
                        
                        logger.debug(f"Importing API function module: {function_module_name}")
                        try:
                            func_module = importlib.import_module(function_module_name)
                            
                            # Extract functions from this module
                            for item_name in dir(func_module):
                                if not item_name.startswith('_'):
                                    item = getattr(func_module, item_name)
                                    # Only include actual API function callables (not imports)
                                    if (callable(item) and 
                                        hasattr(item, '__module__') and 
                                        item.__module__ == function_module_name and
                                        item_name in ['asyncio', 'sync', 'asyncio_detailed', 'sync_detailed']):
                                        logger.debug(f"  Found API function: {item_name} in {function_module_name}")
                                        # Use the module filename as the key (e.g., 'get_post')
                                        function_key = api_file.stem
                                        api_functions[f"{function_key}_{item_name}"] = item
                                        
                        except Exception as e:
                            logger.debug(f"Could not import {function_module_name}: {e}")
                    
                    logger.debug(f"Found {len(api_functions)} API functions total")
                    
                    # 5. Create client instance
                    client_class = getattr(client_module, "Client", None)
                    if not client_class:
                        client_class = getattr(client_module, "AuthenticatedClient", None)
                    
                    if not client_class:
                        raise RuntimeError("Could not find Client or AuthenticatedClient class")
                    
                    logger.debug(f"Creating client instance with base_url: {self.base_url}")
                    client_instance = client_class(base_url=self.base_url)
                    
                    # 6. Extract callables by operation_id
                    callables = self._extract_callables_from_functions(api_functions, client_instance)
                    logger.info(f"Successfully generated {len(callables)} OpenAPI callables")
                    return callables
                    
                finally:
                    sys.path.remove(str(temp_dir))
                    
            except subprocess.TimeoutExpired:
                logger.error("Client generation timed out after 60 seconds")
                raise RuntimeError("Client generation timed out")
            except Exception as e:
                logger.error(f"Error during client generation: {e}")
                raise

    def _extract_callables(self, api_module, client_instance) -> dict[str, Callable]:
        """Extract operation_id -> callable mapping from generated API."""
        callables = {}
        
        logger.debug("Extracting callables from generated API module")
        
        # Check if api_module has submodules (by tag)
        for attr_name in dir(api_module):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(api_module, attr_name)
            
            # Check if it's a submodule (by checking if it has __file__ attribute)
            if hasattr(attr, '__file__'):
                logger.debug(f"Processing tag module: {attr_name}")
                self._extract_callables_from_module(attr, client_instance, callables)
            
            # Also check if it's directly a callable function
            elif callable(attr):
                operation_id = self._get_operation_id(attr, attr_name)
                if operation_id:
                    logger.debug(f"Found callable for operation_id: {operation_id}")
                    bound_callable = self._create_bound_callable(attr, client_instance)
                    callables[operation_id] = bound_callable
        
        logger.debug(f"Extracted {len(callables)} callables total")
        return callables
    
    def _extract_callables_from_functions(self, api_functions: dict, client_instance) -> dict[str, Callable]:
        """Extract callables from a dictionary of API functions."""
        callables = {}
        
        logger.debug("Extracting callables from API functions")
        
        for func_name, func in api_functions.items():
            # Extract operation_id from function name (e.g., 'get_post_asyncio' -> 'get_post')
            # Prefer async versions
            if func_name.endswith('_asyncio'):
                operation_id = func_name.replace('_asyncio', '')
                logger.debug(f"Found callable for operation_id: {operation_id}")
                # Create bound callable that includes client
                bound_callable = self._create_bound_callable(func, client_instance)
                callables[operation_id] = bound_callable
        
        logger.debug(f"Extracted {len(callables)} callables from functions")
        return callables
    
    def _extract_callables_from_module(self, module, client_instance, callables: dict):
        """Extract callables from a specific module."""
        for func_name in dir(module):
            if func_name.startswith('_'):
                continue
            
            func = getattr(module, func_name)
            if not callable(func):
                continue
            
            # Get operation_id from function metadata
            operation_id = self._get_operation_id(func, func_name)
            if operation_id:
                logger.debug(f"Found callable for operation_id: {operation_id}")
                # Create bound callable that includes client
                bound_callable = self._create_bound_callable(func, client_instance)
                callables[operation_id] = bound_callable
    
    def _get_operation_id(self, func: Callable, func_name: str) -> str | None:
        """Extract operation_id from function metadata or derive from name."""
        # First try to get from function attributes (if added by generator)
        if hasattr(func, 'operation_id'):
            return func.operation_id
        
        # Try to get from docstring
        if func.__doc__:
            lines = func.__doc__.strip().split('\n')
            for line in lines:
                if 'operation_id' in line.lower():
                    # Try to extract operation_id from docstring
                    parts = line.split(':')
                    if len(parts) > 1:
                        return parts[1].strip()
        
        # Try to match with our OpenAPI spec operations
        for path_data in self.spec.get('paths', {}).values():
            for method_data in path_data.values():
                if isinstance(method_data, dict) and 'operationId' in method_data:
                    op_id = method_data['operationId']
                    # Convert operation_id to function name format and compare
                    expected_func_name = self._operation_id_to_func_name(op_id)
                    if expected_func_name == func_name:
                        return op_id
        
        # Fallback: use function name as operation_id
        logger.debug(f"Using function name as operation_id: {func_name}")
        return func_name
    
    def _operation_id_to_func_name(self, operation_id: str) -> str:
        """Convert operation_id to expected function name format."""
        # This is a simplified conversion - the actual logic depends on
        # how openapi-python-client converts operation IDs to function names
        return operation_id.lower().replace('-', '_').replace(' ', '_')
    
    def _create_bound_callable(self, func: Callable, client_instance) -> Callable:
        """Create a bound callable that includes the client instance."""
        async def bound_callable(**kwargs):
            # Remove any FastMCP-specific arguments that the generated client won't expect
            clean_kwargs = {k: v for k, v in kwargs.items() if k != 'context'}
            
            # Call the generated function with the client
            return await func(client=client_instance, **clean_kwargs)
        
        # Copy metadata from original function
        bound_callable.__name__ = getattr(func, '__name__', 'unknown')
        bound_callable.__doc__ = getattr(func, '__doc__', None)
        
        return bound_callable


# Export public symbols
__all__ = [
    "OASCallableFactory",
]