"""MCP resource implementations.

Exposes subscribable game state resources:
- game://state: Current full game state
- game://player: Player stats (HP, gold, deck, relics)
- game://combat: Current combat state (monsters, hand, energy)
- game://map: Current map and path options
"""

from __future__ import annotations

from typing import Any

from slay_the_spire_mcp.state import GameStateManager


def get_state_resource(state_manager: GameStateManager) -> dict[str, Any] | None:
    """Get the full game state resource.

    Returns the complete game state as received from the bridge.

    Args:
        state_manager: The GameStateManager to get state from

    Returns:
        Dict containing full game state, or None if no state available
    """
    state = state_manager.get_current_state()
    if state is None:
        return None

    return _serialize_game_state(state)


def get_player_resource(state_manager: GameStateManager) -> dict[str, Any] | None:
    """Get the player stats resource.

    Returns player-specific information including HP, gold, deck, relics, and potions.

    Args:
        state_manager: The GameStateManager to get state from

    Returns:
        Dict containing player stats, or None if no state available
    """
    state = state_manager.get_current_state()
    if state is None:
        return None

    return {
        # Vital stats
        "hp": state.hp,
        "max_hp": state.max_hp,
        "gold": state.gold,
        "current_block": state.current_block,
        # Run progress
        "floor": state.floor,
        "act": state.act,
        # Collections
        "deck": [_serialize_card(card) for card in state.deck],
        "relics": [_serialize_relic(relic) for relic in state.relics],
        "potions": [_serialize_potion(potion) for potion in state.potions],
    }


def get_combat_resource(state_manager: GameStateManager) -> dict[str, Any] | None:
    """Get the current combat state resource.

    Returns combat-specific information including monsters, hand, and energy.
    Returns None if not currently in combat.

    Args:
        state_manager: The GameStateManager to get state from

    Returns:
        Dict containing combat state, or None if no state or not in combat
    """
    state = state_manager.get_current_state()
    if state is None:
        return None

    combat = state.combat_state
    if combat is None:
        return None

    return {
        # Turn info
        "turn": combat.turn,
        # Energy
        "energy": combat.energy,
        "max_energy": combat.max_energy,
        # Player combat stats
        "player_block": combat.player_block,
        "player_powers": combat.player_powers,
        # Monsters
        "monsters": [_serialize_monster(monster) for monster in combat.monsters],
        # Hand
        "hand": [_serialize_card(card) for card in combat.hand],
        # Piles
        "draw_pile": [_serialize_card(card) for card in combat.draw_pile],
        "discard_pile": [_serialize_card(card) for card in combat.discard_pile],
        "exhaust_pile": [_serialize_card(card) for card in combat.exhaust_pile],
        # Pile counts for quick reference
        "draw_pile_count": len(combat.draw_pile),
        "discard_pile_count": len(combat.discard_pile),
        "exhaust_pile_count": len(combat.exhaust_pile),
    }


def get_map_resource(state_manager: GameStateManager) -> dict[str, Any] | None:
    """Get the current map and path options resource.

    Returns map information including node layout and current position.
    Returns None if no map is available.

    Args:
        state_manager: The GameStateManager to get state from

    Returns:
        Dict containing map data, or None if no state or no map available
    """
    state = state_manager.get_current_state()
    if state is None:
        return None

    if state.map is None:
        return None

    return {
        # Position info
        "floor": state.floor,
        "act": state.act,
        "act_boss": state.act_boss,
        "current_node": state.current_node,
        # Map structure
        "map": [[_serialize_map_node(node) for node in row] for row in state.map],
    }


# ==============================================================================
# Serialization Helpers
# ==============================================================================


def _serialize_game_state(state: Any) -> dict[str, Any]:
    """Serialize a GameState to a dict.

    Args:
        state: The GameState to serialize

    Returns:
        Dict representation of the game state
    """
    result: dict[str, Any] = {
        "in_game": state.in_game,
        "screen_type": state.screen_type,
        "floor": state.floor,
        "act": state.act,
        "act_boss": state.act_boss,
        "seed": state.seed,
        "hp": state.hp,
        "max_hp": state.max_hp,
        "gold": state.gold,
        "current_block": state.current_block,
        "deck": [_serialize_card(card) for card in state.deck],
        "relics": [_serialize_relic(relic) for relic in state.relics],
        "potions": [_serialize_potion(potion) for potion in state.potions],
        "choice_list": state.choice_list,
        "screen_state": state.screen_state,
    }

    # Include combat state if present
    if state.combat_state is not None:
        result["combat_state"] = {
            "turn": state.combat_state.turn,
            "energy": state.combat_state.energy,
            "max_energy": state.combat_state.max_energy,
            "player_block": state.combat_state.player_block,
            "player_powers": state.combat_state.player_powers,
            "monsters": [_serialize_monster(m) for m in state.combat_state.monsters],
            "hand": [_serialize_card(c) for c in state.combat_state.hand],
            "draw_pile": [_serialize_card(c) for c in state.combat_state.draw_pile],
            "discard_pile": [
                _serialize_card(c) for c in state.combat_state.discard_pile
            ],
            "exhaust_pile": [
                _serialize_card(c) for c in state.combat_state.exhaust_pile
            ],
        }
    else:
        result["combat_state"] = None

    # Include map if present
    if state.map is not None:
        result["map"] = [
            [_serialize_map_node(node) for node in row] for row in state.map
        ]
        result["current_node"] = state.current_node
    else:
        result["map"] = None
        result["current_node"] = None

    return result


def _serialize_card(card: Any) -> dict[str, Any]:
    """Serialize a Card to a dict.

    Args:
        card: The Card to serialize

    Returns:
        Dict representation of the card
    """
    return {
        "name": card.name,
        "cost": card.cost,
        "type": card.type,
        "upgrades": card.upgrades,
        "id": card.id,
        "exhausts": card.exhausts,
        "ethereal": card.ethereal,
    }


def _serialize_relic(relic: Any) -> dict[str, Any]:
    """Serialize a Relic to a dict.

    Args:
        relic: The Relic to serialize

    Returns:
        Dict representation of the relic
    """
    return {
        "name": relic.name,
        "id": relic.id,
        "counter": relic.counter,
    }


def _serialize_potion(potion: Any) -> dict[str, Any]:
    """Serialize a Potion to a dict.

    Args:
        potion: The Potion to serialize

    Returns:
        Dict representation of the potion
    """
    return {
        "name": potion.name,
        "id": potion.id,
        "can_use": potion.can_use,
        "can_discard": potion.can_discard,
        "requires_target": potion.requires_target,
    }


def _serialize_monster(monster: Any) -> dict[str, Any]:
    """Serialize a Monster to a dict.

    Args:
        monster: The Monster to serialize

    Returns:
        Dict representation of the monster
    """
    return {
        "name": monster.name,
        "id": monster.id,
        "current_hp": monster.current_hp,
        "max_hp": monster.max_hp,
        "block": monster.block,
        "intent": monster.intent,
        "is_gone": monster.is_gone,
        "half_dead": monster.half_dead,
        "powers": monster.powers,
    }


def _serialize_map_node(node: Any) -> dict[str, Any]:
    """Serialize a MapNode to a dict.

    Args:
        node: The MapNode to serialize

    Returns:
        Dict representation of the map node
    """
    return {
        "x": node.x,
        "y": node.y,
        "symbol": node.symbol,
        "children": node.children,
    }
