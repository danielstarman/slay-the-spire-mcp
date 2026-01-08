"""Tests for run context tracking.

Tests for RunContext which maintains history across a run for analysis context.
"""

from __future__ import annotations

import pytest

from slay_the_spire_mcp.context import (
    CombatRecord,
    EventRecord,
    RunContext,
)
from slay_the_spire_mcp.models import (
    Card,
    CombatState,
    GameState,
    Monster,
    Relic,
)

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def run_context() -> RunContext:
    """Fresh run context for testing."""
    return RunContext()


@pytest.fixture
def basic_game_state() -> GameState:
    """Basic game state for testing."""
    return GameState(
        in_game=True,
        screen_type="MAP",
        floor=5,
        act=1,
        hp=70,
        max_hp=80,
        gold=100,
        deck=[
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Strike", cost=1, type="ATTACK"),
            Card(name="Defend", cost=1, type="SKILL"),
            Card(name="Bash", cost=2, type="ATTACK"),
        ],
        relics=[Relic(name="Burning Blood")],
    )


@pytest.fixture
def combat_game_state() -> GameState:
    """Game state in combat."""
    return GameState(
        in_game=True,
        screen_type="NONE",
        floor=3,
        act=1,
        hp=65,
        max_hp=80,
        gold=50,
        deck=[Card(name="Strike", cost=1, type="ATTACK")],
        relics=[Relic(name="Burning Blood")],
        combat_state=CombatState(
            turn=1,
            monsters=[
                Monster(
                    name="Jaw Worm",
                    current_hp=44,
                    max_hp=44,
                    intent="ATTACK",
                ),
            ],
            hand=[Card(name="Strike", cost=1, type="ATTACK")],
            energy=3,
            max_energy=3,
        ),
    )


# ==============================================================================
# RunContext Initialization Tests
# ==============================================================================


class TestRunContextInit:
    """Tests for RunContext initialization."""

    def test_initializes_empty(self, run_context: RunContext) -> None:
        """Context starts with empty history."""
        assert run_context.combats == []
        assert run_context.events == []
        assert run_context.cards_added == []
        assert run_context.cards_removed == []
        assert run_context.relics_acquired == []
        assert run_context.gold_history == []
        assert run_context.hp_history == []

    def test_initializes_with_default_floor(self, run_context: RunContext) -> None:
        """Context starts at floor 0."""
        assert run_context.current_floor == 0
        assert run_context.current_act == 1

    def test_reset_clears_all(self, run_context: RunContext) -> None:
        """Reset clears all history."""
        # Add some data
        run_context.gold_history.append(100)
        run_context.hp_history.append(80)
        run_context.current_floor = 5

        run_context.reset()

        assert run_context.gold_history == []
        assert run_context.hp_history == []
        assert run_context.current_floor == 0


# ==============================================================================
# State Update Tests
# ==============================================================================


class TestStateUpdates:
    """Tests for updating context from game state."""

    def test_updates_floor_and_act(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Updates current floor and act."""
        run_context.update(basic_game_state)

        assert run_context.current_floor == 5
        assert run_context.current_act == 1

    def test_tracks_gold_history(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Records gold values over time on floor changes."""
        run_context.update(basic_game_state)
        assert 100 in run_context.gold_history

        # Move to next floor with different gold
        basic_game_state.floor = 6
        basic_game_state.gold = 150
        run_context.update(basic_game_state)
        assert 150 in run_context.gold_history

    def test_tracks_hp_history(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Records HP values over time on floor changes."""
        run_context.update(basic_game_state)
        assert (70, 80) in run_context.hp_history  # (current, max)

        # Move to next floor with different HP
        basic_game_state.floor = 6
        basic_game_state.hp = 60
        run_context.update(basic_game_state)
        assert (60, 80) in run_context.hp_history

    def test_detects_new_relics(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Detects when new relics are acquired."""
        run_context.update(basic_game_state)
        assert "Burning Blood" in run_context.relics_acquired

        # Add another relic
        basic_game_state.relics.append(Relic(name="Bag of Preparation"))
        run_context.update(basic_game_state)
        assert "Bag of Preparation" in run_context.relics_acquired

    def test_detects_cards_added(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Detects when cards are added to deck."""
        run_context.update(basic_game_state)

        # Add a new card
        basic_game_state.deck.append(Card(name="Pommel Strike", cost=1, type="ATTACK"))
        run_context.update(basic_game_state)

        assert any(c.name == "Pommel Strike" for c in run_context.cards_added)

    def test_detects_cards_removed(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Detects when cards are removed from deck."""
        run_context.update(basic_game_state)

        # Remove a Strike
        basic_game_state.deck = [
            c for c in basic_game_state.deck if c.name != "Strike"
        ][:3]  # Keep only non-Strikes
        run_context.update(basic_game_state)

        assert any(c.name == "Strike" for c in run_context.cards_removed)

    def test_only_updates_on_floor_change(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """HP/gold history only records on floor changes to avoid duplicates."""
        run_context.update(basic_game_state)
        initial_len = len(run_context.gold_history)

        # Same floor, different gold - should not add
        basic_game_state.gold = 120
        run_context.update(basic_game_state)

        # Should still be same length (no duplicate floor entries)
        assert len(run_context.gold_history) == initial_len


# ==============================================================================
# Combat Record Tests
# ==============================================================================


class TestCombatRecords:
    """Tests for combat tracking."""

    def test_records_combat_start(
        self, run_context: RunContext, combat_game_state: GameState
    ) -> None:
        """Records when combat starts."""
        run_context.update(combat_game_state)

        assert len(run_context.combats) >= 1
        latest = run_context.combats[-1]
        assert latest.floor == 3
        assert "Jaw Worm" in latest.enemies

    def test_records_combat_damage_taken(
        self, run_context: RunContext, combat_game_state: GameState
    ) -> None:
        """Records damage taken in combat."""
        # Start combat at 65 HP
        run_context.update(combat_game_state)

        # End combat at 55 HP (took 10 damage)
        combat_game_state.hp = 55
        combat_game_state.combat_state = None  # Combat ended
        combat_game_state.screen_type = "COMBAT_REWARD"
        run_context.update(combat_game_state)

        latest = run_context.combats[-1]
        assert latest.damage_taken == 10

    def test_combat_record_fields(self) -> None:
        """CombatRecord has all required fields."""
        record = CombatRecord(
            floor=5,
            enemies=["Gremlin Nob"],
            damage_taken=25,
            was_elite=True,
        )
        assert record.floor == 5
        assert record.enemies == ["Gremlin Nob"]
        assert record.damage_taken == 25
        assert record.was_elite is True


# ==============================================================================
# Event Record Tests
# ==============================================================================


class TestEventRecords:
    """Tests for event tracking."""

    def test_records_event_choice(self, run_context: RunContext) -> None:
        """Records event choices made."""
        state = GameState(
            in_game=True,
            screen_type="EVENT",
            floor=7,
            act=1,
            hp=55,
            max_hp=80,
            gold=150,
            choice_list=["[Pray] Lose 5 HP", "[Leave] Nothing happens"],
            screen_state={"event_name": "The Divine Fountain"},
        )
        run_context.update(state)

        # Simulate choosing option 1
        state.screen_type = "MAP"  # Event ended
        state.hp = 50  # Lost 5 HP from choice
        run_context.record_event_choice("The Divine Fountain", "[Pray] Lose 5 HP")

        assert len(run_context.events) >= 1
        latest = run_context.events[-1]
        assert latest.event_name == "The Divine Fountain"
        assert latest.choice_made == "[Pray] Lose 5 HP"

    def test_event_record_fields(self) -> None:
        """EventRecord has all required fields."""
        record = EventRecord(
            floor=7,
            event_name="Neow's Lament",
            choice_made="[Gain 100 gold]",
        )
        assert record.floor == 7
        assert record.event_name == "Neow's Lament"
        assert record.choice_made == "[Gain 100 gold]"


# ==============================================================================
# Trend Analysis Tests
# ==============================================================================


class TestTrendAnalysis:
    """Tests for trend analysis methods."""

    def test_hp_trending_down(self, run_context: RunContext) -> None:
        """Detects when HP is trending downward."""
        run_context.hp_history = [
            (80, 80),  # Full HP
            (70, 80),  # Lost 10
            (55, 80),  # Lost 15 more
            (40, 80),  # Lost 15 more
        ]
        assert run_context.is_hp_trending_down() is True

    def test_hp_stable(self, run_context: RunContext) -> None:
        """Detects stable HP."""
        run_context.hp_history = [
            (80, 80),
            (75, 80),
            (78, 80),
            (76, 80),
        ]
        assert run_context.is_hp_trending_down() is False

    def test_hp_trend_with_insufficient_data(self, run_context: RunContext) -> None:
        """Returns False with insufficient data."""
        run_context.hp_history = [(80, 80)]
        assert run_context.is_hp_trending_down() is False

    def test_gold_peak(self, run_context: RunContext) -> None:
        """Tracks gold peak."""
        run_context.gold_history = [50, 100, 200, 150, 75]
        assert run_context.get_gold_peak() == 200

    def test_gold_peak_empty(self, run_context: RunContext) -> None:
        """Returns 0 for empty gold history."""
        assert run_context.get_gold_peak() == 0

    def test_average_damage_per_combat(self, run_context: RunContext) -> None:
        """Calculates average damage taken per combat."""
        run_context.combats = [
            CombatRecord(floor=1, enemies=["Louse"], damage_taken=5),
            CombatRecord(floor=2, enemies=["Cultist"], damage_taken=10),
            CombatRecord(floor=3, enemies=["Jaw Worm"], damage_taken=15),
        ]
        assert run_context.get_average_damage_per_combat() == 10.0

    def test_average_damage_no_combats(self, run_context: RunContext) -> None:
        """Returns 0 for no combats."""
        assert run_context.get_average_damage_per_combat() == 0.0

    def test_spending_too_fast(self, run_context: RunContext) -> None:
        """Detects overspending patterns."""
        run_context.gold_history = [200, 50, 60, 10]
        assert run_context.is_spending_too_fast() is True

    def test_spending_normal(self, run_context: RunContext) -> None:
        """Normal spending is not flagged."""
        run_context.gold_history = [50, 75, 100, 80]
        assert run_context.is_spending_too_fast() is False


# ==============================================================================
# Summary Method Tests
# ==============================================================================


class TestSummaryMethods:
    """Tests for summary methods used by prompts."""

    def test_get_recent_combats_summary(self, run_context: RunContext) -> None:
        """Provides summary of recent combats."""
        run_context.combats = [
            CombatRecord(floor=1, enemies=["Louse", "Louse"], damage_taken=8),
            CombatRecord(floor=3, enemies=["Jaw Worm"], damage_taken=12),
            CombatRecord(
                floor=6, enemies=["Gremlin Nob"], damage_taken=25, was_elite=True
            ),
        ]

        summary = run_context.get_recent_combats_summary(limit=2)

        assert isinstance(summary, str)
        assert "Jaw Worm" in summary or "Gremlin Nob" in summary
        assert len(summary) > 0

    def test_get_deck_evolution_summary(self, run_context: RunContext) -> None:
        """Provides summary of deck changes."""
        run_context.cards_added = [
            Card(name="Pommel Strike", cost=1, type="ATTACK"),
            Card(name="Shrug It Off", cost=1, type="SKILL"),
        ]
        run_context.cards_removed = [
            Card(name="Strike", cost=1, type="ATTACK"),
        ]

        summary = run_context.get_deck_evolution_summary()

        assert isinstance(summary, str)
        assert "Pommel Strike" in summary or "added" in summary.lower()
        assert "Strike" in summary or "removed" in summary.lower()

    def test_get_run_health_summary(self, run_context: RunContext) -> None:
        """Provides health summary for the run."""
        run_context.hp_history = [(80, 80), (65, 80), (50, 80)]
        run_context.combats = [
            CombatRecord(floor=1, enemies=["Louse"], damage_taken=15),
            CombatRecord(floor=3, enemies=["Cultist"], damage_taken=15),
        ]

        summary = run_context.get_run_health_summary()

        assert isinstance(summary, str)
        # Should mention HP trend or damage
        assert any(
            term in summary.lower() for term in ["hp", "health", "damage", "trend"]
        )

    def test_get_full_context_summary(
        self, run_context: RunContext, basic_game_state: GameState
    ) -> None:
        """Provides comprehensive run summary."""
        run_context.update(basic_game_state)
        run_context.combats = [
            CombatRecord(floor=1, enemies=["Louse"], damage_taken=10),
        ]
        run_context.events = [
            EventRecord(floor=4, event_name="Neow", choice_made="[Gold]"),
        ]

        summary = run_context.get_full_context_summary()

        assert isinstance(summary, str)
        assert len(summary) > 50  # Should have meaningful content

    def test_summary_handles_empty_context(self, run_context: RunContext) -> None:
        """Summaries handle empty context gracefully."""
        assert isinstance(run_context.get_recent_combats_summary(), str)
        assert isinstance(run_context.get_deck_evolution_summary(), str)
        assert isinstance(run_context.get_run_health_summary(), str)
        assert isinstance(run_context.get_full_context_summary(), str)


# ==============================================================================
# Edge Cases
# ==============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_not_in_game(self, run_context: RunContext) -> None:
        """Handles state when not in game."""
        state = GameState(in_game=False)
        run_context.update(state)
        # Should not crash, may reset or ignore
        assert True

    def test_handles_act_change(self, run_context: RunContext) -> None:
        """Handles act transitions."""
        state = GameState(
            in_game=True,
            floor=17,
            act=1,
            hp=60,
            max_hp=80,
            gold=100,
        )
        run_context.update(state)

        # Move to act 2
        state.floor = 18
        state.act = 2
        run_context.update(state)

        assert run_context.current_act == 2

    def test_handles_run_reset(self, run_context: RunContext) -> None:
        """Detects new run and resets context."""
        state = GameState(
            in_game=True,
            floor=10,
            act=1,
            hp=50,
            max_hp=80,
            gold=200,
        )
        run_context.update(state)

        # New run starts (floor drops to 0)
        state.floor = 0
        state.hp = 80
        state.gold = 99
        run_context.update(state)

        # Should reset (floor going backwards significantly = new run)
        assert run_context.current_floor == 0
        # Context should be fresh
        assert len(run_context.gold_history) <= 1

    def test_combat_record_with_multiple_enemies(self, run_context: RunContext) -> None:
        """Handles multi-enemy combats."""
        state = GameState(
            in_game=True,
            screen_type="NONE",
            floor=5,
            act=1,
            hp=70,
            max_hp=80,
            gold=100,
            combat_state=CombatState(
                turn=1,
                monsters=[
                    Monster(name="Cultist", current_hp=50, max_hp=50, intent="ATTACK"),
                    Monster(name="Cultist", current_hp=48, max_hp=50, intent="BUFF"),
                ],
                hand=[],
                energy=3,
                max_energy=3,
            ),
        )
        run_context.update(state)

        assert len(run_context.combats) >= 1
        latest = run_context.combats[-1]
        assert len(latest.enemies) >= 2
        assert "Cultist" in latest.enemies
