"""Tests for game state manager."""

from __future__ import annotations

import pytest

from slay_the_spire_mcp.models import GameState, MapNode
from slay_the_spire_mcp.state import GameStateManager
from slay_the_spire_mcp.tools import get_game_state


class TestStateManagerPlaceholder:
    """Placeholder tests for state module.

    These tests will be implemented when the state module is complete.
    """

    def test_state_module_exists(self) -> None:
        """Verify the state module can be imported."""
        from slay_the_spire_mcp import state

        assert state is not None


class TestFloorHistory:
    """Tests for floor history tracking."""

    def test_floor_history_records_visits(self) -> None:
        """Test that floor transitions are recorded in history."""
        manager = GameStateManager()

        # Floor 1 - Monster
        state1 = GameState(floor=1, screen_type="COMBAT", in_game=True)
        manager.update_state_sync(state1)

        # Floor 2 - Event (transition from floor 1)
        state2 = GameState(floor=2, screen_type="EVENT", in_game=True)
        manager.update_state_sync(state2)

        # Check history recorded floor 1
        history = manager.get_floor_history()
        assert len(history) == 1
        assert history[0].floor == 1

    def test_floor_history_with_map_data(self) -> None:
        """Test that floor history extracts symbols from map data."""
        manager = GameStateManager()

        # Floor 1 with map showing current node as 'M'
        node = MapNode(x=3, y=0, symbol="M")
        state1 = GameState(
            floor=1, in_game=True, current_node=(3, 0), map=[[node]]
        )
        manager.update_state_sync(state1)

        # Floor 2
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        history = manager.get_floor_history()
        assert len(history) == 1
        assert history[0].floor == 1
        assert history[0].symbol == "M"

    def test_floor_history_resets_on_new_run(self) -> None:
        """Test that floor history clears when starting a new run."""
        manager = GameStateManager()

        # First run
        state1 = GameState(floor=1, in_game=True)
        manager.update_state_sync(state1)
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        assert len(manager.get_floor_history()) >= 1

        # Simulate progressing to a later floor
        state3 = GameState(floor=5, in_game=True)
        manager.update_state_sync(state3)

        # New run (floor resets to 1 from a higher floor)
        state_new = GameState(floor=1, in_game=True)
        manager.update_state_sync(state_new)

        history = manager.get_floor_history()
        # History should be cleared
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_floor_history_in_get_game_state(self) -> None:
        """Test that floor history is included in get_game_state output."""
        manager = GameStateManager()

        # Create some history
        state1 = GameState(floor=1, in_game=True)
        manager.update_state_sync(state1)
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        # Get state via tool
        result = await get_game_state(manager, None)

        assert result is not None
        assert "floor_history" in result
        assert isinstance(result["floor_history"], list)

    def test_clear_state_clears_history(self) -> None:
        """Test that clear_state also clears floor history."""
        manager = GameStateManager()

        state1 = GameState(floor=1, in_game=True)
        manager.update_state_sync(state1)
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        assert len(manager.get_floor_history()) >= 1

        manager.clear_state()

        assert len(manager.get_floor_history()) == 0

    def test_floor_history_symbol_extraction_from_screen_state(self) -> None:
        """Test symbol extraction from screen_state current_node."""
        manager = GameStateManager()

        # Floor 1 with symbol in screen_state
        state1 = GameState(
            floor=1,
            in_game=True,
            screen_state={"current_node": {"x": 3, "y": 0, "symbol": "E"}},
        )
        manager.update_state_sync(state1)

        # Floor 2
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        history = manager.get_floor_history()
        assert len(history) == 1
        assert history[0].symbol == "E"

    def test_floor_history_symbol_inference_from_room_type(self) -> None:
        """Test symbol inference from room_type when no explicit symbol."""
        manager = GameStateManager()

        # Floor 1 - infer from room_type
        state1 = GameState(
            floor=1, in_game=True, screen_state={"room_type": "MonsterRoom"}
        )
        manager.update_state_sync(state1)

        # Floor 2
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        history = manager.get_floor_history()
        assert len(history) == 1
        assert history[0].symbol == "M"

    def test_floor_history_no_duplicate_same_floor(self) -> None:
        """Test that updating state on the same floor doesn't duplicate history."""
        manager = GameStateManager()

        # Floor 1
        state1 = GameState(floor=1, in_game=True)
        manager.update_state_sync(state1)

        # Still floor 1 (e.g., during combat)
        state1b = GameState(floor=1, in_game=True, hp=50)
        manager.update_state_sync(state1b)

        # Floor 2
        state2 = GameState(floor=2, in_game=True)
        manager.update_state_sync(state2)

        history = manager.get_floor_history()
        # Should only have one entry for floor 1
        assert len(history) == 1
        assert history[0].floor == 1
