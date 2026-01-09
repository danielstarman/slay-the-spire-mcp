"""MCP tool implementations.

Exposes game state and actions as MCP tools:
- get_game_state: Return current game state
- play_card: Play a card by index, optionally targeting a monster
- end_turn: End the current turn
- choose: Make a choice (card reward, event option, etc.)
- potion: Use or discard a potion
"""

from __future__ import annotations

from typing import Any

from slay_the_spire_mcp.models import GameState
from slay_the_spire_mcp.state import GameStateManager, TCPListener


class ToolError(Exception):
    """Exception raised when a tool operation fails.

    This exception is used for validation errors and precondition failures
    that should be reported back to the MCP client as tool errors.
    """

    pass


def _check_game_state(state_manager: GameStateManager) -> GameState:
    """Check that a game state exists and return it.

    Args:
        state_manager: The state manager to check

    Returns:
        The current game state

    Raises:
        ToolError: If no game state exists
    """
    state = state_manager.get_current_state()
    if state is None:
        raise ToolError("No game state available. Game may not be connected.")
    return state


def _check_in_combat(state: GameState) -> None:
    """Check that the game is currently in combat.

    Args:
        state: The current game state

    Raises:
        ToolError: If not in combat
    """
    # Check for combat state or screen_state indicating combat
    is_combat = state.combat_state is not None or (
        isinstance(state.screen_state, dict)
        and state.screen_state.get("name") == "COMBAT"
    )
    if not is_combat:
        raise ToolError(
            f"Not in combat. Current screen type: {state.screen_type}. "
            "This action can only be performed during combat."
        )


async def get_game_state(
    state_manager: GameStateManager,
    tcp_listener: TCPListener | None,  # noqa: ARG001 - kept for API consistency
) -> dict[str, Any] | None:
    """Get the current game state.

    Returns the full game state including deck, relics, potions, and if in
    combat, the current hand, monsters, and energy.

    Args:
        state_manager: The state manager to get state from
        tcp_listener: The TCP listener (unused but passed for API consistency)

    Returns:
        The current game state as a dictionary, or None if no state exists
    """
    state = state_manager.get_current_state()
    if state is None:
        return None

    # Convert to dict using Pydantic's model_dump
    return state.model_dump()


async def play_card(
    state_manager: GameStateManager,
    tcp_listener: TCPListener,
    card_index: int,
    target_index: int | None = None,
) -> dict[str, Any]:
    """Play a card from hand.

    Plays the card at the specified index in the player's hand. If the card
    requires a target (like Strike), provide the target_index of the monster.

    Args:
        state_manager: The state manager to get state from
        tcp_listener: The TCP listener to send commands through
        card_index: Index of the card in hand (0-indexed)
        target_index: Index of the target monster (0-indexed), if required

    Returns:
        Dictionary with success status and optional error message

    Raises:
        ToolError: If not in combat, card index invalid, or no game state
    """
    state = _check_game_state(state_manager)
    _check_in_combat(state)

    # Validate card index
    if card_index < 0:
        raise ToolError(
            f"Invalid card index: {card_index}. Index must be non-negative."
        )

    if state.combat_state is not None:
        hand_size = len(state.combat_state.hand)
        if card_index >= hand_size:
            raise ToolError(
                f"Invalid card index: {card_index}. Hand has {hand_size} cards (indices 0-{hand_size - 1})."
            )

    # Build command
    command: dict[str, Any] = {
        "action": "PLAY",
        "card_index": card_index,
    }
    if target_index is not None:
        command["target_index"] = target_index

    # Send command
    success = await tcp_listener.send_command(command)
    if not success:
        return {"success": False, "error": "Failed to send command to game."}

    return {"success": True}


async def end_turn(
    state_manager: GameStateManager,
    tcp_listener: TCPListener,
) -> dict[str, Any]:
    """End the current turn.

    Ends the player's turn in combat, allowing monsters to act.

    Args:
        state_manager: The state manager to get state from
        tcp_listener: The TCP listener to send commands through

    Returns:
        Dictionary with success status and optional error message

    Raises:
        ToolError: If not in combat or no game state
    """
    state = _check_game_state(state_manager)
    _check_in_combat(state)

    # Send command
    command = {"action": "END"}
    success = await tcp_listener.send_command(command)
    if not success:
        return {"success": False, "error": "Failed to send command to game."}

    return {"success": True}


async def choose(
    state_manager: GameStateManager,
    tcp_listener: TCPListener,
    choice: int | str,
) -> dict[str, Any]:
    """Make a choice.

    Selects an option from a choice screen such as card rewards, event options,
    shop items, etc. Can specify the choice by index or name.

    Args:
        state_manager: The state manager to get state from
        tcp_listener: The TCP listener to send commands through
        choice: Index of the choice (0-indexed) or name of the choice

    Returns:
        Dictionary with success status and optional error message

    Raises:
        ToolError: If no choices available, choice invalid, or no game state
    """
    state = _check_game_state(state_manager)

    # Check that choices are available
    if not state.choice_list:
        raise ToolError(
            f"No choices available. Current screen type: {state.screen_type}. "
            "This action requires a screen with choices (card reward, event, etc.)."
        )

    # Validate choice index if numeric
    if isinstance(choice, int) and (choice < 0 or choice >= len(state.choice_list)):
        raise ToolError(
            f"Invalid choice index: {choice}. Available choices: 0-{len(state.choice_list) - 1} "
            f"({state.choice_list})"
        )

    # Build and send command
    command = {"action": "CHOOSE", "choice": choice}
    success = await tcp_listener.send_command(command)
    if not success:
        return {"success": False, "error": "Failed to send command to game."}

    return {"success": True}


async def potion(
    state_manager: GameStateManager,
    tcp_listener: TCPListener,
    action: str,
    slot: int,
    target_index: int | None = None,
) -> dict[str, Any]:
    """Use or discard a potion.

    Uses or discards the potion at the specified slot. Some potions require
    a target when used (like Fire Potion).

    Args:
        state_manager: The state manager to get state from
        tcp_listener: The TCP listener to send commands through
        action: Either "use" or "discard"
        slot: Index of the potion slot (0-indexed)
        target_index: Index of the target monster (0-indexed), if required

    Returns:
        Dictionary with success status and optional error message

    Raises:
        ToolError: If action invalid, slot invalid, potion not usable, or no game state
    """
    state = _check_game_state(state_manager)

    # Validate action
    if action not in ("use", "discard"):
        raise ToolError(
            f"Invalid potion action: '{action}'. Must be 'use' or 'discard'."
        )

    # Validate slot
    if slot < 0 or slot >= len(state.potions):
        raise ToolError(
            f"Invalid potion slot: {slot}. Available slots: 0-{len(state.potions) - 1}."
        )

    # Check if potion can be used/discarded
    potion_obj = state.potions[slot]
    if action == "use" and not potion_obj.can_use:
        raise ToolError(
            f"Cannot use potion in slot {slot} ('{potion_obj.name}'). "
            "The potion slot may be empty or the potion cannot be used currently."
        )
    if action == "discard" and not potion_obj.can_discard:
        raise ToolError(
            f"Cannot discard potion in slot {slot} ('{potion_obj.name}'). "
            "The potion slot may be empty."
        )

    # Build command
    command: dict[str, Any] = {
        "action": "POTION",
        "potion_action": action,
        "slot": slot,
    }
    if target_index is not None:
        command["target_index"] = target_index

    # Send command
    success = await tcp_listener.send_command(command)
    if not success:
        return {"success": False, "error": "Failed to send command to game."}

    return {"success": True}
