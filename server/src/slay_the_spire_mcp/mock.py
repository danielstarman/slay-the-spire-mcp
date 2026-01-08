"""Mock game state provider for development and testing.

Provides:
- MockStateProvider: Loads game state from JSON fixtures
- MockModeError: Exception for mock mode errors

This module allows development and testing without the actual game running by:
1. Loading game state from JSON fixture files
2. Replaying sequences of states to simulate gameplay
3. Allowing manual state injection for testing specific scenarios
4. Can be triggered via environment variable or CLI flag
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from slay_the_spire_mcp.models import GameState

if TYPE_CHECKING:
    from slay_the_spire_mcp.state import GameStateManager

logger = logging.getLogger(__name__)


class MockModeError(Exception):
    """Exception raised for mock mode errors."""

    pass


class MockStateProvider:
    """Provides mock game state from fixture files.

    This class can replace the TCP listener in development/testing scenarios.
    It loads game state from JSON files and updates the GameStateManager.

    Usage:
        # Direct usage
        mock_provider = MockStateProvider(state_manager)
        await mock_provider.load_fixture(Path("fixture.json"))

        # From environment variables
        mock_provider = MockStateProvider.from_env(state_manager)
        if mock_provider:
            await mock_provider.initialize()
    """

    def __init__(
        self,
        state_manager: GameStateManager,
        fixture_path: Path | None = None,
        delay_ms: int = 100,
    ) -> None:
        """Initialize the mock state provider.

        Args:
            state_manager: GameStateManager to update with loaded states
            fixture_path: Optional path to fixture file or directory
            delay_ms: Delay in milliseconds between states during replay
        """
        self._state_manager = state_manager
        self._fixture_path = fixture_path
        self._delay_ms = delay_ms

    @classmethod
    def from_env(cls, state_manager: GameStateManager) -> MockStateProvider | None:
        """Create a MockStateProvider from environment variables.

        Environment variables:
            MOCK_MODE: Set to "1" to enable mock mode
            MOCK_FIXTURE: Path to fixture file or directory
            MOCK_DELAY_MS: Delay between states in sequence (default: 100)

        Args:
            state_manager: GameStateManager to update with loaded states

        Returns:
            MockStateProvider if MOCK_MODE=1, None otherwise

        Raises:
            MockModeError: If MOCK_MODE=1 but MOCK_FIXTURE is not set
        """
        mock_mode = os.environ.get("MOCK_MODE", "").strip()

        if mock_mode != "1":
            return None

        fixture_path_str = os.environ.get("MOCK_FIXTURE", "").strip()
        if not fixture_path_str:
            raise MockModeError(
                "MOCK_MODE=1 but MOCK_FIXTURE environment variable is not set. "
                "Please set MOCK_FIXTURE to a fixture file or directory path."
            )

        fixture_path = Path(fixture_path_str)
        delay_ms_str = os.environ.get("MOCK_DELAY_MS", "100").strip()

        try:
            delay_ms = int(delay_ms_str)
        except ValueError:
            logger.warning(
                f"Invalid MOCK_DELAY_MS value '{delay_ms_str}', using default 100"
            )
            delay_ms = 100

        logger.info(f"Mock mode enabled: fixture={fixture_path}, delay={delay_ms}ms")

        return cls(
            state_manager=state_manager,
            fixture_path=fixture_path,
            delay_ms=delay_ms,
        )

    async def initialize(self) -> None:
        """Initialize mock mode by loading the configured fixture.

        If fixture_path is a file, loads that single fixture.
        If fixture_path is a directory, replays all JSON files in it.

        Raises:
            MockModeError: If fixture_path is not set or doesn't exist
        """
        if self._fixture_path is None:
            raise MockModeError("No fixture path configured")

        if not self._fixture_path.exists():
            raise MockModeError(f"Fixture path not found: {self._fixture_path}")

        if self._fixture_path.is_file():
            await self.load_fixture(self._fixture_path)
        elif self._fixture_path.is_dir():
            await self.replay_directory(self._fixture_path, self._delay_ms)
        else:
            raise MockModeError(
                f"Fixture path is neither file nor directory: {self._fixture_path}"
            )

    async def load_fixture(self, fixture_path: Path) -> None:
        """Load game state from a JSON fixture file.

        The fixture file should contain game state JSON (not wrapped in
        a message envelope like {"type": "state", "data": {...}}).

        Args:
            fixture_path: Path to the JSON fixture file

        Raises:
            MockModeError: If file not found or JSON is invalid
        """
        if not fixture_path.exists():
            raise MockModeError(f"Fixture file not found: {fixture_path}")

        try:
            with open(fixture_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise MockModeError(
                f"Failed to parse JSON from fixture {fixture_path}: {e}"
            ) from e
        except OSError as e:
            raise MockModeError(
                f"Failed to read fixture file {fixture_path}: {e}"
            ) from e

        # Parse the game state from the fixture data
        game_state = self._parse_fixture_data(data)

        # Update the state manager
        await self._state_manager.update_state(game_state)

        logger.debug(
            f"Loaded fixture: {fixture_path.name} "
            f"(floor={game_state.floor}, screen={game_state.screen_type})"
        )

    async def replay_sequence(
        self, fixture_paths: list[Path], delay_ms: int = 100
    ) -> None:
        """Replay a sequence of fixtures with configurable delay.

        Args:
            fixture_paths: List of paths to JSON fixture files
            delay_ms: Delay in milliseconds between loading each fixture
        """
        if not fixture_paths:
            logger.debug("Empty fixture sequence, nothing to replay")
            return

        for i, fixture_path in enumerate(fixture_paths):
            await self.load_fixture(fixture_path)

            # Delay between states (except after the last one)
            if i < len(fixture_paths) - 1:
                await asyncio.sleep(delay_ms / 1000.0)

    async def replay_directory(self, directory_path: Path, delay_ms: int = 100) -> None:
        """Replay all JSON fixtures in a directory in alphabetical order.

        Args:
            directory_path: Path to directory containing JSON fixtures
            delay_ms: Delay in milliseconds between loading each fixture

        Raises:
            MockModeError: If directory doesn't exist
        """
        if not directory_path.exists():
            raise MockModeError(f"Fixture directory not found: {directory_path}")

        if not directory_path.is_dir():
            raise MockModeError(f"Path is not a directory: {directory_path}")

        # Get all JSON files sorted alphabetically
        json_files = sorted(directory_path.glob("*.json"))

        if not json_files:
            logger.debug(f"No JSON files found in {directory_path}")
            return

        logger.info(f"Replaying {len(json_files)} fixtures from {directory_path}")

        await self.replay_sequence(json_files, delay_ms)

    async def inject_state(self, game_state: GameState) -> None:
        """Directly inject a GameState object.

        This is useful for testing specific scenarios where you want to
        construct the state programmatically rather than load from file.

        Args:
            game_state: The GameState object to inject
        """
        await self._state_manager.update_state(game_state)
        logger.debug(
            f"Injected state: floor={game_state.floor}, screen={game_state.screen_type}"
        )

    def _parse_fixture_data(self, data: dict[str, Any]) -> GameState:
        """Parse fixture data into a GameState.

        Supports two fixture formats:

        1. CommunicationMod format (preferred):
        {
            "available_commands": [...],
            "ready_for_command": true,
            "in_game": true,
            "game_state": { ... game state fields ... }
        }

        2. Legacy format (raw game state, not message-wrapped):
        {
            "screen_type": "...",
            "floor": ...,
            ...
        }

        Args:
            data: Fixture data dictionary

        Returns:
            Parsed GameState object
        """
        from slay_the_spire_mcp.models import Card, Potion, Relic

        # Handle CommunicationMod format (game_state nested)
        if "game_state" in data:
            game_state_data = data.get("game_state", {})
            # in_game can be at top level or in game_state
            in_game = data.get("in_game", game_state_data.get("in_game", False))
        else:
            # Legacy format - data is the game state directly
            game_state_data = data
            in_game = data.get("in_game", False)

        # Parse deck cards
        deck_data = game_state_data.get("deck", [])
        deck = [
            Card(**card) if isinstance(card, dict) else Card(name=str(card))
            for card in deck_data
        ]

        # Parse relics
        relics_data = game_state_data.get("relics", [])
        relics = [
            Relic(**relic) if isinstance(relic, dict) else Relic(name=str(relic))
            for relic in relics_data
        ]

        # Parse potions
        potions_data = game_state_data.get("potions", [])
        potions = [
            Potion(**potion) if isinstance(potion, dict) else Potion(name=str(potion))
            for potion in potions_data
        ]

        # Handle screen_state - might be string or dict
        raw_screen_state = game_state_data.get("screen_state", {})
        if isinstance(raw_screen_state, str):
            screen_state = {"name": raw_screen_state} if raw_screen_state else {}
        elif isinstance(raw_screen_state, dict):
            screen_state = raw_screen_state
        else:
            screen_state = {}

        # HP field: CommunicationMod uses "current_hp", legacy uses "hp"
        hp = game_state_data.get("current_hp", game_state_data.get("hp", 0))

        # Block field: CommunicationMod uses "block", legacy uses "current_block"
        block = game_state_data.get("block", game_state_data.get("current_block", 0))

        return GameState(
            in_game=in_game,
            screen_type=game_state_data.get("screen_type", "NONE"),
            floor=game_state_data.get("floor", 0),
            act=game_state_data.get("act", 1),
            act_boss=game_state_data.get("act_boss"),
            seed=game_state_data.get("seed"),
            hp=hp,
            max_hp=game_state_data.get("max_hp", 0),
            gold=game_state_data.get("gold", 0),
            current_block=block,
            deck=deck,
            relics=relics,
            potions=potions,
            choice_list=game_state_data.get("choice_list", []),
            screen_state=screen_state,
        )
