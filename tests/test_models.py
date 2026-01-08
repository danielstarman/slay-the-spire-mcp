"""Tests for game state data models."""

from __future__ import annotations

from typing import Any

import pytest


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
        """Verify the sample game state fixture loads correctly."""
        assert sample_game_state["in_game"] is True
        assert sample_game_state["screen_type"] == "CARD_REWARD"
        assert len(sample_game_state["choice_list"]) == 3
