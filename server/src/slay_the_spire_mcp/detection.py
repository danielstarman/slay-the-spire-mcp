"""Decision point detection.

Identifies when the game is at a decision point requiring analysis.
Detects the type of decision, available choices, and relevant context.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from slay_the_spire_mcp.models import GameState


class DecisionType(Enum):
    """Types of decision points in Slay the Spire."""

    CARD_REWARD = "CARD_REWARD"
    COMBAT = "COMBAT"
    EVENT = "EVENT"
    SHOP = "SHOP"
    CAMPFIRE = "CAMPFIRE"
    MAP = "MAP"
    BOSS_RELIC = "BOSS_RELIC"
    CARD_SELECT = "CARD_SELECT"
    COMBAT_REWARD = "COMBAT_REWARD"
    HAND_SELECT = "HAND_SELECT"


class DecisionContext(BaseModel):
    """Context information for a decision point.

    Contains fields relevant to the specific decision type.
    Not all fields are populated for every decision type.
    """

    screen_type: str = ""

    # Card reward context
    can_skip: bool = False
    bowl_available: bool = False

    # Combat context
    can_end_turn: bool = False
    usable_potions: list[dict[str, Any]] | None = None
    monsters: list[dict[str, Any]] | None = None
    energy: int = 0
    max_energy: int = 0

    # Event context
    event_name: str | None = None
    event_id: str | None = None
    body_text: str = ""

    # Shop context
    gold: int = 0
    can_purge: bool = False
    purge_cost: int = 0
    shop_cards: list[dict[str, Any]] | None = None
    shop_relics: list[dict[str, Any]] | None = None
    shop_potions: list[dict[str, Any]] | None = None

    # Campfire context
    current_hp: int = 0
    max_hp: int = 0

    # Map context
    next_nodes: list[dict[str, Any]] | None = None

    # Boss relic context
    relic_options: list[dict[str, Any]] | None = None

    # Card select context (transform/remove/upgrade)
    selection_mode: str | None = None  # "transform", "purge", "upgrade"
    num_cards: int = 1
    any_number: bool = False

    # Combat reward context
    rewards: list[dict[str, Any]] | None = None

    # Hand select context
    selection_type: str | None = None
    can_pick_zero: bool = False


class DecisionPoint(BaseModel):
    """A decision point in the game requiring player input.

    Represents a moment where the player must make a choice,
    such as selecting a card reward, making a combat decision,
    or choosing an event option.
    """

    decision_type: DecisionType
    choices: list[str] = Field(default_factory=list)
    context: DecisionContext = Field(default_factory=DecisionContext)


def detect_decision_point(state: GameState) -> DecisionPoint | None:
    """Detect if the game is at a decision point.

    Analyzes the game state to determine if the player needs to make
    a decision, what type of decision it is, and what choices are available.

    Args:
        state: The current game state

    Returns:
        DecisionPoint if at a decision point, None otherwise
    """
    # Not in game = no decision point
    if not state.in_game:
        return None

    # Check screen_type first, then fallback to screen_state
    screen_type = state.screen_type

    # Check for specific screen types
    if screen_type == "CARD_REWARD":
        return _detect_card_reward(state)

    if screen_type == "EVENT":
        return _detect_event(state)

    if screen_type == "SHOP_SCREEN":
        return _detect_shop(state)

    if screen_type == "REST":
        return _detect_campfire(state)

    if screen_type == "MAP":
        return _detect_map(state)

    if screen_type == "BOSS_REWARD":
        return _detect_boss_relic(state)

    if screen_type == "GRID":
        return _detect_card_select(state)

    if screen_type == "COMBAT_REWARD":
        return _detect_combat_reward(state)

    if screen_type == "HAND_SELECT":
        return _detect_hand_select(state)

    # Check screen_state for combat (screen_type is often "NONE" during combat)
    if screen_type == "NONE" and state.combat_state is not None:
        screen_state_name = state.screen_state.get("name", "")
        if screen_state_name == "COMBAT" or state.combat_state.hand:
            return _detect_combat(state)

    # Main menu or other non-decision screens
    if screen_type == "MAIN_MENU":
        return None

    return None


def _detect_card_reward(state: GameState) -> DecisionPoint:
    """Detect card reward decision point."""
    choices = list(state.choice_list)

    # Check for Singing Bowl (bowl_available in screen_state)
    bowl_available = state.screen_state.get("bowl_available", False)

    context = DecisionContext(
        screen_type=state.screen_type,
        can_skip=True,  # Can always skip card rewards
        bowl_available=bowl_available,
    )

    return DecisionPoint(
        decision_type=DecisionType.CARD_REWARD,
        choices=choices,
        context=context,
    )


def _detect_combat(state: GameState) -> DecisionPoint:
    """Detect combat decision point."""
    combat = state.combat_state
    if combat is None:
        # Shouldn't happen, but handle gracefully
        return DecisionPoint(
            decision_type=DecisionType.COMBAT,
            choices=[],
            context=DecisionContext(screen_type="COMBAT"),
        )

    # Build choices from hand
    choices = [f"{card.name} ({card.cost})" for card in combat.hand]

    # Build usable potions list
    usable_potions = [
        {
            "name": p.name,
            "id": p.id,
            "requires_target": p.requires_target,
            "slot": i,
        }
        for i, p in enumerate(state.potions)
        if p.can_use
    ]

    # Build monster info
    monsters = [
        {
            "name": m.name,
            "id": m.id,
            "hp": m.current_hp,
            "max_hp": m.max_hp,
            "block": m.block,
            "intent": m.intent,
            "is_gone": m.is_gone,
        }
        for m in combat.monsters
        if not m.is_gone
    ]

    context = DecisionContext(
        screen_type="COMBAT",
        can_end_turn=True,
        usable_potions=usable_potions if usable_potions else None,
        monsters=monsters if monsters else None,
        energy=combat.energy,
        max_energy=combat.max_energy,
    )

    return DecisionPoint(
        decision_type=DecisionType.COMBAT,
        choices=choices,
        context=context,
    )


def _detect_event(state: GameState) -> DecisionPoint:
    """Detect event decision point."""
    choices = list(state.choice_list)

    event_name = state.screen_state.get("event_name")
    event_id = state.screen_state.get("event_id")
    body_text = state.screen_state.get("body_text", "")

    context = DecisionContext(
        screen_type=state.screen_type,
        event_name=event_name,
        event_id=event_id,
        body_text=body_text,
    )

    return DecisionPoint(
        decision_type=DecisionType.EVENT,
        choices=choices,
        context=context,
    )


def _detect_shop(state: GameState) -> DecisionPoint:
    """Detect shop decision point."""
    # Build choices from available shop items
    choices: list[str] = []

    shop_cards = state.screen_state.get("cards", [])
    shop_relics = state.screen_state.get("relics", [])
    shop_potions = state.screen_state.get("potions", [])

    for card in shop_cards:
        name = card.get("name", "Unknown")
        cost = card.get("cost", 0)
        choices.append(f"{name} ({cost}g)")

    for relic in shop_relics:
        name = relic.get("name", "Unknown")
        cost = relic.get("cost", 0)
        choices.append(f"{name} ({cost}g)")

    for potion in shop_potions:
        name = potion.get("name", "Unknown")
        cost = potion.get("cost", 0)
        choices.append(f"{name} ({cost}g)")

    can_purge = state.screen_state.get("can_purge", False)
    purge_cost = state.screen_state.get("purge_cost", 0)

    context = DecisionContext(
        screen_type=state.screen_type,
        gold=state.gold,
        can_purge=can_purge,
        purge_cost=purge_cost,
        shop_cards=shop_cards if shop_cards else None,
        shop_relics=shop_relics if shop_relics else None,
        shop_potions=shop_potions if shop_potions else None,
    )

    return DecisionPoint(
        decision_type=DecisionType.SHOP,
        choices=choices,
        context=context,
    )


def _detect_campfire(state: GameState) -> DecisionPoint:
    """Detect campfire/rest site decision point."""
    # Choices come from choice_list or screen_state rest_options
    choices = list(state.choice_list)
    if not choices:
        rest_options = state.screen_state.get("rest_options", [])
        choices = list(rest_options)

    context = DecisionContext(
        screen_type=state.screen_type,
        current_hp=state.hp,
        max_hp=state.max_hp,
    )

    return DecisionPoint(
        decision_type=DecisionType.CAMPFIRE,
        choices=choices,
        context=context,
    )


def _detect_map(state: GameState) -> DecisionPoint:
    """Detect map selection decision point."""
    # Get available next nodes
    next_nodes = state.screen_state.get("next_nodes", [])

    # Build choices from nodes
    choices: list[str] = []
    for node in next_nodes:
        x = node.get("x", 0)
        y = node.get("y", 0)
        symbol = node.get("symbol", "?")
        choices.append(f"({x},{y}) {symbol}")

    context = DecisionContext(
        screen_type=state.screen_type,
        next_nodes=next_nodes if next_nodes else None,
    )

    return DecisionPoint(
        decision_type=DecisionType.MAP,
        choices=choices,
        context=context,
    )


def _detect_boss_relic(state: GameState) -> DecisionPoint:
    """Detect boss relic choice decision point."""
    choices = list(state.choice_list)

    # Get relic details from screen_state
    relic_options = state.screen_state.get("relics", [])

    context = DecisionContext(
        screen_type=state.screen_type,
        can_skip=True,  # Can skip boss relics
        relic_options=relic_options if relic_options else None,
    )

    return DecisionPoint(
        decision_type=DecisionType.BOSS_RELIC,
        choices=choices,
        context=context,
    )


def _detect_card_select(state: GameState) -> DecisionPoint:
    """Detect card selection decision point (transform/remove/upgrade)."""
    choices = list(state.choice_list)

    # Determine selection mode
    for_transform = state.screen_state.get("for_transform", False)
    for_upgrade = state.screen_state.get("for_upgrade", False)
    for_purge = state.screen_state.get("for_purge", False)

    if for_transform:
        selection_mode = "transform"
    elif for_purge:
        selection_mode = "purge"
    elif for_upgrade:
        selection_mode = "upgrade"
    else:
        selection_mode = None

    num_cards = state.screen_state.get("num_cards", 1)
    any_number = state.screen_state.get("any_number", False)

    context = DecisionContext(
        screen_type=state.screen_type,
        selection_mode=selection_mode,
        num_cards=num_cards,
        any_number=any_number,
    )

    return DecisionPoint(
        decision_type=DecisionType.CARD_SELECT,
        choices=choices,
        context=context,
    )


def _detect_combat_reward(state: GameState) -> DecisionPoint:
    """Detect combat reward screen decision point."""
    choices = list(state.choice_list)

    rewards = state.screen_state.get("rewards", [])

    context = DecisionContext(
        screen_type=state.screen_type,
        rewards=rewards if rewards else None,
    )

    return DecisionPoint(
        decision_type=DecisionType.COMBAT_REWARD,
        choices=choices,
        context=context,
    )


def _detect_hand_select(state: GameState) -> DecisionPoint:
    """Detect hand selection decision point (during combat)."""
    choices = list(state.choice_list)

    selection_type = state.screen_state.get("selection_type")
    num_cards = state.screen_state.get("num_cards", 1)
    any_number = state.screen_state.get("any_number", False)
    can_pick_zero = state.screen_state.get("can_pick_zero", False)

    context = DecisionContext(
        screen_type=state.screen_type,
        selection_type=selection_type,
        num_cards=num_cards,
        any_number=any_number,
        can_pick_zero=can_pick_zero,
    )

    return DecisionPoint(
        decision_type=DecisionType.HAND_SELECT,
        choices=choices,
        context=context,
    )
