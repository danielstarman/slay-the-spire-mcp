"""Tests for MCP tool implementations.

Tests the MCP tools that expose game state and actions:
- get_game_state: Return current game state
- play_card: Play a card by index, optionally targeting a monster
- end_turn: End the current turn
- choose: Make a choice (card reward, event option, etc.)
- potion: Use or discard a potion
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from slay_the_spire_mcp.models import (
    Card,
    CombatState,
    GameState,
    Monster,
    Potion,
    Relic,
)
from slay_the_spire_mcp.state import GameStateManager, TCPListener
from slay_the_spire_mcp.tools import (
    get_game_state,
    play_card,
    end_turn,
    choose,
    potion,
    ToolError,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def mock_tcp_listener(state_manager: GameStateManager) -> TCPListener:
    """Create a mock TCP listener with send_command mocked."""
    listener = TCPListener(state_manager, host="127.0.0.1", port=7777)
    listener.send_command = AsyncMock(return_value=True)
    return listener


@pytest.fixture
def sample_game_state() -> GameState:
    """Sample game state for testing."""
    return GameState(
        in_game=True,
        screen_type="CARD_REWARD",
        floor=5,
        act=1,
        hp=65,
        max_hp=80,
        gold=99,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
            Card(name="Bash", cost=2, type="ATTACK"),
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[
            Potion(name="Fire Potion", id="Fire Potion", can_use=True, requires_target=True),
            Potion(name="Block Potion", id="Block Potion", can_use=True, requires_target=False),
            Potion(name="Potion Slot", id="Potion Slot", can_use=False, can_discard=False),
        ],
        choice_list=["Strike", "Pommel Strike", "Anger"],
    )


@pytest.fixture
def combat_game_state() -> GameState:
    """Sample combat game state for testing."""
    return GameState(
        in_game=True,
        screen_type="NONE",
        screen_state={"name": "COMBAT"},
        floor=3,
        act=1,
        hp=70,
        max_hp=80,
        gold=50,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
            Card(name="Bash", cost=2, type="ATTACK"),
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[
            Potion(name="Fire Potion", id="Fire Potion", can_use=True, requires_target=True),
            Potion(name="Block Potion", id="Block Potion", can_use=True, requires_target=False),
            Potion(name="Potion Slot", id="Potion Slot", can_use=False, can_discard=False),
        ],
        combat_state=CombatState(
            turn=1,
            energy=3,
            max_energy=3,
            hand=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Bash", cost=2, type="ATTACK"),
            ],
            draw_pile=[Card(name="Strike", cost=1, type="ATTACK")],
            discard_pile=[],
            monsters=[
                Monster(name="Jaw Worm", id="Jaw Worm", current_hp=44, max_hp=44, intent="ATTACK"),
            ],
        ),
    )


# ==============================================================================
# get_game_state Tests
# ==============================================================================


class TestGetGameState:
    """Tests for the get_game_state tool."""

    async def test_returns_current_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Returns the current game state when one exists."""
        state_manager.update_state_sync(sample_game_state)

        result = await get_game_state(state_manager, mock_tcp_listener)

        assert result is not None
        assert result["in_game"] is True
        assert result["screen_type"] == "CARD_REWARD"
        assert result["floor"] == 5
        assert result["hp"] == 65
        assert result["max_hp"] == 80
        assert result["gold"] == 99
        assert len(result["deck"]) == 3
        assert len(result["relics"]) == 1
        assert len(result["potions"]) == 3
        assert result["choice_list"] == ["Strike", "Pommel Strike", "Anger"]

    async def test_returns_none_when_no_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
    ) -> None:
        """Returns None when no game state exists."""
        result = await get_game_state(state_manager, mock_tcp_listener)

        assert result is None

    async def test_returns_combat_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Returns combat state with hand, monsters, etc."""
        state_manager.update_state_sync(combat_game_state)

        result = await get_game_state(state_manager, mock_tcp_listener)

        assert result is not None
        assert result["combat_state"] is not None
        combat = result["combat_state"]
        assert combat["turn"] == 1
        assert combat["energy"] == 3
        assert len(combat["hand"]) == 5
        assert len(combat["monsters"]) == 1
        assert combat["monsters"][0]["name"] == "Jaw Worm"


# ==============================================================================
# play_card Tests
# ==============================================================================


class TestPlayCard:
    """Tests for the play_card tool."""

    async def test_plays_card_without_target(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Plays a card that doesn't require a target."""
        state_manager.update_state_sync(combat_game_state)

        result = await play_card(
            state_manager, mock_tcp_listener, card_index=3, target_index=None
        )

        assert result["success"] is True
        mock_tcp_listener.send_command.assert_called_once()
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "PLAY"
        assert call_args["card_index"] == 3

    async def test_plays_card_with_target(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Plays a card that targets a monster."""
        state_manager.update_state_sync(combat_game_state)

        result = await play_card(
            state_manager, mock_tcp_listener, card_index=1, target_index=0
        )

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "PLAY"
        assert call_args["card_index"] == 1
        assert call_args["target_index"] == 0

    async def test_fails_when_not_in_combat(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Raises error when not in combat."""
        state_manager.update_state_sync(sample_game_state)

        with pytest.raises(ToolError) as exc_info:
            await play_card(state_manager, mock_tcp_listener, card_index=1)

        assert "not in combat" in str(exc_info.value).lower()

    async def test_fails_with_invalid_card_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Raises error when card index is out of range."""
        state_manager.update_state_sync(combat_game_state)

        with pytest.raises(ToolError) as exc_info:
            await play_card(state_manager, mock_tcp_listener, card_index=10)

        assert "invalid" in str(exc_info.value).lower() or "index" in str(exc_info.value).lower()

    async def test_fails_when_no_game_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
    ) -> None:
        """Raises error when no game state exists."""
        with pytest.raises(ToolError) as exc_info:
            await play_card(state_manager, mock_tcp_listener, card_index=1)

        assert "no game" in str(exc_info.value).lower() or "not connected" in str(exc_info.value).lower()

    async def test_fails_when_send_fails(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Returns failure when send_command fails."""
        state_manager.update_state_sync(combat_game_state)
        mock_tcp_listener.send_command = AsyncMock(return_value=False)

        result = await play_card(state_manager, mock_tcp_listener, card_index=1)

        assert result["success"] is False
        assert "failed" in result.get("error", "").lower()


# ==============================================================================
# end_turn Tests
# ==============================================================================


class TestEndTurn:
    """Tests for the end_turn tool."""

    async def test_ends_turn_in_combat(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Sends END command during combat."""
        state_manager.update_state_sync(combat_game_state)

        result = await end_turn(state_manager, mock_tcp_listener)

        assert result["success"] is True
        mock_tcp_listener.send_command.assert_called_once()
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "END"

    async def test_fails_when_not_in_combat(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Raises error when not in combat."""
        state_manager.update_state_sync(sample_game_state)

        with pytest.raises(ToolError) as exc_info:
            await end_turn(state_manager, mock_tcp_listener)

        assert "not in combat" in str(exc_info.value).lower()

    async def test_fails_when_no_game_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
    ) -> None:
        """Raises error when no game state exists."""
        with pytest.raises(ToolError) as exc_info:
            await end_turn(state_manager, mock_tcp_listener)

        assert "no game" in str(exc_info.value).lower() or "not connected" in str(exc_info.value).lower()

    async def test_fails_when_send_fails(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Returns failure when send_command fails."""
        state_manager.update_state_sync(combat_game_state)
        mock_tcp_listener.send_command = AsyncMock(return_value=False)

        result = await end_turn(state_manager, mock_tcp_listener)

        assert result["success"] is False


# ==============================================================================
# choose Tests
# ==============================================================================


class TestChoose:
    """Tests for the choose tool."""

    async def test_chooses_by_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Chooses an option by index."""
        state_manager.update_state_sync(sample_game_state)

        result = await choose(state_manager, mock_tcp_listener, choice=1)

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "CHOOSE"
        assert call_args["choice"] == 1

    async def test_chooses_by_name(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Chooses an option by name."""
        state_manager.update_state_sync(sample_game_state)

        result = await choose(state_manager, mock_tcp_listener, choice="Pommel Strike")

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "CHOOSE"
        assert call_args["choice"] == "Pommel Strike"

    async def test_fails_with_invalid_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Raises error when choice index is out of range."""
        state_manager.update_state_sync(sample_game_state)

        with pytest.raises(ToolError) as exc_info:
            await choose(state_manager, mock_tcp_listener, choice=10)

        assert "invalid" in str(exc_info.value).lower() or "out of range" in str(exc_info.value).lower()

    async def test_fails_when_no_choices_available(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Raises error when no choices are available."""
        # Combat state has empty choice_list
        state_manager.update_state_sync(combat_game_state)

        with pytest.raises(ToolError) as exc_info:
            await choose(state_manager, mock_tcp_listener, choice=0)

        assert "no choices" in str(exc_info.value).lower() or "no options" in str(exc_info.value).lower()

    async def test_fails_when_no_game_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
    ) -> None:
        """Raises error when no game state exists."""
        with pytest.raises(ToolError) as exc_info:
            await choose(state_manager, mock_tcp_listener, choice=0)

        assert "no game" in str(exc_info.value).lower() or "not connected" in str(exc_info.value).lower()

    async def test_fails_when_send_fails(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Returns failure when send_command fails."""
        state_manager.update_state_sync(sample_game_state)
        mock_tcp_listener.send_command = AsyncMock(return_value=False)

        result = await choose(state_manager, mock_tcp_listener, choice=0)

        assert result["success"] is False


# ==============================================================================
# potion Tests
# ==============================================================================


class TestPotion:
    """Tests for the potion tool."""

    async def test_uses_potion_without_target(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Uses a potion that doesn't require a target."""
        state_manager.update_state_sync(combat_game_state)

        result = await potion(
            state_manager, mock_tcp_listener, action="use", slot=1, target_index=None
        )

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "POTION"
        assert call_args["potion_action"] == "use"
        assert call_args["slot"] == 1

    async def test_uses_potion_with_target(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Uses a potion that targets a monster."""
        state_manager.update_state_sync(combat_game_state)

        result = await potion(
            state_manager, mock_tcp_listener, action="use", slot=0, target_index=0
        )

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "POTION"
        assert call_args["potion_action"] == "use"
        assert call_args["slot"] == 0
        assert call_args["target_index"] == 0

    async def test_discards_potion(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Discards a potion."""
        state_manager.update_state_sync(combat_game_state)

        result = await potion(
            state_manager, mock_tcp_listener, action="discard", slot=0
        )

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["action"] == "POTION"
        assert call_args["potion_action"] == "discard"
        assert call_args["slot"] == 0

    async def test_fails_with_invalid_action(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Raises error with invalid action."""
        state_manager.update_state_sync(combat_game_state)

        with pytest.raises(ToolError) as exc_info:
            await potion(state_manager, mock_tcp_listener, action="invalid", slot=0)

        assert "invalid" in str(exc_info.value).lower() or "action" in str(exc_info.value).lower()

    async def test_fails_with_invalid_slot(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Raises error when slot is out of range."""
        state_manager.update_state_sync(combat_game_state)

        with pytest.raises(ToolError) as exc_info:
            await potion(state_manager, mock_tcp_listener, action="use", slot=10)

        assert "invalid" in str(exc_info.value).lower() or "slot" in str(exc_info.value).lower()

    async def test_fails_when_potion_not_usable(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Raises error when trying to use an empty potion slot."""
        state_manager.update_state_sync(combat_game_state)

        # Slot 2 is an empty "Potion Slot" with can_use=False
        with pytest.raises(ToolError) as exc_info:
            await potion(state_manager, mock_tcp_listener, action="use", slot=2)

        assert "cannot" in str(exc_info.value).lower() or "not usable" in str(exc_info.value).lower()

    async def test_fails_when_no_game_state(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
    ) -> None:
        """Raises error when no game state exists."""
        with pytest.raises(ToolError) as exc_info:
            await potion(state_manager, mock_tcp_listener, action="use", slot=0)

        assert "no game" in str(exc_info.value).lower() or "not connected" in str(exc_info.value).lower()

    async def test_fails_when_send_fails(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Returns failure when send_command fails."""
        state_manager.update_state_sync(combat_game_state)
        mock_tcp_listener.send_command = AsyncMock(return_value=False)

        result = await potion(state_manager, mock_tcp_listener, action="use", slot=0)

        assert result["success"] is False


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestToolEdgeCases:
    """Edge case tests for all tools."""

    async def test_play_card_with_zero_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Card index 0 is valid (first card in hand)."""
        state_manager.update_state_sync(combat_game_state)

        result = await play_card(state_manager, mock_tcp_listener, card_index=0)

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["card_index"] == 0

    async def test_play_card_with_negative_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Negative card index raises error."""
        state_manager.update_state_sync(combat_game_state)

        with pytest.raises(ToolError):
            await play_card(state_manager, mock_tcp_listener, card_index=-1)

    async def test_choose_with_zero_index(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        sample_game_state: GameState,
    ) -> None:
        """Choice index 0 is valid (first choice)."""
        state_manager.update_state_sync(sample_game_state)

        result = await choose(state_manager, mock_tcp_listener, choice=0)

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["choice"] == 0

    async def test_potion_with_zero_slot(
        self,
        state_manager: GameStateManager,
        mock_tcp_listener: TCPListener,
        combat_game_state: GameState,
    ) -> None:
        """Potion slot 0 is valid (first slot)."""
        state_manager.update_state_sync(combat_game_state)

        result = await potion(state_manager, mock_tcp_listener, action="use", slot=0)

        assert result["success"] is True
        call_args = mock_tcp_listener.send_command.call_args[0][0]
        assert call_args["slot"] == 0
