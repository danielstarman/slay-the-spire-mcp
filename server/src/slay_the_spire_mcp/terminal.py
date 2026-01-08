"""Terminal output renderer for game state visualization.

Renders game state in a human-readable format for terminal display.
Uses ASCII art and ANSI colors for readability.

This is for debugging and visibility - helps users see what Claude sees.
"""

from __future__ import annotations

import re
from typing import Any

from slay_the_spire_mcp.models import Card, GameState, Monster


# ANSI Color codes
class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"

    # Foreground colors
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"

    # Bright foreground
    BRIGHT_RED = "\x1b[91m"
    BRIGHT_GREEN = "\x1b[92m"
    BRIGHT_YELLOW = "\x1b[93m"
    BRIGHT_CYAN = "\x1b[96m"

    # Background colors
    BG_RED = "\x1b[41m"
    BG_GREEN = "\x1b[42m"
    BG_YELLOW = "\x1b[43m"
    BG_BLUE = "\x1b[44m"


# Unicode characters for visual display
BLOCK_FULL = "\u2588"  # Full block for HP
BLOCK_EMPTY = "\u2591"  # Light shade for missing HP
ENERGY_FULL = "\u26a1"  # Lightning bolt for energy
ENERGY_EMPTY = "\u25cb"  # Circle for missing energy
SHIELD = "\U0001f6e1"  # Shield emoji for block
SKULL = "\u2620"  # Skull for dead
SWORD = "\u2694"  # Swords for attack intent
HEART = "\u2764"  # Heart for HP


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI codes

    Returns:
        Text with all ANSI escape sequences removed
    """
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_pattern.sub("", text)


def render_hp_bar(current: int, maximum: int, width: int = 10) -> str:
    """Render an HP bar with filled and empty blocks.

    Args:
        current: Current HP value
        maximum: Maximum HP value
        width: Width of the bar in characters

    Returns:
        Formatted HP bar string like "[████████░░] 80/100"
    """
    if maximum <= 0:
        maximum = 1  # Avoid division by zero

    ratio = max(0, min(1, current / maximum))
    filled = int(ratio * width)
    empty = width - filled

    # Color based on HP percentage
    if ratio > 0.6:
        color = Colors.GREEN
    elif ratio > 0.3:
        color = Colors.YELLOW
    else:
        color = Colors.RED

    bar = f"{color}[{BLOCK_FULL * filled}{BLOCK_EMPTY * empty}]{Colors.RESET}"
    return f"{bar} {current}/{maximum}"


def render_energy(current: int, maximum: int) -> str:
    """Render energy as lightning bolts and empty circles.

    Args:
        current: Current energy
        maximum: Maximum energy

    Returns:
        Formatted energy string like "⚡⚡⚡○○ (3/5)"
    """
    full = ENERGY_FULL * current
    empty = ENERGY_EMPTY * max(0, maximum - current)
    return (
        f"{Colors.YELLOW}{full}{Colors.DIM}{empty}{Colors.RESET} ({current}/{maximum})"
    )


def render_card(card: Card, index: int | None = None) -> str:
    """Render a single card with name, cost, and optional index.

    Args:
        card: Card to render
        index: Optional index for selection display

    Returns:
        Formatted card string like "[1: Strike+ (1)]"
    """
    name = card.name
    if card.upgrades > 0:
        name = f"{name}+"

    # Handle X-cost cards (cost = -1)
    cost_str = "X" if card.cost < 0 else str(card.cost)

    # Color based on card type
    if card.type == "ATTACK":
        color = Colors.RED
    elif card.type == "SKILL":
        color = Colors.BLUE
    elif card.type == "POWER":
        color = Colors.MAGENTA
    else:
        color = Colors.WHITE

    if index is not None:
        return f"{color}[{index}: {name} ({cost_str})]{Colors.RESET}"
    return f"{color}[{name} ({cost_str})]{Colors.RESET}"


def render_monster(monster: Monster, index: int | None = None) -> str:
    """Render a monster with HP bar, intent, and optional target index.

    Args:
        monster: Monster to render
        index: Optional target index for selection

    Returns:
        Formatted monster display
    """
    lines: list[str] = []

    # Name with optional index
    header = f"{Colors.BOLD}"
    if index is not None:
        header += f"[{index}] "
    header += f"{monster.name}{Colors.RESET}"

    if monster.is_gone:
        header += f" {Colors.DIM}{SKULL} DEAD{Colors.RESET}"
        lines.append(header)
        lines.append(f"  {render_hp_bar(monster.current_hp, monster.max_hp)}")
        return "\n".join(lines)

    lines.append(header)

    # HP bar
    hp_line = f"  {render_hp_bar(monster.current_hp, monster.max_hp)}"
    if monster.block > 0:
        hp_line += f" {Colors.CYAN}{SHIELD} {monster.block}{Colors.RESET}"
    lines.append(hp_line)

    # Intent
    intent_display = _format_intent(monster.intent)
    lines.append(f"  Intent: {intent_display}")

    # Powers/status effects
    if monster.powers:
        power_strs = [_format_power(p) for p in monster.powers]
        lines.append(f"  Status: {', '.join(power_strs)}")

    return "\n".join(lines)


def _format_intent(intent: str) -> str:
    """Format monster intent with symbol and color."""
    intent_map = {
        "ATTACK": (SWORD, Colors.RED, "Attack"),
        "ATTACK_BUFF": (SWORD, Colors.RED, "Attack + Buff"),
        "ATTACK_DEBUFF": (SWORD, Colors.RED, "Attack + Debuff"),
        "ATTACK_DEFEND": (SWORD, Colors.RED, "Attack + Block"),
        "BUFF": ("\u2b06", Colors.MAGENTA, "Buff"),
        "DEBUFF": ("\u2b07", Colors.YELLOW, "Debuff"),
        "STRONG_DEBUFF": ("\u2b07\u2b07", Colors.YELLOW, "Strong Debuff"),
        "DEFEND": (SHIELD, Colors.CYAN, "Block"),
        "DEFEND_BUFF": (SHIELD, Colors.CYAN, "Block + Buff"),
        "DEFEND_DEBUFF": (SHIELD, Colors.CYAN, "Block + Debuff"),
        "ESCAPE": ("\u2192", Colors.WHITE, "Escape"),
        "MAGIC": ("\u2728", Colors.MAGENTA, "Magic"),
        "NONE": ("-", Colors.DIM, "None"),
        "SLEEP": ("z", Colors.DIM, "Sleep"),
        "STUN": ("\u2b50", Colors.YELLOW, "Stunned"),
        "UNKNOWN": ("?", Colors.WHITE, "Unknown"),
    }

    symbol, color, text = intent_map.get(intent, ("?", Colors.WHITE, intent))
    return f"{color}{symbol} {text}{Colors.RESET}"


def _format_power(power: dict[str, Any]) -> str:
    """Format a power/status effect."""
    name = str(power.get("name", power.get("id", "Unknown")))
    amount = power.get("amount", 0)
    if amount != 0:
        return f"{name}({amount})"
    return name


def render_combat_view(game_state: GameState) -> str:
    """Render the full combat view.

    Shows:
    - All monsters with HP, intent, and target indices
    - Player HP, block, and energy
    - Hand of cards with indices

    Args:
        game_state: Current game state (must have combat_state)

    Returns:
        Formatted combat view string
    """
    lines: list[str] = []
    combat = game_state.combat_state

    if combat is None:
        return "No combat state available"

    # Header
    lines.append(f"{Colors.BOLD}=== COMBAT (Turn {combat.turn}) ==={Colors.RESET}")
    lines.append("")

    # Monsters section
    lines.append(f"{Colors.BOLD}--- MONSTERS ---{Colors.RESET}")
    for i, monster in enumerate(combat.monsters):
        lines.append(render_monster(monster, index=i))
        lines.append("")

    # Player section
    lines.append(f"{Colors.BOLD}--- PLAYER ---{Colors.RESET}")
    hp_bar = render_hp_bar(game_state.hp, game_state.max_hp)
    lines.append(f"  {HEART} HP: {hp_bar}")

    if combat.player_block > 0 or game_state.current_block > 0:
        block = combat.player_block or game_state.current_block
        lines.append(f"  {SHIELD} Block: {Colors.CYAN}{block}{Colors.RESET}")

    lines.append(f"  Energy: {render_energy(combat.energy, combat.max_energy)}")

    # Player powers
    if combat.player_powers:
        power_strs = [_format_power(p) for p in combat.player_powers]
        lines.append(f"  Status: {', '.join(power_strs)}")

    lines.append("")

    # Hand section
    lines.append(f"{Colors.BOLD}--- HAND ({len(combat.hand)} cards) ---{Colors.RESET}")
    for i, card in enumerate(combat.hand):
        lines.append(f"  {render_card(card, index=i)}")

    # Pile counts
    lines.append("")
    lines.append(
        f"{Colors.DIM}Draw: {len(combat.draw_pile)} | "
        f"Discard: {len(combat.discard_pile)} | "
        f"Exhaust: {len(combat.exhaust_pile)}{Colors.RESET}"
    )

    return "\n".join(lines)


def render_map_view(game_state: GameState) -> str:
    """Render the map view with node symbols.

    Shows:
    - Map nodes arranged by floor
    - Current position highlighted
    - Legend for node symbols

    Args:
        game_state: Current game state (must have map data)

    Returns:
        Formatted map view string
    """
    lines: list[str] = []
    map_data = game_state.map

    if not map_data:
        return "No map data available"

    lines.append(f"{Colors.BOLD}=== MAP ==={Colors.RESET}")
    lines.append("")

    current = game_state.current_node

    # Render map from top (highest floor) to bottom
    for floor_idx in range(len(map_data) - 1, -1, -1):
        floor_nodes = map_data[floor_idx]
        floor_line = f"F{floor_idx:2d} "

        node_strs: list[str] = []
        for node in floor_nodes:
            symbol = node.symbol
            is_current = current == (node.x, node.y) if current else False

            # Format node with position info
            node_str = _format_map_node(symbol, is_current)
            node_strs.append(node_str)

        floor_line += "  ".join(node_strs) if node_strs else "  (empty)"
        lines.append(floor_line)

    lines.append("")

    # Legend
    lines.append(f"{Colors.DIM}--- Legend ---{Colors.RESET}")
    legend = [
        ("M", "Monster"),
        ("?", "Unknown/Event"),
        ("$", "Shop"),
        ("R", "Rest Site"),
        ("T", "Treasure"),
        ("E", "Elite"),
        ("B", "Boss"),
    ]
    for symbol, meaning in legend:
        color = _get_node_color(symbol)
        lines.append(f"  {color}{symbol}{Colors.RESET} = {meaning}")

    return "\n".join(lines)


def _format_map_node(symbol: str, is_current: bool) -> str:
    """Format a map node with appropriate color and highlighting."""
    color = _get_node_color(symbol)

    if is_current:
        return f"{Colors.BG_YELLOW}{Colors.BOLD}[{symbol}]{Colors.RESET}"
    return f"{color}{symbol}{Colors.RESET}"


def _get_node_color(symbol: str) -> str:
    """Get the color for a map node symbol."""
    color_map = {
        "M": Colors.RED,
        "E": Colors.BRIGHT_RED,
        "?": Colors.YELLOW,
        "$": Colors.GREEN,
        "R": Colors.CYAN,
        "T": Colors.BRIGHT_YELLOW,
        "B": Colors.MAGENTA,
    }
    return color_map.get(symbol, Colors.WHITE)


def render_event_view(game_state: GameState) -> str:
    """Render an event screen with choices.

    Shows:
    - Event name
    - Event description (if available)
    - Numbered choices for selection

    Args:
        game_state: Current game state

    Returns:
        Formatted event view string
    """
    lines: list[str] = []

    screen_state = game_state.screen_state
    event_name = screen_state.get("event_name", "Unknown Event")
    body_text = screen_state.get("body_text", "")

    lines.append(f"{Colors.BOLD}=== EVENT ==={Colors.RESET}")
    lines.append("")
    lines.append(f"{Colors.YELLOW}{event_name}{Colors.RESET}")

    if body_text:
        lines.append("")
        # Wrap body text
        lines.append(f"{Colors.DIM}{body_text}{Colors.RESET}")

    lines.append("")
    lines.append(f"{Colors.BOLD}--- CHOICES ---{Colors.RESET}")

    for i, choice in enumerate(game_state.choice_list):
        lines.append(f"  {Colors.CYAN}[{i}]{Colors.RESET} {choice}")

    return "\n".join(lines)


def render_reward_view(game_state: GameState) -> str:
    """Render a reward screen (cards, relics, gold, etc).

    Shows:
    - Available rewards with indices
    - Card details for card rewards

    Args:
        game_state: Current game state

    Returns:
        Formatted reward view string
    """
    lines: list[str] = []
    screen_state = game_state.screen_state
    screen_type = game_state.screen_type

    lines.append(f"{Colors.BOLD}=== REWARDS ==={Colors.RESET}")
    lines.append("")

    # Handle card rewards specially
    if screen_type == "CARD_REWARD":
        lines.append(f"{Colors.YELLOW}Choose a card:{Colors.RESET}")
        cards = screen_state.get("cards", [])

        for i, card_data in enumerate(cards):
            if isinstance(card_data, dict):
                card = Card(**card_data)
                lines.append(f"  {render_card(card, index=i)}")
            else:
                # Fallback to choice list if no card details
                choice = (
                    game_state.choice_list[i]
                    if i < len(game_state.choice_list)
                    else str(card_data)
                )
                lines.append(f"  [{i}] {choice}")

        lines.append("")
        lines.append(f"  {Colors.DIM}[Skip]{Colors.RESET} Skip reward")

    # Handle combat/boss rewards with multiple reward types
    elif "rewards" in screen_state:
        rewards = screen_state.get("rewards", [])
        for i, reward in enumerate(rewards):
            reward_type = reward.get("type", "UNKNOWN")

            if reward_type == "GOLD":
                gold = reward.get("gold", 0)
                lines.append(f"  [{i}] {Colors.YELLOW}Gold: {gold}{Colors.RESET}")

            elif reward_type == "POTION":
                potion = reward.get("potion", {})
                potion_name = (
                    potion.get("name", "Unknown Potion")
                    if isinstance(potion, dict)
                    else str(potion)
                )
                lines.append(
                    f"  [{i}] {Colors.MAGENTA}Potion: {potion_name}{Colors.RESET}"
                )

            elif reward_type == "RELIC":
                relic = reward.get("relic", {})
                relic_name = (
                    relic.get("name", "Unknown Relic")
                    if isinstance(relic, dict)
                    else str(relic)
                )
                lines.append(f"  [{i}] {Colors.CYAN}Relic: {relic_name}{Colors.RESET}")

            elif reward_type == "CARD":
                lines.append(f"  [{i}] {Colors.GREEN}Card Reward{Colors.RESET}")

            else:
                lines.append(f"  [{i}] {reward_type}")

    # Fallback to choice list
    else:
        for i, choice in enumerate(game_state.choice_list):
            lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)


def render_game_state(game_state: GameState) -> str:
    """Render the game state appropriate to the current screen.

    Dispatches to the appropriate renderer based on screen_type.

    Args:
        game_state: Current game state

    Returns:
        Formatted game state string
    """
    if not game_state.in_game:
        return f"{Colors.DIM}Not in game - at main menu{Colors.RESET}"

    screen_type = game_state.screen_type

    # Combat screens
    if screen_type == "COMBAT" or game_state.combat_state is not None:
        return render_combat_view(game_state)

    # Map screen
    if screen_type == "MAP":
        return render_map_view(game_state)

    # Event screens
    if screen_type == "EVENT":
        return render_event_view(game_state)

    # Reward screens
    if screen_type in ("CARD_REWARD", "COMBAT_REWARD", "BOSS_REWARD"):
        return render_reward_view(game_state)

    # Shop screen
    if screen_type == "SHOP_SCREEN":
        return _render_shop_view(game_state)

    # Rest site
    if screen_type == "REST":
        return _render_rest_view(game_state)

    # Grid select (for card removal, upgrades, etc)
    if screen_type == "GRID":
        return _render_grid_view(game_state)

    # Hand select (for card selection during combat)
    if screen_type == "HAND_SELECT":
        return _render_hand_select_view(game_state)

    # Default: show basic info
    return _render_default_view(game_state)


def _render_shop_view(game_state: GameState) -> str:
    """Render shop screen."""
    lines: list[str] = []
    lines.append(f"{Colors.BOLD}=== SHOP ==={Colors.RESET}")
    lines.append("")
    lines.append(f"Gold: {Colors.YELLOW}{game_state.gold}{Colors.RESET}")
    lines.append("")

    for i, choice in enumerate(game_state.choice_list):
        lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)


def _render_rest_view(game_state: GameState) -> str:
    """Render rest site screen."""
    lines: list[str] = []
    lines.append(f"{Colors.BOLD}=== REST SITE ==={Colors.RESET}")
    lines.append("")
    lines.append(f"HP: {render_hp_bar(game_state.hp, game_state.max_hp)}")
    lines.append("")
    lines.append(f"{Colors.BOLD}Options:{Colors.RESET}")

    for i, choice in enumerate(game_state.choice_list):
        lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)


def _render_grid_view(game_state: GameState) -> str:
    """Render grid selection screen (card removal, upgrade, etc)."""
    lines: list[str] = []
    lines.append(f"{Colors.BOLD}=== CARD SELECTION ==={Colors.RESET}")
    lines.append("")

    for i, choice in enumerate(game_state.choice_list):
        lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)


def _render_hand_select_view(game_state: GameState) -> str:
    """Render hand selection screen."""
    lines: list[str] = []
    lines.append(f"{Colors.BOLD}=== SELECT CARDS ==={Colors.RESET}")
    lines.append("")

    for i, choice in enumerate(game_state.choice_list):
        lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)


def _render_default_view(game_state: GameState) -> str:
    """Render default view for unknown screen types."""
    lines: list[str] = []
    lines.append(f"{Colors.BOLD}=== {game_state.screen_type} ==={Colors.RESET}")
    lines.append("")
    lines.append(f"Floor: {game_state.floor} | Act: {game_state.act}")
    lines.append(f"HP: {render_hp_bar(game_state.hp, game_state.max_hp)}")
    lines.append(f"Gold: {Colors.YELLOW}{game_state.gold}{Colors.RESET}")
    lines.append("")

    if game_state.choice_list:
        lines.append(f"{Colors.BOLD}Choices:{Colors.RESET}")
        for i, choice in enumerate(game_state.choice_list):
            lines.append(f"  [{i}] {choice}")

    return "\n".join(lines)
