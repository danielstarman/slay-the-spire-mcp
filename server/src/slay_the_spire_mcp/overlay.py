"""Overlay push client.

WebSocket client to push analysis results to the SpireBridge mod overlay.
Connects to the mod's WebSocket server and sends recommendations when
decision points are detected.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from typing import Any

from slay_the_spire_mcp.detection import DecisionType, detect_decision_point
from slay_the_spire_mcp.models import GameState

logger = logging.getLogger(__name__)


class OverlayPusher:
    """WebSocket client to push recommendations to SpireBridge mod overlay.

    This client:
    - Connects to the mod's WebSocket server (default port 7778)
    - Sends recommendations when commentary is generated
    - Clears the overlay when transitioning away from decision points
    - Handles reconnection if the connection is lost
    - Queues messages while disconnected (up to max_queue_size)

    The overlay pusher integrates with CommentaryEngine via callbacks:
    - on_commentary_generated: Called when new analysis is ready
    - on_state_change: Called when game state changes (for clearing overlay)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7778,
        reconnect_delay_ms: int = 2000,
        max_queue_size: int = 5,
        enabled: bool = True,
    ) -> None:
        """Initialize the overlay pusher.

        Args:
            host: Host address for mod WebSocket server
            port: Port for mod WebSocket server (default 7778)
            reconnect_delay_ms: Delay between reconnection attempts (milliseconds)
            max_queue_size: Maximum messages to queue while disconnected
            enabled: Whether overlay pushing is enabled
        """
        self._host = host
        self._port = port
        self._reconnect_delay_ms = reconnect_delay_ms
        self._max_queue_size = max_queue_size
        self._enabled = enabled

        self._websocket: Any = None
        self._connection_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._message_queue: deque[dict[str, Any]] = deque(maxlen=max_queue_size)
        self._connected = False
        self._running = False

    @property
    def is_connected(self) -> bool:
        """Return True if WebSocket is connected."""
        return self._connected and self._websocket is not None

    async def start(self) -> None:
        """Start connection loop (runs in background task)."""
        if not self._enabled:
            logger.info("Overlay pusher disabled, not starting")
            return

        if self._running:
            logger.warning("OverlayPusher already running")
            return

        self._running = True
        self._stop_event = asyncio.Event()
        self._connection_task = asyncio.create_task(self._connection_loop())
        logger.info(
            f"Overlay pusher starting, will connect to ws://{self._host}:{self._port}"
        )

    async def stop(self) -> None:
        """Stop connection loop and close WebSocket."""
        if not self._running:
            return

        self._running = False

        # Signal the connection loop to stop
        if self._stop_event:
            self._stop_event.set()

        # Close the WebSocket if connected
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            self._websocket = None
            self._connected = False

        # Cancel the connection task
        if self._connection_task:
            self._connection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connection_task
            self._connection_task = None

        logger.info("Overlay pusher stopped")

    def on_commentary_generated(
        self, commentary: str, decision_type: DecisionType
    ) -> None:
        """Callback for CommentaryEngine. Transforms and pushes recommendations.

        This is a sync callback that queues the message for async sending.

        Args:
            commentary: The generated commentary text
            decision_type: The type of decision this commentary is for
        """
        if not self._enabled or not self._running:
            return

        message = self._transform_to_overlay_format(commentary, decision_type)

        # Queue the message for async sending
        asyncio.create_task(self._send_recommendations(message))

    def on_state_change(self, state: GameState) -> None:
        """Callback for GameStateManager. Clears overlay on non-decision screens.

        This is a sync callback that triggers async clearing.

        Args:
            state: The new game state
        """
        if not self._enabled or not self._running:
            return

        decision = detect_decision_point(state)
        if decision is None:
            # No decision point - clear the overlay
            asyncio.create_task(self._clear_overlay())

    async def _connection_loop(self) -> None:
        """Background task: maintain connection with reconnection backoff."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets package not installed, overlay pusher disabled")
            return

        while self._running:
            try:
                # Attempt to connect
                uri = f"ws://{self._host}:{self._port}"
                logger.debug(f"Attempting to connect to {uri}")

                self._websocket = await websockets.connect(uri)
                self._connected = True
                logger.info(f"Connected to overlay WebSocket at {uri}")

                # Send any queued messages
                await self._flush_queue()

                # Keep connection alive and handle any incoming messages
                try:
                    async for _ in self._websocket:
                        # We don't expect incoming messages, but this keeps the
                        # connection alive and detects disconnects
                        pass
                except websockets.exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed")
                except Exception as e:
                    logger.warning(f"WebSocket error: {e}")

            except Exception as e:
                logger.debug(f"Failed to connect to overlay WebSocket: {e}")

            finally:
                self._connected = False
                self._websocket = None

            # Check if we should stop before sleeping
            if not self._running:
                break

            # Wait before reconnecting (with early exit on stop)
            delay_seconds = self._reconnect_delay_ms / 1000.0
            try:
                if self._stop_event:
                    # Wait for either the delay or the stop signal
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=delay_seconds,
                    )
                    # If we get here, stop was signaled
                    break
            except asyncio.TimeoutError:
                # Timeout means we should try to reconnect
                pass

    async def _send_recommendations(self, message: dict[str, Any]) -> None:
        """Send recommendations JSON to mod, queue if disconnected.

        Args:
            message: The recommendation message to send
        """
        if not self._enabled:
            return

        if self.is_connected and self._websocket:
            try:
                await self._websocket.send(json.dumps(message))
                logger.debug(
                    f"Sent recommendations: {message.get('recommendedAction', '')[:50]}..."
                )
            except Exception as e:
                logger.warning(f"Failed to send recommendations: {e}")
                # Queue the message for later
                self._message_queue.append(message)
        else:
            # Queue the message for when we reconnect
            self._message_queue.append(message)
            logger.debug(f"Queued message (queue size: {len(self._message_queue)})")

    async def _flush_queue(self) -> None:
        """Send all queued messages."""
        while self._message_queue and self.is_connected and self._websocket:
            message = self._message_queue.popleft()
            try:
                await self._websocket.send(json.dumps(message))
                logger.debug("Sent queued message")
            except Exception as e:
                logger.warning(f"Failed to send queued message: {e}")
                # Put it back at the front
                self._message_queue.appendleft(message)
                break

    async def _clear_overlay(self) -> None:
        """Send empty recommendations to clear the overlay."""
        message = {
            "type": "recommendations",
            "recommendedAction": "",
            "reason": "",
        }
        await self._send_recommendations(message)

    def _transform_to_overlay_format(
        self, commentary: str, decision_type: DecisionType
    ) -> dict[str, Any]:
        """Transform commentary and state into mod's expected JSON format.

        For Phase 1, we extract a simple action recommendation and reason
        from the commentary text. Card scores will be added in Phase 2.

        Args:
            commentary: The generated commentary text
            decision_type: The type of decision

        Returns:
            Dict in the format expected by the mod's OverlayManager
        """
        # For Phase 1: Simple extraction of action and reason
        # The commentary is typically structured with headers and content
        # We'll extract a summary for the recommended action

        # Try to extract a recommendation from the commentary
        recommended_action = ""
        reason = ""

        lines = commentary.strip().split("\n")

        # Look for recommendation-related content
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()

            # Look for lines that start with recommendation-related keywords
            if any(
                kw in line_lower
                for kw in ["recommend", "suggest", "should", "take", "choose", "play"]
            ):
                recommended_action = line.strip()
                # Get the next line(s) as reason if they exist
                if i + 1 < len(lines) and lines[i + 1].strip():
                    reason = lines[i + 1].strip()
                break

        # Fallback: Use the first non-header line as the recommendation
        if not recommended_action:
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    recommended_action = stripped[:200]  # Limit length
                    break

        # If we still don't have anything, use a generic message
        if not recommended_action:
            recommended_action = f"Analysis ready for {decision_type.value}"

        return {
            "type": "recommendations",
            "recommendedAction": recommended_action,
            "reason": reason,
        }
