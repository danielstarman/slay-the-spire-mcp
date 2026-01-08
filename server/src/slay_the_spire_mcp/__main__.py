"""Entry point for the Slay the Spire MCP server.

Usage:
    python -m slay_the_spire_mcp
    uv run python -m slay_the_spire_mcp

Environment Variables:
    STS_TCP_HOST: TCP host for bridge connection (default: 127.0.0.1)
    STS_TCP_PORT: TCP port for bridge connection (default: 7777)
    STS_HTTP_PORT: HTTP port for MCP server (default: 8000)
    STS_WS_PORT: WebSocket port for overlay (default: 31337)
    STS_LOG_LEVEL: Logging level (default: INFO)
    STS_MOCK_MODE: Enable mock mode (default: false)
    STS_MOCK_FIXTURE: Path to fixture file/directory for mock mode
    STS_MOCK_DELAY_MS: Delay between states in mock replay (default: 100)

Legacy environment variables (deprecated, use STS_ prefix instead):
    MOCK_MODE: Set to "1" to enable mock mode
    MOCK_FIXTURE: Path to fixture file or directory
    MOCK_DELAY_MS: Delay between states in sequence replay
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from pydantic import ValidationError

from slay_the_spire_mcp.config import Config, get_config, reset_config
from slay_the_spire_mcp.mock import MockModeError, MockStateProvider
from slay_the_spire_mcp.state import GameStateManager


def _migrate_legacy_env_vars() -> None:
    """Migrate legacy environment variables to new STS_ prefixed versions.

    This provides backward compatibility with the old MOCK_MODE, MOCK_FIXTURE,
    and MOCK_DELAY_MS environment variables.
    """
    legacy_mappings = {
        "MOCK_MODE": "STS_MOCK_MODE",
        "MOCK_FIXTURE": "STS_MOCK_FIXTURE",
        "MOCK_DELAY_MS": "STS_MOCK_DELAY_MS",
        "LOG_LEVEL": "STS_LOG_LEVEL",
    }

    for legacy_var, new_var in legacy_mappings.items():
        legacy_value = os.environ.get(legacy_var)
        if legacy_value is not None and os.environ.get(new_var) is None:
            # Convert MOCK_MODE=1 to STS_MOCK_MODE=true
            if legacy_var == "MOCK_MODE":
                legacy_value = "true" if legacy_value.strip() == "1" else "false"
            os.environ[new_var] = legacy_value


async def run_mock_mode(config: Config, state_manager: GameStateManager) -> int:
    """Run the server in mock mode.

    Args:
        config: Application configuration
        state_manager: GameStateManager to update with mock states

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)

    try:
        # Create mock provider from config
        from pathlib import Path

        mock_provider = MockStateProvider(
            state_manager=state_manager,
            fixture_path=Path(config.mock_fixture) if config.mock_fixture else None,
            delay_ms=config.mock_delay_ms,
        )

        await mock_provider.initialize()

        # Display the loaded state
        current_state = state_manager.get_current_state()
        if current_state:
            logger.info(
                f"Mock state loaded: floor={current_state.floor}, "
                f"screen={current_state.screen_type}, "
                f"hp={current_state.hp}/{current_state.max_hp}"
            )
            print("Mock state loaded successfully!")
            print(f"  Floor: {current_state.floor}")
            print(f"  Screen: {current_state.screen_type}")
            print(f"  HP: {current_state.hp}/{current_state.max_hp}")
            print(f"  Gold: {current_state.gold}")
            print(f"  Deck size: {len(current_state.deck)}")
        else:
            logger.warning("No state loaded after mock initialization")

        return 0

    except MockModeError as e:
        logger.error(f"Mock mode error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point."""
    # Migrate legacy environment variables first
    _migrate_legacy_env_vars()

    # Reset config to pick up any migrated env vars
    reset_config()

    try:
        config = get_config()
    except ValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Setup logging from config
    config.setup_logging()

    print("Slay the Spire MCP Server v0.1.0")
    print("Configuration:")
    print(f"  TCP: {config.tcp_host}:{config.tcp_port}")
    print(f"  HTTP: {config.http_port}")
    print(f"  WebSocket: {config.ws_port}")
    print(f"  Log level: {config.log_level}")

    if config.mock_mode:
        print(f"  Mock mode: enabled (fixture: {config.mock_fixture})")
        state_manager = GameStateManager()
        return asyncio.run(run_mock_mode(config, state_manager))

    # Normal mode - not yet implemented
    print("Server not yet implemented.")
    print("Hint: Set STS_MOCK_MODE=true and STS_MOCK_FIXTURE=<path> for mock mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
