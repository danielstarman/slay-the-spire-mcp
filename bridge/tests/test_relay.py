"""Tests for the stdin -> TCP relay bridge.

These tests verify the bridge process correctly:
1. Sends "ready\n" to stdout on startup
2. Connects to MCP server via TCP on localhost:7777
3. Reads JSON lines from stdin and relays them to TCP socket
4. Handles edge cases (empty lines, large payloads)
5. Handles errors gracefully (connection refused, disconnection)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from asyncio import StreamReader, StreamWriter
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from spire_bridge.protocol import DEFAULT_HOST, DEFAULT_PORT
from spire_bridge.relay import Relay

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_stdin() -> AsyncMock:
    """Create a mock async stdin reader."""
    return AsyncMock(spec=StreamReader)


@pytest.fixture
def mock_stdout() -> MagicMock:
    """Create a mock stdout writer."""
    mock = MagicMock()
    mock.write = MagicMock()
    mock.flush = MagicMock()
    return mock


@pytest.fixture
def mock_tcp_writer() -> AsyncMock:
    """Create a mock TCP writer."""
    writer = AsyncMock(spec=StreamWriter)
    writer.write = MagicMock()  # write is sync, drain is async
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = MagicMock(return_value=False)
    return writer


@pytest.fixture
def mock_tcp_reader() -> AsyncMock:
    """Create a mock TCP reader."""
    return AsyncMock(spec=StreamReader)


@pytest.fixture
async def tcp_server() -> AsyncGenerator[tuple[str, int, list[bytes]], None]:
    """Start a real TCP server for integration-style tests."""
    received_messages: list[bytes] = []
    server_ready = asyncio.Event()

    async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
        # Set a larger limit for readline to handle large JSON payloads
        reader._limit = 1024 * 1024  # 1MB limit  # type: ignore[attr-defined]
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                received_messages.append(data)
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    server_ready.set()

    yield addr[0], addr[1], received_messages

    server.close()
    await server.wait_closed()


# =============================================================================
# Happy Path Tests
# =============================================================================


class TestHappyPath:
    """Tests for normal operation."""

    async def test_sends_ready_on_start(self, mock_stdout: MagicMock) -> None:
        """Bridge sends 'ready\\n' to stdout immediately on start."""
        relay = Relay(stdout=mock_stdout)

        # send_ready is called during startup
        relay.send_ready()

        # Verify "ready\n" was written to stdout
        mock_stdout.write.assert_called_once_with("ready\n")
        mock_stdout.flush.assert_called_once()

    async def test_relays_stdin_to_tcp(
        self, tcp_server: tuple[str, int, list[bytes]]
    ) -> None:
        """JSON line from stdin arrives at TCP socket unchanged."""
        host, port, received = tcp_server

        # Create a test JSON message
        test_message = {"type": "state", "data": {"floor": 5, "hp": 65}}
        json_line = json.dumps(test_message) + "\n"

        # Create relay connected to our test server
        relay = Relay(host=host, port=port)

        # Connect to server
        await relay.connect()

        # Send the message
        await relay.send_to_server(json_line)

        # Give the server a moment to receive
        await asyncio.sleep(0.1)

        # Verify the message arrived unchanged
        assert len(received) == 1
        assert received[0].decode("utf-8") == json_line

        await relay.close()


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    async def test_handles_empty_lines(
        self, tcp_server: tuple[str, int, list[bytes]]
    ) -> None:
        """Empty lines from stdin are skipped (not relayed)."""
        host, port, received = tcp_server

        relay = Relay(host=host, port=port)
        await relay.connect()

        # Send empty line - should be skipped
        await relay.send_to_server("")
        await relay.send_to_server("\n")
        await relay.send_to_server("   \n")  # whitespace only

        # Send actual message
        valid_message = '{"type": "test"}\n'
        await relay.send_to_server(valid_message)

        await asyncio.sleep(0.1)

        # Only the valid message should have been sent
        assert len(received) == 1
        assert received[0].decode("utf-8") == valid_message

        await relay.close()

    async def test_handles_large_json(
        self, tcp_server: tuple[str, int, list[bytes]]
    ) -> None:
        """Large JSON payloads (100KB+) relay correctly."""
        host, port, received = tcp_server

        # Create a large JSON payload (100KB+)
        large_data = {
            "type": "state",
            "data": {
                "deck": [{"name": f"Card_{i}", "cost": i % 4, "description": "x" * 50} for i in range(2000)],
                "history": ["event_" + str(i) * 100 for i in range(200)],
            },
        }
        json_line = json.dumps(large_data) + "\n"

        # Verify it's actually over 100KB
        assert len(json_line.encode("utf-8")) > 100_000

        relay = Relay(host=host, port=port)
        await relay.connect()

        await relay.send_to_server(json_line)

        await asyncio.sleep(0.2)  # Give more time for large payload

        # Verify the entire message arrived
        assert len(received) == 1
        received_json = json.loads(received[0].decode("utf-8"))
        assert received_json == large_data

        await relay.close()


# =============================================================================
# Error Condition Tests
# =============================================================================


class TestErrorConditions:
    """Tests for error handling."""

    async def test_handles_connection_refused(self) -> None:
        """If server not running, logs error and exits gracefully."""
        # Try to connect to a port that's definitely not listening
        relay = Relay(host="127.0.0.1", port=59999)

        # Should not raise, but should log error and set connected=False
        connected = await relay.connect()

        assert connected is False
        assert not relay.is_connected

    async def test_reconnects_on_disconnect(
        self, tcp_server: tuple[str, int, list[bytes]]
    ) -> None:
        """If TCP connection drops, attempts reconnection and message is delivered."""
        host, port, received = tcp_server

        relay = Relay(host=host, port=port, reconnect_delay=0.1, max_reconnect_attempts=3)
        await relay.connect()

        assert relay.is_connected

        # Send a message before disconnect to verify baseline
        await relay.send_to_server('{"type": "before_disconnect"}\n')
        await asyncio.sleep(0.1)
        assert len(received) == 1

        # Simulate disconnect by closing the writer
        if relay._writer:
            relay._writer.close()
            await relay._writer.wait_closed()
            relay._writer = None
            relay._reader = None

        assert not relay.is_connected

        # Relay should detect this and try to reconnect
        # Force a send which should trigger reconnect
        result = await relay.send_to_server('{"type": "after_reconnect"}\n')

        # Give time for reconnect attempt
        await asyncio.sleep(0.3)

        # Verify reconnect worked: message was sent successfully and received
        assert result is True, "Send should succeed after reconnection"
        assert relay.is_connected, "Relay should be connected after reconnection"
        assert len(received) == 2, "Message after reconnect should be received"
        assert b"after_reconnect" in received[1]

        await relay.close()

    async def test_last_message_wins_buffer_on_reconnect_failure(self) -> None:
        """Failed sends store the message; latest message wins on retry after reconnect."""
        # Start with no server - connection will fail
        relay = Relay(
            host="127.0.0.1",
            port=59998,  # Port with no server
            reconnect_delay=0.05,
            max_reconnect_attempts=1,  # Fail fast
        )

        # Try to connect - will fail
        connected = await relay.connect()
        assert not connected

        # Send messages while disconnected - they should be buffered (last wins)
        result1 = await relay.send_to_server('{"type": "old_state"}\n')
        result2 = await relay.send_to_server('{"type": "newer_state"}\n')
        result3 = await relay.send_to_server('{"type": "newest_state"}\n')

        # All sends fail
        assert result1 is False
        assert result2 is False
        assert result3 is False

        # Check that only the latest message is buffered
        assert relay._pending_message == '{"type": "newest_state"}\n'

        await relay.close()

    async def test_buffered_message_sent_after_reconnect(
        self, tcp_server: tuple[str, int, list[bytes]]
    ) -> None:
        """Buffered message from failed send is sent after successful reconnect."""
        host, port, received = tcp_server

        relay = Relay(host=host, port=port, reconnect_delay=0.1, max_reconnect_attempts=3)
        await relay.connect()

        # Simulate disconnect
        if relay._writer:
            relay._writer.close()
            await relay._writer.wait_closed()
            relay._writer = None
            relay._reader = None

        # Manually set pending message (simulates failed send during disconnect)
        relay._pending_message = '{"type": "buffered_state"}\n'

        # Now reconnect by sending a new message
        result = await relay.send_to_server('{"type": "new_state"}\n')

        await asyncio.sleep(0.2)

        # Both the buffered and new message should be sent
        assert result is True
        assert len(received) >= 1
        # The buffered message should have been sent first
        messages = [msg.decode("utf-8") for msg in received]
        assert any("buffered_state" in msg for msg in messages), f"Buffered message not found: {messages}"
        assert any("new_state" in msg for msg in messages), f"New message not found: {messages}"

        await relay.close()

    async def test_initial_connection_retry_with_backoff(self) -> None:
        """Initial connection failure retries with exponential backoff."""
        # Start a delayed server that will succeed on the 3rd attempt
        server_ready = asyncio.Event()
        connection_count = 0

        async def delayed_server() -> None:
            nonlocal connection_count
            # Wait a bit before starting the server
            await asyncio.sleep(0.25)

            async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
                nonlocal connection_count
                connection_count += 1
                try:
                    while True:
                        data = await reader.readline()
                        if not data:
                            break
                except asyncio.CancelledError:
                    pass
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = await asyncio.start_server(handle_client, "127.0.0.1", 59997)
            server_ready.set()
            await asyncio.sleep(1)  # Keep server running
            server.close()
            await server.wait_closed()

        server_task = asyncio.create_task(delayed_server())

        try:
            relay = Relay(
                host="127.0.0.1",
                port=59997,
                reconnect_delay=0.1,  # Base delay
                max_reconnect_attempts=5,
            )

            # Initial connect will fail, should retry with backoff
            # We need to test this through run_stdin_relay which has initial retry logic
            start_time = asyncio.get_event_loop().time()
            connected = await relay.connect_with_retry()
            elapsed = asyncio.get_event_loop().time() - start_time

            # Should eventually connect
            assert connected, "Should connect after retries"
            assert relay.is_connected

            # Should have taken some time due to backoff
            assert elapsed >= 0.2, f"Should have waited due to backoff, elapsed: {elapsed}"

            await relay.close()
        finally:
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task

    async def test_initial_connection_gives_up_after_max_attempts(self) -> None:
        """Initial connection gives up after max retry attempts."""
        relay = Relay(
            host="127.0.0.1",
            port=59996,  # Port with no server
            reconnect_delay=0.05,
            max_reconnect_attempts=3,
        )

        # Should fail after max attempts
        connected = await relay.connect_with_retry()

        assert not connected
        assert not relay.is_connected

        await relay.close()


# =============================================================================
# TCP to Stdout Tests
# =============================================================================


class TestTcpToStdout:
    """Tests for TCP to stdout relay (commands from server to mod)."""

    async def test_relays_tcp_to_stdout(self, mock_stdout: MagicMock) -> None:
        """Commands from TCP server are written to stdout."""
        # Create a test server that sends a command after receiving
        received_messages: list[bytes] = []
        command_to_send = '{"command": "PLAY", "card": 1}\n'

        async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
            try:
                # Read any incoming data first
                data = await reader.readline()
                if data:
                    received_messages.append(data)
                    # Send a command back to the relay
                    writer.write(command_to_send.encode("utf-8"))
                    await writer.drain()
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        addr = server.sockets[0].getsockname()
        host, port = addr[0], addr[1]

        try:
            relay = Relay(host=host, port=port, stdout=mock_stdout)
            await relay.connect()

            # Start the TCP to stdout relay task
            tcp_task = asyncio.create_task(relay.run_tcp_to_stdout())

            # Send a message to trigger server response
            await relay.send_to_server('{"type": "state"}\n')

            # Give time for the response to be relayed to stdout
            await asyncio.sleep(0.2)

            # Cancel the tcp relay task
            tcp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tcp_task

            # Verify the command was written to stdout
            # Note: stdout.write is called for ready message and for the command
            calls = [call[0][0] for call in mock_stdout.write.call_args_list]
            assert command_to_send in calls, f"Expected command in stdout writes: {calls}"

            await relay.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_tcp_to_stdout_handles_multiple_commands(
        self, mock_stdout: MagicMock
    ) -> None:
        """Multiple commands from TCP server are all relayed to stdout."""
        commands = [
            '{"command": "PLAY", "card": 1}\n',
            '{"command": "END"}\n',
            '{"command": "CHOOSE", "index": 0}\n',
        ]

        async def handle_client(_reader: StreamReader, writer: StreamWriter) -> None:
            try:
                # Wait a bit then send multiple commands
                await asyncio.sleep(0.05)
                for cmd in commands:
                    writer.write(cmd.encode("utf-8"))
                    await writer.drain()
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        addr = server.sockets[0].getsockname()
        host, port = addr[0], addr[1]

        try:
            relay = Relay(host=host, port=port, stdout=mock_stdout)
            await relay.connect()

            # Start the TCP to stdout relay task
            tcp_task = asyncio.create_task(relay.run_tcp_to_stdout())

            # Wait for commands to be received
            await asyncio.sleep(0.3)

            # Cancel the tcp relay task
            tcp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tcp_task

            # Verify all commands were written to stdout
            calls = [call[0][0] for call in mock_stdout.write.call_args_list]
            for cmd in commands:
                assert cmd in calls, f"Expected {cmd} in stdout writes: {calls}"

            await relay.close()
        finally:
            server.close()
            await server.wait_closed()


# =============================================================================
# Protocol Constants Tests
# =============================================================================


class TestProtocolConstants:
    """Tests for protocol module constants."""

    def test_default_host(self) -> None:
        """Default host is localhost."""
        assert DEFAULT_HOST == "127.0.0.1"

    def test_default_port(self) -> None:
        """Default port is 7777."""
        assert DEFAULT_PORT == 7777


# =============================================================================
# Stdin EOF Retry Tests
# =============================================================================


class TestStdinEOFRetry:
    """Tests for stdin EOF retry logic."""

    async def test_stdin_eof_retries_then_recovers(
        self, tcp_server: tuple[str, int, list[bytes]], mock_stdout: MagicMock
    ) -> None:
        """When stdin returns EOF temporarily, relay retries and recovers."""
        host, port, received = tcp_server

        # Create a mock stdin that returns EOF twice, then data
        mock_stdin = AsyncMock()
        eof_count = 0

        async def mock_readline() -> bytes:
            nonlocal eof_count
            if eof_count < 2:
                eof_count += 1
                return b""  # EOF
            elif eof_count == 2:
                eof_count += 1
                return b'{"type": "recovered"}\n'
            else:
                # Stay alive to allow test to complete
                await asyncio.sleep(10)
                return b""

        mock_stdin.readline = mock_readline

        relay = Relay(
            host=host,
            port=port,
            stdout=mock_stdout,
            stdin_eof_retry_delay=0.1,  # Fast retry for testing
            max_stdin_eof_retries=3,
        )

        # Run relay in background
        relay_task = asyncio.create_task(relay.run_bidirectional(mock_stdin))

        # Wait for recovery and message
        await asyncio.sleep(0.5)

        # Cancel relay
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task

        # Verify the message was received after EOF retries
        assert len(received) >= 1
        assert b"recovered" in received[-1]

    async def test_stdin_eof_gives_up_after_max_retries(
        self, tcp_server: tuple[str, int, list[bytes]], mock_stdout: MagicMock
    ) -> None:
        """When stdin returns EOF persistently, relay gives up after max retries."""
        host, port, received = tcp_server

        # Create a mock stdin that always returns EOF
        mock_stdin = AsyncMock()
        mock_stdin.readline = AsyncMock(return_value=b"")

        relay = Relay(
            host=host,
            port=port,
            stdout=mock_stdout,
            stdin_eof_retry_delay=0.1,  # Fast retry for testing
            max_stdin_eof_retries=2,  # Low limit for faster test
        )

        # Run relay - should exit after retries
        await relay.run_bidirectional(mock_stdin)

        # Verify it tried multiple times (2 retries = 3 total calls)
        # Initial read + 2 retries = 3 calls minimum
        assert mock_stdin.readline.call_count >= 3

    async def test_stdin_eof_resets_counter_on_success(
        self, tcp_server: tuple[str, int, list[bytes]], mock_stdout: MagicMock
    ) -> None:
        """EOF retry counter resets after successful reads."""
        host, port, received = tcp_server

        # Create a mock stdin that alternates: EOF, data, EOF, data
        mock_stdin = AsyncMock()
        call_count = 0

        async def mock_readline() -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count in [1, 3]:
                return b""  # EOF on calls 1 and 3
            elif call_count in [2, 4]:
                return f'{{"type": "msg{call_count}"}}\n'.encode()
            else:
                # Stay alive
                await asyncio.sleep(10)
                return b""

        mock_stdin.readline = mock_readline

        relay = Relay(
            host=host,
            port=port,
            stdout=mock_stdout,
            stdin_eof_retry_delay=0.05,
            max_stdin_eof_retries=1,  # Only 1 retry allowed
        )

        # Run relay in background
        relay_task = asyncio.create_task(relay.run_bidirectional(mock_stdin))

        # Wait for both messages
        await asyncio.sleep(0.3)

        # Cancel relay
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task

        # Both messages should have been received (counter was reset after first success)
        assert len(received) >= 2
        assert b"msg2" in received[0]
        assert b"msg4" in received[1]

    async def test_threaded_stdin_reader_restart(
        self, tcp_server: tuple[str, int, list[bytes]], mock_stdout: MagicMock
    ) -> None:
        """ThreadedStdinReader restart method exists and can be called."""
        from unittest.mock import Mock, patch
        from spire_bridge.relay import ThreadedStdinReader
        import threading

        # Mock stdin to avoid pytest capture issues
        mock_stdin_buffer = Mock()
        mock_stdin_buffer.readline.return_value = b""  # Always EOF

        with patch("sys.stdin") as mock_sys_stdin:
            mock_sys_stdin.buffer = mock_stdin_buffer

            # Create reader
            reader = ThreadedStdinReader()
            loop = asyncio.get_running_loop()

            # Initially not running
            assert not reader.is_running()

            # Start the reader
            reader.start(loop)

            # Thread was created
            assert reader._thread is not None
            original_thread = reader._thread

            # Wait for thread to exit (returns EOF immediately)
            await asyncio.sleep(0.2)
            assert not reader.is_running()

            # Can call restart
            reader.restart()

            # A new thread was created
            assert reader._thread is not None
            assert reader._thread != original_thread  # Different thread object

            # Clean up
            await asyncio.sleep(0.2)

    async def test_stdin_relay_also_has_retry_logic(
        self, tcp_server: tuple[str, int, list[bytes]], mock_stdout: MagicMock
    ) -> None:
        """run_stdin_relay (non-bidirectional) also has EOF retry logic."""
        host, port, received = tcp_server

        # Create a mock stdin that returns EOF once, then data
        mock_stdin = AsyncMock()
        call_count = 0

        async def mock_readline() -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b""  # EOF
            elif call_count == 2:
                return b'{"type": "recovered"}\n'
            else:
                await asyncio.sleep(10)
                return b""

        mock_stdin.readline = mock_readline

        relay = Relay(
            host=host,
            port=port,
            stdout=mock_stdout,
            stdin_eof_retry_delay=0.1,
            max_stdin_eof_retries=2,
        )

        # Run relay in background
        relay_task = asyncio.create_task(relay.run_stdin_relay(mock_stdin))

        # Wait for recovery and message
        await asyncio.sleep(0.3)

        # Cancel relay
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task

        # Verify the message was received after EOF retry
        assert len(received) >= 1
        assert b"recovered" in received[-1]
