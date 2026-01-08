"""Tests for decision point detection.

Tests the detection module that identifies when the game needs player input
and what choices are available.
"""

from __future__ import annotations

import pytest

from slay_the_spire_mcp.detection import (
    DecisionContext,
    DecisionType,
    detect_decision_point,
)
from slay_the_spire_mcp.models import (
    Card,
    CombatState,
    GameState,
    Monster,
    Potion,
    Relic,
)

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def card_reward_state() -> GameState:
    """Game state at card reward screen."""
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
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[],
        choice_list=["Strike", "Pommel Strike", "Anger"],
        screen_state={"bowl_available": False},
    )


@pytest.fixture
def card_reward_with_bowl_state() -> GameState:
    """Game state at card reward screen with Singing Bowl available."""
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
        ],
        relics=[Relic(name="Singing Bowl", id="Singing Bowl")],
        potions=[],
        choice_list=["Strike", "Pommel Strike", "Anger"],
        screen_state={"bowl_available": True},
    )


@pytest.fixture
def combat_state() -> GameState:
    """Game state during combat."""
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
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[
            Potion(name="Fire Potion", id="Fire Potion", can_use=True, requires_target=True),
            Potion(name="Block Potion", id="Block Potion", can_use=True, requires_target=False),
        ],
        combat_state=CombatState(
            turn=1,
            energy=3,
            max_energy=3,
            hand=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Strike", cost=1, type="ATTACK"),
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


@pytest.fixture
def event_state() -> GameState:
    """Game state at an event."""
    return GameState(
        in_game=True,
        screen_type="EVENT",
        floor=4,
        act=1,
        hp=70,
        max_hp=80,
        gold=50,
        deck=[],
        relics=[],
        potions=[],
        choice_list=["[Pray] Lose 5 HP", "[Leave] Nothing happens"],
        screen_state={
            "event_name": "Forgotten Altar",
            "event_id": "Forgotten Altar",
            "body_text": "An ancient altar stands before you...",
        },
    )


@pytest.fixture
def shop_state() -> GameState:
    """Game state at a shop."""
    return GameState(
        in_game=True,
        screen_type="SHOP_SCREEN",
        floor=6,
        act=1,
        hp=70,
        max_hp=80,
        gold=250,
        deck=[],
        relics=[],
        potions=[],
        choice_list=[],  # Shop choices are in screen_state
        screen_state={
            "cards": [
                {"name": "Headbutt", "cost": 75, "id": "Headbutt"},
                {"name": "Shrug It Off", "cost": 75, "id": "Shrug It Off"},
            ],
            "relics": [
                {"name": "Vajra", "cost": 150, "id": "Vajra"},
            ],
            "potions": [
                {"name": "Fire Potion", "cost": 50, "id": "Fire Potion"},
            ],
            "purge_cost": 50,
            "can_purge": True,
        },
    )


@pytest.fixture
def rest_state() -> GameState:
    """Game state at a campfire/rest site."""
    return GameState(
        in_game=True,
        screen_type="REST",
        floor=7,
        act=1,
        hp=50,
        max_hp=80,
        gold=100,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[],
        choice_list=["rest", "smith"],
        screen_state={
            "has_rested": False,
            "rest_options": ["rest", "smith"],
        },
    )


@pytest.fixture
def rest_with_key_state() -> GameState:
    """Game state at a campfire with recall option (has key)."""
    return GameState(
        in_game=True,
        screen_type="REST",
        floor=7,
        act=1,
        hp=80,
        max_hp=80,
        gold=100,
        deck=[],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[],
        choice_list=["rest", "smith", "recall"],
        screen_state={
            "has_rested": False,
            "rest_options": ["rest", "smith", "recall"],
        },
    )


@pytest.fixture
def map_state() -> GameState:
    """Game state at map selection."""
    return GameState(
        in_game=True,
        screen_type="MAP",
        floor=0,
        act=1,
        hp=80,
        max_hp=80,
        gold=99,
        deck=[],
        relics=[],
        potions=[],
        choice_list=[],
        screen_state={
            "current_node": None,
            "next_nodes": [
                {"x": 0, "y": 1, "symbol": "M"},
                {"x": 1, "y": 1, "symbol": "?"},
                {"x": 2, "y": 1, "symbol": "M"},
            ],
        },
    )


@pytest.fixture
def boss_relic_state() -> GameState:
    """Game state at boss relic selection."""
    return GameState(
        in_game=True,
        screen_type="BOSS_REWARD",
        floor=17,
        act=1,
        hp=60,
        max_hp=80,
        gold=200,
        deck=[],
        relics=[],
        potions=[],
        choice_list=["Black Star", "Calling Bell", "Sacred Bark"],
        screen_state={
            "relics": [
                {"name": "Black Star", "id": "Black Star", "description": "Elites drop 2 relics"},
                {"name": "Calling Bell", "id": "Calling Bell", "description": "Gain 3 relics and 3 curses"},
                {"name": "Sacred Bark", "id": "Sacred Bark", "description": "Double potion effects"},
            ],
        },
    )


@pytest.fixture
def card_transform_state() -> GameState:
    """Game state at card transform selection."""
    return GameState(
        in_game=True,
        screen_type="GRID",
        floor=4,
        act=1,
        hp=70,
        max_hp=80,
        gold=100,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
        ],
        relics=[],
        potions=[],
        choice_list=["Strike", "Strike", "Defend"],
        screen_state={
            "for_transform": True,
            "for_upgrade": False,
            "for_purge": False,
            "num_cards": 1,
            "any_number": False,
        },
    )


@pytest.fixture
def card_remove_state() -> GameState:
    """Game state at card remove selection."""
    return GameState(
        in_game=True,
        screen_type="GRID",
        floor=6,
        act=1,
        hp=70,
        max_hp=80,
        gold=100,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
        ],
        relics=[],
        potions=[],
        choice_list=["Strike", "Strike", "Defend"],
        screen_state={
            "for_transform": False,
            "for_upgrade": False,
            "for_purge": True,
            "num_cards": 1,
            "any_number": False,
        },
    )


@pytest.fixture
def card_upgrade_state() -> GameState:
    """Game state at card upgrade selection (smith)."""
    return GameState(
        in_game=True,
        screen_type="GRID",
        floor=7,
        act=1,
        hp=70,
        max_hp=80,
        gold=100,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK", upgrades=0),
            Card(name="Bash", cost=2, type="ATTACK", upgrades=0),
        ],
        relics=[],
        potions=[],
        choice_list=["Strike", "Bash"],
        screen_state={
            "for_transform": False,
            "for_upgrade": True,
            "for_purge": False,
            "num_cards": 1,
            "any_number": False,
        },
    )


@pytest.fixture
def main_menu_state() -> GameState:
    """Game state at main menu (not in game)."""
    return GameState(
        in_game=False,
        screen_type="MAIN_MENU",
        floor=0,
        act=0,
        hp=0,
        max_hp=0,
        gold=0,
        deck=[],
        relics=[],
        potions=[],
        choice_list=[],
    )


@pytest.fixture
def combat_reward_state() -> GameState:
    """Game state at combat reward screen (gold/potion/card button)."""
    return GameState(
        in_game=True,
        screen_type="COMBAT_REWARD",
        floor=3,
        act=1,
        hp=60,
        max_hp=80,
        gold=50,
        deck=[],
        relics=[],
        potions=[],
        choice_list=["gold", "potion", "card"],
        screen_state={
            "rewards": [
                {"type": "GOLD", "gold": 25},
                {"type": "POTION", "potion": {"name": "Fire Potion", "id": "Fire Potion"}},
                {"type": "CARD"},
            ],
        },
    )


@pytest.fixture
def hand_select_state() -> GameState:
    """Game state when selecting cards from hand (e.g., Armaments)."""
    return GameState(
        in_game=True,
        screen_type="HAND_SELECT",
        floor=3,
        act=1,
        hp=70,
        max_hp=80,
        gold=50,
        deck=[],
        relics=[],
        potions=[],
        choice_list=["Strike", "Defend", "Bash"],
        screen_state={
            "selection_type": "upgrade",
            "num_cards": 1,
            "any_number": False,
            "can_pick_zero": False,
        },
        combat_state=CombatState(
            turn=1,
            energy=2,
            max_energy=3,
            hand=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Bash", cost=2, type="ATTACK"),
            ],
            draw_pile=[],
            discard_pile=[],
            monsters=[
                Monster(name="Jaw Worm", id="Jaw Worm", current_hp=30, max_hp=44, intent="ATTACK"),
            ],
        ),
    )


# ==============================================================================
# DecisionType Enum Tests
# ==============================================================================


class TestDecisionType:
    """Tests for the DecisionType enum."""

    def test_card_reward_exists(self) -> None:
        """CARD_REWARD decision type exists."""
        assert DecisionType.CARD_REWARD is not None
        assert DecisionType.CARD_REWARD.value == "CARD_REWARD"

    def test_combat_exists(self) -> None:
        """COMBAT decision type exists."""
        assert DecisionType.COMBAT is not None
        assert DecisionType.COMBAT.value == "COMBAT"

    def test_event_exists(self) -> None:
        """EVENT decision type exists."""
        assert DecisionType.EVENT is not None
        assert DecisionType.EVENT.value == "EVENT"

    def test_shop_exists(self) -> None:
        """SHOP decision type exists."""
        assert DecisionType.SHOP is not None
        assert DecisionType.SHOP.value == "SHOP"

    def test_campfire_exists(self) -> None:
        """CAMPFIRE decision type exists."""
        assert DecisionType.CAMPFIRE is not None
        assert DecisionType.CAMPFIRE.value == "CAMPFIRE"

    def test_map_exists(self) -> None:
        """MAP decision type exists."""
        assert DecisionType.MAP is not None
        assert DecisionType.MAP.value == "MAP"

    def test_boss_relic_exists(self) -> None:
        """BOSS_RELIC decision type exists."""
        assert DecisionType.BOSS_RELIC is not None
        assert DecisionType.BOSS_RELIC.value == "BOSS_RELIC"

    def test_card_select_exists(self) -> None:
        """CARD_SELECT decision type exists for transform/remove/upgrade."""
        assert DecisionType.CARD_SELECT is not None
        assert DecisionType.CARD_SELECT.value == "CARD_SELECT"

    def test_combat_reward_exists(self) -> None:
        """COMBAT_REWARD decision type exists."""
        assert DecisionType.COMBAT_REWARD is not None
        assert DecisionType.COMBAT_REWARD.value == "COMBAT_REWARD"

    def test_hand_select_exists(self) -> None:
        """HAND_SELECT decision type exists."""
        assert DecisionType.HAND_SELECT is not None
        assert DecisionType.HAND_SELECT.value == "HAND_SELECT"


# ==============================================================================
# Card Reward Detection Tests
# ==============================================================================


class TestCardRewardDetection:
    """Tests for card reward screen detection."""

    def test_detects_card_reward(self, card_reward_state: GameState) -> None:
        """Detects card reward decision point."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert result.decision_type == DecisionType.CARD_REWARD

    def test_card_reward_includes_choices(self, card_reward_state: GameState) -> None:
        """Card reward includes available card choices."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert "Strike" in result.choices
        assert "Pommel Strike" in result.choices
        assert "Anger" in result.choices

    def test_card_reward_includes_skip_option(self, card_reward_state: GameState) -> None:
        """Card reward always includes skip as an option."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert result.context.can_skip is True

    def test_card_reward_with_bowl_includes_bowl_option(
        self, card_reward_with_bowl_state: GameState
    ) -> None:
        """Card reward with Singing Bowl includes bowl option."""
        result = detect_decision_point(card_reward_with_bowl_state)

        assert result is not None
        assert result.context.bowl_available is True

    def test_card_reward_context_has_screen_type(self, card_reward_state: GameState) -> None:
        """Card reward context includes screen type."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert result.context.screen_type == "CARD_REWARD"


# ==============================================================================
# Combat Detection Tests
# ==============================================================================


class TestCombatDetection:
    """Tests for combat turn detection."""

    def test_detects_combat(self, combat_state: GameState) -> None:
        """Detects combat decision point."""
        result = detect_decision_point(combat_state)

        assert result is not None
        assert result.decision_type == DecisionType.COMBAT

    def test_combat_includes_hand_as_choices(self, combat_state: GameState) -> None:
        """Combat choices include playable cards in hand."""
        result = detect_decision_point(combat_state)

        assert result is not None
        # Should include cards that can be played
        assert any("Strike" in choice for choice in result.choices)

    def test_combat_includes_end_turn_option(self, combat_state: GameState) -> None:
        """Combat includes end turn as an option."""
        result = detect_decision_point(combat_state)

        assert result is not None
        assert result.context.can_end_turn is True

    def test_combat_includes_usable_potions(self, combat_state: GameState) -> None:
        """Combat context includes usable potions."""
        result = detect_decision_point(combat_state)

        assert result is not None
        assert result.context.usable_potions is not None
        assert len(result.context.usable_potions) == 2  # Fire Potion and Block Potion

    def test_combat_includes_monster_info(self, combat_state: GameState) -> None:
        """Combat context includes monster information."""
        result = detect_decision_point(combat_state)

        assert result is not None
        assert result.context.monsters is not None
        assert len(result.context.monsters) == 1
        assert result.context.monsters[0]["name"] == "Jaw Worm"

    def test_combat_includes_energy_info(self, combat_state: GameState) -> None:
        """Combat context includes energy information."""
        result = detect_decision_point(combat_state)

        assert result is not None
        assert result.context.energy == 3
        assert result.context.max_energy == 3


# ==============================================================================
# Event Detection Tests
# ==============================================================================


class TestEventDetection:
    """Tests for event choice detection."""

    def test_detects_event(self, event_state: GameState) -> None:
        """Detects event decision point."""
        result = detect_decision_point(event_state)

        assert result is not None
        assert result.decision_type == DecisionType.EVENT

    def test_event_includes_choices(self, event_state: GameState) -> None:
        """Event includes available choices."""
        result = detect_decision_point(event_state)

        assert result is not None
        assert len(result.choices) == 2
        assert "[Pray] Lose 5 HP" in result.choices
        assert "[Leave] Nothing happens" in result.choices

    def test_event_context_has_event_name(self, event_state: GameState) -> None:
        """Event context includes event name."""
        result = detect_decision_point(event_state)

        assert result is not None
        assert result.context.event_name == "Forgotten Altar"

    def test_event_context_has_body_text(self, event_state: GameState) -> None:
        """Event context includes body text."""
        result = detect_decision_point(event_state)

        assert result is not None
        assert "ancient altar" in result.context.body_text.lower()


# ==============================================================================
# Shop Detection Tests
# ==============================================================================


class TestShopDetection:
    """Tests for shop detection."""

    def test_detects_shop(self, shop_state: GameState) -> None:
        """Detects shop decision point."""
        result = detect_decision_point(shop_state)

        assert result is not None
        assert result.decision_type == DecisionType.SHOP

    def test_shop_includes_purchasable_items(self, shop_state: GameState) -> None:
        """Shop includes purchasable items in choices."""
        result = detect_decision_point(shop_state)

        assert result is not None
        # Choices should include cards, relics, potions available
        assert len(result.choices) > 0

    def test_shop_context_has_gold(self, shop_state: GameState) -> None:
        """Shop context includes current gold."""
        result = detect_decision_point(shop_state)

        assert result is not None
        assert result.context.gold == 250

    def test_shop_context_has_purge_info(self, shop_state: GameState) -> None:
        """Shop context includes purge availability."""
        result = detect_decision_point(shop_state)

        assert result is not None
        assert result.context.can_purge is True
        assert result.context.purge_cost == 50

    def test_shop_context_has_items(self, shop_state: GameState) -> None:
        """Shop context includes available items with prices."""
        result = detect_decision_point(shop_state)

        assert result is not None
        assert result.context.shop_cards is not None
        assert result.context.shop_relics is not None
        assert result.context.shop_potions is not None


# ==============================================================================
# Campfire Detection Tests
# ==============================================================================


class TestCampfireDetection:
    """Tests for campfire/rest site detection."""

    def test_detects_campfire(self, rest_state: GameState) -> None:
        """Detects campfire decision point."""
        result = detect_decision_point(rest_state)

        assert result is not None
        assert result.decision_type == DecisionType.CAMPFIRE

    def test_campfire_includes_rest_option(self, rest_state: GameState) -> None:
        """Campfire includes rest option."""
        result = detect_decision_point(rest_state)

        assert result is not None
        assert "rest" in result.choices

    def test_campfire_includes_smith_option(self, rest_state: GameState) -> None:
        """Campfire includes smith (upgrade) option."""
        result = detect_decision_point(rest_state)

        assert result is not None
        assert "smith" in result.choices

    def test_campfire_with_key_includes_recall(self, rest_with_key_state: GameState) -> None:
        """Campfire with ruby key includes recall option."""
        result = detect_decision_point(rest_with_key_state)

        assert result is not None
        assert "recall" in result.choices

    def test_campfire_context_has_hp_info(self, rest_state: GameState) -> None:
        """Campfire context includes HP information for rest decision."""
        result = detect_decision_point(rest_state)

        assert result is not None
        assert result.context.current_hp == 50
        assert result.context.max_hp == 80


# ==============================================================================
# Map Detection Tests
# ==============================================================================


class TestMapDetection:
    """Tests for map selection detection."""

    def test_detects_map(self, map_state: GameState) -> None:
        """Detects map decision point."""
        result = detect_decision_point(map_state)

        assert result is not None
        assert result.decision_type == DecisionType.MAP

    def test_map_includes_available_nodes(self, map_state: GameState) -> None:
        """Map includes available nodes as choices."""
        result = detect_decision_point(map_state)

        assert result is not None
        assert len(result.choices) > 0

    def test_map_context_has_node_types(self, map_state: GameState) -> None:
        """Map context includes node type information."""
        result = detect_decision_point(map_state)

        assert result is not None
        assert result.context.next_nodes is not None
        assert len(result.context.next_nodes) == 3


# ==============================================================================
# Boss Relic Detection Tests
# ==============================================================================


class TestBossRelicDetection:
    """Tests for boss relic choice detection."""

    def test_detects_boss_relic(self, boss_relic_state: GameState) -> None:
        """Detects boss relic decision point."""
        result = detect_decision_point(boss_relic_state)

        assert result is not None
        assert result.decision_type == DecisionType.BOSS_RELIC

    def test_boss_relic_includes_choices(self, boss_relic_state: GameState) -> None:
        """Boss relic includes available relics as choices."""
        result = detect_decision_point(boss_relic_state)

        assert result is not None
        assert "Black Star" in result.choices
        assert "Calling Bell" in result.choices
        assert "Sacred Bark" in result.choices

    def test_boss_relic_includes_skip_option(self, boss_relic_state: GameState) -> None:
        """Boss relic includes skip option."""
        result = detect_decision_point(boss_relic_state)

        assert result is not None
        assert result.context.can_skip is True

    def test_boss_relic_context_has_relic_info(self, boss_relic_state: GameState) -> None:
        """Boss relic context includes relic descriptions."""
        result = detect_decision_point(boss_relic_state)

        assert result is not None
        assert result.context.relic_options is not None
        assert len(result.context.relic_options) == 3


# ==============================================================================
# Card Selection Detection Tests (Transform/Remove/Upgrade)
# ==============================================================================


class TestCardSelectDetection:
    """Tests for card transform/remove/upgrade selection detection."""

    def test_detects_card_transform(self, card_transform_state: GameState) -> None:
        """Detects card transform decision point."""
        result = detect_decision_point(card_transform_state)

        assert result is not None
        assert result.decision_type == DecisionType.CARD_SELECT

    def test_card_transform_context_indicates_transform(
        self, card_transform_state: GameState
    ) -> None:
        """Card transform context indicates transform mode."""
        result = detect_decision_point(card_transform_state)

        assert result is not None
        assert result.context.selection_mode == "transform"

    def test_detects_card_remove(self, card_remove_state: GameState) -> None:
        """Detects card remove decision point."""
        result = detect_decision_point(card_remove_state)

        assert result is not None
        assert result.decision_type == DecisionType.CARD_SELECT

    def test_card_remove_context_indicates_purge(self, card_remove_state: GameState) -> None:
        """Card remove context indicates purge mode."""
        result = detect_decision_point(card_remove_state)

        assert result is not None
        assert result.context.selection_mode == "purge"

    def test_detects_card_upgrade(self, card_upgrade_state: GameState) -> None:
        """Detects card upgrade selection."""
        result = detect_decision_point(card_upgrade_state)

        assert result is not None
        assert result.decision_type == DecisionType.CARD_SELECT

    def test_card_upgrade_context_indicates_upgrade(
        self, card_upgrade_state: GameState
    ) -> None:
        """Card upgrade context indicates upgrade mode."""
        result = detect_decision_point(card_upgrade_state)

        assert result is not None
        assert result.context.selection_mode == "upgrade"

    def test_card_select_includes_cards_as_choices(
        self, card_transform_state: GameState
    ) -> None:
        """Card select includes available cards as choices."""
        result = detect_decision_point(card_transform_state)

        assert result is not None
        assert "Strike" in result.choices
        assert "Defend" in result.choices


# ==============================================================================
# Combat Reward Detection Tests
# ==============================================================================


class TestCombatRewardDetection:
    """Tests for combat reward screen detection."""

    def test_detects_combat_reward(self, combat_reward_state: GameState) -> None:
        """Detects combat reward decision point."""
        result = detect_decision_point(combat_reward_state)

        assert result is not None
        assert result.decision_type == DecisionType.COMBAT_REWARD

    def test_combat_reward_includes_reward_types(
        self, combat_reward_state: GameState
    ) -> None:
        """Combat reward includes available reward types."""
        result = detect_decision_point(combat_reward_state)

        assert result is not None
        assert result.context.rewards is not None


# ==============================================================================
# Hand Select Detection Tests
# ==============================================================================


class TestHandSelectDetection:
    """Tests for hand select detection (during combat)."""

    def test_detects_hand_select(self, hand_select_state: GameState) -> None:
        """Detects hand select decision point."""
        result = detect_decision_point(hand_select_state)

        assert result is not None
        assert result.decision_type == DecisionType.HAND_SELECT

    def test_hand_select_includes_cards(self, hand_select_state: GameState) -> None:
        """Hand select includes cards that can be selected."""
        result = detect_decision_point(hand_select_state)

        assert result is not None
        assert len(result.choices) == 3

    def test_hand_select_context_has_selection_type(
        self, hand_select_state: GameState
    ) -> None:
        """Hand select context includes selection type."""
        result = detect_decision_point(hand_select_state)

        assert result is not None
        assert result.context.selection_type == "upgrade"


# ==============================================================================
# No Decision Point Tests
# ==============================================================================


class TestNoDecisionPoint:
    """Tests for states that are not decision points."""

    def test_no_decision_at_main_menu(self, main_menu_state: GameState) -> None:
        """Returns None when at main menu."""
        result = detect_decision_point(main_menu_state)

        assert result is None

    def test_no_decision_when_not_in_game(self) -> None:
        """Returns None when not in game."""
        state = GameState(in_game=False, screen_type="NONE")

        result = detect_decision_point(state)

        assert result is None


# ==============================================================================
# DecisionPoint Model Tests
# ==============================================================================


class TestDecisionPointModel:
    """Tests for the DecisionPoint model structure."""

    def test_decision_point_has_type(self, card_reward_state: GameState) -> None:
        """DecisionPoint has decision_type field."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert hasattr(result, "decision_type")
        assert isinstance(result.decision_type, DecisionType)

    def test_decision_point_has_choices(self, card_reward_state: GameState) -> None:
        """DecisionPoint has choices field."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert hasattr(result, "choices")
        assert isinstance(result.choices, list)

    def test_decision_point_has_context(self, card_reward_state: GameState) -> None:
        """DecisionPoint has context field."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert hasattr(result, "context")
        assert isinstance(result.context, DecisionContext)


# ==============================================================================
# DecisionContext Model Tests
# ==============================================================================


class TestDecisionContextModel:
    """Tests for the DecisionContext model structure."""

    def test_context_has_screen_type(self, card_reward_state: GameState) -> None:
        """DecisionContext has screen_type field."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        assert hasattr(result.context, "screen_type")

    def test_context_converts_to_dict(self, card_reward_state: GameState) -> None:
        """DecisionContext can be converted to dict."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        context_dict = result.context.model_dump()
        assert isinstance(context_dict, dict)
        assert "screen_type" in context_dict

    def test_decision_point_converts_to_dict(self, card_reward_state: GameState) -> None:
        """DecisionPoint can be converted to dict for serialization."""
        result = detect_decision_point(card_reward_state)

        assert result is not None
        result_dict = result.model_dump()
        assert isinstance(result_dict, dict)
        assert "decision_type" in result_dict
        assert "choices" in result_dict
        assert "context" in result_dict
