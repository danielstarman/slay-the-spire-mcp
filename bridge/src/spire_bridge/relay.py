"""Async relay between stdin/stdout and TCP socket.

Relays game state from mod (stdin) to MCP server (TCP :7777)
and commands from MCP server back to mod (stdout).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import threading
from asyncio import StreamReader, StreamWriter
from typing import Protocol, TextIO

from spire_bridge.protocol import (
    DEFAULT_HOST,
    DEFAULT_MAX_RECONNECT_ATTEMPTS,
    DEFAULT_MAX_STDIN_EOF_RETRIES,
    DEFAULT_PORT,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_STDIN_EOF_RETRY_DELAY,
    READY_MESSAGE,
    is_valid_message,
    normalize_line,
)

logger = logging.getLogger(__name__)


class AsyncLineReader(Protocol):
    """Protocol for async line readers (duck typing for StreamReader)."""

    async def readline(self) -> bytes:
        """Read a line asynchronously."""
        ...


class Relay:
    """Async relay between stdin/stdout and TCP socket.

    The relay:
    1. Sends "ready\\n" to stdout on startup (CommunicationMod protocol)
    2. Connects to MCP server via TCP on localhost:7777
    3. Reads JSON lines from stdin (game state from SpireBridge mod)
    4. Relays each line to the TCP socket
    5. Handles connection errors gracefully with reconnection
    6. Retries on stdin EOF before giving up (handles transient errors)

    Attributes:
        host: The TCP server host to connect to
        port: The TCP server port to connect to
        reconnect_delay: Seconds to wait between reconnect attempts
        max_reconnect_attempts: Maximum number of reconnect attempts
        stdin_eof_retry_delay: Seconds to wait between stdin EOF retries
        max_stdin_eof_retries: Maximum number of stdin EOF retry attempts
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        stdout: TextIO | None = None,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        stdin_eof_retry_delay: float = DEFAULT_STDIN_EOF_RETRY_DELAY,
        max_stdin_eof_retries: int = DEFAULT_MAX_STDIN_EOF_RETRIES,
    ) -> None:
        """Initialize the relay.

        Args:
            host: The TCP server host to connect to
            port: The TCP server port to connect to
            stdout: The stdout stream to write to (defaults to sys.stdout)
            reconnect_delay: Seconds to wait between reconnect attempts
            max_reconnect_attempts: Maximum number of reconnect attempts
            stdin_eof_retry_delay: Seconds to wait between stdin EOF retries
            max_stdin_eof_retries: Maximum number of stdin EOF retry attempts
        """
        self.host = host
        self.port = port
        self._stdout: TextIO = stdout if stdout is not None else sys.stdout
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.stdin_eof_retry_delay = stdin_eof_retry_delay
        self.max_stdin_eof_retries = max_stdin_eof_retries

        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._reconnect_count = 0
        self._pending_message: str | None = None  # Last-message-wins buffer

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to the TCP server."""
        return self._writer is not None and not self._writer.is_closing()

    def send_ready(self) -> None:
        """Send the ready signal to stdout.

        This follows the CommunicationMod protocol - the subprocess
        sends "ready\\n" to stdout to indicate it's ready for input.
        """
        self._stdout.write(READY_MESSAGE)
        self._stdout.flush()

    async def connect(self) -> bool:
        """Connect to the TCP server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            self._reconnect_count = 0
            logger.info("Connected to MCP server at %s:%d", self.host, self.port)
            return True
        except OSError as e:
            logger.error(
                "Failed to connect to MCP server at %s:%d: %s",
                self.host,
                self.port,
                e,
            )
            self._reader = None
            self._writer = None
            return False

    async def connect_with_retry(self) -> bool:
        """Connect to the TCP server with exponential backoff retry.

        Retries connection with exponential backoff up to max_reconnect_attempts.
        Backoff is bounded at 10 seconds.

        Returns:
            True if connection successful, False if all attempts failed
        """
        attempt = 0
        max_backoff = 10.0  # Cap backoff at 10 seconds

        while attempt < self.max_reconnect_attempts:
            if await self.connect():
                return True

            attempt += 1
            if attempt < self.max_reconnect_attempts:
                # Exponential backoff: delay * 2^(attempt-1), bounded
                backoff = min(self.reconnect_delay * (2 ** (attempt - 1)), max_backoff)
                logger.info(
                    "Connection attempt %d/%d failed, retrying in %.2fs",
                    attempt,
                    self.max_reconnect_attempts,
                    backoff,
                )
                await asyncio.sleep(backoff)

        logger.error("Failed to connect after %d attempts", self.max_reconnect_attempts)
        return False

    async def _ensure_connected(self) -> bool:
        """Ensure we're connected, attempting reconnection if needed.

        Returns:
            True if connected (or reconnected), False if unable to connect
        """
        if self.is_connected:
            return True

        # Attempt reconnection
        while self._reconnect_count < self.max_reconnect_attempts:
            self._reconnect_count += 1
            logger.info(
                "Reconnection attempt %d/%d",
                self._reconnect_count,
                self.max_reconnect_attempts,
            )
            await asyncio.sleep(self.reconnect_delay)

            if await self.connect():
                return True

        logger.error(
            "Failed to reconnect after %d attempts", self.max_reconnect_attempts
        )
        return False

    async def _send_raw(self, normalized: str) -> bool:
        """Send a normalized line to the TCP server.

        Args:
            normalized: The normalized line to send (must end with newline)

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if self._writer is None:
                return False

            self._writer.write(normalized.encode("utf-8"))
            await self._writer.drain()
            return True
        except OSError as e:
            logger.error("Failed to send to server: %s", e)
            # Mark as disconnected for next send to trigger reconnect
            if self._writer:
                self._writer.close()
                with contextlib.suppress(OSError):
                    await self._writer.wait_closed()
            self._writer = None
            self._reader = None
            return False

    async def send_to_server(self, line: str) -> bool:
        """Send a line to the TCP server.

        Empty lines and whitespace-only lines are skipped.
        If send fails, the message is stored in a "last message wins" buffer
        and will be retried on the next successful reconnect.

        Args:
            line: The line to send (should be JSON + newline)

        Returns:
            True if sent successfully, False otherwise
        """
        # Skip empty/whitespace lines
        if not is_valid_message(line):
            return True  # Not an error, just skipped

        # Normalize the line (ensure trailing newline)
        normalized = normalize_line(line)
        if not normalized:
            return True

        # Ensure connection
        if not await self._ensure_connected():
            # Store in last-message-wins buffer for retry after reconnect
            self._pending_message = normalized
            logger.warning("Connection failed, buffered message for retry")
            return False

        # Send any pending buffered message first
        if self._pending_message is not None:
            pending = self._pending_message
            self._pending_message = None
            if not await self._send_raw(pending):
                # Failed to send pending, buffer current message instead
                self._pending_message = normalized
                return False

        # Now send the current message
        if not await self._send_raw(normalized):
            # Failed to send, buffer for retry
            self._pending_message = normalized
            return False

        return True

    async def close(self) -> None:
        """Close the TCP connection."""
        if self._writer:
            self._writer.close()
            with contextlib.suppress(OSError):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None
            logger.info("Connection closed")

    async def _handle_stdin_with_retry(self, stdin: AsyncLineReader) -> None:
        """Handle stdin reading with EOF retry logic.

        Reads from stdin in a loop, retrying on EOF up to max_stdin_eof_retries times.
        Resets retry counter on successful reads. Sends received data to TCP server.

        Args:
            stdin: The async stdin stream reader

        Raises:
            StopAsyncIteration: When EOF persists after max retries (signals shutdown)
        """
        stdin_eof_retries = 0

        while True:
            line_bytes = await stdin.readline()
            if not line_bytes:
                # EOF on stdin - could be transient or permanent
                stdin_eof_retries += 1

                if stdin_eof_retries > self.max_stdin_eof_retries:
                    logger.info(
                        "EOF on stdin persisted after %d retries, shutting down",
                        self.max_stdin_eof_retries
                    )
                    raise StopAsyncIteration

                logger.warning(
                    "EOF on stdin (attempt %d/%d), retrying after %.1fs",
                    stdin_eof_retries,
                    self.max_stdin_eof_retries,
                    self.stdin_eof_retry_delay
                )

                # Wait before retry
                await asyncio.sleep(self.stdin_eof_retry_delay)

                # If this is a ThreadedStdinReader, try to restart it
                if isinstance(stdin, ThreadedStdinReader):
                    if not stdin.is_running():
                        stdin.restart()
                    else:
                        logger.warning("ThreadedStdinReader still running, cannot restart")

                # Continue to retry readline
                continue

            # Successfully read data - reset retry counter
            stdin_eof_retries = 0

            line = line_bytes.decode("utf-8")
            await self.send_to_server(line)

    async def run_tcp_to_stdout(self) -> None:
        """Run the TCP to stdout relay.

        Reads lines from the TCP server and writes them to stdout.
        This relays commands from the MCP server back to the mod.
        """
        try:
            while True:
                if self._reader is None:
                    # Not connected, wait a bit and retry
                    await asyncio.sleep(0.1)
                    continue

                try:
                    line_bytes = await self._reader.readline()
                    if not line_bytes:
                        # EOF from server, wait for reconnect
                        logger.info("EOF from TCP server")
                        await asyncio.sleep(0.1)
                        continue

                    line = line_bytes.decode("utf-8")
                    if line.strip():  # Skip empty lines
                        self._stdout.write(line)
                        self._stdout.flush()
                        logger.debug("Relayed command to stdout: %s", line.strip())
                except OSError as e:
                    logger.error("Error reading from TCP server: %s", e)
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("TCP to stdout relay cancelled")

    async def run_stdin_relay(self, stdin: AsyncLineReader) -> None:
        """Run the relay, reading from stdin and forwarding to TCP.

        This is the main relay loop. It reads lines from stdin
        and sends them to the TCP server.

        Args:
            stdin: The async stdin stream reader
        """
        self.send_ready()

        if not await self.connect_with_retry():
            logger.error("Initial connection failed after retries, exiting")
            return

        try:
            await self._handle_stdin_with_retry(stdin)
        except StopAsyncIteration:
            # EOF persisted after retries, exit gracefully
            logger.info("Stdin relay shutting down after exhausting retries")
        except asyncio.CancelledError:
            logger.info("Relay cancelled")
        finally:
            await self.close()

    async def run_bidirectional(self, stdin: AsyncLineReader) -> None:
        """Run bidirectional relay between stdin/stdout and TCP.

        This is the main entry point that runs both:
        - stdin -> TCP (game state from mod to MCP server)
        - TCP -> stdout (commands from MCP server to mod)

        Args:
            stdin: The async stdin stream reader
        """
        self.send_ready()

        if not await self.connect_with_retry():
            logger.error("Initial connection failed after retries, exiting")
            return

        # Start TCP to stdout relay in background
        tcp_to_stdout_task = asyncio.create_task(self.run_tcp_to_stdout())

        try:
            await self._handle_stdin_with_retry(stdin)
        except StopAsyncIteration:
            # EOF persisted after retries, exit gracefully
            logger.info("Bidirectional relay shutting down after exhausting retries")
        except asyncio.CancelledError:
            logger.info("Relay cancelled")
        finally:
            tcp_to_stdout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tcp_to_stdout_task
            await self.close()


class ThreadedStdinReader:
    """Windows-compatible async stdin reader using a background thread.

    On Windows, asyncio's ProactorEventLoop (the default since Python 3.8)
    doesn't support `loop.connect_read_pipe()` for stdin. This class works
    around that limitation by using a daemon thread that performs blocking
    reads from stdin and puts lines into an asyncio-compatible queue.

    The reader can be restarted after EOF or crashes to retry stdin reading.
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


async def create_stdin_reader() -> AsyncLineReader:
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


async def run_relay(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> int:
    """Run the bidirectional stdin/stdout to TCP relay.

    This is the main entry point for running the relay.
    Relays game state from mod (stdin) to MCP server (TCP)
    and commands from MCP server back to mod (stdout).

    Args:
        host: The TCP server host
        port: The TCP server port

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    relay = Relay(host=host, port=port)

    try:
        stdin_reader = await create_stdin_reader()
        await relay.run_bidirectional(stdin_reader)
        return 0
    except asyncio.CancelledError:
        logger.info("Relay cancelled")
        return 0
    except OSError as e:
        logger.error("Relay I/O error: %s", e)
        return 1
    except Exception as e:
        logger.exception("Relay failed with unexpected error: %s", e)
        return 1
