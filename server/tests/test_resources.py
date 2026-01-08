"""Tests for MCP resource implementations.

Tests the MCP resources that expose game state:
- game://state - Current full game state
- game://player - Player stats (HP, gold, deck, relics)
- game://combat - Current combat state (monsters, hand, energy)
- game://map - Current map and path options
"""

from __future__ import annotations

import pytest

from slay_the_spire_mcp.models import (
    Card,
    CombatState,
    GameState,
    MapNode,
    Monster,
    Potion,
    Relic,
)
from slay_the_spire_mcp.resources import (
    get_combat_resource,
    get_map_resource,
    get_player_resource,
    get_state_resource,
)
from slay_the_spire_mcp.state import GameStateManager

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def sample_deck() -> list[Card]:
    """Sample deck for testing."""
    return [
        Card(name="Strike", cost=1, type="ATTACK", upgrades=0),
        Card(name="Strike", cost=1, type="ATTACK", upgrades=0),
        Card(name="Defend", cost=1, type="SKILL", upgrades=0),
        Card(name="Defend", cost=1, type="SKILL", upgrades=0),
        Card(name="Bash", cost=2, type="ATTACK", upgrades=0),
    ]


@pytest.fixture
def sample_relics() -> list[Relic]:
    """Sample relics for testing."""
    return [
        Relic(name="Burning Blood", id="Burning Blood", counter=-1),
        Relic(name="Vajra", id="Vajra", counter=-1),
    ]


@pytest.fixture
def sample_potions() -> list[Potion]:
    """Sample potions for testing."""
    return [
        Potion(name="Block Potion", id="Block Potion", can_use=True),
        Potion(
            name="Fire Potion", id="Fire Potion", can_use=True, requires_target=True
        ),
    ]


@pytest.fixture
def sample_monsters() -> list[Monster]:
    """Sample monsters for testing."""
    return [
        Monster(
            name="Jaw Worm",
            id="JawWorm",
            current_hp=40,
            max_hp=44,
            block=0,
            intent="ATTACK",
            is_gone=False,
        ),
    ]


@pytest.fixture
def sample_hand() -> list[Card]:
    """Sample hand for testing."""
    return [
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Defend", cost=1, type="SKILL"),
        Card(name="Bash", cost=2, type="ATTACK"),
    ]


@pytest.fixture
def sample_combat_state(
    sample_monsters: list[Monster], sample_hand: list[Card]
) -> CombatState:
    """Sample combat state for testing."""
    return CombatState(
        turn=1,
        monsters=sample_monsters,
        hand=sample_hand,
        draw_pile=[Card(name="Strike", cost=1, type="ATTACK")],
        discard_pile=[],
        exhaust_pile=[],
        energy=3,
        max_energy=3,
        player_block=0,
        player_powers=[],
    )


@pytest.fixture
def sample_map() -> list[list[MapNode]]:
    """Sample map for testing."""
    return [
        [MapNode(x=0, y=0, symbol="M", children=[(1, 1), (2, 1)])],
        [
            MapNode(x=1, y=1, symbol="?", children=[(1, 2)]),
            MapNode(x=2, y=1, symbol="$", children=[(2, 2)]),
        ],
        [
            MapNode(x=1, y=2, symbol="E", children=[(1, 3)]),
            MapNode(x=2, y=2, symbol="R", children=[(1, 3)]),
        ],
        [MapNode(x=1, y=3, symbol="B", children=[])],
    ]


@pytest.fixture
def full_game_state(
    sample_deck: list[Card],
    sample_relics: list[Relic],
    sample_potions: list[Potion],
    sample_combat_state: CombatState,
    sample_map: list[list[MapNode]],
) -> GameState:
    """Full game state with all fields populated."""
    return GameState(
        in_game=True,
        screen_type="COMBAT",
        floor=5,
        act=1,
        act_boss="Slime Boss",
        seed=123456789,
        hp=65,
        max_hp=80,
        gold=150,
        current_block=5,
        deck=sample_deck,
        relics=sample_relics,
        potions=sample_potions,
        choice_list=["Strike", "Defend", "Bash"],
        screen_state={"name": "COMBAT"},
        combat_state=sample_combat_state,
        map=sample_map,
        current_node=(0, 0),
    )


@pytest.fixture
def non_combat_game_state(
    sample_deck: list[Card],
    sample_relics: list[Relic],
    sample_map: list[list[MapNode]],
) -> GameState:
    """Game state on the map screen (not in combat)."""
    return GameState(
        in_game=True,
        screen_type="MAP",
        floor=5,
        act=1,
        act_boss="Slime Boss",
        seed=123456789,
        hp=65,
        max_hp=80,
        gold=150,
        current_block=0,
        deck=sample_deck,
        relics=sample_relics,
        potions=[],
        choice_list=[],
        screen_state={},
        combat_state=None,
        map=sample_map,
        current_node=(1, 1),
    )


# ==============================================================================
# game://state Resource Tests
# ==============================================================================


class TestStateResource:
    """Tests for the game://state resource."""

    def test_returns_full_state_when_available(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://state returns the complete game state."""
        state_manager.update_state_sync(full_game_state)

        result = get_state_resource(state_manager)

        assert result is not None
        assert result["in_game"] is True
        assert result["screen_type"] == "COMBAT"
        assert result["floor"] == 5
        assert result["act"] == 1
        assert result["hp"] == 65
        assert result["max_hp"] == 80
        assert result["gold"] == 150

    def test_returns_none_when_no_state(self, state_manager: GameStateManager) -> None:
        """game://state returns None when no state is available."""
        result = get_state_resource(state_manager)

        assert result is None

    def test_includes_deck_info(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://state includes deck information."""
        state_manager.update_state_sync(full_game_state)

        result = get_state_resource(state_manager)

        assert result is not None
        assert "deck" in result
        assert len(result["deck"]) == 5

    def test_includes_relics_info(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://state includes relics information."""
        state_manager.update_state_sync(full_game_state)

        result = get_state_resource(state_manager)

        assert result is not None
        assert "relics" in result
        assert len(result["relics"]) == 2

    def test_includes_combat_state_when_in_combat(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://state includes combat state when in combat."""
        state_manager.update_state_sync(full_game_state)

        result = get_state_resource(state_manager)

        assert result is not None
        assert "combat_state" in result
        assert result["combat_state"] is not None


# ==============================================================================
# game://player Resource Tests
# ==============================================================================


class TestPlayerResource:
    """Tests for the game://player resource."""

    def test_returns_player_stats(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://player returns player stats."""
        state_manager.update_state_sync(full_game_state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert result["hp"] == 65
        assert result["max_hp"] == 80
        assert result["gold"] == 150
        assert result["current_block"] == 5

    def test_returns_none_when_no_state(self, state_manager: GameStateManager) -> None:
        """game://player returns None when no state is available."""
        result = get_player_resource(state_manager)

        assert result is None

    def test_includes_deck(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://player includes the player's deck."""
        state_manager.update_state_sync(full_game_state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert "deck" in result
        assert len(result["deck"]) == 5
        # Verify deck card structure
        assert result["deck"][0]["name"] == "Strike"
        assert result["deck"][0]["cost"] == 1
        assert result["deck"][0]["type"] == "ATTACK"

    def test_includes_relics(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://player includes the player's relics."""
        state_manager.update_state_sync(full_game_state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert "relics" in result
        assert len(result["relics"]) == 2
        # Verify relic structure
        assert result["relics"][0]["name"] == "Burning Blood"

    def test_includes_potions(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://player includes the player's potions."""
        state_manager.update_state_sync(full_game_state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert "potions" in result
        assert len(result["potions"]) == 2

    def test_includes_run_info(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://player includes run information (floor, act)."""
        state_manager.update_state_sync(full_game_state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert result["floor"] == 5
        assert result["act"] == 1


# ==============================================================================
# game://combat Resource Tests
# ==============================================================================


class TestCombatResource:
    """Tests for the game://combat resource."""

    def test_returns_combat_state_when_in_combat(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat returns combat state when in combat."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert "monsters" in result
        assert "hand" in result
        assert "energy" in result

    def test_returns_none_when_no_state(self, state_manager: GameStateManager) -> None:
        """game://combat returns None when no state is available."""
        result = get_combat_resource(state_manager)

        assert result is None

    def test_returns_none_when_not_in_combat(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://combat returns None when not in combat."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_combat_resource(state_manager)

        assert result is None

    def test_includes_monsters(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes monster information."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert len(result["monsters"]) == 1
        monster = result["monsters"][0]
        assert monster["name"] == "Jaw Worm"
        assert monster["current_hp"] == 40
        assert monster["max_hp"] == 44
        assert monster["intent"] == "ATTACK"

    def test_includes_hand(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes hand information."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert len(result["hand"]) == 3
        # Verify card structure
        assert result["hand"][0]["name"] == "Strike"
        assert result["hand"][0]["cost"] == 1

    def test_includes_energy(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes energy information."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert result["energy"] == 3
        assert result["max_energy"] == 3

    def test_includes_turn_number(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes turn number."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert result["turn"] == 1

    def test_includes_draw_and_discard_piles(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes draw and discard pile info."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert "draw_pile" in result
        assert "discard_pile" in result
        assert "exhaust_pile" in result
        assert result["draw_pile_count"] == 1
        assert result["discard_pile_count"] == 0
        assert result["exhaust_pile_count"] == 0

    def test_includes_player_block(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes player block."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert result["player_block"] == 0

    def test_includes_player_powers(
        self, state_manager: GameStateManager, full_game_state: GameState
    ) -> None:
        """game://combat includes player powers/buffs."""
        state_manager.update_state_sync(full_game_state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert "player_powers" in result


# ==============================================================================
# game://map Resource Tests
# ==============================================================================


class TestMapResource:
    """Tests for the game://map resource."""

    def test_returns_map_when_available(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map returns map data when available."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        assert "map" in result

    def test_returns_none_when_no_state(self, state_manager: GameStateManager) -> None:
        """game://map returns None when no state is available."""
        result = get_map_resource(state_manager)

        assert result is None

    def test_returns_none_when_no_map(self, state_manager: GameStateManager) -> None:
        """game://map returns None when map is not available."""
        state = GameState(
            in_game=True,
            screen_type="SHOP",
            floor=5,
            map=None,
        )
        state_manager.update_state_sync(state)

        result = get_map_resource(state_manager)

        assert result is None

    def test_includes_current_position(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map includes current node position."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        assert result["current_node"] == (1, 1)

    def test_includes_floor_info(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map includes floor information."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        assert result["floor"] == 5
        assert result["act"] == 1

    def test_includes_act_boss(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map includes act boss information."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        assert result["act_boss"] == "Slime Boss"

    def test_map_nodes_have_symbols(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map nodes include room symbols."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        # Check first row, first node
        first_row = result["map"][0]
        assert len(first_row) == 1
        assert first_row[0]["symbol"] == "M"

    def test_map_nodes_have_children(
        self, state_manager: GameStateManager, non_combat_game_state: GameState
    ) -> None:
        """game://map nodes include children (connections)."""
        state_manager.update_state_sync(non_combat_game_state)

        result = get_map_resource(state_manager)

        assert result is not None
        first_node = result["map"][0][0]
        assert "children" in first_node
        assert len(first_node["children"]) == 2


# ==============================================================================
# Edge Cases and Error Handling
# ==============================================================================


class TestResourceEdgeCases:
    """Tests for edge cases in resource handling."""

    def test_empty_deck(self, state_manager: GameStateManager) -> None:
        """Player resource handles empty deck."""
        state = GameState(
            in_game=True,
            screen_type="MAP",
            floor=1,
            hp=80,
            max_hp=80,
            gold=99,
            deck=[],
            relics=[],
            potions=[],
        )
        state_manager.update_state_sync(state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert result["deck"] == []

    def test_empty_relics(self, state_manager: GameStateManager) -> None:
        """Player resource handles empty relics."""
        state = GameState(
            in_game=True,
            screen_type="MAP",
            floor=1,
            hp=80,
            max_hp=80,
            gold=99,
            deck=[],
            relics=[],
            potions=[],
        )
        state_manager.update_state_sync(state)

        result = get_player_resource(state_manager)

        assert result is not None
        assert result["relics"] == []

    def test_combat_with_empty_hand(self, state_manager: GameStateManager) -> None:
        """Combat resource handles empty hand."""
        combat = CombatState(
            turn=5,
            monsters=[Monster(name="Slime", current_hp=10, max_hp=10)],
            hand=[],
            draw_pile=[],
            discard_pile=[Card(name="Strike", cost=1, type="ATTACK")],
            exhaust_pile=[],
            energy=0,
            max_energy=3,
        )
        state = GameState(
            in_game=True,
            screen_type="COMBAT",
            floor=1,
            hp=50,
            max_hp=80,
            combat_state=combat,
        )
        state_manager.update_state_sync(state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert result["hand"] == []
        assert result["energy"] == 0

    def test_combat_with_dead_monsters(self, state_manager: GameStateManager) -> None:
        """Combat resource includes dead/gone monsters."""
        combat = CombatState(
            turn=2,
            monsters=[
                Monster(
                    name="Jaw Worm",
                    current_hp=0,
                    max_hp=44,
                    is_gone=True,
                ),
                Monster(
                    name="Louse",
                    current_hp=10,
                    max_hp=15,
                    is_gone=False,
                ),
            ],
            hand=[Card(name="Strike", cost=1, type="ATTACK")],
            draw_pile=[],
            discard_pile=[],
            exhaust_pile=[],
            energy=2,
            max_energy=3,
        )
        state = GameState(
            in_game=True,
            screen_type="COMBAT",
            floor=3,
            combat_state=combat,
        )
        state_manager.update_state_sync(state)

        result = get_combat_resource(state_manager)

        assert result is not None
        assert len(result["monsters"]) == 2
        # Verify gone status is preserved
        assert result["monsters"][0]["is_gone"] is True
        assert result["monsters"][1]["is_gone"] is False

    def test_not_in_game(self, state_manager: GameStateManager) -> None:
        """Resources handle not_in_game state."""
        state = GameState(
            in_game=False,
            screen_type="MAIN_MENU",
            floor=0,
        )
        state_manager.update_state_sync(state)

        # State resource should still return the state
        state_result = get_state_resource(state_manager)
        assert state_result is not None
        assert state_result["in_game"] is False

        # Player resource should return data (even if mostly empty)
        player_result = get_player_resource(state_manager)
        assert player_result is not None

        # Combat resource should return None (not in combat)
        combat_result = get_combat_resource(state_manager)
        assert combat_result is None

        # Map resource should return None (no map)
        map_result = get_map_resource(state_manager)
        assert map_result is None
