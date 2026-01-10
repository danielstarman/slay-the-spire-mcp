"""Auto-commentary system for decision points.

Generates analysis commentary when the game reaches a decision point,
without requiring user prompting. When the player tabs to Claude Code,
analysis is already waiting.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable

from slay_the_spire_mcp import prompts
from slay_the_spire_mcp.context import RunContext
from slay_the_spire_mcp.detection import (
    DecisionPoint,
    DecisionType,
    detect_decision_point,
)
from slay_the_spire_mcp.models import GameState

logger = logging.getLogger(__name__)


class CommentaryEngine:
    """Generates and manages automatic commentary for decision points.

    When registered as a state change callback, this engine:
    1. Detects when the game reaches a new decision point
    2. Generates appropriate analysis commentary
    3. Caches the result and notifies listeners

    Combat decision points are explicitly skipped - commentary is only
    generated for non-combat decisions like card rewards, events, etc.
    """

    def __init__(
        self,
        run_context: RunContext,
        debounce_ms: int = 500,
    ) -> None:
        """Initialize the commentary engine.

        Args:
            run_context: RunContext instance for tracking run history
            debounce_ms: Minimum milliseconds between commentary for same decision
        """
        self._run_context = run_context
        self._debounce_ms = debounce_ms
        self._last_decision_hash: str | None = None
        self._last_update_time: float = 0.0
        self._cached_commentary: str | None = None
        self._cached_decision_type: DecisionType | None = None
        self._commentary_callbacks: list[Callable[[str, DecisionType], None]] = []

    def on_state_change(self, state: GameState) -> None:
        """Callback for state changes. Detects new decision points.

        This method should be registered with GameStateManager.on_state_change().
        It will:
        1. Update the run context with the new state
        2. Detect if we're at a decision point
        3. Skip combat decisions (per design requirement)
        4. Debounce rapid updates for same decision
        5. Generate and cache commentary
        6. Notify all registered callbacks

        Args:
            state: The new game state
        """
        # Update run context first
        self._run_context.update(state)

        # Detect decision point
        decision = detect_decision_point(state)
        if decision is None:
            return

        # Skip combat decisions (per design requirement)
        if decision.decision_type == DecisionType.COMBAT:
            return

        # Compute decision hash for debouncing
        decision_hash = self._compute_decision_hash(decision, state)
        now = time.monotonic()

        # Debounce: skip if same decision too recently
        if (
            decision_hash == self._last_decision_hash
            and (now - self._last_update_time) * 1000 < self._debounce_ms
        ):
            return

        self._last_decision_hash = decision_hash
        self._last_update_time = now

        # Generate commentary
        commentary = self._generate_commentary(decision, state)
        self._cached_commentary = commentary
        self._cached_decision_type = decision.decision_type

        # Notify listeners
        for callback in self._commentary_callbacks:
            try:
                callback(commentary, decision.decision_type)
            except Exception as e:
                # Log errors but don't crash - this is a notification callback
                callback_name = getattr(callback, "__name__", repr(callback))
                logger.error(
                    "Error in commentary callback '%s': %s",
                    callback_name,
                    e,
                    exc_info=True,
                )

    def _compute_decision_hash(self, decision: DecisionPoint, state: GameState) -> str:
        """Compute hash to identify unique decision points.

        Hash is based on: screen_type, floor, and sorted choices.
        This allows detecting when we're at the "same" decision point
        for debouncing purposes.

        Args:
            decision: The detected decision point
            state: The current game state

        Returns:
            MD5 hash string identifying this decision
        """
        key_parts = [
            state.screen_type,
            str(state.floor),
            str(sorted(decision.choices)),
        ]
        return hashlib.md5(":".join(key_parts).encode()).hexdigest()

    def _generate_commentary(self, decision: DecisionPoint, state: GameState) -> str:
        """Generate analysis commentary for the decision point.

        Selects the appropriate prompt generator based on decision type
        and appends run context summary.

        Args:
            decision: The detected decision point
            state: The current game state

        Returns:
            Generated commentary string
        """
        # Map decision types to prompt generators
        prompt_map: dict[DecisionType, Callable[[GameState], str]] = {
            DecisionType.CARD_REWARD: prompts.evaluate_card_reward,
            DecisionType.EVENT: prompts.evaluate_event,
            DecisionType.MAP: prompts.plan_path,
            DecisionType.SHOP: prompts.evaluate_shop,
            DecisionType.CAMPFIRE: prompts.evaluate_campfire,
            DecisionType.BOSS_RELIC: prompts.evaluate_boss_relic,
            # Combat is skipped above, but include for completeness
            DecisionType.COMBAT: prompts.analyze_combat,
        }

        generator = prompt_map.get(decision.decision_type)

        if generator is None:
            # Fallback for decision types without specific prompt
            analysis_prompt = f"Decision point: {decision.decision_type.value}\n\n"
            analysis_prompt += f"Choices: {', '.join(decision.choices)}"
        else:
            # Generate the structured prompt
            analysis_prompt = generator(state)

        # Add run context summary
        context_summary = self._run_context.get_full_context_summary()

        return f"{analysis_prompt}\n\n## Run History Context\n{context_summary}"

    def get_cached_commentary(self) -> tuple[str | None, DecisionType | None]:
        """Get the most recent cached commentary.

        Returns:
            Tuple of (commentary, decision_type), both None if no commentary cached
        """
        return self._cached_commentary, self._cached_decision_type

    def on_commentary_generated(
        self, callback: Callable[[str, DecisionType], None]
    ) -> None:
        """Register callback for when new commentary is generated.

        The callback will be called with (commentary, decision_type) whenever
        new commentary is generated.

        Args:
            callback: Function to call when commentary is generated
        """
        self._commentary_callbacks.append(callback)

    def clear_cache(self) -> None:
        """Clear cached commentary.

        Useful when starting a new run or resetting state.
        """
        self._cached_commentary = None
        self._cached_decision_type = None
        self._last_decision_hash = None
