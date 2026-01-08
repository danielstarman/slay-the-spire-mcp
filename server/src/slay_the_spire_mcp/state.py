"""Game state manager and TCP listener.

Provides:
- GameStateManager: Singleton that maintains the current game state
- TCPListener: Async TCP server that receives state from the bridge process
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

from slay_the_spire_mcp.models import GameState, parse_game_state_from_message

logger = logging.getLogger(__name__)

# Buffer size limits to prevent memory exhaustion
MAX_BUFFER_SIZE = 10 * 1024 * 1024  # 10 MB max buffer
MAX_LINE_LENGTH = 1 * 1024 * 1024  # 1 MB max single line


class GameStateManager:
    """Manages the current game state received from the bridge.

    This class maintains:
    - The current game state
    - The previous state for change detection
    - Callbacks for state change notifications
    """

    def __init__(self) -> None:
        """Initialize the state manager."""
        self._current_state: GameState | None = None
        self._previous_state: GameState | None = None
        self._state_callbacks: list[Callable[[GameState], None]] = []
        self._lock = asyncio.Lock()

    def get_current_state(self) -> GameState | None:
        """Get the current game state.

        Returns:
            The current GameState, or None if no state has been received.
        """
        return self._current_state

    def get_previous_state(self) -> GameState | None:
        """Get the previous game state.

        Returns:
            The previous GameState, or None if only one state received.
        """
        return self._previous_state

    async def update_state(self, new_state: GameState) -> None:
        """Update the current game state.

        Args:
            new_state: The new game state to set
        """
        async with self._lock:
            self._previous_state = self._current_state
            self._current_state = new_state

        # Notify callbacks (outside lock)
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                # Log with callback identity for debugging, but don't crash the state update
                callback_name = getattr(callback, "__name__", repr(callback))
                logger.error(
                    "Error in state callback '%s': %s",
                    callback_name,
                    e,
                    exc_info=True,
                )

    def update_state_sync(self, new_state: GameState) -> None:
        """Synchronously update the current game state.

        Used when not in an async context.

        Args:
            new_state: The new game state to set
        """
        self._previous_state = self._current_state
        self._current_state = new_state

        # Notify callbacks
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                # Log with callback identity for debugging, but don't crash the state update
                callback_name = getattr(callback, "__name__", repr(callback))
                logger.error(
                    "Error in state callback '%s': %s",
                    callback_name,
                    e,
                    exc_info=True,
                )

    def on_state_change(self, callback: Callable[[GameState], None]) -> None:
        """Register a callback for state changes.

        Args:
            callback: Function to call when state changes
        """
        self._state_callbacks.append(callback)

    def clear_state(self) -> None:
        """Clear the current state."""
        self._current_state = None
        self._previous_state = None


class TCPListener:
    """TCP listener that receives game state from the bridge process.

    Listens on a TCP port for connections from the bridge process.
    Expects newline-delimited JSON messages containing game state.
    """

    def __init__(
        self,
        state_manager: GameStateManager,
        host: str = "127.0.0.1",
        port: int = 7777,
    ) -> None:
        """Initialize the TCP listener.

        Args:
            state_manager: GameStateManager to update with received states
            host: Host to bind to (default: 127.0.0.1 for local-only)
            port: Port to listen on (default: 7777)
        """
        self._state_manager = state_manager
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self._running = False
        self._client_writer: asyncio.StreamWriter | None = None
        self._writer_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Check if the listener is running."""
        return self._running

    async def start(self) -> None:
        """Start the TCP listener.

        Creates and starts the asyncio TCP server.
        """
        if self._running:
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._port,
        )
        self._running = True
        logger.info(f"TCP listener started on {self._host}:{self._port}")

        # Start serving in background (don't block) and track the task
        self._serve_task = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        """Background task to serve connections."""
        if self._server is None:
            return
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the TCP listener."""
        if not self._running:
            return

        self._running = False

        # Clear client writer
        async with self._writer_lock:
            self._client_writer = None

        # Cancel the serve task first
        if self._serve_task is not None:
            self._serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._serve_task
            self._serve_task = None

        # Then close the server
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("TCP listener stopped")

    async def send_command(self, command: dict[str, Any] | str) -> bool:
        """Send a command to the connected bridge.

        Args:
            command: Command to send - either a dict (will be JSON serialized)
                    or a string (assumed to be valid JSON)

        Returns:
            True if command was sent successfully, False if no client connected
            or send failed
        """
        async with self._writer_lock:
            if self._client_writer is None:
                logger.debug("Cannot send command: no client connected")
                return False

            # Serialize if needed
            json_str = json.dumps(command) if isinstance(command, dict) else command

            # Ensure newline delimiter
            if not json_str.endswith("\n"):
                json_str += "\n"

            try:
                self._client_writer.write(json_str.encode("utf-8"))
                await self._client_writer.drain()
                logger.debug(f"Sent command to bridge: {json_str.strip()}")
                return True
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"Failed to send command to bridge: {e}")
                self._client_writer = None
                return False

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a connected client.

        Reads newline-delimited JSON messages and updates the state manager.
        Uses byte-level buffering to safely handle UTF-8 multi-byte characters
        that may be split across reads.

        Args:
            reader: Stream reader for incoming data
            writer: Stream writer for sending commands to the bridge
        """
        addr = writer.get_extra_info("peername")
        logger.info(f"Bridge connected from {addr}")

        # Store writer for send_command
        async with self._writer_lock:
            self._client_writer = writer

        # Buffer bytes (not str) to handle UTF-8 correctly
        buffer = bytearray()

        try:
            while self._running:
                # Read data with a timeout to check running flag periodically
                try:
                    data = await asyncio.wait_for(
                        reader.read(4096),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                if not data:
                    # Connection closed
                    logger.info(f"Bridge disconnected from {addr}")
                    break

                # Add to buffer (bytes, not decoded yet)
                buffer.extend(data)

                # Check total buffer size limit
                if len(buffer) > MAX_BUFFER_SIZE:
                    logger.error(
                        f"Buffer size exceeded {MAX_BUFFER_SIZE} bytes, "
                        f"dropping connection from {addr}"
                    )
                    break

                # Process complete lines (split on newline bytes)
                while b"\n" in buffer:
                    newline_pos = buffer.index(b"\n")

                    # Check line length limit before the newline
                    if newline_pos > MAX_LINE_LENGTH:
                        logger.error(
                            f"Line length exceeded {MAX_LINE_LENGTH} bytes, "
                            f"dropping connection from {addr}"
                        )
                        # Clear buffer and close connection
                        buffer.clear()
                        return

                    # Extract the line (bytes up to newline)
                    line_bytes = bytes(buffer[:newline_pos])
                    # Remove processed bytes including newline
                    del buffer[: newline_pos + 1]

                    # Now decode the complete line (safe for UTF-8)
                    try:
                        line = line_bytes.decode("utf-8").strip()
                    except UnicodeDecodeError as e:
                        logger.error(f"UTF-8 decode error from bridge: {e}")
                        continue

                    if not line:
                        # Empty line, skip
                        continue

                    await self._process_line(line)

        except ConnectionResetError:
            logger.warning(f"Connection reset by bridge at {addr}")
        except asyncio.CancelledError:
            logger.info(f"Client handler cancelled for {addr}")
        except OSError as e:
            logger.error(f"I/O error handling bridge connection from {addr}: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error handling bridge connection from {addr}: {e}",
                exc_info=True,
            )
        finally:
            # Clear stored writer on disconnect
            async with self._writer_lock:
                if self._client_writer is writer:
                    self._client_writer = None
            writer.close()
            # Suppress only expected exceptions during close (broken pipe, etc.)
            with contextlib.suppress(OSError, asyncio.CancelledError):
                await writer.wait_closed()

    async def _process_line(self, line: str) -> None:
        """Process a single line of JSON.

        Args:
            line: A complete JSON line to parse
        """
        try:
            message: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as e:
            # Log with enough context to diagnose, truncate very long lines
            truncated = line[:200] + "..." if len(line) > 200 else line
            logger.error(
                f"Invalid JSON from bridge at position {e.pos}: {e.msg}. "
                f"Line (truncated): {truncated}"
            )
            return

        # Parse game state from message
        try:
            game_state = parse_game_state_from_message(message)
        except Exception as e:
            # Catch any unexpected parsing errors to prevent crash
            logger.error(
                f"Error parsing game state from message: {e}. "
                f"Message type: {message.get('type', 'unknown')}",
                exc_info=True,
            )
            return

        if game_state is not None:
            await self._state_manager.update_state(game_state)
            logger.debug(
                f"State updated: floor={game_state.floor}, "
                f"screen={game_state.screen_type}"
            )
        else:
            # Not necessarily an error - could be a non-state message type
            msg_type = message.get("type", message.get("message_type", "unknown"))
            logger.debug(f"Received non-state message type: {msg_type}")
