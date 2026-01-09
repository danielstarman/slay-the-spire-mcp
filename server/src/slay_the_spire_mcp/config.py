"""Configuration management for Slay the Spire MCP Server.

This module provides centralized configuration with support for:
- Environment variables (primary)
- Sensible defaults for all settings
- Type validation via Pydantic
- Easy testing through config overrides

Environment Variables:
    STS_TCP_HOST: TCP host for bridge connection (default: 127.0.0.1)
    STS_TCP_PORT: TCP port for bridge connection (default: 7777)
    STS_HTTP_PORT: HTTP port for MCP server (default: 8000)
    STS_WS_PORT: WebSocket port for overlay (default: 31337)
    STS_LOG_LEVEL: Logging level (default: INFO)
    STS_MOCK_MODE: Enable mock mode (default: false)

Usage:
    from slay_the_spire_mcp.config import get_config, Config

    # Get the singleton config instance
    config = get_config()

    # Access settings
    tcp_port = config.tcp_port
    log_level = config.log_level

    # For testing, create a custom config
    test_config = Config(tcp_port=8888, mock_mode=True)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration with environment variable support.

    All settings can be overridden via environment variables prefixed with STS_.
    For example, STS_TCP_PORT=8888 sets tcp_port to 8888.

    Attributes:
        tcp_host: Host address for TCP listener (bridge connection)
        tcp_port: Port for TCP listener (bridge connection)
        http_port: Port for MCP HTTP server
        ws_port: Port for WebSocket overlay communication
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        mock_mode: Enable mock mode for development/testing
        mock_fixture: Path to fixture file/directory for mock mode
        mock_delay_ms: Delay between states in mock sequence replay
    """

    model_config = SettingsConfigDict(
        env_prefix="STS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Network configuration
    tcp_host: str = Field(
        default="127.0.0.1",
        description="Host address for TCP listener (bridge connection)",
    )
    tcp_port: int = Field(
        default=7777,
        ge=1,
        le=65535,
        description="Port for TCP listener (bridge connection)",
    )
    http_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port for MCP HTTP server",
    )
    ws_port: int = Field(
        default=31337,
        ge=1,
        le=65535,
        description="Port for WebSocket overlay communication",
    )

    # Logging configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Transport configuration
    transport: Literal["http", "stdio"] = Field(
        default="http",
        description="MCP transport type: 'http' for streamable-http, 'stdio' for stdio",
    )

    # Mock mode configuration
    mock_mode: bool = Field(
        default=False,
        description="Enable mock mode for development/testing",
    )
    mock_fixture: str | None = Field(
        default=None,
        description="Path to fixture file/directory for mock mode",
    )
    mock_delay_ms: int = Field(
        default=100,
        ge=0,
        description="Delay between states in mock sequence replay (milliseconds)",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: Any) -> Any:
        """Normalize log level to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @model_validator(mode="after")
    def validate_mock_mode(self) -> Config:
        """Validate that mock_fixture is set when mock_mode is enabled."""
        if self.mock_mode and not self.mock_fixture:
            raise ValueError(
                "mock_fixture must be set when mock_mode is enabled. "
                "Set STS_MOCK_FIXTURE environment variable."
            )
        return self

    def setup_logging(self) -> None:
        """Configure logging based on config settings."""
        logging.basicConfig(
            level=getattr(logging, self.log_level, logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for logging/debugging.

        Returns:
            Dictionary of all config values
        """
        return {
            "tcp_host": self.tcp_host,
            "tcp_port": self.tcp_port,
            "http_port": self.http_port,
            "ws_port": self.ws_port,
            "log_level": self.log_level,
            "transport": self.transport,
            "mock_mode": self.mock_mode,
            "mock_fixture": self.mock_fixture,
            "mock_delay_ms": self.mock_delay_ms,
        }


# Module-level singleton instance
_config_instance: Config | None = None


def get_config() -> Config:
    """Get the singleton configuration instance.

    Creates the config on first call, caching it for subsequent calls.
    The config is loaded from environment variables and optional .env file.

    Returns:
        The Config singleton instance

    Note:
        For testing, use set_config() to inject a test configuration,
        or call reset_config() to force reloading from environment.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def set_config(config: Config) -> None:
    """Set the configuration instance (primarily for testing).

    Args:
        config: Config instance to use as the singleton
    """
    global _config_instance
    _config_instance = config


def reset_config() -> None:
    """Reset the configuration singleton.

    Forces the next get_config() call to reload from environment.
    Useful for testing different configurations.
    """
    global _config_instance
    _config_instance = None


# Legacy environment variable support for backward compatibility
# These functions read from the old-style env vars if the new ones aren't set


def _get_legacy_env(new_var: str, legacy_var: str, default: str) -> str:
    """Get value from new env var, falling back to legacy var.

    Args:
        new_var: New-style environment variable name (e.g., STS_TCP_PORT)
        legacy_var: Legacy environment variable name (e.g., TCP_PORT)
        default: Default value if neither is set

    Returns:
        Value from new_var, legacy_var, or default (in that priority order)
    """
    value = os.environ.get(new_var)
    if value is not None:
        return value
    legacy_value = os.environ.get(legacy_var)
    if legacy_value is not None:
        return legacy_value
    return default
