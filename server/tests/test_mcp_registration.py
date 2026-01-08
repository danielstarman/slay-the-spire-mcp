"""Tests for MCP server tool/resource/prompt registration.

Integration tests that verify tools, resources, and prompts are properly
registered with the FastMCP server and can be called through the MCP protocol.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any, AsyncIterator

import pytest
from mcp.server.fastmcp import FastMCP

from slay_the_spire_mcp.config import Config


# ==============================================================================
# Helper Functions
# ==============================================================================


async def get_free_port() -> int:
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# Tool Registration Tests
# ==============================================================================


class TestToolRegistration:
    """Tests for MCP tool registration."""

    def test_mcp_server_has_tools(self) -> None:
        """MCP server should have tools registered."""
        from slay_the_spire_mcp.server import mcp

        # FastMCP stores registered tools
        tools = mcp._tool_manager._tools
        tool_names = list(tools.keys())

        # Verify expected tools are registered
        expected_tools = [
            "get_game_state",
            "play_card",
            "end_turn",
            "choose",
            "potion",
        ]
        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Tool '{tool_name}' not registered"

    def test_get_game_state_tool_registered(self) -> None:
        """get_game_state tool should be registered with correct metadata."""
        from slay_the_spire_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "get_game_state" in tools

        tool = tools["get_game_state"]
        # Verify it has a description (from docstring)
        assert tool.description is not None
        assert len(tool.description) > 0

    def test_play_card_tool_registered(self) -> None:
        """play_card tool should be registered with correct parameters."""
        from slay_the_spire_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "play_card" in tools

        tool = tools["play_card"]
        # Verify it has parameters defined
        assert tool.parameters is not None

    def test_end_turn_tool_registered(self) -> None:
        """end_turn tool should be registered."""
        from slay_the_spire_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "end_turn" in tools

    def test_choose_tool_registered(self) -> None:
        """choose tool should be registered."""
        from slay_the_spire_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "choose" in tools

    def test_potion_tool_registered(self) -> None:
        """potion tool should be registered."""
        from slay_the_spire_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "potion" in tools


# ==============================================================================
# Resource Registration Tests
# ==============================================================================


class TestResourceRegistration:
    """Tests for MCP resource registration."""

    def test_mcp_server_has_resources(self) -> None:
        """MCP server should have resources registered."""
        from slay_the_spire_mcp.server import mcp

        # FastMCP stores resources with context as templates
        templates = mcp._resource_manager._templates
        template_uris = list(templates.keys())

        # Verify expected resources are registered
        expected_resources = [
            "game://state",
            "game://player",
            "game://combat",
            "game://map",
        ]
        for uri in expected_resources:
            assert uri in template_uris, f"Resource '{uri}' not registered"

    def test_state_resource_registered(self) -> None:
        """game://state resource should be registered."""
        from slay_the_spire_mcp.server import mcp

        templates = mcp._resource_manager._templates
        assert "game://state" in templates

    def test_player_resource_registered(self) -> None:
        """game://player resource should be registered."""
        from slay_the_spire_mcp.server import mcp

        templates = mcp._resource_manager._templates
        assert "game://player" in templates

    def test_combat_resource_registered(self) -> None:
        """game://combat resource should be registered."""
        from slay_the_spire_mcp.server import mcp

        templates = mcp._resource_manager._templates
        assert "game://combat" in templates

    def test_map_resource_registered(self) -> None:
        """game://map resource should be registered."""
        from slay_the_spire_mcp.server import mcp

        templates = mcp._resource_manager._templates
        assert "game://map" in templates


# ==============================================================================
# Prompt Registration Tests
# ==============================================================================


class TestPromptRegistration:
    """Tests for MCP prompt registration."""

    def test_mcp_server_has_prompts(self) -> None:
        """MCP server should have prompts registered."""
        from slay_the_spire_mcp.server import mcp

        # FastMCP stores registered prompts
        prompts = mcp._prompt_manager._prompts
        prompt_names = list(prompts.keys())

        # Verify expected prompts are registered
        expected_prompts = [
            "analyze_combat",
            "evaluate_card_reward",
            "plan_path",
            "evaluate_event",
        ]
        for name in expected_prompts:
            assert name in prompt_names, f"Prompt '{name}' not registered"

    def test_analyze_combat_prompt_registered(self) -> None:
        """analyze_combat prompt should be registered."""
        from slay_the_spire_mcp.server import mcp

        prompts = mcp._prompt_manager._prompts
        assert "analyze_combat" in prompts

    def test_evaluate_card_reward_prompt_registered(self) -> None:
        """evaluate_card_reward prompt should be registered."""
        from slay_the_spire_mcp.server import mcp

        prompts = mcp._prompt_manager._prompts
        assert "evaluate_card_reward" in prompts

    def test_plan_path_prompt_registered(self) -> None:
        """plan_path prompt should be registered."""
        from slay_the_spire_mcp.server import mcp

        prompts = mcp._prompt_manager._prompts
        assert "plan_path" in prompts

    def test_evaluate_event_prompt_registered(self) -> None:
        """evaluate_event prompt should be registered."""
        from slay_the_spire_mcp.server import mcp

        prompts = mcp._prompt_manager._prompts
        assert "evaluate_event" in prompts


# ==============================================================================
# Tool Invocation Tests (via lifespan context)
# ==============================================================================


class TestToolInvocation:
    """Tests for invoking tools with proper context."""

    async def test_get_game_state_with_no_state(self) -> None:
        """get_game_state returns None when no state is available."""
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()
        config = Config(tcp_port=port)

        async with app_lifespan(server, config=config) as ctx:
            # Directly test the underlying function with context
            from slay_the_spire_mcp import tools

            result = await tools.get_game_state(ctx.state_manager, ctx.tcp_listener)
            assert result is None

    async def test_get_game_state_with_state(self) -> None:
        """get_game_state returns state when available."""
        from slay_the_spire_mcp.models import GameState
        from slay_the_spire_mcp.server import app_lifespan, create_mcp_server

        server = create_mcp_server()
        port = await get_free_port()
        config = Config(tcp_port=port)

        async with app_lifespan(server, config=config) as ctx:
            # Set up state
            state = GameState(
                in_game=True,
                screen_type="MAP",
                floor=5,
                hp=70,
                max_hp=80,
                gold=100,
            )
            await ctx.state_manager.update_state(state)

            # Test
            from slay_the_spire_mcp import tools

            result = await tools.get_game_state(ctx.state_manager, ctx.tcp_listener)

            assert result is not None
            assert result["screen_type"] == "MAP"
            assert result["floor"] == 5
            assert result["hp"] == 70


# ==============================================================================
# Resource Invocation Tests
# ==============================================================================


class TestResourceInvocation:
    """Tests for invoking resources with proper context."""

    def test_state_resource_with_no_state(self) -> None:
        """game://state returns None when no state is available."""
        from slay_the_spire_mcp import resources
        from slay_the_spire_mcp.state import GameStateManager

        state_manager = GameStateManager()
        result = resources.get_state_resource(state_manager)
        assert result is None

    def test_state_resource_with_state(self) -> None:
        """game://state returns data when state is available."""
        from slay_the_spire_mcp import resources
        from slay_the_spire_mcp.models import GameState
        from slay_the_spire_mcp.state import GameStateManager

        state_manager = GameStateManager()
        state = GameState(
            in_game=True,
            screen_type="COMBAT",
            floor=3,
            hp=60,
            max_hp=80,
        )
        state_manager.update_state_sync(state)

        result = resources.get_state_resource(state_manager)

        assert result is not None
        assert result["screen_type"] == "COMBAT"
        assert result["floor"] == 3


# ==============================================================================
# Prompt Invocation Tests
# ==============================================================================


class TestPromptInvocation:
    """Tests for invoking prompts."""

    def test_analyze_combat_prompt_generates_text(self) -> None:
        """analyze_combat generates proper prompt text."""
        from slay_the_spire_mcp import prompts
        from slay_the_spire_mcp.models import (
            Card,
            CombatState,
            GameState,
            Monster,
        )

        state = GameState(
            in_game=True,
            screen_type="COMBAT",
            floor=3,
            hp=70,
            max_hp=80,
            combat_state=CombatState(
                turn=1,
                monsters=[Monster(name="Jaw Worm", current_hp=40, max_hp=44)],
                hand=[Card(name="Strike", cost=1, type="ATTACK")],
                energy=3,
                max_energy=3,
            ),
        )

        result = prompts.analyze_combat(state)

        assert isinstance(result, str)
        assert "Jaw Worm" in result
        assert "Strike" in result
        assert "energy" in result.lower()
