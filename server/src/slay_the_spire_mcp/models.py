"""Game state data models.

Pydantic models for Slay the Spire game entities.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseGameModel(BaseModel):
    """Base model for all game entities.

    Configured to ignore extra fields that CommunicationMod may send
    but we don't model. This prevents validation errors when the mod
    sends additional fields.
    """

    model_config = ConfigDict(extra="ignore")


class Card(BaseGameModel):
    """A card in the player's deck or hand."""

    name: str
    cost: int = 0
    type: str = "UNKNOWN"
    upgrades: int = 0

    # Additional fields that may be present
    id: str | None = None
    exhausts: bool = False
    ethereal: bool = False


class Relic(BaseGameModel):
    """A relic the player has collected."""

    name: str
    id: str | None = None
    counter: int = -1


class Potion(BaseGameModel):
    """A potion in the player's potion slots."""

    name: str
    id: str | None = None
    can_use: bool = True
    can_discard: bool = True
    requires_target: bool = False


class Monster(BaseGameModel):
    """A monster in combat."""

    name: str
    id: str | None = None
    current_hp: int = 0
    max_hp: int = 0
    block: int = 0
    intent: str = "UNKNOWN"
    is_gone: bool = False
    half_dead: bool = False

    # Status effects
    powers: list[dict[str, Any]] = Field(default_factory=list)


class MapNode(BaseGameModel):
    """A node on the act map."""

    x: int
    y: int
    symbol: str = "?"
    children: list[tuple[int, int]] = Field(default_factory=list)


class GameState(BaseGameModel):
    """Complete game state received from the bridge.

    This model represents the full game state as sent by CommunicationMod/SpireBridge.
    """

    # Core game status
    in_game: bool = False
    screen_type: str = "NONE"

    # Run progress
    floor: int = 0
    act: int = 1
    act_boss: str | None = None
    seed: int | None = None

    # Player stats
    hp: int = 0
    max_hp: int = 0
    gold: int = 0
    current_block: int = 0

    # Collections
    deck: list[Card] = Field(default_factory=list)
    relics: list[Relic] = Field(default_factory=list)
    potions: list[Potion] = Field(default_factory=list)

    # Choice/screen specific
    choice_list: list[str] = Field(default_factory=list)
    screen_state: dict[str, Any] = Field(default_factory=dict)

    # Combat specific (only populated during combat)
    combat_state: CombatState | None = None

    # Map (only populated on map screen)
    map: list[list[MapNode]] | None = None
    current_node: tuple[int, int] | None = None


class CombatState(BaseGameModel):
    """Combat-specific state information."""

    turn: int = 0
    monsters: list[Monster] = Field(default_factory=list)
    hand: list[Card] = Field(default_factory=list)
    draw_pile: list[Card] = Field(default_factory=list)
    discard_pile: list[Card] = Field(default_factory=list)
    exhaust_pile: list[Card] = Field(default_factory=list)
    energy: int = 0
    max_energy: int = 3
    player_block: int = 0
    player_powers: list[dict[str, Any]] = Field(default_factory=list)


def parse_game_state_from_message(message: dict[str, Any]) -> GameState | None:
    """Parse a game state from a bridge message.

    The bridge sends messages with format:
    {
        "type": "state",
        "data": { ... game state fields ... }
    }

    Args:
        message: The parsed JSON message from the bridge

    Returns:
        GameState if message is a valid state message, None otherwise
    """
    if message.get("type") != "state":
        return None

    data = message.get("data", {})
    if not data:
        return None

    # Parse deck cards
    deck_data = data.get("deck", [])
    deck = [
        Card(**card) if isinstance(card, dict) else Card(name=str(card))
        for card in deck_data
    ]

    # Parse relics
    relics_data = data.get("relics", [])
    relics = [
        Relic(**relic) if isinstance(relic, dict) else Relic(name=str(relic))
        for relic in relics_data
    ]

    # Parse potions
    potions_data = data.get("potions", [])
    potions = [
        Potion(**potion) if isinstance(potion, dict) else Potion(name=str(potion))
        for potion in potions_data
    ]

    # Handle screen_state - CommunicationMod sometimes sends a string (e.g., "COMBAT")
    # instead of a dict. Normalize to dict format.
    raw_screen_state = data.get("screen_state", {})
    if isinstance(raw_screen_state, str):
        screen_state = {"name": raw_screen_state} if raw_screen_state else {}
    elif isinstance(raw_screen_state, dict):
        screen_state = raw_screen_state
    else:
        screen_state = {}

    return GameState(
        in_game=data.get("in_game", False),
        screen_type=data.get("screen_type", "NONE"),
        floor=data.get("floor", 0),
        act=data.get("act", 1),
        act_boss=data.get("act_boss"),
        seed=data.get("seed"),
        hp=data.get("hp", 0),
        max_hp=data.get("max_hp", 0),
        gold=data.get("gold", 0),
        current_block=data.get("current_block", 0),
        deck=deck,
        relics=relics,
        potions=potions,
        choice_list=data.get("choice_list", []),
        screen_state=screen_state,
    )
