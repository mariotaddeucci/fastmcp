"""Tests for the CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import fastmcp.cli.run
from fastmcp.cli import cli

# Set up test runner
runner = CliRunner()


@pytest.fixture
def mock_console():
    """Mock the rich console to test output."""
    with patch("fastmcp.cli.cli.console") as mock_console:
        yield mock_console


@pytest.fixture
def mock_logger():
    """Mock the logger to test logging."""
    with patch("fastmcp.cli.cli.logger") as mock_logger:
        yield mock_logger


@pytest.fixture
def mock_exit():
    """Mock sys.exit to prevent tests from exiting."""
    with patch("sys.exit") as mock_exit:
        yield mock_exit


@pytest.fixture
def temp_python_file(tmp_path: Path) -> Path:
    """Create a temporary Python file with a test server."""
    server_code = """
from mcp import Server

class TestServer(Server):
    name = "test_server"
    dependencies = ["package1", "package2"]

    def run(self, **kwargs):
        print("Running server with", kwargs)

mcp = TestServer()
server = TestServer()
app = TestServer()
custom_server = TestServer()
"""
    file_path = tmp_path / "test_server.py"
    file_path.write_text(server_code)
    return file_path


@pytest.fixture
def temp_env_file(tmp_path: Path) -> Path:
    """Create a temporary .env file."""
    env_content = """
TEST_VAR1=value1
TEST_VAR2=value2
"""
    env_path = tmp_path / ".env"
    env_path.write_text(env_content)
    return env_path


class TestFilePathParsing:
    """Tests for file path parsing functionality."""

    def test_parse_simple_file_path_without_object_specification(self):
        """Test parsing a simple file path without object specification."""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.expanduser") as mock_expanduser,
            patch("pathlib.Path.resolve") as mock_resolve,
        ):
            mock_exists.return_value = True
            mock_is_file.return_value = True
            mock_expanduser.return_value = Path("file.py")
            mock_resolve.return_value = Path("file.py")

            path, obj = fastmcp.cli.run.parse_file_path("file.py")
            assert path == Path("file.py")
            assert obj is None

    def test_parse_file_path_with_object_specification(self):
        """Test parsing file path with object specification using colon syntax."""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.expanduser") as mock_expanduser,
            patch("pathlib.Path.resolve") as mock_resolve,
        ):
            mock_exists.return_value = True
            mock_is_file.return_value = True
            mock_expanduser.return_value = Path("file.py")
            mock_resolve.return_value = Path("file.py")

            path, obj = fastmcp.cli.run.parse_file_path("file.py:server")
            assert path == Path("file.py")
            assert obj == "server"

    def test_parse_windows_file_path_with_drive_letter(self):
        """Test parsing Windows file path with drive letter and object specification."""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.expanduser") as mock_expanduser,
            patch("pathlib.Path.resolve") as mock_resolve,
        ):
            mock_exists.return_value = True
            mock_is_file.return_value = True
            mock_expanduser.return_value = Path("C:/path/file.py")
            mock_resolve.return_value = Path("C:/path/file.py")

            path, obj = fastmcp.cli.run.parse_file_path("C:/path/file.py:server")
            assert path == Path("C:/path/file.py")
            assert obj == "server"

    def test_parse_directory_path_raises_error_and_exits(self, mock_exit):
        """Test parsing path that points to directory rather than file raises error."""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.expanduser") as mock_expanduser,
            patch("pathlib.Path.resolve") as mock_resolve,
            patch("fastmcp.cli.run.logger") as mock_logger,
        ):
            mock_exists.return_value = True
            mock_is_file.return_value = False
            mock_expanduser.return_value = Path("directory")
            mock_resolve.return_value = Path("directory")

            fastmcp.cli.run.parse_file_path("directory")
            mock_logger.error.assert_called_once()
            mock_exit.assert_called_once_with(1)


class TestRunCommandExecution:
    """Tests for the run command execution functionality."""

    def test_successful_server_execution_with_default_options(
        self, temp_python_file: Path
    ):
        """Test successful server execution using default transport and options."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
            patch("fastmcp.cli.run.logger") as mock_logger,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(cli.app, ["run", str(temp_python_file)])
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with()
            mock_logger.debug.assert_called_with(
                f'Found server "test_server" in {temp_python_file}'
            )

    def test_server_execution_with_sse_transport_option(self, temp_python_file: Path):
        """Test server execution with SSE transport option specified."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(
                cli.app, ["run", str(temp_python_file), "--transport", "sse"]
            )
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with(transport="sse")

    def test_server_execution_with_custom_host_binding(self, temp_python_file: Path):
        """Test server execution with custom host binding option."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(
                cli.app, ["run", str(temp_python_file), "--host", "0.0.0.0"]
            )
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with(host="0.0.0.0")

    def test_server_execution_with_custom_port_number(self, temp_python_file: Path):
        """Test server execution with custom port number specified."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(
                cli.app, ["run", str(temp_python_file), "--port", "8080"]
            )
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with(port=8080)

    def test_server_execution_with_debug_log_level(self, temp_python_file: Path):
        """Test server execution with debug log level specified."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(
                cli.app, ["run", str(temp_python_file), "--log-level", "DEBUG"]
            )
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with(log_level="DEBUG")

    def test_server_execution_with_all_transport_options_combined(
        self, temp_python_file: Path
    ):
        """Test server execution with all transport options specified together."""
        with (
            patch("fastmcp.cli.run.parse_file_path") as mock_parse,
            patch("fastmcp.cli.run.import_server") as mock_import,
        ):
            mock_parse.return_value = (temp_python_file, None)
            mock_server = MagicMock()
            mock_server.name = "test_server"
            mock_import.return_value = mock_server

            result = runner.invoke(
                cli.app,
                [
                    "run",
                    str(temp_python_file),
                    "--transport",
                    "sse",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8080",
                    "--log-level",
                    "DEBUG",
                ],
            )
            assert result.exit_code == 0
            mock_server.run.assert_called_once_with(
                transport="sse", host="0.0.0.0", port=8080, log_level="DEBUG"
            )


class TestServerArgumentInjection:
    """Tests for the server argument injection functionality via import_server_with_args."""

    def test_import_server_without_command_line_arguments(self, temp_python_file: Path):
        """Test importing server when no command line arguments are provided."""
        with patch("fastmcp.cli.run.import_server") as mock_import:
            mock_server = MagicMock()
            mock_import.return_value = mock_server

            result = fastmcp.cli.run.import_server_with_args(
                temp_python_file, None, None
            )

            assert result == mock_server
            mock_import.assert_called_once_with(temp_python_file, None)

    def test_import_server_with_command_line_arguments_modifies_sys_argv(
        self, temp_python_file: Path
    ):
        """Test importing server with command line arguments properly modifies and restores sys.argv."""
        import sys

        with patch("fastmcp.cli.run.import_server") as mock_import:
            mock_server = MagicMock()
            mock_import.return_value = mock_server

            original_argv = sys.argv[:]

            result = fastmcp.cli.run.import_server_with_args(
                temp_python_file, "custom_server", ["--config", "test.json", "--debug"]
            )

            assert result == mock_server
            mock_import.assert_called_once_with(temp_python_file, "custom_server")
            # Verify sys.argv was restored
            assert sys.argv == original_argv

    def test_import_server_restores_sys_argv_even_when_import_fails(
        self, temp_python_file: Path
    ):
        """Test that sys.argv is properly restored even when server import raises exception."""
        import sys

        with patch("fastmcp.cli.run.import_server") as mock_import:
            mock_import.side_effect = ImportError("Test error")

            original_argv = sys.argv[:]

            with pytest.raises(ImportError):
                fastmcp.cli.run.import_server_with_args(
                    temp_python_file, None, ["--config", "test.json"]
                )

            # Verify sys.argv was restored even after exception
            assert sys.argv == original_argv
