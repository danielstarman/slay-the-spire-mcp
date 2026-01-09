"""Game state data models.

Pydantic models for Slay the Spire game entities.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


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


class FloorHistory(BaseGameModel):
    """A record of a visited node/floor in the current run.

    Tracks the sequence of nodes visited during a run to provide context
    about the path taken through the map.
    """

    floor: int
    symbol: str
    details: str | None = None


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

    Supports two message formats:

    1. CommunicationMod format (preferred):
    {
        "available_commands": [...],
        "ready_for_command": true,
        "in_game": true,
        "game_state": { ... game state fields ... }
    }

    2. Legacy internal format:
    {
        "type": "state",
        "data": { ... game state fields ... }
    }

    Args:
        message: The parsed JSON message from the bridge

    Returns:
        GameState if message is a valid state message, None otherwise
    """
    # Try CommunicationMod format first (has game_state at top level)
    if "game_state" in message:
        data = message.get("game_state", {})
        # Use top-level in_game if present, otherwise check game_state
        in_game = message.get("in_game", data.get("in_game", False))
    # Fall back to legacy internal format
    elif message.get("type") == "state":
        data = message.get("data", {})
        in_game = data.get("in_game", False)
    else:
        return None

    if not data:
        return None

    # Parse deck cards with error handling
    deck_data = data.get("deck", [])
    deck: list[Card] = []
    for i, card in enumerate(deck_data):
        try:
            if isinstance(card, dict):
                deck.append(Card(**card))
            else:
                deck.append(Card(name=str(card)))
        except ValidationError as e:
            logger.warning(
                "Failed to parse card at index %d: %s. Card data: %s",
                i,
                e,
                card,
            )
            # Skip invalid card rather than failing entire state parse

    # Parse relics with error handling
    relics_data = data.get("relics", [])
    relics: list[Relic] = []
    for i, relic in enumerate(relics_data):
        try:
            if isinstance(relic, dict):
                relics.append(Relic(**relic))
            else:
                relics.append(Relic(name=str(relic)))
        except ValidationError as e:
            logger.warning(
                "Failed to parse relic at index %d: %s. Relic data: %s",
                i,
                e,
                relic,
            )
            # Skip invalid relic rather than failing entire state parse

    # Parse potions with error handling
    potions_data = data.get("potions", [])
    potions: list[Potion] = []
    for i, potion in enumerate(potions_data):
        try:
            if isinstance(potion, dict):
                potions.append(Potion(**potion))
            else:
                potions.append(Potion(name=str(potion)))
        except ValidationError as e:
            logger.warning(
                "Failed to parse potion at index %d: %s. Potion data: %s",
                i,
                e,
                potion,
            )
            # Skip invalid potion rather than failing entire state parse

    # Handle screen_state - CommunicationMod sometimes sends a string (e.g., "COMBAT")
    # instead of a dict. Normalize to dict format.
    raw_screen_state = data.get("screen_state", {})
    if isinstance(raw_screen_state, str):
        screen_state = {"name": raw_screen_state} if raw_screen_state else {}
    elif isinstance(raw_screen_state, dict):
        screen_state = raw_screen_state
    else:
        screen_state = {}

    # HP field: CommunicationMod uses "current_hp", legacy uses "hp"
    hp = data.get("current_hp", data.get("hp", 0))

    # Block field: CommunicationMod uses "block", legacy uses "current_block"
    block = data.get("block", data.get("current_block", 0))

    # Parse map data with error handling
    # CommunicationMod sends map as a 2D array where children are dicts like {"x": 0, "y": 1}
    # We need to transform them to tuples (0, 1) for the MapNode model
    map_data = data.get("map")
    parsed_map: list[list[MapNode]] | None = None
    if map_data and isinstance(map_data, list):
        parsed_map = []
        for row_idx, row in enumerate(map_data):
            if not isinstance(row, list):
                logger.warning(
                    "Invalid map row at index %d: expected list, got %s",
                    row_idx,
                    type(row).__name__,
                )
                continue
            parsed_row: list[MapNode] = []
            for node_idx, node in enumerate(row):
                try:
                    if isinstance(node, dict):
                        # Transform children from [{"x": 0, "y": 1}] to [(0, 1)]
                        raw_children = node.get("children", [])
                        children: list[tuple[int, int]] = []
                        for child in raw_children:
                            if isinstance(child, dict) and "x" in child and "y" in child:
                                children.append((child["x"], child["y"]))
                        parsed_row.append(
                            MapNode(
                                x=node.get("x", 0),
                                y=node.get("y", 0),
                                symbol=node.get("symbol", "?"),
                                children=children,
                            )
                        )
                    else:
                        logger.warning(
                            "Invalid map node at row %d, index %d: expected dict, got %s",
                            row_idx,
                            node_idx,
                            type(node).__name__,
                        )
                except ValidationError as e:
                    logger.warning(
                        "Failed to parse map node at row %d, index %d: %s. Node data: %s",
                        row_idx,
                        node_idx,
                        e,
                        node,
                    )
            parsed_map.append(parsed_row)

    # Parse current_node from screen_state
    # CommunicationMod sends it as {"x": 3, "y": 0}, we need tuple (3, 0)
    current_node: tuple[int, int] | None = None
    raw_current_node = screen_state.get("current_node")
    if isinstance(raw_current_node, dict) and "x" in raw_current_node and "y" in raw_current_node:
        try:
            current_node = (raw_current_node["x"], raw_current_node["y"])
        except (TypeError, KeyError) as e:
            logger.warning(
                "Failed to parse current_node: %s. Data: %s",
                e,
                raw_current_node,
            )

    return GameState(
        in_game=in_game,
        screen_type=data.get("screen_type", "NONE"),
        floor=data.get("floor", 0),
        act=data.get("act", 1),
        act_boss=data.get("act_boss"),
        seed=data.get("seed"),
        hp=hp,
        max_hp=data.get("max_hp", 0),
        gold=data.get("gold", 0),
        current_block=block,
        deck=deck,
        relics=relics,
        potions=potions,
        choice_list=data.get("choice_list", []),
        screen_state=screen_state,
        map=parsed_map,
        current_node=current_node,
    )
