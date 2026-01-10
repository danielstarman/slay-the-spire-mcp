"""MCP prompt implementations.

Analysis prompts for Claude to reason about game state.
Each prompt provides structured context and guidance for strategic analysis.
"""

from __future__ import annotations

from slay_the_spire_mcp.models import Card, GameState


def analyze_combat(state: GameState) -> str:
    """Generate a prompt for analyzing the current combat situation.

    Provides structured context about:
    - Current hand and energy
    - Monster information (HP, intent, status effects)
    - Player status (HP, block, powers)
    - Available potions
    - Strategic guidance for turn planning

    Args:
        state: Current game state with combat information

    Returns:
        A structured prompt string for combat analysis
    """
    if state.combat_state is None:
        return "Not in combat. No combat state available to analyze."

    combat = state.combat_state

    # Build monster information
    monster_lines = []
    for i, monster in enumerate(combat.monsters):
        if monster.is_gone:
            continue
        powers_str = ""
        if monster.powers:
            power_names = [p.get("name", "Unknown") for p in monster.powers]
            powers_str = f" | Powers: {', '.join(power_names)}"
        monster_lines.append(
            f"  {i + 1}. {monster.name}: {monster.current_hp}/{monster.max_hp} HP, "
            f"Block: {monster.block}, Intent: {monster.intent}{powers_str}"
        )
    monsters_section = "\n".join(monster_lines) if monster_lines else "  No enemies"

    # Build hand information
    hand_lines = []
    for i, card in enumerate(combat.hand):
        upgrade_str = "+" if card.upgrades > 0 else ""
        hand_lines.append(f"  {i + 1}. {card.name}{upgrade_str} ({card.cost} energy)")
    hand_section = "\n".join(hand_lines) if hand_lines else "  No cards in hand"

    # Build player powers
    player_powers_str = ""
    if combat.player_powers:
        power_names = [p.get("name", "Unknown") for p in combat.player_powers]
        player_powers_str = f"\nPlayer Powers: {', '.join(power_names)}"

    # Build potions section
    potion_lines = []
    for potion in state.potions:
        if potion.can_use and potion.name != "Potion Slot":
            target_str = " (requires target)" if potion.requires_target else ""
            potion_lines.append(f"  - {potion.name}{target_str}")
    potions_section = "\n".join(potion_lines) if potion_lines else "  No usable potions"

    # Build relic context (some relics affect combat)
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    prompt = f"""## Combat Analysis - Turn {combat.turn}

### Player Status
- HP: {state.hp}/{state.max_hp}
- Block: {combat.player_block}
- Energy: {combat.energy}/{combat.max_energy}{player_powers_str}

### Enemies
{monsters_section}

### Hand ({len(combat.hand)} cards)
{hand_section}

### Available Potions
{potions_section}

### Relics
{relics_str}

### Deck Information
- Draw pile: {len(combat.draw_pile)} cards
- Discard pile: {len(combat.discard_pile)} cards
- Exhaust pile: {len(combat.exhaust_pile)} cards

---

## Analysis Request

Please analyze this combat situation and recommend the optimal play sequence. Consider:

1. **Immediate Threat**: What damage is incoming? Do we need to block?
2. **Damage Priority**: Can we kill enemies before they act? Which target is highest priority?
3. **Energy Efficiency**: What's the best use of our {combat.energy} energy?
4. **Card Synergies**: Are there any card combinations in hand?
5. **Future Turns**: What cards might we draw? Should we set up for next turn?
6. **Potion Usage**: Should we use any potions this turn?

Recommend a specific play order with reasoning for each card played."""

    return prompt


def evaluate_card_reward(state: GameState) -> str:
    """Generate a prompt for evaluating card reward choices.

    Provides structured context about:
    - Available card choices
    - Current deck composition
    - Run progress and upcoming challenges
    - Strategic guidance for card selection

    Args:
        state: Current game state with card reward information

    Returns:
        A structured prompt string for card reward evaluation
    """
    # Check for empty choices
    if not state.choice_list:
        return "No card choices available. The choice list is empty."

    # Build card choices section
    choice_lines = [f"  {i + 1}. {card}" for i, card in enumerate(state.choice_list)]
    choices_section = "\n".join(choice_lines)

    # Analyze current deck composition
    deck_by_type: dict[str, list[str]] = {
        "ATTACK": [],
        "SKILL": [],
        "POWER": [],
        "OTHER": [],
    }
    for card in state.deck:
        card_type = card.type if card.type in deck_by_type else "OTHER"
        upgrade_str = "+" if card.upgrades > 0 else ""
        deck_by_type[card_type].append(f"{card.name}{upgrade_str}")

    deck_analysis_lines = []
    for card_type, cards in deck_by_type.items():
        if cards:
            deck_analysis_lines.append(f"  {card_type}: {len(cards)} cards")

    deck_analysis = (
        "\n".join(deck_analysis_lines) if deck_analysis_lines else "  Empty deck"
    )

    # Build relic context
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    prompt = f"""## Card Reward Evaluation

### Available Choices
{choices_section}
  {len(state.choice_list) + 1}. Skip (take no card)

### Current Deck ({len(state.deck)} cards)
{deck_analysis}

### Deck Contents
{_format_deck_contents(state.deck)}

### Run Context
- Floor: {state.floor}
- Act: {state.act}
- HP: {state.hp}/{state.max_hp}
- Gold: {state.gold}

### Relics
{relics_str}

---

## Analysis Request

Please evaluate each card choice and recommend the best option. Consider:

1. **Deck Synergy**: How does each card fit with our current deck?
2. **Deck Size**: Is our deck too big? Should we skip to stay lean?
3. **Card Quality**: Which card provides the most value?
4. **Run Needs**: What does our deck lack? (damage, defense, scaling, etc.)
5. **Upcoming Challenges**: What fights are we preparing for? (elites, boss)
6. **Skip Value**: Is no card better than a mediocre addition?

Recommend a specific choice with detailed reasoning."""

    return prompt


def plan_path(state: GameState) -> str:
    """Generate a prompt for planning the map path.

    Provides structured context about:
    - Available path options
    - Current HP and resources
    - Node type explanations
    - Risk assessment guidance

    Args:
        state: Current game state with map information

    Returns:
        A structured prompt string for path planning
    """
    if state.map is None:
        return "No map data available. Map is not displayed or accessible."

    # Build map visualization
    map_lines = []
    for row_idx, row in enumerate(state.map):
        row_nodes = []
        for node in row:
            current_marker = "*" if state.current_node == (node.x, node.y) else ""
            row_nodes.append(f"{current_marker}{node.symbol}({node.x},{node.y})")
        map_lines.append(f"  Row {row_idx}: {' | '.join(row_nodes)}")
    map_section = "\n".join(map_lines) if map_lines else "  No nodes visible"

    # Build relic context
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    # Build potion context
    potion_names = [p.name for p in state.potions if p.name != "Potion Slot"]
    potions_str = ", ".join(potion_names) if potion_names else "None"

    # Calculate HP percentage for risk assessment
    hp_percent = (state.hp / state.max_hp * 100) if state.max_hp > 0 else 0

    prompt = f"""## Path Planning

### Current Position
- Floor: {state.floor}
- Act: {state.act}
- Current Node: {state.current_node}

### Player Status
- HP: {state.hp}/{state.max_hp} ({hp_percent:.0f}%)
- Gold: {state.gold}
- Deck Size: {len(state.deck)} cards

### Resources
- Relics: {relics_str}
- Potions: {potions_str}

### Map Layout
{map_section}

### Node Type Legend
- M = Monster (normal enemy encounter)
- E = Elite (tough enemy, drops relic)
- ? = Unknown/Event (random event or enemy)
- $ = Shop (buy cards, relics, potions)
- R = Rest Site (heal or upgrade)
- T = Treasure (free relic)
- B = Boss

---

## Analysis Request

Please analyze the available paths and recommend the best route. Consider:

1. **HP Assessment**: At {hp_percent:.0f}% HP, how much risk can we take?
2. **Elite Risk/Reward**: Is our deck strong enough for elites?
3. **Rest Site Value**: Do we need healing or would an upgrade be better?
4. **Shop Planning**: Do we have enough gold ({state.gold}) for meaningful purchases?
5. **Event Outcomes**: Are unknown events worth the variance?
6. **Path Flexibility**: Which route gives the best options going forward?

Recommend a specific path with reasoning for each node choice."""

    return prompt


def evaluate_event(state: GameState) -> str:
    """Generate a prompt for analyzing event options.

    Provides structured context about:
    - Event name and choices
    - Current resources (HP, gold, etc.)
    - Risk/reward assessment guidance

    Args:
        state: Current game state with event information

    Returns:
        A structured prompt string for event evaluation
    """
    # Check if we're at an event
    if state.screen_type != "EVENT" and not state.choice_list:
        return "Not at an event. No event choices available to evaluate."

    # Get event name from screen_state
    event_name = "Unknown Event"
    if isinstance(state.screen_state, dict):
        event_name = state.screen_state.get("event_name", "Unknown Event")

    # Build choices section
    if state.choice_list:
        choice_lines = [
            f"  {i + 1}. {choice}" for i, choice in enumerate(state.choice_list)
        ]
        choices_section = "\n".join(choice_lines)
    else:
        choices_section = "  No choices available"

    # Build relic context
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    # Calculate HP percentage for risk assessment
    hp_percent = (state.hp / state.max_hp * 100) if state.max_hp > 0 else 0

    # Deck summary
    deck_size = len(state.deck)
    attack_count = sum(1 for c in state.deck if c.type == "ATTACK")
    skill_count = sum(1 for c in state.deck if c.type == "SKILL")

    prompt = f"""## Event Evaluation: {event_name}

### Available Choices
{choices_section}

### Current Status
- HP: {state.hp}/{state.max_hp} ({hp_percent:.0f}%)
- Gold: {state.gold}
- Floor: {state.floor}
- Act: {state.act}

### Deck Summary
- Total Cards: {deck_size}
- Attacks: {attack_count}
- Skills: {skill_count}

### Relics
{relics_str}

---

## Analysis Request

Please evaluate each event choice and recommend the best option. Consider:

1. **HP Cost/Benefit**: Can we afford HP loss at {hp_percent:.0f}%?
2. **Gold Value**: Is spending {state.gold} gold worth the reward?
3. **Deck Impact**: Will this add/remove cards that help or hurt our deck?
4. **Relic Synergies**: Do our relics interact with any options?
5. **Risk Assessment**: What's the worst-case outcome for risky choices?
6. **Run Context**: Are we preparing for boss/elite? Can we afford variance?

Recommend a specific choice with detailed reasoning."""

    return prompt


def evaluate_shop(state: GameState) -> str:
    """Generate a prompt for evaluating shop purchases.

    Provides structured context about:
    - Available items with prices
    - Current gold and deck
    - Purge availability
    - Strategic guidance for purchases

    Args:
        state: Current game state with shop information

    Returns:
        A structured prompt string for shop evaluation
    """
    # Get shop items from screen_state
    shop_cards = state.screen_state.get("cards", [])
    shop_relics = state.screen_state.get("relics", [])
    shop_potions = state.screen_state.get("potions", [])
    can_purge = state.screen_state.get("can_purge", False)
    purge_cost = state.screen_state.get("purge_cost", 0)

    # Build items section
    items_lines = []

    if shop_cards:
        items_lines.append("Cards:")
        for card in shop_cards:
            name = card.get("name", "Unknown")
            cost = card.get("price", card.get("cost", 0))
            items_lines.append(f"  - {name} ({cost}g)")

    if shop_relics:
        items_lines.append("Relics:")
        for relic in shop_relics:
            name = relic.get("name", "Unknown")
            cost = relic.get("price", relic.get("cost", 0))
            items_lines.append(f"  - {name} ({cost}g)")

    if shop_potions:
        items_lines.append("Potions:")
        for potion in shop_potions:
            name = potion.get("name", "Unknown")
            cost = potion.get("price", potion.get("cost", 0))
            items_lines.append(f"  - {name} ({cost}g)")

    items_section = "\n".join(items_lines) if items_lines else "  No items available"

    # Deck summary
    deck_size = len(state.deck)
    attack_count = sum(1 for c in state.deck if c.type == "ATTACK")
    skill_count = sum(1 for c in state.deck if c.type == "SKILL")
    power_count = sum(1 for c in state.deck if c.type == "POWER")

    # Build relic context
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    # Calculate HP percentage
    hp_percent = (state.hp / state.max_hp * 100) if state.max_hp > 0 else 0

    prompt = f"""## Shop Evaluation

### Current Resources
- Gold: {state.gold}
- HP: {state.hp}/{state.max_hp} ({hp_percent:.0f}%)
- Floor: {state.floor}
- Act: {state.act}

### Available Items
{items_section}

### Card Removal
- Available: {"Yes" if can_purge else "No"}
- Cost: {purge_cost}g

### Deck Summary
- Total Cards: {deck_size}
- Attacks: {attack_count}
- Skills: {skill_count}
- Powers: {power_count}

### Current Relics
{relics_str}

---

## Analysis Request

Please evaluate the shop options and recommend purchases. Consider:

1. **Budget**: With {state.gold} gold, what can we afford?
2. **Deck Needs**: What does our deck lack that the shop could provide?
3. **Card Removal**: Should we prioritize removing a Strike/Defend?
4. **Relic Value**: Are any relics worth the investment?
5. **Potion Utility**: Do we need potions for upcoming challenges?
6. **Save Gold**: Is it better to save gold for a future shop?

Recommend specific purchases with priority order and reasoning."""

    return prompt


def evaluate_campfire(state: GameState) -> str:
    """Generate a prompt for evaluating campfire/rest site options.

    Provides structured context about:
    - Current HP and healing value
    - Upgradeable cards in deck
    - Other campfire options (lift, dig, recall, etc.)
    - Strategic guidance for rest site decisions

    Args:
        state: Current game state at rest site

    Returns:
        A structured prompt string for campfire evaluation
    """
    # Get rest options from choice_list or screen_state
    rest_options = list(state.choice_list)
    if not rest_options:
        rest_options = state.screen_state.get("rest_options", [])

    # Calculate healing value (rest heals 30% of max HP)
    heal_amount = int(state.max_hp * 0.3)
    hp_after_rest = min(state.max_hp, state.hp + heal_amount)

    # Calculate HP percentage
    hp_percent = (state.hp / state.max_hp * 100) if state.max_hp > 0 else 0

    # Find upgradeable cards (not already upgraded)
    upgradeable_cards = [c for c in state.deck if c.upgrades == 0]

    # Key upgrade targets
    upgrade_priorities = []
    for card in upgradeable_cards:
        # Highlight high-value upgrade targets
        if card.name in ["Bash", "Neutralize", "Eruption", "Zap"]:
            upgrade_priorities.append(f"{card.name} (starter - high priority)")
        elif card.type == "POWER":
            upgrade_priorities.append(f"{card.name} (power - good target)")
        elif card.type == "ATTACK" and card.cost >= 2:
            upgrade_priorities.append(f"{card.name} (high-cost attack)")

    upgrade_section = (
        "\n".join(f"  - {c}" for c in upgrade_priorities[:5])
        if upgrade_priorities
        else "  No notable upgrade targets"
    )

    # Build relic context
    relic_names = [r.name for r in state.relics] if state.relics else []
    relics_str = ", ".join(relic_names) if relic_names else "None"

    # Check for relevant relics
    has_regal_pillow = any(r.name == "Regal Pillow" for r in state.relics)
    has_dream_catcher = any(r.name == "Dream Catcher" for r in state.relics)

    relic_notes = []
    if has_regal_pillow:
        relic_notes.append("Regal Pillow: Rest heals 15 extra HP")
    if has_dream_catcher:
        relic_notes.append("Dream Catcher: Rest adds card to deck")

    relic_note_str = (
        "\n".join(relic_notes) if relic_notes else "No rest-affecting relics"
    )

    prompt = f"""## Campfire Evaluation

### Available Options
{chr(10).join(f"  - {opt}" for opt in rest_options)}

### HP Status
- Current HP: {state.hp}/{state.max_hp} ({hp_percent:.0f}%)
- Heal Amount: {heal_amount} HP (rest)
- HP After Rest: {hp_after_rest}/{state.max_hp}

### Upgrade Candidates
{upgrade_section}
- Total upgradeable cards: {len(upgradeable_cards)}

### Rest Site Relics
{relic_note_str}

### Run Position
- Floor: {state.floor}
- Act: {state.act}

### Current Relics
{relics_str}

---

## Analysis Request

Please evaluate the campfire options and recommend the best choice. Consider:

1. **HP Threshold**: At {hp_percent:.0f}% HP, do we need to heal?
2. **Upgrade Value**: Would upgrading a key card increase our win rate more than healing?
3. **Upcoming Challenges**: Is the next fight an elite or boss?
4. **Relic Synergies**: Do any relics affect our decision?
5. **Act Progress**: How far into the act are we?
6. **Deck State**: Does our deck need an upgrade to function?

Recommend a specific choice with detailed reasoning."""

    return prompt


def evaluate_boss_relic(state: GameState) -> str:
    """Generate a prompt for evaluating boss relic choices.

    Provides structured context about:
    - Available boss relics with descriptions
    - Current deck and relics
    - Strategic guidance for relic selection

    Args:
        state: Current game state at boss relic selection

    Returns:
        A structured prompt string for boss relic evaluation
    """
    # Get relic options from screen_state
    relic_options = state.screen_state.get("relics", [])

    # Build relic choices section
    relic_lines = []
    for i, relic in enumerate(relic_options):
        name = relic.get("name", "Unknown")
        desc = relic.get("description", "No description available")
        relic_lines.append(f"  {i + 1}. {name}")
        relic_lines.append(f"     {desc}")

    relics_section = "\n".join(relic_lines) if relic_lines else "  No relics available"

    # Deck summary
    deck_size = len(state.deck)
    attack_count = sum(1 for c in state.deck if c.type == "ATTACK")
    skill_count = sum(1 for c in state.deck if c.type == "SKILL")
    power_count = sum(1 for c in state.deck if c.type == "POWER")

    # Current relics
    current_relic_names = [r.name for r in state.relics] if state.relics else []
    current_relics_str = (
        ", ".join(current_relic_names) if current_relic_names else "None"
    )

    # Calculate HP percentage
    hp_percent = (state.hp / state.max_hp * 100) if state.max_hp > 0 else 0

    # Count potions
    potion_count = sum(1 for p in state.potions if p.name != "Potion Slot")
    potion_slots = len(state.potions)

    prompt = f"""## Boss Relic Selection

### Available Boss Relics
{relics_section}

### Option to Skip
You can skip the boss relic if none are beneficial.

### Current Status
- HP: {state.hp}/{state.max_hp} ({hp_percent:.0f}%)
- Gold: {state.gold}
- Floor: {state.floor}
- Potions: {potion_count}/{potion_slots} slots filled

### Deck Summary
- Total Cards: {deck_size}
- Attacks: {attack_count}
- Skills: {skill_count}
- Powers: {power_count}

### Current Relics
{current_relics_str}

---

## Analysis Request

Please evaluate the boss relic options and recommend the best choice. Consider:

1. **Relic Synergy**: How does each relic work with our current deck/relics?
2. **Downside Assessment**: What are the risks of each relic's downside?
3. **Future Value**: Which relic provides the most value for the rest of the run?
4. **Skip Option**: Is skipping better than taking a harmful relic?
5. **Act Transition**: We're entering a new act - what challenges lie ahead?
6. **Build Direction**: Does a relic push us toward a specific strategy?

Recommend a specific choice with detailed reasoning."""

    return prompt


def _format_deck_contents(deck: list[Card]) -> str:
    """Format deck contents for display.

    Groups cards by name and shows counts.

    Args:
        deck: List of Card objects

    Returns:
        Formatted string showing deck contents
    """
    if not deck:
        return "  Empty"

    card_counts: dict[str, int] = {}
    for card in deck:
        upgrade_str = "+" if card.upgrades > 0 else ""
        card_name = f"{card.name}{upgrade_str}"
        card_counts[card_name] = card_counts.get(card_name, 0) + 1

    lines = []
    for card_name, count in sorted(card_counts.items()):
        count_str = f" x{count}" if count > 1 else ""
        lines.append(f"  - {card_name}{count_str}")

    return "\n".join(lines)
