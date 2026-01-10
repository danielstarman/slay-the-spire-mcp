"""Tests for StdinListener and ThreadedStdinReader.

Tests the stdin/stdout I/O for direct CommunicationMod connection.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slay_the_spire_mcp.state import GameStateManager

if TYPE_CHECKING:
    from slay_the_spire_mcp.stdin_io import StdinListener


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for testing."""
    return GameStateManager()


@pytest.fixture
def mock_stdout() -> io.StringIO:
    """Create a mock stdout for capturing output."""
    return io.StringIO()


@pytest.fixture
def stdin_listener(
    state_manager: GameStateManager, mock_stdout: io.StringIO
) -> "StdinListener":
    """Create a StdinListener with mock stdout."""
    from slay_the_spire_mcp.stdin_io import StdinListener

    return StdinListener(state_manager, stdout=mock_stdout)


# ==============================================================================
# Happy Path Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_stdin_listener_sends_ready_on_start(
    stdin_listener: "StdinListener", mock_stdout: io.StringIO
) -> None:
    """StdinListener should send 'ready\\n' to stdout on start."""
    # Patch stdin reading to prevent actual stdin blocking
    with patch.object(stdin_listener, "_read_stdin_loop", new_callable=AsyncMock):
        await stdin_listener.start()

        # Check that "ready\n" was written to stdout
        output = mock_stdout.getvalue()
        assert output == "ready\n", f"Expected 'ready\\n', got {output!r}"

        # Cleanup
        await stdin_listener.stop()


@pytest.mark.asyncio
async def test_stdin_listener_receives_state(
    state_manager: GameStateManager, mock_stdout: io.StringIO
) -> None:
    """StdinListener should update GameStateManager when receiving valid JSON state."""
    from slay_the_spire_mcp.stdin_io import StdinListener

    listener = StdinListener(state_manager, stdout=mock_stdout)

    # Create a test game state message
    test_state = {
        "game_state": {
            "in_game": True,
            "screen_type": "MAP",
            "floor": 5,
            "act": 1,
            "hp": 70,
            "max_hp": 80,
            "gold": 100,
            "deck": [],
            "relics": [],
            "potions": [],
        },
        "in_game": True,
    }

    # Simulate processing a line
    await listener._process_line(json.dumps(test_state))

    # Verify state was updated
    current_state = state_manager.get_current_state()
    assert current_state is not None
    assert current_state.floor == 5
    assert current_state.screen_type == "MAP"
    assert current_state.hp == 70


@pytest.mark.asyncio
async def test_stdin_listener_sends_command(
    stdin_listener: "StdinListener", mock_stdout: io.StringIO
) -> None:
    """StdinListener should write JSON commands to stdout with newline."""
    # Start the listener (with patched stdin loop)
    with patch.object(stdin_listener, "_read_stdin_loop", new_callable=AsyncMock):
        await stdin_listener.start()

        # Clear the "ready\n" output
        mock_stdout.truncate(0)
        mock_stdout.seek(0)

        # Send a command
        command = {"action": "PLAY", "card_index": 0}
        success = await stdin_listener.send_command(command)

        assert success is True

        # Check output
        output = mock_stdout.getvalue()
        assert output.endswith("\n")
        parsed = json.loads(output.strip())
        assert parsed == command

        await stdin_listener.stop()


@pytest.mark.asyncio
async def test_stdin_listener_sends_string_command(
    stdin_listener: "StdinListener", mock_stdout: io.StringIO
) -> None:
    """StdinListener should accept string commands and add newline if needed."""
    with patch.object(stdin_listener, "_read_stdin_loop", new_callable=AsyncMock):
        await stdin_listener.start()

        mock_stdout.truncate(0)
        mock_stdout.seek(0)

        # Send a string command (already JSON)
        success = await stdin_listener.send_command('{"action":"END"}')

        assert success is True
        output = mock_stdout.getvalue()
        assert output == '{"action":"END"}\n'

        await stdin_listener.stop()


# ==============================================================================
# Edge Cases
# ==============================================================================


@pytest.mark.asyncio
async def test_stdin_listener_double_start(
    stdin_listener: "StdinListener", mock_stdout: io.StringIO
) -> None:
    """Calling start() twice should be idempotent (no error, no double ready)."""
    with patch.object(stdin_listener, "_read_stdin_loop", new_callable=AsyncMock):
        await stdin_listener.start()
        await stdin_listener.start()  # Second call should be no-op

        # Should only have one "ready\n"
        output = mock_stdout.getvalue()
        assert output == "ready\n", f"Expected single 'ready\\n', got {output!r}"

        await stdin_listener.stop()


@pytest.mark.asyncio
async def test_stdin_listener_stop_when_not_running(
    stdin_listener: "StdinListener",
) -> None:
    """Calling stop() when not running should be idempotent (no error)."""
    # Should not raise
    await stdin_listener.stop()
    await stdin_listener.stop()


@pytest.mark.asyncio
async def test_stdin_invalid_json_handled(
    state_manager: GameStateManager, mock_stdout: io.StringIO
) -> None:
    """Invalid JSON on stdin should be logged and not crash."""
    from slay_the_spire_mcp.stdin_io import StdinListener

    listener = StdinListener(state_manager, stdout=mock_stdout)

    # Process invalid JSON - should not raise
    await listener._process_line("not valid json {{{")

    # State should remain None
    assert state_manager.get_current_state() is None


@pytest.mark.asyncio
async def test_stdin_utf8_handling(
    state_manager: GameStateManager, mock_stdout: io.StringIO
) -> None:
    """UTF-8 characters in game state should be parsed correctly."""
    from slay_the_spire_mcp.stdin_io import StdinListener

    listener = StdinListener(state_manager, stdout=mock_stdout)

    # State with UTF-8 characters
    test_state = {
        "game_state": {
            "in_game": True,
            "screen_type": "EVENT",
            "floor": 1,
            "act": 1,
            "hp": 80,
            "max_hp": 80,
            "gold": 99,
            "deck": [{"name": "Strike+"}],  # + character
            "relics": [],
            "potions": [],
        },
        "in_game": True,
    }

    await listener._process_line(json.dumps(test_state))

    current_state = state_manager.get_current_state()
    assert current_state is not None
    assert len(current_state.deck) == 1
    assert current_state.deck[0].name == "Strike+"


# ==============================================================================
# Error Conditions
# ==============================================================================


@pytest.mark.asyncio
async def test_stdin_listener_send_command_when_not_running(
    stdin_listener: "StdinListener",
) -> None:
    """send_command should return False when listener is not running."""
    # Don't start the listener
    success = await stdin_listener.send_command({"action": "END"})
    assert success is False


@pytest.mark.asyncio
async def test_stdin_listener_stdout_write_error(
    state_manager: GameStateManager,
) -> None:
    """send_command should return False and log error on stdout write failure."""
    from slay_the_spire_mcp.stdin_io import StdinListener

    # Create a mock stdout that raises on write
    mock_stdout = MagicMock()
    mock_stdout.write.side_effect = OSError("Broken pipe")

    listener = StdinListener(state_manager, stdout=mock_stdout)

    # Force running state
    listener._running = True

    # Should catch error and return False
    success = await listener.send_command({"action": "END"})
    assert success is False


# ==============================================================================
# Config Validation Tests
# ==============================================================================


def test_stdin_mode_requires_http_transport() -> None:
    """stdin_mode=true with transport=stdio should raise validation error."""
    from pydantic import ValidationError

    from slay_the_spire_mcp.config import Config

    with pytest.raises(ValidationError) as exc_info:
        Config(stdin_mode=True, transport="stdio")

    error = str(exc_info.value)
    assert "stdin_mode" in error.lower() or "transport" in error.lower()


def test_stdin_mode_with_http_transport() -> None:
    """stdin_mode=true with transport=http should be valid."""
    from slay_the_spire_mcp.config import Config

    # Should not raise
    config = Config(stdin_mode=True, transport="http")
    assert config.stdin_mode is True
    assert config.transport == "http"


def test_stdin_mode_defaults_to_false() -> None:
    """stdin_mode should default to False."""
    from slay_the_spire_mcp.config import Config

    config = Config()
    assert config.stdin_mode is False


# ==============================================================================
# GameListener Protocol Tests
# ==============================================================================


def test_stdin_listener_implements_game_listener_protocol() -> None:
    """StdinListener should implement the GameListener protocol."""
    from slay_the_spire_mcp.stdin_io import GameListener, StdinListener

    # Check that StdinListener is structurally compatible with GameListener
    listener = StdinListener(GameStateManager())

    # Verify required protocol members exist
    assert hasattr(listener, "is_running")
    assert hasattr(listener, "start")
    assert hasattr(listener, "stop")
    assert hasattr(listener, "send_command")

    # Verify property returns correct type
    assert isinstance(listener.is_running, bool)


def test_tcp_listener_implements_game_listener_protocol() -> None:
    """TCPListener should be compatible with GameListener protocol."""
    from slay_the_spire_mcp.state import TCPListener

    listener = TCPListener(GameStateManager())

    # Verify required protocol members exist
    assert hasattr(listener, "is_running")
    assert hasattr(listener, "start")
    assert hasattr(listener, "stop")
    assert hasattr(listener, "send_command")

    assert isinstance(listener.is_running, bool)


# ==============================================================================
# ThreadedStdinReader Tests
# ==============================================================================


def test_threaded_stdin_reader_not_running_initially() -> None:
    """ThreadedStdinReader should not be running before start()."""
    from slay_the_spire_mcp.stdin_io import ThreadedStdinReader

    reader = ThreadedStdinReader()
    assert reader.is_running() is False


@pytest.mark.asyncio
async def test_threaded_stdin_reader_readline_returns_bytes() -> None:
    """ThreadedStdinReader.readline() should return bytes."""
    from slay_the_spire_mcp.stdin_io import ThreadedStdinReader

    reader = ThreadedStdinReader()
    loop = asyncio.get_running_loop()

    # Pre-populate the queue for testing
    reader._queue = asyncio.Queue()
    await reader._queue.put(b"test line\n")

    # readline should return the bytes
    result = await reader.readline()
    assert result == b"test line\n"


def test_threaded_stdin_reader_restart_when_running_warns() -> None:
    """Calling restart() while running should log a warning and not restart."""
    from slay_the_spire_mcp.stdin_io import ThreadedStdinReader

    reader = ThreadedStdinReader()
    reader._is_running = True  # Simulate running state

    # restart() should not create a new thread
    reader.restart()

    # Should still show as running (wasn't restarted)
    assert reader._is_running is True
