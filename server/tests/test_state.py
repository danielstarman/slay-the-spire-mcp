"""Tests for GameStateManager state tracking functionality.

Tests the state manager's ability to:
- Track when state was last updated
- Track bridge connection status
- Detect stale game state
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from slay_the_spire_mcp.models import (
    Card,
    GameState,
    Relic,
)
from slay_the_spire_mcp.state import GameStateManager


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def sample_game_state() -> GameState:
    """Sample game state for testing."""
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
            Card(name="Bash", cost=2, type="ATTACK"),
        ],
        relics=[Relic(name="Burning Blood", id="Burning Blood")],
        potions=[],
        choice_list=["Strike", "Pommel Strike", "Anger"],
    )


# ==============================================================================
# State Age Tracking Tests
# ==============================================================================


class TestStateAgeTracking:
    """Tests for state age tracking functionality."""

    def test_state_age_none_when_never_updated(
        self, state_manager: GameStateManager
    ) -> None:
        """get_state_age_seconds returns None when state has never been updated."""
        assert state_manager.get_state_age_seconds() is None

    def test_state_age_tracked_after_update(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """After state update, get_state_age_seconds returns approximately 0."""
        state_manager.update_state_sync(sample_game_state)

        age = state_manager.get_state_age_seconds()
        assert age is not None
        # Should be very close to 0 (just updated)
        assert age < 1.0

    def test_state_age_increases_over_time(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """State age increases as time passes."""
        # Use a mock to control time
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager.update_state_sync(sample_game_state)

            # Advance time by 10 seconds
            time_mock.monotonic.return_value = mock_time + 10.0
            age = state_manager.get_state_age_seconds()

            assert age is not None
            assert abs(age - 10.0) < 0.01  # Should be approximately 10 seconds


# ==============================================================================
# Bridge Connection Flag Tests
# ==============================================================================


class TestBridgeConnectionFlag:
    """Tests for bridge connection status tracking."""

    def test_bridge_disconnected_by_default(
        self, state_manager: GameStateManager
    ) -> None:
        """Bridge is marked as disconnected by default."""
        # The internal flag should be False initially
        assert state_manager._bridge_connected is False

    def test_set_bridge_connected_true(
        self, state_manager: GameStateManager
    ) -> None:
        """set_bridge_connected(True) marks bridge as connected."""
        state_manager.set_bridge_connected(True)
        assert state_manager._bridge_connected is True

    def test_set_bridge_connected_false(
        self, state_manager: GameStateManager
    ) -> None:
        """set_bridge_connected(False) marks bridge as disconnected."""
        state_manager.set_bridge_connected(True)
        state_manager.set_bridge_connected(False)
        assert state_manager._bridge_connected is False

    def test_reconnect_updates_connected_flag(
        self, state_manager: GameStateManager
    ) -> None:
        """Reconnecting sets connected flag back to True."""
        state_manager.set_bridge_connected(True)
        state_manager.set_bridge_connected(False)
        state_manager.set_bridge_connected(True)
        assert state_manager._bridge_connected is True


# ==============================================================================
# Staleness Detection Tests
# ==============================================================================


class TestStalenessDetection:
    """Tests for stale state detection."""

    def test_not_stale_when_never_updated(
        self, state_manager: GameStateManager
    ) -> None:
        """State is not stale if it was never received (None)."""
        assert state_manager.is_state_stale() is False

    def test_not_stale_when_connected(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """State is never stale while bridge is connected."""
        state_manager.set_bridge_connected(True)
        state_manager.update_state_sync(sample_game_state)

        # Even with mocked old timestamp, should not be stale if connected
        mock_time = 1000.0
        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager._last_state_time = mock_time - 100  # 100 seconds old

            assert state_manager.is_state_stale() is False

    def test_stale_when_disconnected_and_old(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """State is stale when bridge disconnected and age exceeds threshold."""
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager.update_state_sync(sample_game_state)
            state_manager.set_bridge_connected(False)

            # Advance time past threshold (default 30 seconds)
            time_mock.monotonic.return_value = mock_time + 35.0

            assert state_manager.is_state_stale() is True

    def test_not_stale_when_disconnected_but_recent(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """State is not stale when disconnected but within threshold."""
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager.update_state_sync(sample_game_state)
            state_manager.set_bridge_connected(False)

            # Only 10 seconds have passed (within 30s threshold)
            time_mock.monotonic.return_value = mock_time + 10.0

            assert state_manager.is_state_stale() is False

    def test_stale_threshold_custom(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """Custom threshold is respected."""
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager.update_state_sync(sample_game_state)
            state_manager.set_bridge_connected(False)

            # 15 seconds have passed
            time_mock.monotonic.return_value = mock_time + 15.0

            # With 10 second threshold, should be stale
            assert state_manager.is_state_stale(threshold_seconds=10.0) is True

            # With 20 second threshold, should not be stale
            assert state_manager.is_state_stale(threshold_seconds=20.0) is False

    def test_reconnect_clears_staleness(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """Reconnecting clears the stale state."""
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager.update_state_sync(sample_game_state)

            # Disconnect and advance time past threshold
            state_manager.set_bridge_connected(False)
            time_mock.monotonic.return_value = mock_time + 60.0

            # Should be stale
            assert state_manager.is_state_stale() is True

            # Reconnect
            state_manager.set_bridge_connected(True)

            # No longer stale (even though age is still old)
            assert state_manager.is_state_stale() is False


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestStalenessIntegration:
    """Integration tests for staleness tracking."""

    def test_full_disconnect_flow(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """Full flow: connect, update, disconnect, verify stale."""
        # Simulate bridge connecting
        state_manager.set_bridge_connected(True)

        # Receive state update
        state_manager.update_state_sync(sample_game_state)

        # Should not be stale (connected with fresh state)
        assert state_manager.is_state_stale() is False

        # Simulate disconnect
        state_manager.set_bridge_connected(False)

        # Use mocking to simulate time passing
        mock_time = 1000.0
        with patch("slay_the_spire_mcp.state.time") as time_mock:
            time_mock.monotonic.return_value = mock_time
            state_manager._last_state_time = mock_time - 60  # 60 seconds ago

            # Now should be stale
            assert state_manager.is_state_stale() is True

    def test_full_reconnect_flow(
        self,
        state_manager: GameStateManager,
        sample_game_state: GameState,
    ) -> None:
        """Full flow: disconnect, reconnect, new state clears staleness."""
        mock_time = 1000.0

        with patch("slay_the_spire_mcp.state.time") as time_mock:
            # Initial connect and update
            time_mock.monotonic.return_value = mock_time
            state_manager.set_bridge_connected(True)
            state_manager.update_state_sync(sample_game_state)

            # Disconnect
            state_manager.set_bridge_connected(False)

            # Time passes
            time_mock.monotonic.return_value = mock_time + 60.0
            assert state_manager.is_state_stale() is True

            # Reconnect and receive new state
            state_manager.set_bridge_connected(True)
            time_mock.monotonic.return_value = mock_time + 61.0
            state_manager.update_state_sync(sample_game_state)

            # Should not be stale anymore
            assert state_manager.is_state_stale() is False

            # Check age is fresh
            time_mock.monotonic.return_value = mock_time + 61.5
            age = state_manager.get_state_age_seconds()
            assert age is not None
            assert age < 1.0
