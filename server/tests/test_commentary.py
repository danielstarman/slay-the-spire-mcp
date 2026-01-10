"""Tests for auto-commentary system.

Tests the CommentaryEngine that generates analysis when decision points are detected.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from slay_the_spire_mcp.context import RunContext
from slay_the_spire_mcp.detection import DecisionType
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
def run_context() -> RunContext:
    """Create a fresh RunContext for testing."""
    return RunContext()


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
        deck=[Card(name="Strike", cost=1, type="ATTACK")],
        relics=[],
        potions=[],
        choice_list=[],
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
                {
                    "name": "Black Star",
                    "id": "Black Star",
                    "description": "Elites drop 2 relics",
                },
                {
                    "name": "Calling Bell",
                    "id": "Calling Bell",
                    "description": "Gain 3 relics and 3 curses",
                },
                {
                    "name": "Sacred Bark",
                    "id": "Sacred Bark",
                    "description": "Double potion effects",
                },
            ],
        },
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
            Potion(
                name="Fire Potion", id="Fire Potion", can_use=True, requires_target=True
            ),
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
                Monster(
                    name="Jaw Worm", id="Jaw Worm", current_hp=44, max_hp=44, intent="ATTACK"
                ),
            ],
        ),
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


# ==============================================================================
# CommentaryEngine Initialization Tests
# ==============================================================================


class TestCommentaryEngineInit:
    """Tests for CommentaryEngine initialization."""

    def test_engine_initializes_with_run_context(self, run_context: RunContext) -> None:
        """CommentaryEngine initializes with a RunContext."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        assert engine is not None

    def test_engine_accepts_custom_debounce(self, run_context: RunContext) -> None:
        """CommentaryEngine accepts custom debounce_ms parameter."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context, debounce_ms=1000)
        assert engine is not None

    def test_engine_has_no_cached_commentary_initially(
        self, run_context: RunContext
    ) -> None:
        """CommentaryEngine starts with no cached commentary."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is None
        assert decision_type is None


# ==============================================================================
# Happy Path Tests - Commentary Generation
# ==============================================================================


class TestCommentaryGeneration:
    """Tests for commentary generation on decision points."""

    def test_commentary_generated_on_card_reward(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Given state change to CARD_REWARD screen, commentary engine generates analysis."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(card_reward_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.CARD_REWARD
        assert "card" in commentary.lower() or "reward" in commentary.lower()

    def test_commentary_generated_on_event(
        self, run_context: RunContext, event_state: GameState
    ) -> None:
        """Given state change to EVENT screen, commentary engine generates analysis."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(event_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.EVENT
        assert "event" in commentary.lower()

    def test_commentary_generated_on_map(
        self, run_context: RunContext, map_state: GameState
    ) -> None:
        """Given state change to MAP screen, commentary engine generates path planning prompt."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(map_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.MAP
        # Should contain map/path planning content
        assert "path" in commentary.lower() or "map" in commentary.lower()

    def test_commentary_generated_on_shop(
        self, run_context: RunContext, shop_state: GameState
    ) -> None:
        """Given state change to SHOP_SCREEN, commentary engine generates shop evaluation prompt."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(shop_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.SHOP
        assert "shop" in commentary.lower()

    def test_commentary_generated_on_campfire(
        self, run_context: RunContext, rest_state: GameState
    ) -> None:
        """Given state change to REST screen, commentary engine generates campfire evaluation prompt."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(rest_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.CAMPFIRE
        assert "rest" in commentary.lower() or "campfire" in commentary.lower()

    def test_commentary_generated_on_boss_relic(
        self, run_context: RunContext, boss_relic_state: GameState
    ) -> None:
        """Given state change to BOSS_REWARD screen, commentary engine generates boss relic evaluation prompt."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(boss_relic_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.BOSS_RELIC
        assert "relic" in commentary.lower() or "boss" in commentary.lower()

    def test_commentary_includes_run_context(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Generated commentary includes run history (context summary)."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(card_reward_state)

        commentary, _ = engine.get_cached_commentary()
        assert commentary is not None
        # Should include run history context section
        assert "run" in commentary.lower() or "context" in commentary.lower()


# ==============================================================================
# Combat Skip Tests
# ==============================================================================


class TestCombatSkip:
    """Tests that combat decision points are skipped."""

    def test_no_commentary_for_combat(
        self, run_context: RunContext, combat_state: GameState
    ) -> None:
        """State updates during combat do not trigger commentary."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(combat_state)

        commentary, decision_type = engine.get_cached_commentary()
        # Combat should be skipped - no commentary generated
        assert commentary is None
        assert decision_type is None


# ==============================================================================
# Debouncing Tests
# ==============================================================================


class TestDebouncing:
    """Tests for debouncing rapid state updates."""

    def test_debounce_same_decision(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Rapid state updates for same decision only generate commentary once."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        callback_count = 0

        def count_callback(commentary: str, decision_type: DecisionType) -> None:
            nonlocal callback_count
            callback_count += 1

        engine = CommentaryEngine(run_context, debounce_ms=500)
        engine.on_commentary_generated(count_callback)

        # Rapid updates with same state
        engine.on_state_change(card_reward_state)
        engine.on_state_change(card_reward_state)
        engine.on_state_change(card_reward_state)

        # Should only have generated commentary once
        assert callback_count == 1

    def test_debounce_resets_on_floor_change(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Floor change resets debounce, allowing new commentary."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        callback_count = 0

        def count_callback(commentary: str, decision_type: DecisionType) -> None:
            nonlocal callback_count
            callback_count += 1

        engine = CommentaryEngine(run_context, debounce_ms=500)
        engine.on_commentary_generated(count_callback)

        # First update
        engine.on_state_change(card_reward_state)

        # Same state but different floor
        new_floor_state = card_reward_state.model_copy(update={"floor": 6})
        engine.on_state_change(new_floor_state)

        # Should have generated commentary twice (floor changed)
        assert callback_count == 2

    def test_debounce_resets_on_screen_change(
        self, run_context: RunContext, card_reward_state: GameState, event_state: GameState
    ) -> None:
        """Screen type change resets debounce."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        callback_count = 0

        def count_callback(commentary: str, decision_type: DecisionType) -> None:
            nonlocal callback_count
            callback_count += 1

        engine = CommentaryEngine(run_context, debounce_ms=500)
        engine.on_commentary_generated(count_callback)

        engine.on_state_change(card_reward_state)
        engine.on_state_change(event_state)  # Different screen type

        # Should have generated commentary twice
        assert callback_count == 2


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_no_commentary_when_not_in_game(
        self, run_context: RunContext, main_menu_state: GameState
    ) -> None:
        """Main menu state does not trigger commentary."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)
        engine.on_state_change(main_menu_state)

        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is None
        assert decision_type is None

    def test_run_context_resets_on_new_run(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Starting new run clears cached commentary."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        engine = CommentaryEngine(run_context)

        # Generate commentary on high floor
        high_floor_state = card_reward_state.model_copy(update={"floor": 10})
        engine.on_state_change(high_floor_state)
        assert engine.get_cached_commentary()[0] is not None

        # Reset to floor 0 (new run)
        new_run_state = card_reward_state.model_copy(update={"floor": 0})
        engine.on_state_change(new_run_state)

        # Commentary should be regenerated (not the same as before)
        commentary, _ = engine.get_cached_commentary()
        assert commentary is not None

    def test_commentary_survives_callback_error(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """If one callback fails, others still execute."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        results: list[str] = []

        def failing_callback(commentary: str, decision_type: DecisionType) -> None:
            raise ValueError("Intentional test error")

        def success_callback(commentary: str, decision_type: DecisionType) -> None:
            results.append("success")

        engine = CommentaryEngine(run_context)
        engine.on_commentary_generated(failing_callback)
        engine.on_commentary_generated(success_callback)

        # Should not raise, and second callback should still execute
        engine.on_state_change(card_reward_state)
        assert "success" in results


# ==============================================================================
# Error Condition Tests
# ==============================================================================


class TestErrorConditions:
    """Tests for error conditions."""

    def test_missing_prompt_generator_fallback(
        self, run_context: RunContext
    ) -> None:
        """Decision type without specific prompt uses generic fallback."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        # Create a state that triggers HAND_SELECT (less common decision type)
        state = GameState(
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
            choice_list=["Strike", "Defend"],
            screen_state={
                "selection_type": "upgrade",
                "num_cards": 1,
            },
        )

        engine = CommentaryEngine(run_context)
        engine.on_state_change(state)

        # Should generate some commentary (fallback)
        commentary, decision_type = engine.get_cached_commentary()
        assert commentary is not None
        assert decision_type == DecisionType.HAND_SELECT


# ==============================================================================
# Callback Tests
# ==============================================================================


class TestCallbacks:
    """Tests for commentary callbacks."""

    def test_callback_receives_commentary_and_type(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Callback receives both commentary and decision type."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        received_commentary: str | None = None
        received_type: DecisionType | None = None

        def capture_callback(commentary: str, decision_type: DecisionType) -> None:
            nonlocal received_commentary, received_type
            received_commentary = commentary
            received_type = decision_type

        engine = CommentaryEngine(run_context)
        engine.on_commentary_generated(capture_callback)
        engine.on_state_change(card_reward_state)

        assert received_commentary is not None
        assert received_type == DecisionType.CARD_REWARD

    def test_multiple_callbacks_all_called(
        self, run_context: RunContext, card_reward_state: GameState
    ) -> None:
        """Multiple registered callbacks are all called."""
        from slay_the_spire_mcp.commentary import CommentaryEngine

        results: list[int] = []

        engine = CommentaryEngine(run_context)
        engine.on_commentary_generated(lambda c, t: results.append(1))
        engine.on_commentary_generated(lambda c, t: results.append(2))
        engine.on_commentary_generated(lambda c, t: results.append(3))

        engine.on_state_change(card_reward_state)

        assert results == [1, 2, 3]
