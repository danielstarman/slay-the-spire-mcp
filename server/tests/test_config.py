"""Tests for configuration system.

Tests the configuration module's ability to:
- Load settings from environment variables
- Use sensible defaults when not configured
- Validate configuration values
- Handle configuration precedence (env vs defaults)
- Handle invalid configuration gracefully
"""

from __future__ import annotations

import os
from typing import Any, Generator

import pytest
from pydantic import ValidationError

from slay_the_spire_mcp.config import Config, get_config, reset_config, set_config


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Clean environment variables before and after each test."""
    # Save original environment
    original_env = {
        key: os.environ.get(key)
        for key in [
            "STS_TCP_HOST",
            "STS_TCP_PORT",
            "STS_HTTP_PORT",
            "STS_WS_PORT",
            "STS_LOG_LEVEL",
            "STS_TRANSPORT",
            "STS_MOCK_MODE",
            "STS_MOCK_FIXTURE",
            "STS_MOCK_DELAY_MS",
        ]
    }

    # Reset config singleton before test
    reset_config()

    # Clear all STS_ env vars
    for key in list(os.environ.keys()):
        if key.startswith("STS_"):
            del os.environ[key]

    yield

    # Restore original environment
    for key in list(os.environ.keys()):
        if key.startswith("STS_"):
            del os.environ[key]

    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value

    # Reset config singleton after test
    reset_config()


# ==============================================================================
# Happy Path Tests
# ==============================================================================


class TestConfigHappyPath:
    """Tests for normal configuration operation."""

    def test_default_values(self) -> None:
        """Defaults work when no config is set."""
        config = Config()

        assert config.tcp_host == "127.0.0.1"
        assert config.tcp_port == 7777
        assert config.http_port == 8000
        assert config.ws_port == 31337
        assert config.log_level == "INFO"
        assert config.mock_mode is False
        assert config.mock_fixture is None
        assert config.mock_delay_ms == 100

    def test_env_var_port_override(self) -> None:
        """Environment variables override default ports."""
        os.environ["STS_TCP_PORT"] = "8888"
        os.environ["STS_HTTP_PORT"] = "9000"
        os.environ["STS_WS_PORT"] = "40000"

        config = Config()

        assert config.tcp_port == 8888
        assert config.http_port == 9000
        assert config.ws_port == 40000

    def test_env_var_host_override(self) -> None:
        """Environment variable overrides default host."""
        os.environ["STS_TCP_HOST"] = "0.0.0.0"

        config = Config()

        assert config.tcp_host == "0.0.0.0"

    def test_env_var_log_level_override(self) -> None:
        """Environment variable overrides default log level."""
        os.environ["STS_LOG_LEVEL"] = "DEBUG"

        config = Config()

        assert config.log_level == "DEBUG"

    def test_log_level_case_insensitive(self) -> None:
        """Log level is normalized to uppercase."""
        os.environ["STS_LOG_LEVEL"] = "debug"

        config = Config()

        assert config.log_level == "DEBUG"

    def test_mock_mode_with_fixture(self) -> None:
        """Mock mode can be enabled with fixture path."""
        os.environ["STS_MOCK_MODE"] = "true"
        os.environ["STS_MOCK_FIXTURE"] = "/path/to/fixture.json"

        config = Config()

        assert config.mock_mode is True
        assert config.mock_fixture == "/path/to/fixture.json"

    def test_mock_delay_override(self) -> None:
        """Mock delay can be configured."""
        os.environ["STS_MOCK_MODE"] = "true"
        os.environ["STS_MOCK_FIXTURE"] = "/path/to/fixture.json"
        os.environ["STS_MOCK_DELAY_MS"] = "500"

        config = Config()

        assert config.mock_delay_ms == 500

    def test_transport_default_is_http(self) -> None:
        """Transport defaults to http."""
        config = Config()

        assert config.transport == "http"

    def test_transport_stdio_override(self) -> None:
        """Transport can be set to stdio via env var."""
        os.environ["STS_TRANSPORT"] = "stdio"

        config = Config()

        assert config.transport == "stdio"

    def test_transport_http_explicit(self) -> None:
        """Transport can be explicitly set to http via env var."""
        os.environ["STS_TRANSPORT"] = "http"

        config = Config()

        assert config.transport == "http"

    def test_config_to_dict(self) -> None:
        """Config can be converted to dictionary."""
        config = Config()

        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["tcp_host"] == "127.0.0.1"
        assert config_dict["tcp_port"] == 7777
        assert config_dict["http_port"] == 8000
        assert config_dict["ws_port"] == 31337
        assert config_dict["log_level"] == "INFO"
        assert config_dict["transport"] == "http"
        assert config_dict["mock_mode"] is False


class TestConfigSingleton:
    """Tests for configuration singleton behavior."""

    def test_get_config_returns_same_instance(self) -> None:
        """get_config returns the same instance on repeated calls."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_set_config_replaces_singleton(self) -> None:
        """set_config replaces the singleton instance."""
        custom_config = Config(tcp_port=9999)

        set_config(custom_config)
        retrieved = get_config()

        assert retrieved is custom_config
        assert retrieved.tcp_port == 9999

    def test_reset_config_clears_singleton(self) -> None:
        """reset_config forces reload on next get_config."""
        # Get initial config
        config1 = get_config()

        # Reset
        reset_config()

        # Change env
        os.environ["STS_TCP_PORT"] = "5555"

        # Get config again - should have new value
        config2 = get_config()

        assert config1 is not config2
        assert config2.tcp_port == 5555


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestConfigEdgeCases:
    """Tests for configuration edge cases."""

    def test_config_precedence_env_over_default(self) -> None:
        """Environment variables take precedence over defaults."""
        # Set env var
        os.environ["STS_TCP_PORT"] = "1234"

        config = Config()

        # Env var should win
        assert config.tcp_port == 1234

    def test_config_with_boolean_strings(self) -> None:
        """Boolean config accepts various string formats."""
        # Test "true"
        os.environ["STS_MOCK_MODE"] = "true"
        os.environ["STS_MOCK_FIXTURE"] = "/path"
        config = Config()
        assert config.mock_mode is True

        reset_config()

        # Test "1"
        os.environ["STS_MOCK_MODE"] = "1"
        os.environ["STS_MOCK_FIXTURE"] = "/path"
        config = Config()
        assert config.mock_mode is True

        reset_config()

        # Test "false"
        os.environ["STS_MOCK_MODE"] = "false"
        del os.environ["STS_MOCK_FIXTURE"]
        config = Config()
        assert config.mock_mode is False

    def test_all_log_levels_valid(self) -> None:
        """All standard log levels are accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            os.environ["STS_LOG_LEVEL"] = level
            config = Config()
            assert config.log_level == level
            reset_config()


# ==============================================================================
# Error Condition Tests
# ==============================================================================


class TestConfigErrors:
    """Tests for configuration error handling."""

    def test_invalid_port_type(self) -> None:
        """Non-numeric port raises validation error."""
        os.environ["STS_TCP_PORT"] = "not_a_number"

        with pytest.raises(ValidationError):
            Config()

    def test_port_out_of_range_low(self) -> None:
        """Port below valid range raises validation error."""
        os.environ["STS_TCP_PORT"] = "0"

        with pytest.raises(ValidationError):
            Config()

    def test_port_out_of_range_high(self) -> None:
        """Port above valid range raises validation error."""
        os.environ["STS_TCP_PORT"] = "99999"

        with pytest.raises(ValidationError):
            Config()

    def test_invalid_log_level(self) -> None:
        """Invalid log level raises validation error."""
        os.environ["STS_LOG_LEVEL"] = "INVALID_LEVEL"

        with pytest.raises(ValidationError):
            Config()

    def test_mock_mode_without_fixture(self) -> None:
        """Mock mode enabled without fixture raises validation error."""
        os.environ["STS_MOCK_MODE"] = "true"
        # Not setting STS_MOCK_FIXTURE

        with pytest.raises(ValidationError) as exc_info:
            Config()

        assert "mock_fixture" in str(exc_info.value).lower()

    def test_negative_mock_delay(self) -> None:
        """Negative mock delay raises validation error."""
        os.environ["STS_MOCK_MODE"] = "true"
        os.environ["STS_MOCK_FIXTURE"] = "/path"
        os.environ["STS_MOCK_DELAY_MS"] = "-100"

        with pytest.raises(ValidationError):
            Config()

    def test_invalid_transport(self) -> None:
        """Invalid transport value raises validation error."""
        os.environ["STS_TRANSPORT"] = "invalid"

        with pytest.raises(ValidationError):
            Config()


# ==============================================================================
# Integration Tests - Verify Config is APPLIED
# ==============================================================================


class TestConfigApplied:
    """Tests that verify configuration is actually applied, not just loaded."""

    def test_config_values_accessible(self) -> None:
        """Config values can be accessed after creation."""
        os.environ["STS_TCP_PORT"] = "4321"
        os.environ["STS_HTTP_PORT"] = "8765"

        config = Config()

        # Values should be accessible and correct
        assert config.tcp_port == 4321
        assert config.http_port == 8765

        # Should be usable in string formatting
        assert f"Listening on port {config.tcp_port}" == "Listening on port 4321"

    def test_setup_logging_called(self) -> None:
        """setup_logging configures logging module."""
        import logging

        os.environ["STS_LOG_LEVEL"] = "WARNING"
        config = Config()

        # Call setup_logging
        config.setup_logging()

        # Check root logger level was set
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_config_can_be_passed_to_functions(self) -> None:
        """Config can be passed to functions that use its values."""
        config = Config(tcp_port=5678)

        def use_port(cfg: Config) -> int:
            return cfg.tcp_port * 2

        result = use_port(config)
        assert result == 11356
