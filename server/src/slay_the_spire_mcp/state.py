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
import time
from collections.abc import Callable
from typing import Any

from slay_the_spire_mcp.models import (
    FloorHistory,
    GameState,
    parse_game_state_from_message,
)

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
        self._floor_history: list[FloorHistory] = []
        # Staleness tracking
        self._last_state_time: float | None = None
        self._bridge_connected: bool = False

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

    def get_floor_history(self) -> list[FloorHistory]:
        """Get the history of visited nodes in the current run.

        Returns:
            A copy of the floor history list.
        """
        return self._floor_history.copy()

    async def update_state(self, new_state: GameState) -> None:
        """Update the current game state.

        Args:
            new_state: The new game state to set
        """
        async with self._lock:
            self._previous_state = self._current_state
            self._current_state = new_state
            self._last_state_time = time.monotonic()
            # Track floor transitions
            self._track_floor_transition_sync(new_state)

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
        self._last_state_time = time.monotonic()

        # Track floor transitions
        self._track_floor_transition_sync(new_state)

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

    def set_bridge_connected(self, connected: bool) -> None:
        """Update bridge connection status.

        Args:
            connected: True if bridge is connected, False otherwise
        """
        self._bridge_connected = connected
        if not connected:
            logger.info("Bridge disconnected - state may become stale")

    def get_state_age_seconds(self) -> float | None:
        """Get seconds since last state update.

        Returns:
            Seconds since last state update, or None if never updated.
        """
        if self._last_state_time is None:
            return None
        return time.monotonic() - self._last_state_time

    def is_state_stale(self, threshold_seconds: float = 30.0) -> bool:
        """Check if state is likely stale.

        State is considered stale if:
        - Bridge is not connected AND
        - Last update was more than threshold_seconds ago

        Args:
            threshold_seconds: How old state must be to be considered stale.
                Default is 30 seconds.

        Returns:
            True if state is stale, False otherwise.
        """
        if self._bridge_connected:
            return False
        age = self.get_state_age_seconds()
        return age is not None and age > threshold_seconds

    def _track_floor_transition_sync(self, new_state: GameState) -> None:
        """Track floor transitions and record visited nodes.

        Args:
            new_state: The new game state
        """
        # If this is a new run (floor resets to 0 or 1), clear history
        if (
            new_state.floor <= 1
            and self._previous_state
            and self._previous_state.floor > new_state.floor
        ):
            self._floor_history.clear()

        # If floor increased, record the previous floor's node
        if self._previous_state and new_state.floor > self._previous_state.floor:
            # Try to get node symbol from previous state
            symbol = self._extract_node_symbol(self._previous_state)
            # Use "?" as fallback for unknown node types
            if not symbol:
                symbol = "?"
            entry = FloorHistory(
                floor=self._previous_state.floor,
                symbol=symbol,
                details=None,  # Can be enhanced later
            )
            self._floor_history.append(entry)

    def _extract_node_symbol(self, state: GameState) -> str | None:
        """Extract the node symbol from game state.

        Tries multiple approaches:
        1. If map data exists with current_node, look up the symbol
        2. If screen_state has current_node, use that
        3. Infer from screen_type/room_type

        Args:
            state: The game state to extract symbol from

        Returns:
            The node symbol, or None if it cannot be determined
        """
        # Try to get from map data with current_node
        if state.map and state.current_node:
            x, y = state.current_node
            for row in state.map:
                for node in row:
                    if node.x == x and node.y == y:
                        return node.symbol

        # Try to get from screen_state
        if isinstance(state.screen_state, dict):
            current_node_data = state.screen_state.get("current_node")
            if isinstance(current_node_data, dict):
                symbol = current_node_data.get("symbol")
                if isinstance(symbol, str):
                    return symbol

        # Fallback: infer from screen_type or room_type
        # This is less reliable but better than nothing
        screen_state_dict = (
            state.screen_state if isinstance(state.screen_state, dict) else {}
        )
        room_type = screen_state_dict.get("room_type", "")
        screen_type_str = str(state.screen_type).upper()
        room_type_upper = room_type.upper()

        if "MONSTER" in room_type_upper or "COMBAT" in screen_type_str:
            return "M"
        elif "ELITE" in room_type_upper:
            return "E"
        elif "EVENT" in room_type_upper or "EVENT" in screen_type_str:
            return "?"
        elif "REST" in room_type_upper or "REST" in screen_type_str:
            return "R"
        elif "SHOP" in room_type_upper or "SHOP" in screen_type_str:
            return "$"
        elif "TREASURE" in room_type_upper or "TREASURE" in screen_type_str:
            return "T"

        return None

    def clear_state(self) -> None:
        """Clear the current state and floor history."""
        self._current_state = None
        self._previous_state = None
        self._floor_history.clear()


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

        # Try to clean up stale processes if port is in use
        from slay_the_spire_mcp.startup import cleanup_stale_port

        if not cleanup_stale_port(self._host, self._port):
            logger.warning(
                f"Port {self._port} may still be in use after cleanup attempt"
            )

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

        # Mark bridge as connected
        self._state_manager.set_bridge_connected(True)

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
            # Mark bridge as disconnected
            self._state_manager.set_bridge_connected(False)
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
