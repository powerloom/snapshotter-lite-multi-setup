"""Basic tests for Powerloom Snapshotter CLI"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from snapshotter_cli import __version__, get_version_string
from snapshotter_cli.cli import app
from snapshotter_cli.utils.models import ChainConfig, PowerloomChainConfig


def test_version():
    """Test that version is defined and follows expected format."""
    # Just check that version exists and is a string
    assert isinstance(__version__, str)
    assert len(__version__) > 0
    # Check it follows semantic versioning pattern
    parts = __version__.split(".")
    assert len(parts) >= 2  # At least major.minor


def test_get_version_string():
    """Test that get_version_string returns a properly formatted version."""
    version_str = get_version_string()
    assert isinstance(version_str, str)
    assert __version__ in version_str  # Should contain base version


def test_cli_help():
    """Test that CLI help command works."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Powerloom Snapshotter Node Management CLI" in result.stdout


def test_cli_version():
    """Test that CLI version command works."""
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Powerloom Snapshotter CLI version:" in result.stdout


def test_list_command():
    """Test that list command works."""
    runner = CliRunner()
    # Mock the fetch_markets_config to avoid network calls
    with patch("snapshotter_cli.cli.fetch_markets_config") as mock_fetch:
        mock_fetch.return_value = []
        result = runner.invoke(app, ["list"])
        # Should fail gracefully when no markets config
        assert result.exit_code == 1


def test_status_command():
    """Test that status command works."""
    runner = CliRunner()
    # Mock the screen sessions check
    with patch("snapshotter_cli.cli.list_snapshotter_screen_sessions") as mock_list:
        mock_list.return_value = []
        with patch("snapshotter_cli.cli.fetch_markets_config") as mock_fetch:
            # Create a proper PowerloomChainConfig object
            chain_config = ChainConfig(name="TEST", chainId=1, rpcURL="http://test")
            powerloom_config = PowerloomChainConfig(
                powerloomChain=chain_config, dataMarkets=[]
            )
            mock_fetch.return_value = [powerloom_config]

            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "No running screen sessions found" in result.stdout
