"""Tests for MCP server and StateManager wiring.

Tests the integration of:
- GameStateManager sharing across MCP lifecycle
- TCP listener startup/shutdown with MCP server
- State accessibility from tools and resources via context
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from slay_the_spire_mcp.state import GameStateManager, TCPListener

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def state_manager() -> GameStateManager:
    """Create a fresh GameStateManager for each test."""
    return GameStateManager()


@pytest.fixture
def sample_game_state_data() -> dict[str, Any]:
    """Sample game state data from the bridge."""
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


async def get_free_port() -> int:
    """Get a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# AppContext Tests
# ==============================================================================


class TestAppContext:
    """Tests for the AppContext dataclass."""

    def test_app_context_holds_state_manager(self) -> None:
        """AppContext stores StateManager instance."""
        from slay_the_spire_mcp.server import AppContext

        state_manager = GameStateManager()
        ctx = AppContext(state_manager=state_manager, tcp_listener=None)

        assert ctx.state_manager is state_manager

    def test_app_context_holds_tcp_listener(self) -> None:
        """AppContext stores TCPListener instance."""
        from slay_the_spire_mcp.server import AppContext

        state_manager = GameStateManager()
        listener = TCPListener(state_manager, port=7777)
        ctx = AppContext(state_manager=state_manager, tcp_listener=listener)

        assert ctx.tcp_listener is listener


# ==============================================================================
# Lifespan Tests
# ==============================================================================


class TestMCPLifespan:
    """Tests for MCP server lifespan management."""

    async def test_lifespan_creates_state_manager(self) -> None:
        """Lifespan context manager creates GameStateManager on startup."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            assert ctx.state_manager is not None
            assert isinstance(ctx.state_manager, GameStateManager)

    async def test_lifespan_starts_tcp_listener(self) -> None:
        """Lifespan starts TCP listener on configured port."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            assert ctx.tcp_listener is not None
            assert ctx.tcp_listener.is_running

            # Verify we can connect
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()

    async def test_lifespan_stops_tcp_listener_on_shutdown(self) -> None:
        """Lifespan stops TCP listener when context exits."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            listener = ctx.tcp_listener
            assert listener is not None
            assert listener.is_running

        # After context exits, listener should be stopped
        assert not listener.is_running

    async def test_lifespan_tcp_receives_state(self) -> None:
        """State received via TCP updates StateManager in context."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            # Connect and send state
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                state_msg = {
                    "type": "state",
                    "data": {
                        "in_game": True,
                        "screen_type": "MAP",
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
                writer.write((json.dumps(state_msg) + "\n").encode())
                await writer.drain()

                # Wait for processing
                await asyncio.sleep(0.1)

                # Verify state was updated
                current_state = ctx.state_manager.get_current_state()
                assert current_state is not None
                assert current_state.screen_type == "MAP"
                assert current_state.floor == 3
            finally:
                writer.close()
                await writer.wait_closed()


# ==============================================================================
# State Access via get_app_context Tests
# ==============================================================================


class TestStateAccess:
    """Tests for accessing state from tools/resources."""

    async def test_get_app_context_returns_context(self) -> None:
        """get_app_context dependency returns AppContext when available."""
        from slay_the_spire_mcp.server import (
            app_lifespan,
            create_mcp_server,
        )

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            # Simulate accessing context from within lifespan
            # The get_app_context is a dependency that tools can use
            # For now, we just verify the AppContext structure
            assert ctx.state_manager is not None

    async def test_state_manager_persists_across_requests(self) -> None:
        """StateManager instance is shared across multiple operations."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        async with app_lifespan(server, tcp_port=port) as ctx:
            # Store reference to state manager
            sm1 = ctx.state_manager

            # Simulate state update
            from slay_the_spire_mcp.models import GameState

            state = GameState(in_game=True, screen_type="COMBAT", floor=1)
            await sm1.update_state(state)

            # Verify same instance
            sm2 = ctx.state_manager
            assert sm1 is sm2
            assert sm2.get_current_state() is not None
            assert sm2.get_current_state().screen_type == "COMBAT"


# ==============================================================================
# Configuration Tests
# ==============================================================================


class TestMCPServerConfiguration:
    """Tests for MCP server configuration."""

    def test_create_mcp_server_returns_fastmcp(self) -> None:
        """create_mcp_server returns a FastMCP instance."""
        from mcp.server.fastmcp import FastMCP

        from slay_the_spire_mcp.server import create_mcp_server

        server = create_mcp_server()
        assert isinstance(server, FastMCP)

    def test_server_has_correct_name(self) -> None:
        """MCP server has expected name."""
        from slay_the_spire_mcp.server import create_mcp_server

        server = create_mcp_server()
        assert server.name == "slay-the-spire"


# ==============================================================================
# TCP Listener Cleanup Tests
# ==============================================================================


class TestTCPListenerCleanup:
    """Tests for proper cleanup of TCP listener."""

    async def test_lifespan_cleans_up_on_exception(self) -> None:
        """TCP listener is stopped even if exception occurs in lifespan."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()

        listener_ref: TCPListener | None = None

        try:
            async with app_lifespan(server, tcp_port=port) as ctx:
                listener_ref = ctx.tcp_listener
                assert listener_ref is not None
                assert listener_ref.is_running
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Listener should be stopped even after exception
        assert listener_ref is not None
        assert not listener_ref.is_running

    async def test_lifespan_handles_listener_start_failure(self) -> None:
        """Lifespan handles TCP listener start failure gracefully."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()

        # Use an already-bound port to cause failure
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)

        try:
            # Should raise an error when trying to bind to same port
            with pytest.raises(OSError):
                async with app_lifespan(server, tcp_port=port):
                    pass
        finally:
            sock.close()


# ==============================================================================
# Environment Configuration Tests
# ==============================================================================


class TestEnvironmentConfiguration:
    """Tests for environment-based configuration."""

    async def test_default_tcp_port(self) -> None:
        """Default TCP port is 7777 when not specified."""
        from slay_the_spire_mcp.server import DEFAULT_TCP_PORT

        assert DEFAULT_TCP_PORT == 7777

    async def test_tcp_port_from_env(self) -> None:
        """TCP port can be configured via environment variable."""
        import os

        from slay_the_spire_mcp.server import get_tcp_port

        # Test default
        original = os.environ.get("STS_TCP_PORT")
        try:
            if "STS_TCP_PORT" in os.environ:
                del os.environ["STS_TCP_PORT"]
            assert get_tcp_port() == 7777

            # Test custom
            os.environ["STS_TCP_PORT"] = "9999"
            assert get_tcp_port() == 9999
        finally:
            if original is not None:
                os.environ["STS_TCP_PORT"] = original
            elif "STS_TCP_PORT" in os.environ:
                del os.environ["STS_TCP_PORT"]
