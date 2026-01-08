"""Tests for MCP prompt implementations.

Tests for analysis prompts that guide Claude's reasoning about game state.
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
from slay_the_spire_mcp.prompts import (
    analyze_combat,
    evaluate_card_reward,
    evaluate_event,
    plan_path,
)

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def basic_deck() -> list[Card]:
    """Basic Ironclad starter deck."""
    return [
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Strike", cost=1, type="ATTACK"),
        Card(name="Defend", cost=1, type="SKILL"),
        Card(name="Defend", cost=1, type="SKILL"),
        Card(name="Defend", cost=1, type="SKILL"),
        Card(name="Defend", cost=1, type="SKILL"),
        Card(name="Bash", cost=2, type="ATTACK"),
    ]


@pytest.fixture
def basic_relics() -> list[Relic]:
    """Basic Ironclad starter relic."""
    return [Relic(name="Burning Blood")]


@pytest.fixture
def combat_state(basic_deck: list[Card]) -> GameState:
    """Game state during combat."""
    return GameState(
        in_game=True,
        screen_type="NONE",
        floor=3,
        act=1,
        hp=70,
        max_hp=80,
        gold=50,
        deck=basic_deck,
        relics=[Relic(name="Burning Blood")],
        potions=[Potion(name="Fire Potion", can_use=True, requires_target=True)],
        combat_state=CombatState(
            turn=1,
            monsters=[
                Monster(
                    name="Jaw Worm",
                    current_hp=44,
                    max_hp=44,
                    block=0,
                    intent="ATTACK",
                    powers=[],
                )
            ],
            hand=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Bash", cost=2, type="ATTACK"),
            ],
            draw_pile=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Defend", cost=1, type="SKILL"),
                Card(name="Defend", cost=1, type="SKILL"),
            ],
            discard_pile=[],
            exhaust_pile=[],
            energy=3,
            max_energy=3,
            player_block=0,
            player_powers=[],
        ),
    )


@pytest.fixture
def card_reward_state(basic_deck: list[Card]) -> GameState:
    """Game state during card reward screen."""
    return GameState(
        in_game=True,
        screen_type="CARD_REWARD",
        floor=5,
        act=1,
        hp=65,
        max_hp=80,
        gold=99,
        deck=basic_deck,
        relics=[Relic(name="Burning Blood")],
        potions=[],
        choice_list=["Pommel Strike", "Anger", "Clothesline"],
    )


@pytest.fixture
def map_state(basic_deck: list[Card]) -> GameState:
    """Game state on map screen."""
    return GameState(
        in_game=True,
        screen_type="MAP",
        floor=5,
        act=1,
        hp=60,
        max_hp=80,
        gold=120,
        deck=basic_deck,
        relics=[Relic(name="Burning Blood")],
        potions=[Potion(name="Block Potion", can_use=True)],
        map=[
            [MapNode(x=0, y=0, symbol="M", children=[(0, 1), (1, 1)])],
            [
                MapNode(x=0, y=1, symbol="?", children=[(0, 2)]),
                MapNode(x=1, y=1, symbol="M", children=[(1, 2)]),
            ],
            [
                MapNode(x=0, y=2, symbol="$", children=[(0, 3)]),
                MapNode(x=1, y=2, symbol="R", children=[(1, 3)]),
            ],
            [
                MapNode(x=0, y=3, symbol="E", children=[]),
                MapNode(x=1, y=3, symbol="E", children=[]),
            ],
        ],
        current_node=(0, 0),
    )


@pytest.fixture
def event_state(basic_deck: list[Card]) -> GameState:
    """Game state during an event."""
    return GameState(
        in_game=True,
        screen_type="EVENT",
        floor=7,
        act=1,
        hp=55,
        max_hp=80,
        gold=150,
        deck=basic_deck,
        relics=[Relic(name="Burning Blood")],
        potions=[],
        choice_list=["[Pray] Lose 5 HP", "[Leave] Nothing happens"],
        screen_state={"event_name": "The Divine Fountain"},
    )


# ==============================================================================
# analyze_combat Tests
# ==============================================================================


class TestAnalyzeCombat:
    """Tests for the analyze_combat prompt."""

    def test_returns_string(self, combat_state: GameState) -> None:
        """Prompt returns a non-empty string."""
        result = analyze_combat(combat_state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_monster_info(self, combat_state: GameState) -> None:
        """Prompt includes monster name and HP."""
        result = analyze_combat(combat_state)
        assert "Jaw Worm" in result
        assert "44" in result  # HP

    def test_includes_intent(self, combat_state: GameState) -> None:
        """Prompt includes monster intent."""
        result = analyze_combat(combat_state)
        assert "ATTACK" in result or "attack" in result.lower()

    def test_includes_energy(self, combat_state: GameState) -> None:
        """Prompt includes available energy."""
        result = analyze_combat(combat_state)
        assert "3" in result  # Energy
        assert "energy" in result.lower()

    def test_includes_hand_cards(self, combat_state: GameState) -> None:
        """Prompt includes cards in hand."""
        result = analyze_combat(combat_state)
        assert "Strike" in result
        assert "Defend" in result
        assert "Bash" in result

    def test_includes_player_hp(self, combat_state: GameState) -> None:
        """Prompt includes player HP."""
        result = analyze_combat(combat_state)
        assert "70" in result  # Current HP
        assert "80" in result  # Max HP

    def test_includes_analysis_guidance(self, combat_state: GameState) -> None:
        """Prompt includes guidance for analysis."""
        result = analyze_combat(combat_state)
        # Should mention damage, block, or strategic considerations
        assert any(
            term in result.lower()
            for term in ["damage", "block", "priority", "recommend", "analysis"]
        )

    def test_includes_potions_if_available(self, combat_state: GameState) -> None:
        """Prompt mentions available potions."""
        result = analyze_combat(combat_state)
        assert "Fire Potion" in result or "potion" in result.lower()

    def test_handles_multiple_monsters(self) -> None:
        """Prompt handles multiple monsters correctly."""
        state = GameState(
            in_game=True,
            screen_type="NONE",
            hp=50,
            max_hp=80,
            combat_state=CombatState(
                turn=1,
                monsters=[
                    Monster(name="Cultist", current_hp=50, max_hp=50, intent="BUFF"),
                    Monster(name="Cultist", current_hp=48, max_hp=50, intent="ATTACK"),
                ],
                hand=[Card(name="Strike", cost=1, type="ATTACK")],
                energy=3,
                max_energy=3,
            ),
        )
        result = analyze_combat(state)
        assert "Cultist" in result
        # Should mention both monsters or indicate multiple enemies
        assert result.count("Cultist") >= 1 or "enemies" in result.lower()

    def test_handles_no_combat_state(self) -> None:
        """Prompt handles missing combat state gracefully."""
        state = GameState(in_game=True, screen_type="MAP", hp=70, max_hp=80)
        result = analyze_combat(state)
        # Should return something indicating no combat
        assert "not in combat" in result.lower() or "no combat" in result.lower()


# ==============================================================================
# evaluate_card_reward Tests
# ==============================================================================


class TestEvaluateCardReward:
    """Tests for the evaluate_card_reward prompt."""

    def test_returns_string(self, card_reward_state: GameState) -> None:
        """Prompt returns a non-empty string."""
        result = evaluate_card_reward(card_reward_state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_card_choices(self, card_reward_state: GameState) -> None:
        """Prompt includes all card choices."""
        result = evaluate_card_reward(card_reward_state)
        assert "Pommel Strike" in result
        assert "Anger" in result
        assert "Clothesline" in result

    def test_includes_current_deck(self, card_reward_state: GameState) -> None:
        """Prompt mentions deck context."""
        result = evaluate_card_reward(card_reward_state)
        # Should mention deck size or composition
        assert "deck" in result.lower()

    def test_includes_skip_option(self, card_reward_state: GameState) -> None:
        """Prompt mentions skip as an option."""
        result = evaluate_card_reward(card_reward_state)
        assert "skip" in result.lower()

    def test_includes_floor_context(self, card_reward_state: GameState) -> None:
        """Prompt includes floor/progression context."""
        result = evaluate_card_reward(card_reward_state)
        assert "5" in result or "floor" in result.lower() or "act" in result.lower()

    def test_includes_evaluation_criteria(self, card_reward_state: GameState) -> None:
        """Prompt includes criteria for evaluation."""
        result = evaluate_card_reward(card_reward_state)
        # Should mention synergy, value, or similar
        assert any(
            term in result.lower()
            for term in ["synergy", "value", "consider", "recommend", "analysis"]
        )

    def test_handles_empty_choices(self) -> None:
        """Prompt handles empty choice list."""
        state = GameState(
            in_game=True,
            screen_type="CARD_REWARD",
            hp=70,
            max_hp=80,
            choice_list=[],
        )
        result = evaluate_card_reward(state)
        assert isinstance(result, str)
        # Should indicate no choices available
        assert "no" in result.lower() or "empty" in result.lower()


# ==============================================================================
# plan_path Tests
# ==============================================================================


class TestPlanPath:
    """Tests for the plan_path prompt."""

    def test_returns_string(self, map_state: GameState) -> None:
        """Prompt returns a non-empty string."""
        result = plan_path(map_state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_hp_context(self, map_state: GameState) -> None:
        """Prompt includes HP for risk assessment."""
        result = plan_path(map_state)
        assert "60" in result or "80" in result
        assert "hp" in result.lower() or "health" in result.lower()

    def test_includes_node_types(self, map_state: GameState) -> None:
        """Prompt mentions different node types."""
        result = plan_path(map_state)
        # Should mention at least some node types or their meanings
        assert any(
            symbol in result for symbol in ["M", "?", "$", "R", "E"]
        ) or any(
            term in result.lower()
            for term in ["monster", "elite", "event", "rest", "shop", "unknown"]
        )

    def test_includes_floor_context(self, map_state: GameState) -> None:
        """Prompt includes floor information."""
        result = plan_path(map_state)
        assert "5" in result or "floor" in result.lower()

    def test_includes_risk_assessment_guidance(self, map_state: GameState) -> None:
        """Prompt guides risk assessment."""
        result = plan_path(map_state)
        assert any(
            term in result.lower()
            for term in ["risk", "path", "recommend", "consider", "route"]
        )

    def test_handles_no_map(self) -> None:
        """Prompt handles missing map gracefully."""
        state = GameState(
            in_game=True,
            screen_type="COMBAT",
            hp=70,
            max_hp=80,
            map=None,
        )
        result = plan_path(state)
        assert "no map" in result.lower() or "not available" in result.lower()

    def test_includes_gold_context(self, map_state: GameState) -> None:
        """Prompt includes gold for shop decisions."""
        result = plan_path(map_state)
        assert "120" in result or "gold" in result.lower()


# ==============================================================================
# evaluate_event Tests
# ==============================================================================


class TestEvaluateEvent:
    """Tests for the evaluate_event prompt."""

    def test_returns_string(self, event_state: GameState) -> None:
        """Prompt returns a non-empty string."""
        result = evaluate_event(event_state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_event_name(self, event_state: GameState) -> None:
        """Prompt includes event name if available."""
        result = evaluate_event(event_state)
        assert "Divine Fountain" in result or "event" in result.lower()

    def test_includes_choices(self, event_state: GameState) -> None:
        """Prompt includes event choices."""
        result = evaluate_event(event_state)
        assert "Pray" in result or "Leave" in result
        assert "5 HP" in result or "lose" in result.lower()

    def test_includes_hp_context(self, event_state: GameState) -> None:
        """Prompt includes HP for risk evaluation."""
        result = evaluate_event(event_state)
        assert "55" in result or "80" in result or "hp" in result.lower()

    def test_includes_gold_context(self, event_state: GameState) -> None:
        """Prompt includes gold for cost evaluation."""
        result = evaluate_event(event_state)
        assert "150" in result or "gold" in result.lower()

    def test_includes_evaluation_guidance(self, event_state: GameState) -> None:
        """Prompt includes guidance for evaluation."""
        result = evaluate_event(event_state)
        assert any(
            term in result.lower()
            for term in ["risk", "reward", "recommend", "consider", "analysis"]
        )

    def test_handles_no_event(self) -> None:
        """Prompt handles non-event state gracefully."""
        state = GameState(
            in_game=True,
            screen_type="MAP",
            hp=70,
            max_hp=80,
            choice_list=[],
        )
        result = evaluate_event(state)
        assert "no event" in result.lower() or "not at event" in result.lower()

    def test_handles_empty_choices(self) -> None:
        """Prompt handles event with no choices."""
        state = GameState(
            in_game=True,
            screen_type="EVENT",
            hp=70,
            max_hp=80,
            choice_list=[],
            screen_state={"event_name": "Some Event"},
        )
        result = evaluate_event(state)
        assert isinstance(result, str)


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestPromptIntegration:
    """Integration tests for prompts working together."""

    def test_all_prompts_handle_minimal_state(self) -> None:
        """All prompts handle minimal game state without crashing."""
        minimal_state = GameState(in_game=True, hp=50, max_hp=80)

        # None should raise an exception
        result_combat = analyze_combat(minimal_state)
        result_card = evaluate_card_reward(minimal_state)
        result_path = plan_path(minimal_state)
        result_event = evaluate_event(minimal_state)

        assert all(
            isinstance(r, str)
            for r in [result_combat, result_card, result_path, result_event]
        )

    def test_prompts_are_distinct(
        self,
        combat_state: GameState,
        card_reward_state: GameState,
        map_state: GameState,
        event_state: GameState,
    ) -> None:
        """Each prompt produces distinct output appropriate to its context."""
        combat_result = analyze_combat(combat_state)
        card_result = evaluate_card_reward(card_reward_state)
        path_result = plan_path(map_state)
        event_result = evaluate_event(event_state)

        # Results should be different
        results = [combat_result, card_result, path_result, event_result]
        assert len(set(results)) == 4, "All prompts should produce distinct outputs"
