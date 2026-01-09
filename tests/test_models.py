"""Tests for game state data models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from slay_the_spire_mcp.models import (
    Card,
    CombatState,
    GameState,
    Monster,
    Potion,
    Relic,
    parse_game_state_from_message,
)


# =============================================================================
# Model Basic Tests
# =============================================================================


class TestCardModel:
    """Tests for the Card model."""

    def test_card_with_all_fields(self) -> None:
        """Card with all fields populated."""
        card = Card(
            name="Strike",
            cost=1,
            type="ATTACK",
            upgrades=0,
            id="Strike_R",
            exhausts=False,
            ethereal=False,
        )
        assert card.name == "Strike"
        assert card.cost == 1
        assert card.type == "ATTACK"
        assert card.upgrades == 0
        assert card.id == "Strike_R"
        assert card.exhausts is False
        assert card.ethereal is False

    def test_card_minimal_fields(self) -> None:
        """Card with only required fields uses defaults."""
        card = Card(name="Test Card")
        assert card.name == "Test Card"
        assert card.cost == 0  # default
        assert card.type == "UNKNOWN"  # default
        assert card.upgrades == 0  # default
        assert card.id is None  # default
        assert card.exhausts is False  # default
        assert card.ethereal is False  # default

    def test_card_ignores_extra_fields(self) -> None:
        """Card ignores extra fields from CommunicationMod."""
        card = Card(
            name="Bash",
            cost=2,
            rarity="BASIC",  # extra field
            uuid="bash-1",  # extra field
        )
        assert card.name == "Bash"
        assert card.cost == 2


class TestRelicModel:
    """Tests for the Relic model."""

    def test_relic_with_all_fields(self) -> None:
        """Relic with all fields populated."""
        relic = Relic(name="Burning Blood", id="Burning Blood", counter=5)
        assert relic.name == "Burning Blood"
        assert relic.id == "Burning Blood"
        assert relic.counter == 5

    def test_relic_minimal_fields(self) -> None:
        """Relic with only required fields uses defaults."""
        relic = Relic(name="Test Relic")
        assert relic.name == "Test Relic"
        assert relic.id is None
        assert relic.counter == -1  # default


class TestPotionModel:
    """Tests for the Potion model."""

    def test_potion_with_all_fields(self) -> None:
        """Potion with all fields populated."""
        potion = Potion(
            name="Fire Potion",
            id="Fire Potion",
            can_use=True,
            can_discard=True,
            requires_target=True,
        )
        assert potion.name == "Fire Potion"
        assert potion.id == "Fire Potion"
        assert potion.can_use is True
        assert potion.can_discard is True
        assert potion.requires_target is True

    def test_potion_slot_empty(self) -> None:
        """Empty potion slot representation."""
        potion = Potion(
            name="Potion Slot",
            can_use=False,
            can_discard=False,
            requires_target=False,
        )
        assert potion.name == "Potion Slot"
        assert potion.can_use is False


class TestMonsterModel:
    """Tests for the Monster model."""

    def test_monster_with_all_fields(self) -> None:
        """Monster with all fields populated."""
        monster = Monster(
            name="Jaw Worm",
            id="Jaw Worm",
            current_hp=44,
            max_hp=44,
            block=5,
            intent="ATTACK",
            is_gone=False,
            half_dead=False,
            powers=[{"id": "Vulnerable", "amount": 2}],
        )
        assert monster.name == "Jaw Worm"
        assert monster.current_hp == 44
        assert monster.max_hp == 44
        assert monster.block == 5
        assert monster.intent == "ATTACK"
        assert monster.is_gone is False
        assert monster.half_dead is False
        assert len(monster.powers) == 1

    def test_monster_minimal(self) -> None:
        """Monster with only required fields."""
        monster = Monster(name="Test Monster")
        assert monster.name == "Test Monster"
        assert monster.current_hp == 0
        assert monster.max_hp == 0
        assert monster.intent == "UNKNOWN"
        assert monster.powers == []


class TestCombatStateModel:
    """Tests for the CombatState model."""

    def test_combat_state_full(self) -> None:
        """CombatState with all fields populated."""
        combat = CombatState(
            turn=1,
            monsters=[Monster(name="Jaw Worm", current_hp=44, max_hp=44)],
            hand=[Card(name="Strike", cost=1)],
            draw_pile=[Card(name="Defend", cost=1)],
            discard_pile=[],
            exhaust_pile=[],
            energy=3,
            max_energy=3,
            player_block=0,
            player_powers=[],
        )
        assert combat.turn == 1
        assert len(combat.monsters) == 1
        assert len(combat.hand) == 1
        assert len(combat.draw_pile) == 1
        assert combat.energy == 3
        assert combat.max_energy == 3

    def test_combat_state_defaults(self) -> None:
        """CombatState with default values."""
        combat = CombatState()
        assert combat.turn == 0
        assert combat.monsters == []
        assert combat.hand == []
        assert combat.draw_pile == []
        assert combat.energy == 0
        assert combat.max_energy == 3


class TestGameStateModel:
    """Tests for the GameState model."""

    def test_game_state_full(self) -> None:
        """GameState with all fields populated."""
        state = GameState(
            in_game=True,
            screen_type="CARD_REWARD",
            floor=5,
            act=1,
            act_boss="Slime Boss",
            seed=123456789,
            hp=65,
            max_hp=80,
            gold=99,
            current_block=0,
            deck=[Card(name="Strike", cost=1)],
            relics=[Relic(name="Burning Blood")],
            potions=[Potion(name="Fire Potion")],
            choice_list=["Strike", "Defend"],
            screen_state={"cards": []},
        )
        assert state.in_game is True
        assert state.screen_type == "CARD_REWARD"
        assert state.floor == 5
        assert state.act == 1
        assert state.hp == 65
        assert state.gold == 99
        assert len(state.deck) == 1
        assert len(state.relics) == 1
        assert len(state.potions) == 1
        assert len(state.choice_list) == 2

    def test_game_state_defaults(self) -> None:
        """GameState with default values."""
        state = GameState()
        assert state.in_game is False
        assert state.screen_type == "NONE"
        assert state.floor == 0
        assert state.act == 1
        assert state.hp == 0
        assert state.deck == []
        assert state.relics == []
        assert state.potions == []
        assert state.choice_list == []
        assert state.combat_state is None


# =============================================================================
# parse_game_state_from_message Tests
# =============================================================================


class TestParseGameStateFromMessage:
    """Tests for the parse_game_state_from_message function."""

    def test_parse_communication_mod_format(
        self, game_states_dir: Path
    ) -> None:
        """Parse CommunicationMod format message."""
        fixture_path = game_states_dir / "card_reward.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.in_game is True
        assert state.screen_type == "CARD_REWARD"
        assert state.floor == 5
        assert state.act == 1
        assert state.hp == 65
        assert state.max_hp == 80
        assert state.gold == 99
        assert len(state.deck) == 10
        assert len(state.relics) == 1
        assert len(state.potions) == 3
        assert len(state.choice_list) == 3

    def test_parse_legacy_format(self) -> None:
        """Parse legacy internal format message."""
        message = {
            "type": "state",
            "data": {
                "in_game": True,
                "screen_type": "EVENT",
                "floor": 4,
                "act": 1,
                "hp": 72,
                "max_hp": 80,
                "gold": 100,
                "deck": [],
                "relics": [],
                "potions": [],
            },
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.in_game is True
        assert state.screen_type == "EVENT"
        assert state.floor == 4
        assert state.hp == 72

    def test_parse_with_current_hp_field(self) -> None:
        """Parse message using current_hp field (CommunicationMod)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "floor": 3,
                "current_hp": 70,
                "max_hp": 80,
                "gold": 50,
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.hp == 70  # Should use current_hp

    def test_parse_with_hp_field(self) -> None:
        """Parse message using hp field (legacy)."""
        message = {
            "type": "state",
            "data": {
                "in_game": True,
                "screen_type": "NONE",
                "floor": 3,
                "hp": 70,
                "max_hp": 80,
            },
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.hp == 70

    def test_parse_with_block_field(self) -> None:
        """Parse message using block field (CommunicationMod)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "floor": 3,
                "block": 10,
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.current_block == 10

    def test_parse_with_current_block_field(self) -> None:
        """Parse message using current_block field (legacy)."""
        message = {
            "type": "state",
            "data": {
                "in_game": True,
                "screen_type": "NONE",
                "floor": 3,
                "current_block": 15,
            },
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.current_block == 15

    def test_parse_unknown_message_type(self) -> None:
        """Unknown message type returns None."""
        message = {"type": "command", "action": "PLAY"}

        state = parse_game_state_from_message(message)

        assert state is None

    def test_parse_empty_message(self) -> None:
        """Empty message returns None."""
        state = parse_game_state_from_message({})

        assert state is None

    def test_parse_empty_game_state(self) -> None:
        """Empty game_state returns None."""
        message = {"game_state": {}}

        state = parse_game_state_from_message(message)

        assert state is None

    def test_parse_empty_data(self) -> None:
        """Empty data in legacy format returns None."""
        message = {"type": "state", "data": {}}

        state = parse_game_state_from_message(message)

        assert state is None

    def test_parse_card_as_string(self) -> None:
        """Parse deck with card as plain string (fallback)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "deck": ["Strike", "Defend", "Bash"],
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert len(state.deck) == 3
        assert state.deck[0].name == "Strike"
        assert state.deck[1].name == "Defend"
        assert state.deck[2].name == "Bash"

    def test_parse_relic_as_string(self) -> None:
        """Parse relics with relic as plain string (fallback)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "relics": ["Burning Blood", "Vajra"],
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert len(state.relics) == 2
        assert state.relics[0].name == "Burning Blood"
        assert state.relics[1].name == "Vajra"

    def test_parse_potion_as_string(self) -> None:
        """Parse potions with potion as plain string (fallback)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "potions": ["Fire Potion", "Block Potion"],
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert len(state.potions) == 2
        assert state.potions[0].name == "Fire Potion"
        assert state.potions[1].name == "Block Potion"

    def test_parse_screen_state_as_string(self) -> None:
        """Parse screen_state as string (normalized to dict)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "screen_state": "COMBAT",
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_state == {"name": "COMBAT"}

    def test_parse_screen_state_as_empty_string(self) -> None:
        """Parse empty screen_state string (normalized to empty dict)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "screen_state": "",
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_state == {}

    def test_parse_screen_state_invalid_type(self) -> None:
        """Parse screen_state with invalid type (normalized to empty dict)."""
        message = {
            "game_state": {
                "in_game": True,
                "screen_type": "NONE",
                "screen_state": 12345,  # Invalid type
            }
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_state == {}

    def test_parse_in_game_from_top_level(self) -> None:
        """Parse in_game from top level (CommunicationMod format)."""
        message = {
            "in_game": True,
            "game_state": {
                "screen_type": "NONE",
                "floor": 1,
                # in_game not in game_state
            },
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.in_game is True

    def test_parse_in_game_from_game_state(self) -> None:
        """Parse in_game from game_state when not at top level."""
        message = {
            "game_state": {
                "in_game": False,
                "screen_type": "MAIN_MENU",
            },
        }

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.in_game is False

    def test_parse_map_state_includes_map_data(self, game_states_dir: Path) -> None:
        """Parse map state fixture includes parsed map."""
        fixture_path = game_states_dir / "map.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.map is not None
        assert len(state.map) == 2  # Two rows in fixture
        assert len(state.map[0]) == 7  # First row has 7 nodes

    def test_parse_map_children_as_tuples(self, game_states_dir: Path) -> None:
        """Map children are transformed from dicts to tuples."""
        fixture_path = game_states_dir / "map.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.map is not None
        # Node at x=3, y=0 has children [(2,1), (3,1), (4,1)] per fixture
        node = state.map[0][3]
        assert node.children == [(2, 1), (3, 1), (4, 1)]

    def test_parse_map_current_node(self, game_states_dir: Path) -> None:
        """current_node is extracted from screen_state."""
        fixture_path = game_states_dir / "map.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.current_node == (3, 0)


class TestParseGameStateWithFixtures:
    """Tests using the JSON fixture files."""

    def test_parse_combat_state(self, game_states_dir: Path) -> None:
        """Parse combat state fixture."""
        fixture_path = game_states_dir / "combat.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.in_game is True
        assert state.screen_type == "NONE"
        assert state.floor == 3
        assert state.hp == 70
        assert state.max_hp == 80
        assert state.gold == 50
        assert state.act_boss == "Slime Boss"
        assert len(state.deck) == 10  # 5 Strikes, 4 Defends, 1 Bash
        assert len(state.relics) == 1
        assert len(state.potions) == 3

    def test_parse_event_state(self, game_states_dir: Path) -> None:
        """Parse event state fixture."""
        fixture_path = game_states_dir / "event.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_type == "EVENT"
        assert state.floor == 4
        assert state.hp == 72
        assert state.gold == 120
        assert len(state.choice_list) == 3
        assert "Eat" in state.choice_list
        assert "Feed" in state.choice_list
        assert "Leave" in state.choice_list
        assert state.screen_state.get("event_id") == "Big Fish"

    def test_parse_shop_state(self, game_states_dir: Path) -> None:
        """Parse shop state fixture."""
        fixture_path = game_states_dir / "shop.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_type == "SHOP_SCREEN"
        assert state.floor == 7
        assert state.gold == 250
        assert state.screen_state.get("can_purge") is True
        assert state.screen_state.get("purge_cost") == 75

    def test_parse_rest_state(self, game_states_dir: Path) -> None:
        """Parse rest site state fixture."""
        fixture_path = game_states_dir / "rest.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_type == "REST"
        assert state.floor == 6
        assert state.hp == 55
        assert state.max_hp == 80
        assert len(state.choice_list) == 2
        assert "rest" in state.choice_list
        assert "smith" in state.choice_list

    def test_parse_map_state(self, game_states_dir: Path) -> None:
        """Parse map state fixture."""
        fixture_path = game_states_dir / "map.json"
        with open(fixture_path) as f:
            message = json.load(f)

        state = parse_game_state_from_message(message)

        assert state is not None
        assert state.screen_type == "MAP"
        assert state.floor == 1
        assert state.hp == 80
        assert state.max_hp == 80
        assert len(state.choice_list) == 3


class TestModelsPlaceholder:
    """Placeholder tests for models module.

    These tests will be implemented when the models module is complete.
    """

    def test_models_module_exists(self) -> None:
        """Verify the models module can be imported."""
        from slay_the_spire_mcp import models

        assert models is not None

    def test_sample_game_state_fixture(
        self, sample_game_state: dict[str, Any]
    ) -> None:
        """Verify the sample game state fixture loads correctly.

        The fixture is in CommunicationMod format with game_state nested.
        """
        assert sample_game_state["in_game"] is True
        # CommunicationMod format has game_state nested
        game_state = sample_game_state.get("game_state", sample_game_state)
        assert game_state["screen_type"] == "CARD_REWARD"
        assert len(game_state["choice_list"]) == 3
