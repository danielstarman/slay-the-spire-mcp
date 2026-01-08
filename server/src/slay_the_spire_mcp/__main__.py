"""Entry point for the Slay the Spire MCP server.

Usage:
    python -m slay_the_spire_mcp
    uv run python -m slay_the_spire_mcp

Environment Variables:
    MOCK_MODE: Set to "1" to enable mock mode (load state from fixtures)
    MOCK_FIXTURE: Path to fixture file or directory (required if MOCK_MODE=1)
    MOCK_DELAY_MS: Delay between states in sequence replay (default: 100)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from slay_the_spire_mcp.mock import MockModeError, MockStateProvider
from slay_the_spire_mcp.state import GameStateManager


def setup_logging() -> None:
    """Configure logging based on environment."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def run_mock_mode(state_manager: GameStateManager) -> int:
    """Run the server in mock mode.

    Args:
        state_manager: GameStateManager to update with mock states

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)

    try:
        mock_provider = MockStateProvider.from_env(state_manager)
        if mock_provider is None:
            logger.error("Mock mode requested but MOCK_MODE!=1")
            return 1

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
    setup_logging()

    print("Slay the Spire MCP Server v0.1.0")

    # Check if mock mode is enabled
    mock_mode = os.environ.get("MOCK_MODE", "").strip() == "1"

    if mock_mode:
        print("Running in mock mode...")
        state_manager = GameStateManager()
        return asyncio.run(run_mock_mode(state_manager))

    # Normal mode - not yet implemented
    print("Server not yet implemented.")
    print("Hint: Set MOCK_MODE=1 and MOCK_FIXTURE=<path> for mock mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
