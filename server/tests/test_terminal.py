"""Tests for terminal output renderer.

Tests TDD-style for the terminal renderer that displays game state
in a human-readable format for debugging and visibility.
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
from slay_the_spire_mcp.terminal import (
    render_card,
    render_combat_view,
    render_energy,
    render_event_view,
    render_game_state,
    render_hp_bar,
    render_map_view,
    render_monster,
    render_reward_view,
    strip_ansi,
)


class TestHPBar:
    """Tests for HP bar rendering."""

    def test_full_hp(self) -> None:
        """Full HP shows a full bar."""
        result = render_hp_bar(100, 100)
        # Should contain filled characters
        assert "100/100" in result
        # Bar should be mostly filled
        stripped = strip_ansi(result)
        assert stripped.count("\u2588") == 10  # All 10 blocks filled

    def test_partial_hp(self) -> None:
        """Partial HP shows partial bar."""
        result = render_hp_bar(80, 100)
        assert "80/100" in result
        stripped = strip_ansi(result)
        # 80% = 8 filled blocks
        assert stripped.count("\u2588") == 8
        assert stripped.count("\u2591") == 2  # 2 empty blocks

    def test_low_hp(self) -> None:
        """Low HP shows mostly empty bar."""
        result = render_hp_bar(10, 100)
        assert "10/100" in result
        stripped = strip_ansi(result)
        assert stripped.count("\u2588") == 1  # 1 filled block
        assert stripped.count("\u2591") == 9  # 9 empty blocks

    def test_zero_hp(self) -> None:
        """Zero HP shows empty bar."""
        result = render_hp_bar(0, 100)
        assert "0/100" in result
        stripped = strip_ansi(result)
        assert stripped.count("\u2588") == 0  # No filled blocks

    def test_custom_width(self) -> None:
        """Bar can have custom width."""
        result = render_hp_bar(50, 100, width=20)
        stripped = strip_ansi(result)
        # 50% of 20 = 10 filled
        assert stripped.count("\u2588") == 10
        assert stripped.count("\u2591") == 10


class TestEnergy:
    """Tests for energy rendering."""

    def test_full_energy(self) -> None:
        """Full energy shows all filled."""
        result = render_energy(3, 3)
        stripped = strip_ansi(result)
        assert stripped.count("\u26a1") == 3  # 3 lightning bolts
        assert stripped.count("\u25cb") == 0  # No empty circles

    def test_partial_energy(self) -> None:
        """Partial energy shows some empty."""
        result = render_energy(2, 5)
        stripped = strip_ansi(result)
        assert stripped.count("\u26a1") == 2  # 2 lightning bolts
        assert stripped.count("\u25cb") == 3  # 3 empty circles

    def test_no_energy(self) -> None:
        """No energy shows all empty."""
        result = render_energy(0, 3)
        stripped = strip_ansi(result)
        assert stripped.count("\u26a1") == 0
        assert stripped.count("\u25cb") == 3

    def test_energy_text(self) -> None:
        """Energy includes numeric text."""
        result = render_energy(2, 4)
        assert "(2/4)" in result


class TestCardRendering:
    """Tests for card formatting."""

    def test_simple_card(self) -> None:
        """Basic card shows name and cost."""
        card = Card(name="Strike", cost=1, type="ATTACK")
        result = render_card(card)
        assert "Strike" in result
        assert "(1)" in result

    def test_zero_cost_card(self) -> None:
        """Zero cost card shows 0."""
        card = Card(name="Anger", cost=0, type="ATTACK")
        result = render_card(card)
        assert "Anger" in result
        assert "(0)" in result

    def test_upgraded_card(self) -> None:
        """Upgraded card shows + indicator."""
        card = Card(name="Strike", cost=1, type="ATTACK", upgrades=1)
        result = render_card(card)
        assert "Strike+" in result

    def test_x_cost_card(self) -> None:
        """X-cost card (cost=-1) shows X."""
        card = Card(name="Whirlwind", cost=-1, type="ATTACK")
        result = render_card(card)
        assert "Whirlwind" in result
        assert "(X)" in result

    def test_card_with_index(self) -> None:
        """Card can show index for selection."""
        card = Card(name="Defend", cost=1, type="SKILL")
        result = render_card(card, index=2)
        assert "2:" in result or "[2]" in result
        assert "Defend" in result


class TestMonsterRendering:
    """Tests for monster display."""

    def test_basic_monster(self) -> None:
        """Monster shows name, HP bar, and intent."""
        monster = Monster(
            name="Jaw Worm",
            current_hp=44,
            max_hp=44,
            intent="ATTACK",
        )
        result = render_monster(monster)
        assert "Jaw Worm" in result
        assert "44/44" in result
        assert "ATTACK" in result or "\u2694" in result  # Sword symbol or text

    def test_monster_with_block(self) -> None:
        """Monster with block shows shield."""
        monster = Monster(
            name="Gremlin Nob",
            current_hp=82,
            max_hp=82,
            block=5,
            intent="ATTACK",
        )
        result = render_monster(monster)
        assert "5" in result  # Block value
        assert "\U0001f6e1" in result or "block" in result.lower()  # Shield or text

    def test_dead_monster(self) -> None:
        """Dead monster shows as gone."""
        monster = Monster(
            name="Acid Slime (M)",
            current_hp=0,
            max_hp=28,
            is_gone=True,
            intent="NONE",
        )
        result = render_monster(monster)
        # Should indicate dead/gone
        assert "DEAD" in result or "\u2620" in result or "0/28" in result

    def test_monster_with_index(self) -> None:
        """Monster shows target index."""
        monster = Monster(
            name="Cultist",
            current_hp=50,
            max_hp=50,
            intent="BUFF",
        )
        result = render_monster(monster, index=0)
        assert "[0]" in result or "0:" in result


class TestCombatView:
    """Tests for full combat view rendering."""

    def test_combat_view_structure(self) -> None:
        """Combat view shows all components."""
        combat = CombatState(
            turn=1,
            monsters=[
                Monster(name="Jaw Worm", current_hp=44, max_hp=44, intent="ATTACK"),
            ],
            hand=[
                Card(name="Strike", cost=1, type="ATTACK"),
                Card(name="Defend", cost=1, type="SKILL"),
            ],
            energy=3,
            max_energy=3,
            player_block=0,
        )
        game_state = GameState(
            in_game=True,
            screen_type="COMBAT",
            hp=80,
            max_hp=80,
            combat_state=combat,
        )

        result = render_combat_view(game_state)

        # Should have all sections
        assert "Jaw Worm" in result  # Monster
        assert "Strike" in result  # Card
        assert "Defend" in result  # Card
        assert "80/80" in result or "80" in result  # Player HP

    def test_combat_view_multiple_monsters(self) -> None:
        """Combat view handles multiple monsters."""
        combat = CombatState(
            turn=1,
            monsters=[
                Monster(name="Cultist", current_hp=48, max_hp=48, intent="ATTACK"),
                Monster(name="Cultist", current_hp=48, max_hp=48, intent="BUFF"),
            ],
            hand=[Card(name="Strike", cost=1)],
            energy=3,
            max_energy=3,
        )
        game_state = GameState(
            in_game=True,
            screen_type="COMBAT",
            hp=70,
            max_hp=80,
            combat_state=combat,
        )

        result = render_combat_view(game_state)
        # Should show both with indices
        assert "[0]" in result or "0:" in result
        assert "[1]" in result or "1:" in result


class TestMapView:
    """Tests for map rendering."""

    def test_simple_map(self) -> None:
        """Map shows nodes with symbols."""
        map_data: list[list[MapNode]] = [
            [MapNode(x=0, y=0, symbol="M")],
            [MapNode(x=0, y=1, symbol="?"), MapNode(x=1, y=1, symbol="$")],
            [MapNode(x=0, y=2, symbol="R")],
        ]
        game_state = GameState(
            in_game=True,
            screen_type="MAP",
            map=map_data,
            current_node=(0, 0),
        )

        result = render_map_view(game_state)
        # Should contain node symbols
        assert "M" in result  # Monster
        assert "?" in result  # Unknown/event
        assert "$" in result  # Shop
        assert "R" in result  # Rest

    def test_current_position_highlighted(self) -> None:
        """Current position is highlighted."""
        map_data: list[list[MapNode]] = [
            [MapNode(x=0, y=0, symbol="M")],
            [MapNode(x=0, y=1, symbol="?")],
        ]
        game_state = GameState(
            in_game=True,
            screen_type="MAP",
            map=map_data,
            current_node=(0, 0),
        )

        result = render_map_view(game_state)
        # Current position should be marked somehow (ANSI colors or marker)
        # Check that ANSI codes are present near M or there's a marker
        assert "[M]" in result or "\x1b[" in result

    def test_map_symbols_legend(self) -> None:
        """Map includes a legend for symbols."""
        map_data: list[list[MapNode]] = [
            [MapNode(x=0, y=0, symbol="M")],
        ]
        game_state = GameState(
            in_game=True,
            screen_type="MAP",
            map=map_data,
        )

        result = render_map_view(game_state)
        # Should have some legend
        assert "M" in result.lower() or "monster" in result.lower() or "M=" in result


class TestEventView:
    """Tests for event rendering."""

    def test_event_with_choices(self) -> None:
        """Event shows name and numbered choices."""
        game_state = GameState(
            in_game=True,
            screen_type="EVENT",
            screen_state={
                "event_name": "Big Fish",
                "body_text": "You see a fish that is big.",
            },
            choice_list=["Eat (Heal 5 HP)", "Feed (Lose 5 HP)", "Leave"],
        )

        result = render_event_view(game_state)
        assert "Big Fish" in result
        assert "Eat" in result or "0" in result
        assert "Feed" in result or "1" in result
        assert "Leave" in result or "2" in result

    def test_event_choices_numbered(self) -> None:
        """Event choices have selection numbers."""
        game_state = GameState(
            in_game=True,
            screen_type="EVENT",
            screen_state={"event_name": "Test Event"},
            choice_list=["Option A", "Option B"],
        )

        result = render_event_view(game_state)
        # Choices should be numbered for selection
        assert "[0]" in result or "0:" in result or "1." in result


class TestRewardView:
    """Tests for reward screen rendering."""

    def test_card_rewards(self) -> None:
        """Card rewards show card options."""
        game_state = GameState(
            in_game=True,
            screen_type="CARD_REWARD",
            choice_list=["Strike", "Defend", "Bash"],
            screen_state={
                "cards": [
                    {"name": "Strike", "cost": 1, "type": "ATTACK"},
                    {"name": "Defend", "cost": 1, "type": "SKILL"},
                    {"name": "Bash", "cost": 2, "type": "ATTACK"},
                ]
            },
        )

        result = render_reward_view(game_state)
        assert "Strike" in result
        assert "Defend" in result
        assert "Bash" in result

    def test_gold_reward(self) -> None:
        """Gold rewards show amount."""
        game_state = GameState(
            in_game=True,
            screen_type="COMBAT_REWARD",
            screen_state={
                "rewards": [
                    {"type": "GOLD", "gold": 25},
                    {"type": "POTION", "potion": {"name": "Block Potion"}},
                ]
            },
            choice_list=["Gold", "Block Potion"],
        )

        result = render_reward_view(game_state)
        assert "25" in result or "gold" in result.lower()

    def test_relic_reward(self) -> None:
        """Relic rewards show relic name."""
        game_state = GameState(
            in_game=True,
            screen_type="BOSS_REWARD",
            screen_state={
                "rewards": [
                    {"type": "RELIC", "relic": {"name": "Black Star"}},
                ]
            },
            choice_list=["Black Star", "Skip"],
        )

        result = render_reward_view(game_state)
        assert "Black Star" in result


class TestGameStateRendering:
    """Tests for the main render_game_state dispatcher."""

    def test_combat_dispatches_to_combat_view(self) -> None:
        """Combat screen type uses combat renderer."""
        combat = CombatState(
            turn=1,
            monsters=[Monster(name="Test", current_hp=10, max_hp=10)],
            hand=[Card(name="Strike", cost=1)],
            energy=3,
            max_energy=3,
        )
        game_state = GameState(
            in_game=True,
            screen_type="COMBAT",
            hp=50,
            max_hp=50,
            combat_state=combat,
        )

        result = render_game_state(game_state)
        assert "Test" in result  # Monster name
        assert "Strike" in result  # Card name

    def test_map_dispatches_to_map_view(self) -> None:
        """Map screen type uses map renderer."""
        map_data: list[list[MapNode]] = [
            [MapNode(x=0, y=0, symbol="M")],
        ]
        game_state = GameState(
            in_game=True,
            screen_type="MAP",
            map=map_data,
        )

        result = render_game_state(game_state)
        assert "M" in result

    def test_event_dispatches_to_event_view(self) -> None:
        """Event screen type uses event renderer."""
        game_state = GameState(
            in_game=True,
            screen_type="EVENT",
            screen_state={"event_name": "Test Event"},
            choice_list=["Choice 1"],
        )

        result = render_game_state(game_state)
        assert "Test Event" in result

    def test_not_in_game(self) -> None:
        """Not in game shows appropriate message."""
        game_state = GameState(in_game=False)

        result = render_game_state(game_state)
        assert "not in game" in result.lower() or "menu" in result.lower()


class TestStripAnsi:
    """Tests for ANSI code stripping utility."""

    def test_strips_color_codes(self) -> None:
        """Removes ANSI color codes."""
        text = "\x1b[31mRed Text\x1b[0m"
        assert strip_ansi(text) == "Red Text"

    def test_strips_multiple_codes(self) -> None:
        """Removes multiple ANSI codes."""
        text = "\x1b[1m\x1b[32mBold Green\x1b[0m Normal"
        assert strip_ansi(text) == "Bold Green Normal"

    def test_preserves_plain_text(self) -> None:
        """Plain text unchanged."""
        text = "Hello World"
        assert strip_ansi(text) == "Hello World"
