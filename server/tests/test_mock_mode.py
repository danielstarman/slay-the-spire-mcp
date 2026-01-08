"""Tests for mock mode functionality.

Tests the server's ability to:
- Load game state from fixture files for development/testing
- Replay sequences of states to simulate gameplay
- Allow manual state injection for testing scenarios
- Be triggered via environment variables
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import json
from pathlib import Path
from typing import Any

import pytest

from slay_the_spire_mcp.mock import MockStateProvider, MockModeError
from slay_the_spire_mcp.state import GameStateManager
from slay_the_spire_mcp.models import GameState


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    # Navigate from server/tests to tests/fixtures/game_states
    return Path(__file__).parent.parent.parent / "tests" / "fixtures" / "game_states"


@pytest.fixture
def card_reward_fixture(fixtures_dir: Path) -> Path:
    """Path to the card_reward.json fixture."""
    return fixtures_dir / "card_reward.json"


@pytest.fixture
def combat_fixture(fixtures_dir: Path) -> Path:
    """Path to the combat.json fixture."""
    return fixtures_dir / "combat.json"


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def sample_game_state_dict() -> dict[str, Any]:
    """Sample game state as dictionary."""
    return {
        "in_game": True,
        "screen_type": "CARD_REWARD",
        "floor": 5,
        "act": 1,
        "hp": 65,
        "max_hp": 80,
        "gold": 99,
        "deck": [
            {"id": "Strike_R", "name": "Strike", "cost": 1, "type": "ATTACK", "upgraded": False}
        ],
        "relics": [{"id": "Burning Blood", "name": "Burning Blood", "counter": -1}],
        "potions": [],
        "choice_list": ["Strike", "Pommel Strike", "Anger"],
        "seed": 123456789,
        "class": "IRONCLAD",
        "ascension": 0,
    }


# ==============================================================================
# Happy Path Tests
# ==============================================================================


class TestMockModeHappyPath:
    """Tests for normal operation of mock mode."""

    async def test_load_state_from_fixture(
        self, state_manager: GameStateManager, card_reward_fixture: Path
    ) -> None:
        """Load a fixture file, GameStateManager has that state."""
        mock_provider = MockStateProvider(state_manager)

        # Load the fixture
        await mock_provider.load_fixture(card_reward_fixture)

        # Verify state was loaded
        current_state = state_manager.get_current_state()
        assert current_state is not None
        assert current_state.in_game is True
        assert current_state.screen_type == "CARD_REWARD"
        assert current_state.floor == 5
        assert current_state.hp == 65

    async def test_replay_state_sequence(
        self,
        state_manager: GameStateManager,
        card_reward_fixture: Path,
        combat_fixture: Path,
    ) -> None:
        """Given list of fixtures, replays them in order with configurable delay."""
        mock_provider = MockStateProvider(state_manager)

        # Track state changes
        states_received: list[GameState] = []

        def on_state(state: GameState) -> None:
            states_received.append(state)

        state_manager.on_state_change(on_state)

        # Replay sequence with minimal delay
        fixtures = [card_reward_fixture, combat_fixture]
        await mock_provider.replay_sequence(fixtures, delay_ms=10)

        # Verify both states were processed in order
        assert len(states_received) == 2
        assert states_received[0].screen_type == "CARD_REWARD"
        assert states_received[0].floor == 5
        assert states_received[1].screen_type == "NONE"  # Combat state
        assert states_received[1].floor == 3

    async def test_inject_state_manually(
        self, state_manager: GameStateManager
    ) -> None:
        """Directly inject a GameState object."""
        mock_provider = MockStateProvider(state_manager)

        # Create a GameState object
        game_state = GameState(
            in_game=True,
            screen_type="MAP",
            floor=10,
            act=2,
            hp=50,
            max_hp=80,
            gold=200,
        )

        # Inject the state
        await mock_provider.inject_state(game_state)

        # Verify state was injected
        current_state = state_manager.get_current_state()
        assert current_state is not None
        assert current_state.screen_type == "MAP"
        assert current_state.floor == 10
        assert current_state.act == 2
        assert current_state.hp == 50

    async def test_load_directory_of_fixtures(
        self, state_manager: GameStateManager, fixtures_dir: Path
    ) -> None:
        """Load all fixtures from a directory in alphabetical order."""
        mock_provider = MockStateProvider(state_manager)

        # Track state changes
        states_received: list[GameState] = []

        def on_state(state: GameState) -> None:
            states_received.append(state)

        state_manager.on_state_change(on_state)

        # Replay directory with minimal delay
        await mock_provider.replay_directory(fixtures_dir, delay_ms=10)

        # Should have loaded both fixtures (card_reward.json, combat.json in alpha order)
        assert len(states_received) == 2
        # card_reward.json comes before combat.json alphabetically
        assert states_received[0].screen_type == "CARD_REWARD"
        assert states_received[1].screen_type == "NONE"  # Combat


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestMockModeEdgeCases:
    """Tests for edge cases in mock mode."""

    async def test_load_nonexistent_fixture(
        self, state_manager: GameStateManager
    ) -> None:
        """Raises clear error with file path."""
        mock_provider = MockStateProvider(state_manager)

        nonexistent_path = Path("/nonexistent/fixture.json")

        with pytest.raises(MockModeError) as exc_info:
            await mock_provider.load_fixture(nonexistent_path)

        # Error message should include the file path
        assert str(nonexistent_path) in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    async def test_replay_empty_sequence(
        self, state_manager: GameStateManager
    ) -> None:
        """Empty sequence is no-op (doesn't crash)."""
        mock_provider = MockStateProvider(state_manager)

        # Track state changes
        states_received: list[GameState] = []

        def on_state(state: GameState) -> None:
            states_received.append(state)

        state_manager.on_state_change(on_state)

        # Replay empty sequence
        await mock_provider.replay_sequence([], delay_ms=10)

        # No states should have been received
        assert len(states_received) == 0
        assert state_manager.get_current_state() is None

    async def test_replay_empty_directory(
        self, state_manager: GameStateManager
    ) -> None:
        """Empty directory is no-op (doesn't crash)."""
        mock_provider = MockStateProvider(state_manager)

        # Create a temporary empty directory
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir)

            # Track state changes
            states_received: list[GameState] = []

            def on_state(state: GameState) -> None:
                states_received.append(state)

            state_manager.on_state_change(on_state)

            # Replay empty directory
            await mock_provider.replay_directory(empty_dir, delay_ms=10)

            # No states should have been received
            assert len(states_received) == 0

    async def test_load_invalid_json_fixture(
        self, state_manager: GameStateManager
    ) -> None:
        """Invalid JSON raises clear error."""
        mock_provider = MockStateProvider(state_manager)

        # Create a temporary file with invalid JSON
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{ invalid json here")
            temp_path = Path(f.name)

        try:
            with pytest.raises(MockModeError) as exc_info:
                await mock_provider.load_fixture(temp_path)

            # Error should mention JSON parsing
            assert "json" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()
        finally:
            temp_path.unlink()


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestMockModeIntegration:
    """Integration tests for mock mode with environment variables."""

    async def test_mock_mode_via_env_var(
        self,
        state_manager: GameStateManager,
        card_reward_fixture: Path,
    ) -> None:
        """Setting MOCK_MODE=1 and MOCK_FIXTURE=path loads that fixture."""
        # Save original env vars
        original_mock_mode = os.environ.get("MOCK_MODE")
        original_mock_fixture = os.environ.get("MOCK_FIXTURE")

        try:
            # Set env vars
            os.environ["MOCK_MODE"] = "1"
            os.environ["MOCK_FIXTURE"] = str(card_reward_fixture)

            # Create provider that reads from env vars
            mock_provider = MockStateProvider.from_env(state_manager)

            # Initialize (loads fixture from env var)
            await mock_provider.initialize()

            # Verify state was loaded
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.screen_type == "CARD_REWARD"
            assert current_state.floor == 5

        finally:
            # Restore original env vars
            if original_mock_mode is not None:
                os.environ["MOCK_MODE"] = original_mock_mode
            else:
                os.environ.pop("MOCK_MODE", None)

            if original_mock_fixture is not None:
                os.environ["MOCK_FIXTURE"] = original_mock_fixture
            else:
                os.environ.pop("MOCK_FIXTURE", None)

    async def test_mock_mode_with_directory_fixture(
        self,
        state_manager: GameStateManager,
        fixtures_dir: Path,
    ) -> None:
        """MOCK_FIXTURE can be a directory for sequence replay."""
        # Save original env vars
        original_mock_mode = os.environ.get("MOCK_MODE")
        original_mock_fixture = os.environ.get("MOCK_FIXTURE")
        original_mock_delay = os.environ.get("MOCK_DELAY_MS")

        try:
            # Set env vars
            os.environ["MOCK_MODE"] = "1"
            os.environ["MOCK_FIXTURE"] = str(fixtures_dir)
            os.environ["MOCK_DELAY_MS"] = "10"

            # Track state changes
            states_received: list[GameState] = []

            def on_state(state: GameState) -> None:
                states_received.append(state)

            state_manager.on_state_change(on_state)

            # Create provider from env vars
            mock_provider = MockStateProvider.from_env(state_manager)

            # Initialize (loads directory from env var)
            await mock_provider.initialize()

            # Verify both states were loaded
            assert len(states_received) == 2

        finally:
            # Restore original env vars
            if original_mock_mode is not None:
                os.environ["MOCK_MODE"] = original_mock_mode
            else:
                os.environ.pop("MOCK_MODE", None)

            if original_mock_fixture is not None:
                os.environ["MOCK_FIXTURE"] = original_mock_fixture
            else:
                os.environ.pop("MOCK_FIXTURE", None)

            if original_mock_delay is not None:
                os.environ["MOCK_DELAY_MS"] = original_mock_delay
            else:
                os.environ.pop("MOCK_DELAY_MS", None)

    async def test_mock_mode_not_enabled(
        self, state_manager: GameStateManager
    ) -> None:
        """When MOCK_MODE is not set, from_env returns None."""
        # Save and clear env vars
        original_mock_mode = os.environ.get("MOCK_MODE")

        try:
            os.environ.pop("MOCK_MODE", None)

            # from_env should return None when mock mode is not enabled
            result = MockStateProvider.from_env(state_manager)
            assert result is None

        finally:
            if original_mock_mode is not None:
                os.environ["MOCK_MODE"] = original_mock_mode

    async def test_mock_mode_missing_fixture_path(
        self, state_manager: GameStateManager
    ) -> None:
        """When MOCK_MODE=1 but MOCK_FIXTURE not set, raises error."""
        # Save original env vars
        original_mock_mode = os.environ.get("MOCK_MODE")
        original_mock_fixture = os.environ.get("MOCK_FIXTURE")

        try:
            os.environ["MOCK_MODE"] = "1"
            os.environ.pop("MOCK_FIXTURE", None)

            with pytest.raises(MockModeError) as exc_info:
                MockStateProvider.from_env(state_manager)

            assert "MOCK_FIXTURE" in str(exc_info.value)

        finally:
            if original_mock_mode is not None:
                os.environ["MOCK_MODE"] = original_mock_mode
            else:
                os.environ.pop("MOCK_MODE", None)

            if original_mock_fixture is not None:
                os.environ["MOCK_FIXTURE"] = original_mock_fixture
