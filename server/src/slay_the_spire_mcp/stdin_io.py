"""Stdin/stdout I/O for direct CommunicationMod connection.

This module provides the StdinListener class for running the MCP server
in unified mode, where game state is read from stdin and commands are
written to stdout. This eliminates the need for the separate bridge process.

Usage:
    When CommunicationMod spawns the MCP server directly:
    1. Server sends "ready\\n" to stdout (CommunicationMod protocol)
    2. Server reads JSON game state from stdin
    3. Server writes JSON commands to stdout
    4. MCP clients connect via HTTP (NOT stdio - stdout is for game I/O)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import threading
from collections.abc import Callable
from typing import Any, Protocol, TextIO

from slay_the_spire_mcp.models import parse_game_state_from_message
from slay_the_spire_mcp.state import GameStateManager

logger = logging.getLogger(__name__)

# Protocol message for CommunicationMod handshake
READY_MESSAGE = "ready\n"

# EOF retry configuration
DEFAULT_STDIN_EOF_RETRY_DELAY = 0.5
DEFAULT_MAX_STDIN_EOF_RETRIES = 5


class GameListener(Protocol):
    """Protocol for game I/O listeners (TCP or Stdin).

    This protocol defines the interface that both TCPListener and StdinListener
    implement, allowing them to be used interchangeably in the MCP tools.
    """

    @property
    def is_running(self) -> bool:
        """Check if the listener is running."""
        ...

    async def start(self) -> None:
        """Start the listener."""
        ...

    async def stop(self) -> None:
        """Stop the listener."""
        ...

    async def send_command(self, command: dict[str, Any] | str) -> bool:
        """Send a command to the game.

        Args:
            command: Command to send - either a dict (JSON serialized) or string

        Returns:
            True if sent successfully, False otherwise
        """
        ...


class ThreadedStdinReader:
    """Windows-compatible async stdin reader using a background thread.

    On Windows, asyncio's ProactorEventLoop (the default since Python 3.8)
    doesn't support `loop.connect_read_pipe()` for stdin. This class works
    around that limitation by using a daemon thread that performs blocking
    reads from stdin and puts lines into an asyncio-compatible queue.

    The reader can be restarted after EOF or crashes to retry stdin reading.

    Copied from bridge/src/spire_bridge/relay.py with minor adaptations.
    """

    def __init__(self) -> None:
        """Initialize the threaded stdin reader."""
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._is_running = False

    def _reader_thread(self) -> None:
        """Background thread that reads from stdin and puts lines in queue.

        This runs in a separate thread and performs blocking stdin reads.
        Each line is put into the asyncio queue in a thread-safe manner.
        """
        self._is_running = True
        try:
            while True:
                # Use stdin.buffer for binary reads (consistent with StreamReader)
                line = sys.stdin.buffer.readline()
                if not line:
                    # EOF - put empty bytes to signal end
                    logger.info("ThreadedStdinReader: stdin EOF received")
                    break
                # Schedule the put on the event loop (thread-safe)
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, line)
        except Exception as e:
            # Log the actual error - silent failures are unacceptable!
            logger.error(
                "ThreadedStdinReader crashed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
        finally:
            self._is_running = False
            # Signal EOF by putting empty bytes
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, b"")

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the background reader thread.

        Args:
            loop: The asyncio event loop to use for queue operations
        """
        self._loop = loop
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        """Check if the reader thread is currently running.

        Returns:
            True if the thread is active and reading, False otherwise
        """
        return self._is_running

    def restart(self) -> None:
        """Restart the reader thread after EOF or crash.

        Creates a new thread to retry stdin reading. The old thread
        should have already exited (checked via is_running()).
        """
        if self._is_running:
            logger.warning("Cannot restart ThreadedStdinReader while still running")
            return

        if self._loop is None:
            logger.error("Cannot restart ThreadedStdinReader without event loop")
            return

        logger.info("Restarting ThreadedStdinReader")
        # Create a fresh queue to avoid returning stale EOF markers or data
        self._queue = asyncio.Queue()
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()

    async def readline(self) -> bytes:
        """Read a line from stdin asynchronously.

        Returns:
            The next line from stdin as bytes, or empty bytes on EOF.
        """
        return await self._queue.get()


class StdinListener:
    """Listener that reads game state from stdin and writes commands to stdout.

    This replaces TCPListener when running in stdin mode (unified process).
    Implements the same interface as TCPListener for drop-in replacement.

    Attributes:
        state_manager: GameStateManager to update with received states
        stdout: The stdout stream to write commands to
        on_start: Optional callback to invoke after sending "ready"
    """

    def __init__(
        self,
        state_manager: GameStateManager,
        stdout: TextIO | None = None,
        on_start: Callable[[], None] | None = None,
        stdin_eof_retry_delay: float = DEFAULT_STDIN_EOF_RETRY_DELAY,
        max_stdin_eof_retries: int = DEFAULT_MAX_STDIN_EOF_RETRIES,
    ) -> None:
        """Initialize the stdin listener.

        Args:
            state_manager: GameStateManager to update with received states
            stdout: The stdout stream to write to (defaults to sys.stdout)
            on_start: Optional callback invoked after sending "ready"
            stdin_eof_retry_delay: Seconds to wait between stdin EOF retries
            max_stdin_eof_retries: Maximum number of stdin EOF retry attempts
        """
        self._state_manager = state_manager
        self._stdout = stdout if stdout is not None else sys.stdout
        self._on_start = on_start
        self._stdin_eof_retry_delay = stdin_eof_retry_delay
        self._max_stdin_eof_retries = max_stdin_eof_retries
        self._running = False
        self._stdin_task: asyncio.Task[None] | None = None
        self._stdin_reader: ThreadedStdinReader | None = None

    @property
    def is_running(self) -> bool:
        """Check if the listener is running."""
        return self._running

    async def start(self) -> None:
        """Start listening on stdin. Sends 'ready\\n' to stdout."""
        if self._running:
            return

        # Send ready message (CommunicationMod protocol)
        self._stdout.write(READY_MESSAGE)
        self._stdout.flush()
        logger.info("Sent 'ready' to stdout")

        if self._on_start:
            self._on_start()

        self._running = True
        self._state_manager.set_bridge_connected(True)

        # Start stdin reading task
        self._stdin_task = asyncio.create_task(self._read_stdin_loop())
        logger.info("StdinListener started")

    async def stop(self) -> None:
        """Stop the stdin listener."""
        if not self._running:
            return

        self._running = False
        self._state_manager.set_bridge_connected(False)

        if self._stdin_task:
            self._stdin_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stdin_task
            self._stdin_task = None

        logger.info("StdinListener stopped")

    async def send_command(self, command: dict[str, Any] | str) -> bool:
        """Write a command to stdout.

        Commands are JSON-serialized and newline-delimited.

        Args:
            command: Command to send - either a dict (JSON serialized) or string

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._running:
            logger.debug("Cannot send command: not running")
            return False

        json_str = json.dumps(command) if isinstance(command, dict) else command
        if not json_str.endswith("\n"):
            json_str += "\n"

        try:
            self._stdout.write(json_str)
            self._stdout.flush()
            logger.debug(f"Sent command to stdout: {json_str.strip()}")
            return True
        except OSError as e:
            logger.error(f"Failed to write to stdout: {e}")
            return False

    async def _read_stdin_loop(self) -> None:
        """Main loop reading JSON lines from stdin with EOF retry logic."""
        # Create Windows-compatible stdin reader
        loop = asyncio.get_running_loop()
        if sys.platform == "win32":
            self._stdin_reader = ThreadedStdinReader()
            self._stdin_reader.start(loop)
            reader = self._stdin_reader
        else:
            # Unix/Mac: use connect_read_pipe (more efficient)
            unix_reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(unix_reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            reader = unix_reader  # type: ignore[assignment]

        stdin_eof_retries = 0

        try:
            while self._running:
                line_bytes = await reader.readline()
                if not line_bytes:
                    # EOF on stdin - could be transient or permanent
                    stdin_eof_retries += 1

                    if stdin_eof_retries > self._max_stdin_eof_retries:
                        logger.info(
                            "EOF on stdin persisted after %d retries, shutting down",
                            self._max_stdin_eof_retries,
                        )
                        break

                    logger.warning(
                        "EOF on stdin (attempt %d/%d), retrying after %.1fs",
                        stdin_eof_retries,
                        self._max_stdin_eof_retries,
                        self._stdin_eof_retry_delay,
                    )

                    await asyncio.sleep(self._stdin_eof_retry_delay)

                    # If this is a ThreadedStdinReader, try to restart it
                    if isinstance(reader, ThreadedStdinReader):
                        if not reader.is_running():
                            reader.restart()
                        else:
                            logger.warning(
                                "ThreadedStdinReader still running, cannot restart"
                            )

                    continue

                # Successfully read data - reset retry counter
                stdin_eof_retries = 0

                # Decode and process
                try:
                    line = line_bytes.decode("utf-8").strip()
                except UnicodeDecodeError as e:
                    logger.error(f"UTF-8 decode error: {e}")
                    continue

                if not line:
                    continue

                await self._process_line(line)

        except asyncio.CancelledError:
            logger.info("Stdin read loop cancelled")
        except Exception as e:
            logger.error(f"Error in stdin read loop: {e}", exc_info=True)

    async def _process_line(self, line: str) -> None:
        """Process a single JSON line from stdin.

        Args:
            line: A complete JSON line to parse
        """
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            truncated = line[:200] + "..." if len(line) > 200 else line
            logger.error(f"Invalid JSON: {e.msg}. Line: {truncated}")
            return

        try:
            game_state = parse_game_state_from_message(message)
        except Exception as e:
            logger.error(f"Error parsing game state: {e}", exc_info=True)
            return

        if game_state is not None:
            await self._state_manager.update_state(game_state)
            logger.debug(
                f"State updated: floor={game_state.floor}, screen={game_state.screen_type}"
            )


async def create_stdin_reader() -> ThreadedStdinReader | asyncio.StreamReader:
    """Create an async reader for stdin.

    On Windows, uses a thread-based reader since ProactorEventLoop
    doesn't support connect_read_pipe() for stdin. On other platforms,
    uses the standard asyncio approach.

    Returns:
        An async reader with a readline() method
    """
    if sys.platform == "win32":
        # Windows: use thread-based reader
        reader = ThreadedStdinReader()
        reader.start(asyncio.get_running_loop())
        return reader
    else:
        # Unix/Mac: use connect_read_pipe (more efficient)
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        return reader
