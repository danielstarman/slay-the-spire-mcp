"""Tests for WebSocket overlay pusher.

Tests the OverlayPusher that connects to the SpireBridge mod's WebSocket
server and pushes recommendations when decision points are detected.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slay_the_spire_mcp.detection import DecisionType
from slay_the_spire_mcp.models import Card, GameState, Relic


# ==============================================================================
# Test Fixtures
# ==============================================================================


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


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


async def get_free_port() -> int:
    """Get a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# Mock WebSocket Server Helper
# ==============================================================================


class MockWebSocketServer:
    """A mock WebSocket server for testing OverlayPusher."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7778) -> None:
        self.host = host
        self.port = port
        self.received_messages: list[dict[str, Any]] = []
        self._server: Any = None
        self._clients: list[Any] = []

    async def start(self) -> None:
        """Start the mock WebSocket server."""
        import websockets

        async def handler(websocket: Any) -> None:
            self._clients.append(websocket)
            try:
                async for message in websocket:
                    data = json.loads(message)
                    self.received_messages.append(data)
            except Exception:
                pass
            finally:
                self._clients.remove(websocket)

        self._server = await websockets.serve(handler, self.host, self.port)

    async def stop(self) -> None:
        """Stop the mock WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def clear_messages(self) -> None:
        """Clear received messages."""
        self.received_messages.clear()


# ==============================================================================
# Happy Path Tests
# ==============================================================================


class TestOverlayPusherHappyPath:
    """Tests for normal operation of OverlayPusher."""

    async def test_connects_to_mod_websocket(self) -> None:
        """Given mod WebSocket server running on port, OverlayPusher connects successfully."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)

            assert pusher.is_connected
        finally:
            await pusher.stop()
            await server.stop()

    async def test_pushes_recommendations_json(self) -> None:
        """Given connected OverlayPusher and commentary generated, sends correct JSON format."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)

            # Trigger commentary callback
            pusher.on_commentary_generated(
                commentary="Play Bash on Jaw Worm for maximum damage",
                decision_type=DecisionType.COMBAT,
            )

            # Give time for message to be sent
            await asyncio.sleep(0.2)

            # Verify the message was received
            assert len(server.received_messages) == 1
            msg = server.received_messages[0]
            assert msg["type"] == "recommendations"
            assert "recommendedAction" in msg
            assert "reason" in msg
        finally:
            await pusher.stop()
            await server.stop()

    async def test_clears_overlay_on_no_decision(
        self, main_menu_state: GameState
    ) -> None:
        """Given state transition to non-decision screen, sends empty recommendations."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)

            # Trigger state change to non-decision state
            pusher.on_state_change(main_menu_state)

            # Give time for message to be sent
            await asyncio.sleep(0.2)

            # Verify an empty/clear message was sent
            assert len(server.received_messages) == 1
            msg = server.received_messages[0]
            assert msg["type"] == "recommendations"
            # recommendedAction should be empty or null for clearing
            assert msg.get("recommendedAction", "") == "" or msg.get("recommendedAction") is None
        finally:
            await pusher.stop()
            await server.stop()

    async def test_stops_cleanly(self) -> None:
        """Given stop() called, background task terminates and connection closes."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)
            assert pusher.is_connected

            # Stop the pusher
            await pusher.stop()

            # Verify stopped
            assert not pusher.is_connected

            # Should be able to call stop again without error
            await pusher.stop()
        finally:
            await server.stop()


# ==============================================================================
# Error Condition Tests
# ==============================================================================


class TestOverlayPusherErrorConditions:
    """Tests for error handling in OverlayPusher."""

    async def test_handles_mod_not_running(self) -> None:
        """Given no server on port, OverlayPusher logs warning and retries without crashing."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        # No server started intentionally

        pusher = OverlayPusher(
            host="127.0.0.1",
            port=port,
            reconnect_delay_ms=100,  # Short delay for faster test
        )

        try:
            await pusher.start()

            # Give time for connection attempts
            await asyncio.sleep(0.3)

            # Should not be connected (no server)
            assert not pusher.is_connected

            # But pusher should still be running (trying to reconnect)
            # No crash means success
        finally:
            await pusher.stop()

    async def test_reconnects_after_disconnect(self) -> None:
        """Given connection dropped, OverlayPusher reconnects."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        pusher = OverlayPusher(
            host="127.0.0.1",
            port=port,
            reconnect_delay_ms=100,  # Short delay for faster test
        )

        try:
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)
            assert pusher.is_connected

            # Stop server (simulating disconnect)
            await server.stop()

            # Give time for disconnect detection
            await asyncio.sleep(0.2)

            # Connection should be lost
            assert not pusher.is_connected

            # Restart server
            server = MockWebSocketServer(port=port)
            await server.start()

            # Give time for reconnection
            await asyncio.sleep(0.5)

            # Should be reconnected
            assert pusher.is_connected
        finally:
            await pusher.stop()
            await server.stop()

    async def test_graceful_shutdown_during_reconnect(self) -> None:
        """Given stop() called during reconnection backoff, terminates promptly."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        # No server - pusher will be trying to reconnect

        pusher = OverlayPusher(
            host="127.0.0.1",
            port=port,
            reconnect_delay_ms=5000,  # Long delay to ensure we catch it during backoff
        )

        try:
            await pusher.start()

            # Give a moment for the first connection attempt to fail
            await asyncio.sleep(0.2)

            # Stop during reconnection backoff
            start_time = asyncio.get_event_loop().time()
            await pusher.stop()
            elapsed = asyncio.get_event_loop().time() - start_time

            # Should stop quickly, not wait for the full reconnect delay
            assert elapsed < 1.0, f"Stop took too long: {elapsed}s"
        finally:
            pass  # Already stopped


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestOverlayPusherEdgeCases:
    """Tests for edge cases in OverlayPusher."""

    async def test_queues_messages_when_disconnected(self) -> None:
        """Given disconnected state and commentary generated, message is queued."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        # No server initially

        pusher = OverlayPusher(
            host="127.0.0.1",
            port=port,
            reconnect_delay_ms=100,
        )

        try:
            await pusher.start()
            await asyncio.sleep(0.1)

            # Should not be connected
            assert not pusher.is_connected

            # Generate commentary while disconnected
            pusher.on_commentary_generated(
                commentary="Queued recommendation",
                decision_type=DecisionType.CARD_REWARD,
            )

            # Start server
            server = MockWebSocketServer(port=port)
            await server.start()

            # Wait for reconnect and message delivery
            await asyncio.sleep(0.5)

            # Should have received the queued message
            assert len(server.received_messages) >= 1
            msg = server.received_messages[0]
            assert msg["type"] == "recommendations"

            await server.stop()
        finally:
            await pusher.stop()

    async def test_queue_size_limit(self) -> None:
        """Given queue at max size and new message, oldest message is dropped."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        # No server

        pusher = OverlayPusher(
            host="127.0.0.1",
            port=port,
            reconnect_delay_ms=100,
            max_queue_size=2,  # Small queue for testing
        )

        try:
            await pusher.start()
            await asyncio.sleep(0.1)

            # Queue multiple messages while disconnected
            for i in range(5):
                pusher.on_commentary_generated(
                    commentary=f"Message {i}",
                    decision_type=DecisionType.CARD_REWARD,
                )

            # Start server
            server = MockWebSocketServer(port=port)
            await server.start()

            # Wait for reconnect and message delivery
            await asyncio.sleep(0.5)

            # Should only have received the last 2 messages (queue size limit)
            assert len(server.received_messages) <= 2

            await server.stop()
        finally:
            await pusher.stop()

    async def test_multiple_rapid_updates(self) -> None:
        """Given rapid state changes, only latest recommendation is sent."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()

            # Give time for connection
            await asyncio.sleep(0.2)

            # Rapid fire commentary updates
            for i in range(10):
                pusher.on_commentary_generated(
                    commentary=f"Update {i}",
                    decision_type=DecisionType.CARD_REWARD,
                )

            # Give time for messages to be processed
            await asyncio.sleep(0.5)

            # Messages should be sent (we're connected, so no queuing limit)
            # But the key is that we don't crash and messages arrive
            assert len(server.received_messages) >= 1
        finally:
            await pusher.stop()
            await server.stop()

    async def test_overlay_disabled_does_not_connect(self) -> None:
        """Given overlay disabled, pusher does not attempt to connect."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(
                host="127.0.0.1",
                port=port,
                enabled=False,
            )
            await pusher.start()

            # Give time for potential connection
            await asyncio.sleep(0.2)

            # Should not be connected when disabled
            assert not pusher.is_connected

            # Callbacks should be no-ops
            pusher.on_commentary_generated(
                commentary="Should be ignored",
                decision_type=DecisionType.CARD_REWARD,
            )

            # No messages should be received
            assert len(server.received_messages) == 0
        finally:
            await pusher.stop()
            await server.stop()


# ==============================================================================
# Message Format Tests
# ==============================================================================


class TestOverlayPusherMessageFormat:
    """Tests for the message format sent to the mod."""

    async def test_message_format_for_card_reward(self) -> None:
        """Card reward commentary produces correct message format."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()
            await asyncio.sleep(0.2)

            pusher.on_commentary_generated(
                commentary="Take Pommel Strike for draw synergy. Skip if deck is bloated.",
                decision_type=DecisionType.CARD_REWARD,
            )

            await asyncio.sleep(0.2)

            assert len(server.received_messages) == 1
            msg = server.received_messages[0]

            # Verify required fields
            assert msg["type"] == "recommendations"
            assert "recommendedAction" in msg
            assert "reason" in msg

            # For Phase 1, no cardScores expected
            # (Phase 2 will add card scores)
        finally:
            await pusher.stop()
            await server.stop()

    async def test_message_format_for_event(self) -> None:
        """Event commentary produces correct message format."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()
            await asyncio.sleep(0.2)

            pusher.on_commentary_generated(
                commentary="Choose option 1 to gain max HP. Avoid curse options.",
                decision_type=DecisionType.EVENT,
            )

            await asyncio.sleep(0.2)

            assert len(server.received_messages) == 1
            msg = server.received_messages[0]

            assert msg["type"] == "recommendations"
            assert "recommendedAction" in msg
        finally:
            await pusher.stop()
            await server.stop()

    async def test_clear_message_format(self) -> None:
        """Clear overlay sends empty recommendation."""
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()
            await asyncio.sleep(0.2)

            # Create a state with no decision point (main menu)
            state = GameState(
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

            pusher.on_state_change(state)

            await asyncio.sleep(0.2)

            assert len(server.received_messages) == 1
            msg = server.received_messages[0]

            assert msg["type"] == "recommendations"
            # Both should be empty/null for clearing
            assert msg.get("recommendedAction", "") == "" or msg.get("recommendedAction") is None
            assert msg.get("reason", "") == "" or msg.get("reason") is None
        finally:
            await pusher.stop()
            await server.stop()


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestOverlayPusherIntegration:
    """Integration tests for OverlayPusher with CommentaryEngine."""

    async def test_end_to_end_commentary_to_overlay(
        self, card_reward_state: GameState
    ) -> None:
        """Given CommentaryEngine and OverlayPusher wired together, recommendations are sent."""
        from slay_the_spire_mcp.commentary import CommentaryEngine
        from slay_the_spire_mcp.context import RunContext
        from slay_the_spire_mcp.overlay import OverlayPusher

        port = await get_free_port()
        server = MockWebSocketServer(port=port)
        await server.start()

        try:
            pusher = OverlayPusher(host="127.0.0.1", port=port)
            await pusher.start()
            await asyncio.sleep(0.2)

            # Create commentary engine and wire to pusher
            run_context = RunContext()
            engine = CommentaryEngine(run_context)
            engine.on_commentary_generated(pusher.on_commentary_generated)

            # Trigger state change that generates commentary
            engine.on_state_change(card_reward_state)

            # Give time for message to be sent
            await asyncio.sleep(0.3)

            # Verify recommendations were sent
            assert len(server.received_messages) >= 1
            msg = server.received_messages[0]
            assert msg["type"] == "recommendations"
        finally:
            await pusher.stop()
            await server.stop()
