"""Run context tracking.

Maintains history of the current run for analysis context.
Tracks combats, events, deck evolution, gold/HP trends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slay_the_spire_mcp.models import Card, GameState


@dataclass
class CombatRecord:
    """Record of a combat encounter."""

    floor: int
    enemies: list[str]
    damage_taken: int = 0
    was_elite: bool = False
    was_boss: bool = False


@dataclass
class EventRecord:
    """Record of an event encounter."""

    floor: int
    event_name: str
    choice_made: str = ""


@dataclass
class RunContext:
    """Tracks context across a run for better advice.

    Maintains history of:
    - Recent combats (enemies faced, damage taken)
    - Recent events (choices made)
    - Cards added/removed this run
    - Relics acquired
    - Gold history (peaks, spending)
    - HP history (damage patterns)
    """

    # Current position
    current_floor: int = 0
    current_act: int = 1

    # Combat history
    combats: list[CombatRecord] = field(default_factory=list)

    # Event history
    events: list[EventRecord] = field(default_factory=list)

    # Deck evolution
    cards_added: list[Card] = field(default_factory=list)
    cards_removed: list[Card] = field(default_factory=list)

    # Relics acquired during this run
    relics_acquired: list[str] = field(default_factory=list)

    # Value history (recorded per floor)
    gold_history: list[int] = field(default_factory=list)
    hp_history: list[tuple[int, int]] = field(default_factory=list)  # (current, max)

    # Internal state tracking
    _last_floor: int = field(default=-1, repr=False)
    _last_deck_names: set[str] = field(default_factory=set, repr=False)
    _last_relic_names: set[str] = field(default_factory=set, repr=False)
    _in_combat: bool = field(default=False, repr=False)
    _combat_start_hp: int = field(default=0, repr=False)
    _current_combat_enemies: list[str] = field(default_factory=list, repr=False)

    def reset(self) -> None:
        """Reset all context for a new run."""
        self.current_floor = 0
        self.current_act = 1
        self.combats = []
        self.events = []
        self.cards_added = []
        self.cards_removed = []
        self.relics_acquired = []
        self.gold_history = []
        self.hp_history = []
        self._last_floor = -1
        self._last_deck_names = set()
        self._last_relic_names = set()
        self._in_combat = False
        self._combat_start_hp = 0
        self._current_combat_enemies = []

    def update(self, state: GameState) -> None:
        """Update context from a new game state.

        Args:
            state: The current game state
        """
        if not state.in_game:
            return

        # Detect new run (floor dropped significantly)
        if state.floor < self.current_floor - 5:
            self.reset()

        # Update position
        self.current_floor = state.floor
        self.current_act = state.act

        # Track floor-based history (only on floor change)
        if state.floor != self._last_floor:
            self.gold_history.append(state.gold)
            self.hp_history.append((state.hp, state.max_hp))
            self._last_floor = state.floor

        # Track combat
        self._update_combat_tracking(state)

        # Track deck changes
        self._update_deck_tracking(state)

        # Track relic changes
        self._update_relic_tracking(state)

    def _update_combat_tracking(self, state: GameState) -> None:
        """Track combat start/end and damage."""
        is_in_combat = state.combat_state is not None

        if is_in_combat and not self._in_combat:
            # Combat just started
            self._in_combat = True
            self._combat_start_hp = state.hp
            self._current_combat_enemies = []

            if state.combat_state:
                for monster in state.combat_state.monsters:
                    self._current_combat_enemies.append(monster.name)

                # Create initial combat record
                # Detect elite/boss from screen type or enemy names
                enemy_names = [m.name for m in state.combat_state.monsters]
                is_elite = self._is_elite_fight(enemy_names)
                is_boss = self._is_boss_fight(enemy_names)

                self.combats.append(
                    CombatRecord(
                        floor=state.floor,
                        enemies=enemy_names,
                        damage_taken=0,
                        was_elite=is_elite,
                        was_boss=is_boss,
                    )
                )

        elif not is_in_combat and self._in_combat:
            # Combat just ended
            self._in_combat = False
            damage_taken = self._combat_start_hp - state.hp

            # Update the last combat record with damage taken
            if self.combats:
                self.combats[-1].damage_taken = max(0, damage_taken)

    def _is_elite_fight(self, enemies: list[str]) -> bool:
        """Detect if this is an elite fight."""
        elite_names = {
            "Gremlin Nob",
            "Lagavulin",
            "Sentry",
            "Book of Stabbing",
            "Gremlin Leader",
            "Taskmaster",
            "Nemesis",
            "Reptomancer",
            "Giant Head",
            "Spire Growth",
            "Maw",
        }
        return any(e in elite_names for e in enemies)

    def _is_boss_fight(self, enemies: list[str]) -> bool:
        """Detect if this is a boss fight."""
        boss_names = {
            "Slime Boss",
            "The Guardian",
            "Hexaghost",
            "Automaton",
            "Collector",
            "Champ",
            "Awakened One",
            "Donu",
            "Deca",
            "Time Eater",
            "The Heart",
            "Corrupt Heart",
        }
        return any(e in boss_names for e in enemies)

    def _update_deck_tracking(self, state: GameState) -> None:
        """Track cards added and removed from deck."""
        # Import here to avoid circular import issues at module level
        from slay_the_spire_mcp.models import Card

        current_deck_names: dict[str, int] = {}
        for card in state.deck:
            current_deck_names[card.name] = current_deck_names.get(card.name, 0) + 1

        if self._last_deck_names:
            # Simplified: just track new unique cards (by name)
            current_names = set(current_deck_names.keys())
            last_names = self._last_deck_names

            # Cards added (in current but not in last)
            for name in current_names - last_names:
                self.cards_added.append(Card(name=name, cost=0, type="UNKNOWN"))

            # Cards removed (in last but not in current)
            for name in last_names - current_names:
                self.cards_removed.append(Card(name=name, cost=0, type="UNKNOWN"))

        self._last_deck_names = set(current_deck_names.keys())

    def _update_relic_tracking(self, state: GameState) -> None:
        """Track relics acquired."""
        current_relic_names = {r.name for r in state.relics}

        # New relics
        for name in current_relic_names - self._last_relic_names:
            self.relics_acquired.append(name)

        self._last_relic_names = current_relic_names

    def record_event_choice(self, event_name: str, choice: str) -> None:
        """Record an event choice made by the player.

        Args:
            event_name: Name of the event
            choice: The choice that was made
        """
        self.events.append(
            EventRecord(
                floor=self.current_floor,
                event_name=event_name,
                choice_made=choice,
            )
        )

    # =========================================================================
    # Trend Analysis Methods
    # =========================================================================

    def is_hp_trending_down(self) -> bool:
        """Check if HP is trending downward over recent floors.

        Returns:
            True if HP has been consistently decreasing
        """
        if len(self.hp_history) < 3:
            return False

        # Look at last 4 data points
        recent = self.hp_history[-4:]
        if len(recent) < 3:
            recent = self.hp_history

        # Calculate HP as percentage of max for fair comparison
        percentages = [current / max_hp for current, max_hp in recent if max_hp > 0]

        if len(percentages) < 3:
            return False

        # Check if each entry is lower than the previous
        decreasing_count = sum(
            1 for i in range(1, len(percentages)) if percentages[i] < percentages[i - 1]
        )

        # If more than half are decreasing, HP is trending down
        return decreasing_count >= len(percentages) - 1

    def get_gold_peak(self) -> int:
        """Get the peak gold value this run.

        Returns:
            Maximum gold value recorded, or 0 if no history
        """
        if not self.gold_history:
            return 0
        return max(self.gold_history)

    def get_average_damage_per_combat(self) -> float:
        """Calculate average damage taken per combat.

        Returns:
            Average damage, or 0.0 if no combats
        """
        if not self.combats:
            return 0.0

        total_damage = sum(c.damage_taken for c in self.combats)
        return total_damage / len(self.combats)

    def is_spending_too_fast(self) -> bool:
        """Check if gold is being spent too quickly.

        Returns:
            True if gold dropped significantly without recovery
        """
        if len(self.gold_history) < 3:
            return False

        peak = self.get_gold_peak()
        if peak < 100:
            return False  # Not enough gold to worry about

        recent = self.gold_history[-3:]
        # If we're at less than 25% of peak and dropped more than 75%
        current = recent[-1] if recent else 0
        return current < peak * 0.25 and peak - current > 100

    # =========================================================================
    # Summary Methods for Prompts
    # =========================================================================

    def get_recent_combats_summary(self, limit: int = 3) -> str:
        """Get a summary of recent combats.

        Args:
            limit: Maximum number of combats to include

        Returns:
            Human-readable summary string
        """
        if not self.combats:
            return "No combats recorded yet this run."

        recent = self.combats[-limit:]
        lines = ["Recent combats:"]

        for combat in recent:
            enemy_str = ", ".join(combat.enemies)
            elite_tag = " (ELITE)" if combat.was_elite else ""
            boss_tag = " (BOSS)" if combat.was_boss else ""
            lines.append(
                f"  Floor {combat.floor}: {enemy_str}{elite_tag}{boss_tag} "
                f"- took {combat.damage_taken} damage"
            )

        return "\n".join(lines)

    def get_deck_evolution_summary(self) -> str:
        """Get a summary of deck changes this run.

        Returns:
            Human-readable summary string
        """
        if not self.cards_added and not self.cards_removed:
            return "No deck changes recorded yet this run."

        lines = ["Deck evolution:"]

        if self.cards_added:
            added_names = [c.name for c in self.cards_added]
            lines.append(f"  Added: {', '.join(added_names)}")

        if self.cards_removed:
            removed_names = [c.name for c in self.cards_removed]
            lines.append(f"  Removed: {', '.join(removed_names)}")

        return "\n".join(lines)

    def get_run_health_summary(self) -> str:
        """Get a health/damage summary for the run.

        Returns:
            Human-readable summary string
        """
        lines = ["Run health summary:"]

        if self.hp_history:
            current_hp, max_hp = self.hp_history[-1]
            lines.append(f"  Current HP: {current_hp}/{max_hp}")

            if self.is_hp_trending_down():
                lines.append("  WARNING: HP is trending downward!")

        if self.combats:
            avg_damage = self.get_average_damage_per_combat()
            lines.append(f"  Average damage per combat: {avg_damage:.1f}")

            total_damage = sum(c.damage_taken for c in self.combats)
            lines.append(f"  Total damage taken: {total_damage}")

        if len(lines) == 1:
            return "No health data recorded yet this run."

        return "\n".join(lines)

    def get_full_context_summary(self) -> str:
        """Get a comprehensive run context summary.

        Returns:
            Full context summary for use in prompts
        """
        lines = [
            f"=== Run Context (Act {self.current_act}, Floor {self.current_floor}) ===",
            "",
        ]

        # Health summary
        lines.append(self.get_run_health_summary())
        lines.append("")

        # Combat summary
        lines.append(self.get_recent_combats_summary())
        lines.append("")

        # Deck evolution
        lines.append(self.get_deck_evolution_summary())
        lines.append("")

        # Relics
        if self.relics_acquired:
            lines.append(f"Relics acquired: {', '.join(self.relics_acquired)}")
        else:
            lines.append("No relics acquired yet.")
        lines.append("")

        # Gold
        if self.gold_history:
            current_gold = self.gold_history[-1]
            peak_gold = self.get_gold_peak()
            lines.append(f"Gold: {current_gold} (peak: {peak_gold})")
            if self.is_spending_too_fast():
                lines.append("  WARNING: Spending gold quickly!")

        # Events
        if self.events:
            lines.append("")
            lines.append("Recent events:")
            for event in self.events[-3:]:
                lines.append(
                    f"  Floor {event.floor}: {event.event_name} - {event.choice_made}"
                )

        return "\n".join(lines)
