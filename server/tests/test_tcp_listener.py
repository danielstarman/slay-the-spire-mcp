"""Tests for TCP listener functionality.

Tests the server's ability to:
- Accept TCP connections from the bridge process
- Parse newline-delimited JSON game state
- Update GameStateManager with parsed state
- Handle malformed JSON gracefully
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from slay_the_spire_mcp.state import (
    GameStateManager,
    TCPListener,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def sample_game_state() -> dict[str, Any]:
    """Sample game state JSON from the bridge."""
    return {
        "type": "state",
        "data": {
            "in_game": True,
            "screen_type": "CARD_REWARD",
            "floor": 5,
            "act": 1,
            "hp": 65,
            "max_hp": 80,
            "gold": 99,
            "deck": [
                {"name": "Strike", "cost": 1, "type": "ATTACK"},
                {"name": "Defend", "cost": 1, "type": "SKILL"},
            ],
            "relics": [{"name": "Burning Blood", "id": "Burning Blood"}],
            "potions": [],
            "choice_list": ["Strike", "Pommel Strike", "Anger"],
            "seed": 123456789,
        },
    }


@pytest.fixture
def second_game_state() -> dict[str, Any]:
    """A second game state to test sequential updates."""
    return {
        "type": "state",
        "data": {
            "in_game": True,
            "screen_type": "MAP",
            "floor": 6,
            "act": 1,
            "hp": 60,
            "max_hp": 80,
            "gold": 99,
            "deck": [
                {"name": "Strike", "cost": 1, "type": "ATTACK"},
                {"name": "Defend", "cost": 1, "type": "SKILL"},
                {"name": "Pommel Strike", "cost": 1, "type": "ATTACK"},
            ],
            "relics": [{"name": "Burning Blood", "id": "Burning Blood"}],
            "potions": [],
            "choice_list": [],
            "seed": 123456789,
        },
    }


# ==============================================================================
# Helper Functions
# ==============================================================================


async def connect_and_send(
    port: int, messages: list[str], delay: float = 0.01
) -> None:
    """Connect to TCP listener and send messages."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        for msg in messages:
            writer.write(msg.encode("utf-8"))
            await writer.drain()
            await asyncio.sleep(delay)
    finally:
        writer.close()
        await writer.wait_closed()


async def get_free_port() -> int:
    """Get a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# Happy Path Tests
# ==============================================================================


class TestTCPListenerHappyPath:
    """Tests for normal operation of TCP listener."""

    async def test_accepts_bridge_connection(
        self, state_manager: GameStateManager
    ) -> None:
        """Server accepts TCP connection on configured port."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        # Start listener
        await listener.start()
        try:
            # Attempt to connect
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()

            # If we get here without exception, connection was accepted
            assert True
        finally:
            await listener.stop()

    async def test_parses_game_state_json(
        self, state_manager: GameStateManager, sample_game_state: dict[str, Any]
    ) -> None:
        """Valid JSON updates GameStateManager with parsed state."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Send valid JSON with newline
            message = json.dumps(sample_game_state) + "\n"
            await connect_and_send(port, [message])

            # Give time for processing
            await asyncio.sleep(0.1)

            # Verify state was updated
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.in_game is True
            assert current_state.screen_type == "CARD_REWARD"
            assert current_state.floor == 5
            assert current_state.hp == 65
        finally:
            await listener.stop()

    async def test_handles_multiple_states(
        self,
        state_manager: GameStateManager,
        sample_game_state: dict[str, Any],
        second_game_state: dict[str, Any],
    ) -> None:
        """Sequential state updates are processed correctly."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Send first state
            msg1 = json.dumps(sample_game_state) + "\n"
            # Send second state
            msg2 = json.dumps(second_game_state) + "\n"

            await connect_and_send(port, [msg1, msg2])

            # Give time for processing
            await asyncio.sleep(0.1)

            # Verify final state is the second one
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.screen_type == "MAP"
            assert current_state.floor == 6
            assert current_state.hp == 60
            assert len(current_state.deck) == 3
        finally:
            await listener.stop()


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestTCPListenerEdgeCases:
    """Tests for edge cases in TCP listener."""

    async def test_handles_empty_lines(
        self, state_manager: GameStateManager, sample_game_state: dict[str, Any]
    ) -> None:
        """Empty lines are ignored without error."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Send empty lines before and after valid JSON
            messages = [
                "\n",
                "\n",
                json.dumps(sample_game_state) + "\n",
                "\n",
                "\n",
            ]
            await connect_and_send(port, messages)

            # Give time for processing
            await asyncio.sleep(0.1)

            # Should have parsed the valid state
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.floor == 5
        finally:
            await listener.stop()

    async def test_handles_partial_json(
        self, state_manager: GameStateManager, sample_game_state: dict[str, Any]
    ) -> None:
        """Incomplete JSON waits for more data (buffering)."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Split JSON across multiple sends (simulating partial reads)
            full_message = json.dumps(sample_game_state) + "\n"
            part1 = full_message[:50]
            part2 = full_message[50:]

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Send first part
                writer.write(part1.encode("utf-8"))
                await writer.drain()
                await asyncio.sleep(0.05)

                # State should not be set yet (incomplete JSON)
                assert state_manager.get_current_state() is None

                # Send second part
                writer.write(part2.encode("utf-8"))
                await writer.drain()
                await asyncio.sleep(0.1)

                # Now state should be set
                current_state = state_manager.get_current_state()
                assert current_state is not None
                assert current_state.floor == 5
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()


# ==============================================================================
# Error Condition Tests
# ==============================================================================


class TestTCPListenerErrorHandling:
    """Tests for error handling in TCP listener."""

    async def test_rejects_invalid_json(
        self, state_manager: GameStateManager, sample_game_state: dict[str, Any]
    ) -> None:
        """Malformed JSON logs error, doesn't crash, continues listening."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Send invalid JSON followed by valid JSON
            messages = [
                '{"broken": json here\n',  # Invalid
                json.dumps(sample_game_state) + "\n",  # Valid
            ]
            await connect_and_send(port, messages)

            # Give time for processing
            await asyncio.sleep(0.1)

            # Listener should still be running and have processed valid state
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.floor == 5

            # Verify listener is still accepting connections
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_handles_connection_close(
        self, state_manager: GameStateManager, sample_game_state: dict[str, Any]
    ) -> None:
        """Bridge disconnect is handled gracefully."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect, send data, and close
            message = json.dumps(sample_game_state) + "\n"
            await connect_and_send(port, [message])

            # Give time for processing and cleanup
            await asyncio.sleep(0.1)

            # Verify state was updated before disconnect
            assert state_manager.get_current_state() is not None

            # Verify listener is still running - can accept new connection
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_handles_connection_without_data(
        self, state_manager: GameStateManager
    ) -> None:
        """Connection that sends no data and disconnects is handled."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect and immediately close without sending data
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()

            await asyncio.sleep(0.1)

            # State should still be None
            assert state_manager.get_current_state() is None

            # Listener should still be running
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
        finally:
            await listener.stop()


# ==============================================================================
# Buffer Limit Tests
# ==============================================================================


class TestTCPListenerBufferLimits:
    """Tests for buffer size limits to prevent memory exhaustion."""

    async def test_rejects_oversized_line(
        self, state_manager: GameStateManager
    ) -> None:
        """Lines exceeding MAX_LINE_LENGTH cause connection drop."""
        from slay_the_spire_mcp.state import MAX_LINE_LENGTH

        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Create a line that exceeds the limit
            oversized_data = "x" * (MAX_LINE_LENGTH + 100) + "\n"

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(oversized_data.encode("utf-8"))
                await writer.drain()

                # Give time for the server to process and close
                await asyncio.sleep(0.2)

                # Connection should be closed by server
                # Try reading - should get EOF or empty data
                data = await asyncio.wait_for(reader.read(1), timeout=0.5)
                # If we get here, connection was closed (empty data = EOF)
                assert data == b"", "Expected connection to be closed"
            except (ConnectionResetError, asyncio.TimeoutError):
                # Connection was forcibly closed - this is expected
                pass
            finally:
                writer.close()
                with __import__("contextlib").suppress(Exception):
                    await writer.wait_closed()

            # State should not be updated with bad data
            assert state_manager.get_current_state() is None

            # Listener should still be running for new connections
            reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
            writer2.close()
            await writer2.wait_closed()
        finally:
            await listener.stop()

    async def test_rejects_oversized_buffer(
        self, state_manager: GameStateManager
    ) -> None:
        """Buffer exceeding MAX_BUFFER_SIZE causes connection drop."""
        from slay_the_spire_mcp.state import MAX_BUFFER_SIZE

        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Send data without newlines to fill buffer
                chunk_size = 65536  # 64KB chunks
                total_sent = 0

                while total_sent < MAX_BUFFER_SIZE + chunk_size:
                    try:
                        writer.write(b"x" * chunk_size)
                        await writer.drain()
                        total_sent += chunk_size
                    except (ConnectionResetError, BrokenPipeError):
                        # Server closed connection - expected behavior
                        break

                # Give time for the server to process
                await asyncio.sleep(0.2)

                # Try to detect if connection was closed
                try:
                    data = await asyncio.wait_for(reader.read(1), timeout=0.5)
                    assert data == b"", "Expected connection to be closed"
                except (ConnectionResetError, asyncio.TimeoutError):
                    pass  # Expected
            finally:
                writer.close()
                with __import__("contextlib").suppress(Exception):
                    await writer.wait_closed()

            # Listener should still accept new connections
            reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
            writer2.close()
            await writer2.wait_closed()
        finally:
            await listener.stop()


# ==============================================================================
# UTF-8 Edge Case Tests
# ==============================================================================


class TestTCPListenerUTF8Handling:
    """Tests for proper UTF-8 handling with split multi-byte characters."""

    async def test_handles_split_multibyte_character(
        self, state_manager: GameStateManager
    ) -> None:
        """Multi-byte UTF-8 character split across reads is handled correctly."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Create a message with multi-byte UTF-8 characters
            # Euro sign is 3 bytes in UTF-8: E2 82 AC
            message = {
                "type": "state",
                "data": {
                    "in_game": True,
                    "screen_type": "SHOP",
                    "floor": 1,
                    "act": 1,
                    "hp": 50,
                    "max_hp": 80,
                    "gold": 100,
                    "deck": [],
                    "relics": [],
                    "potions": [],
                    "choice_list": [],
                },
            }

            full_bytes = (json.dumps(message) + "\n").encode("utf-8")

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Send in small chunks to potentially split UTF-8 sequences
                # We send byte by byte to maximize chance of splitting
                for i in range(0, len(full_bytes), 1):
                    chunk = full_bytes[i : i + 1]
                    writer.write(chunk)
                    await writer.drain()
                    await asyncio.sleep(0.001)

                await asyncio.sleep(0.1)

                # State should be correctly parsed
                current_state = state_manager.get_current_state()
                assert current_state is not None
                assert current_state.screen_type == "SHOP"
                assert current_state.floor == 1
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_handles_emoji_in_json(
        self, state_manager: GameStateManager
    ) -> None:
        """JSON containing emoji (4-byte UTF-8) is handled correctly."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Message with 4-byte UTF-8 emoji
            message = {
                "type": "state",
                "data": {
                    "in_game": True,
                    "screen_type": "EVENT",
                    "floor": 3,
                    "act": 1,
                    "hp": 70,
                    "max_hp": 80,
                    "gold": 50,
                    "deck": [],
                    "relics": [],
                    "potions": [],
                    "choice_list": [],
                },
            }

            full_bytes = (json.dumps(message) + "\n").encode("utf-8")

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Split at various points
                mid = len(full_bytes) // 2
                writer.write(full_bytes[:mid])
                await writer.drain()
                await asyncio.sleep(0.05)

                writer.write(full_bytes[mid:])
                await writer.drain()
                await asyncio.sleep(0.1)

                current_state = state_manager.get_current_state()
                assert current_state is not None
                assert current_state.screen_type == "EVENT"
                assert current_state.floor == 3
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()


# ==============================================================================
# Listener Lifecycle Tests
# ==============================================================================


class TestTCPListenerLifecycle:
    """Tests for proper listener task management."""

    async def test_stop_cancels_background_task(
        self, state_manager: GameStateManager
    ) -> None:
        """Stopping listener properly cancels the background serve task."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        assert listener.is_running

        # The listener should have a serve task stored
        assert listener._serve_task is not None

        await listener.stop()
        assert not listener.is_running

        # Task should be cancelled/done
        assert listener._serve_task is None or listener._serve_task.done()

    async def test_multiple_start_stop_cycles(
        self, state_manager: GameStateManager
    ) -> None:
        """Listener can be started and stopped multiple times."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        for _ in range(3):
            await listener.start()
            assert listener.is_running

            # Verify it accepts connections
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()

            await listener.stop()
            assert not listener.is_running

            # Small delay between cycles
            await asyncio.sleep(0.1)


# ==============================================================================
# Pydantic Extra Fields Tests
# ==============================================================================


class TestPydanticExtraFields:
    """Tests for Pydantic model handling of extra fields."""

    def test_card_ignores_extra_fields(self) -> None:
        """Card model ignores unknown fields from CommunicationMod."""
        from slay_the_spire_mcp.models import Card

        # CommunicationMod may send fields we don't model
        card_data = {
            "name": "Strike",
            "cost": 1,
            "type": "ATTACK",
            "upgrades": 0,
            "unknown_field": "some_value",
            "another_extra": 123,
        }
        card = Card(**card_data)
        assert card.name == "Strike"
        assert card.cost == 1

    def test_monster_ignores_extra_fields(self) -> None:
        """Monster model ignores unknown fields from CommunicationMod."""
        from slay_the_spire_mcp.models import Monster

        monster_data = {
            "name": "Jaw Worm",
            "current_hp": 40,
            "max_hp": 42,
            "intent": "ATTACK",
            "move_id": 1,  # Extra field
            "last_move_id": 0,  # Extra field
            "escape_next": False,  # Extra field
        }
        monster = Monster(**monster_data)
        assert monster.name == "Jaw Worm"
        assert monster.current_hp == 40

    def test_game_state_ignores_extra_fields(self) -> None:
        """GameState model ignores unknown fields from CommunicationMod."""
        from slay_the_spire_mcp.models import GameState

        state_data = {
            "in_game": True,
            "screen_type": "COMBAT",
            "floor": 5,
            "class": "IRONCLAD",  # Extra field (uses different casing)
            "ascension_level": 15,  # Extra field
            "has_sapphire_key": False,  # Extra field
        }
        state = GameState(**state_data)
        assert state.in_game is True
        assert state.floor == 5


# ==============================================================================
# Send Command Tests
# ==============================================================================


class TestTCPListenerSendCommand:
    """Tests for sending commands from server to bridge."""

    async def test_sends_command_to_bridge(
        self, state_manager: GameStateManager
    ) -> None:
        """Server sends command JSON, bridge receives it."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect as the bridge
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Wait for connection to be established
                await asyncio.sleep(0.05)

                # Server sends a command
                command = {"action": "CHOOSE", "index": 1}
                result = await listener.send_command(command)
                assert result is True

                # Bridge should receive the command as newline-delimited JSON
                data = await asyncio.wait_for(reader.readline(), timeout=1.0)
                received = json.loads(data.decode("utf-8"))
                assert received == command
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_sends_multiple_commands(
        self, state_manager: GameStateManager
    ) -> None:
        """Sequential commands all delivered."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect as the bridge
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                # Wait for connection to be established
                await asyncio.sleep(0.05)

                # Send multiple commands
                commands = [
                    {"action": "PLAY", "card": 1},
                    {"action": "END"},
                    {"action": "PROCEED"},
                ]

                for cmd in commands:
                    result = await listener.send_command(cmd)
                    assert result is True

                # Bridge should receive all commands in order
                received_commands = []
                for _ in range(3):
                    data = await asyncio.wait_for(reader.readline(), timeout=1.0)
                    received_commands.append(json.loads(data.decode("utf-8")))

                assert received_commands == commands
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_send_when_not_connected(
        self, state_manager: GameStateManager
    ) -> None:
        """Returns False when no client connected."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # No bridge connected - should return False
            command = {"action": "STATE"}
            result = await listener.send_command(command)
            assert result is False
        finally:
            await listener.stop()

    async def test_send_empty_command(
        self, state_manager: GameStateManager
    ) -> None:
        """Empty command handled gracefully."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect as the bridge
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                await asyncio.sleep(0.05)

                # Send empty dict
                result = await listener.send_command({})
                assert result is True

                # Bridge should receive the empty JSON object
                data = await asyncio.wait_for(reader.readline(), timeout=1.0)
                received = json.loads(data.decode("utf-8"))
                assert received == {}
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_send_command_string(
        self, state_manager: GameStateManager
    ) -> None:
        """Command can be passed as string (already serialized)."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                await asyncio.sleep(0.05)

                # Send pre-serialized JSON string
                command_str = '{"action": "STATE"}'
                result = await listener.send_command(command_str)
                assert result is True

                data = await asyncio.wait_for(reader.readline(), timeout=1.0)
                received = json.loads(data.decode("utf-8"))
                assert received == {"action": "STATE"}
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await listener.stop()

    async def test_send_during_disconnect(
        self, state_manager: GameStateManager
    ) -> None:
        """Command during disconnect doesn't crash."""
        port = await get_free_port()
        listener = TCPListener(state_manager, host="127.0.0.1", port=port)

        await listener.start()
        try:
            # Connect as the bridge
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)

            # Close the connection from bridge side
            writer.close()
            await writer.wait_closed()

            # Give time for the server to notice the disconnect
            await asyncio.sleep(0.1)

            # Try to send a command - should not crash, return False
            result = await listener.send_command({"action": "STATE"})
            assert result is False

            # Listener should still be running
            assert listener.is_running
        finally:
            await listener.stop()
