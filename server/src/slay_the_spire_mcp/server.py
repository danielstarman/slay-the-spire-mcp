"""FastMCP server setup.

This module configures and runs the MCP server with Streamable HTTP transport.

Key responsibilities:
- Initialize FastMCP server with lifespan management
- Start TCP listener for bridge connection on configurable port
- Provide shared state context for tools and resources
- Register MCP tools, resources, and prompts

Configuration is managed via the config module. See config.py for details.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from slay_the_spire_mcp import prompts as prompt_impl
from slay_the_spire_mcp import resources as resource_impl
from slay_the_spire_mcp import tools as tool_impl
from slay_the_spire_mcp.config import Config, get_config
from slay_the_spire_mcp.state import GameStateManager, TCPListener

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context shared across MCP server lifecycle.

    This context is created during server startup and available to all
    tools and resources via the lifespan context.

    Attributes:
        state_manager: GameStateManager instance that maintains current game state
        tcp_listener: TCPListener instance for receiving state from bridge (may be None)
        config: Application configuration
    """

    state_manager: GameStateManager
    tcp_listener: TCPListener | None
    config: Config


# Type alias for MCP Context with our AppContext
MCPContext = Context[ServerSession, AppContext]


@asynccontextmanager
async def app_lifespan(
    server: FastMCP,  # noqa: ARG001 - Required by FastMCP lifespan signature
    config: Config | None = None,
) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context.

    This context manager:
    1. Creates a GameStateManager on startup
    2. Starts TCP listener for bridge communication
    3. Yields AppContext for tools/resources to access
    4. Stops TCP listener on shutdown

    Args:
        server: FastMCP server instance (required by lifespan protocol)
        config: Application configuration (default: from get_config())

    Yields:
        AppContext containing state_manager, tcp_listener, and config
    """
    # Use provided config or get from singleton
    cfg = config if config is not None else get_config()

    # Create state manager
    state_manager = GameStateManager()
    logger.info("GameStateManager initialized")

    # Create and start TCP listener
    tcp_listener = TCPListener(state_manager, host=cfg.tcp_host, port=cfg.tcp_port)

    try:
        await tcp_listener.start()
        logger.info(f"TCP listener started on {cfg.tcp_host}:{cfg.tcp_port}")

        yield AppContext(
            state_manager=state_manager,
            tcp_listener=tcp_listener,
            config=cfg,
        )

    finally:
        # Always stop TCP listener on shutdown
        if tcp_listener.is_running:
            await tcp_listener.stop()
            logger.info("TCP listener stopped")


def create_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server.

    Returns:
        Configured FastMCP server instance (without lifespan - use app_lifespan)
    """
    server = FastMCP(name="slay-the-spire")
    return server


def get_app_context() -> AppContext:
    """Dependency for accessing AppContext in tools.

    This is a placeholder that will be properly injected by the MCP framework
    when the server is running. Direct calls outside of tool context will fail.

    Returns:
        AppContext from lifespan

    Raises:
        RuntimeError: If called outside of MCP server context
    """
    # This will be replaced by proper dependency injection
    # when tools are implemented. For now, it's a placeholder.
    raise RuntimeError(
        "get_app_context must be called within MCP server context. "
        "Use Context parameter in tool functions."
    )


# Create server instance for module-level access
mcp = create_mcp_server()


# ==============================================================================
# MCP Tool Registration
# ==============================================================================


@mcp.tool()
async def get_game_state(
    ctx: MCPContext,
) -> str:
    """Get the current game state.

    Returns the full game state including deck, relics, potions, and if in
    combat, the current hand, monsters, and energy.

    Returns:
        JSON string of the current game state, or a message if no state exists.
    """
    app_ctx = ctx.request_context.lifespan_context
    if app_ctx.tcp_listener is None:
        return json.dumps(
            {"status": "error", "message": "TCP listener not initialized"}
        )
    result = await tool_impl.get_game_state(app_ctx.state_manager, app_ctx.tcp_listener)
    if result is None:
        return json.dumps({"status": "no_state", "message": "No game state available"})
    return json.dumps(result)


@mcp.tool()
async def play_card(
    ctx: MCPContext,
    card_index: int,
    target_index: int | None = None,
) -> str:
    """Play a card from hand.

    Plays the card at the specified index in the player's hand. If the card
    requires a target (like Strike), provide the target_index of the monster.

    Args:
        card_index: Index of the card in hand (0-indexed)
        target_index: Index of the target monster (0-indexed), if required

    Returns:
        JSON string with success status and optional error message.
    """
    app_ctx = ctx.request_context.lifespan_context
    if app_ctx.tcp_listener is None:
        return json.dumps({"success": False, "error": "TCP listener not initialized"})
    try:
        result = await tool_impl.play_card(
            app_ctx.state_manager, app_ctx.tcp_listener, card_index, target_index
        )
        return json.dumps(result)
    except tool_impl.ToolError as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def end_turn(
    ctx: MCPContext,
) -> str:
    """End the current turn.

    Ends the player's turn in combat, allowing monsters to act.

    Returns:
        JSON string with success status and optional error message.
    """
    app_ctx = ctx.request_context.lifespan_context
    if app_ctx.tcp_listener is None:
        return json.dumps({"success": False, "error": "TCP listener not initialized"})
    try:
        result = await tool_impl.end_turn(app_ctx.state_manager, app_ctx.tcp_listener)
        return json.dumps(result)
    except tool_impl.ToolError as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def choose(
    ctx: MCPContext,
    choice: int | str,
) -> str:
    """Make a choice.

    Selects an option from a choice screen such as card rewards, event options,
    shop items, etc. Can specify the choice by index or name.

    Args:
        choice: Index of the choice (0-indexed) or name of the choice

    Returns:
        JSON string with success status and optional error message.
    """
    app_ctx = ctx.request_context.lifespan_context
    if app_ctx.tcp_listener is None:
        return json.dumps({"success": False, "error": "TCP listener not initialized"})
    try:
        result = await tool_impl.choose(
            app_ctx.state_manager, app_ctx.tcp_listener, choice
        )
        return json.dumps(result)
    except tool_impl.ToolError as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def potion(
    ctx: MCPContext,
    action: str,
    slot: int,
    target_index: int | None = None,
) -> str:
    """Use or discard a potion.

    Uses or discards the potion at the specified slot. Some potions require
    a target when used (like Fire Potion).

    Args:
        action: Either "use" or "discard"
        slot: Index of the potion slot (0-indexed)
        target_index: Index of the target monster (0-indexed), if required

    Returns:
        JSON string with success status and optional error message.
    """
    app_ctx = ctx.request_context.lifespan_context
    if app_ctx.tcp_listener is None:
        return json.dumps({"success": False, "error": "TCP listener not initialized"})
    try:
        result = await tool_impl.potion(
            app_ctx.state_manager, app_ctx.tcp_listener, action, slot, target_index
        )
        return json.dumps(result)
    except tool_impl.ToolError as e:
        return json.dumps({"success": False, "error": str(e)})


# ==============================================================================
# MCP Resource Registration
# ==============================================================================


@mcp.resource("game://state")
def game_state_resource(
    ctx: MCPContext,
) -> str:
    """Current full game state.

    Returns the complete game state as received from the bridge including
    all player stats, deck, relics, potions, and combat state if in combat.
    """
    app_ctx = ctx.request_context.lifespan_context
    result = resource_impl.get_state_resource(app_ctx.state_manager)
    if result is None:
        return json.dumps({"status": "no_state", "message": "No game state available"})
    return json.dumps(result)


@mcp.resource("game://player")
def game_player_resource(
    ctx: MCPContext,
) -> str:
    """Player stats including HP, gold, deck, and relics.

    Returns player-specific information including current HP, max HP,
    gold, deck contents, relics, and potions.
    """
    app_ctx = ctx.request_context.lifespan_context
    result = resource_impl.get_player_resource(app_ctx.state_manager)
    if result is None:
        return json.dumps({"status": "no_state", "message": "No game state available"})
    return json.dumps(result)


@mcp.resource("game://combat")
def game_combat_resource(
    ctx: MCPContext,
) -> str:
    """Current combat state including monsters, hand, and energy.

    Returns combat-specific information including monster stats and intents,
    current hand, energy, and draw/discard pile information. Returns null
    status if not currently in combat.
    """
    app_ctx = ctx.request_context.lifespan_context
    result = resource_impl.get_combat_resource(app_ctx.state_manager)
    if result is None:
        return json.dumps(
            {"status": "not_in_combat", "message": "Not currently in combat"}
        )
    return json.dumps(result)


@mcp.resource("game://map")
def game_map_resource(
    ctx: MCPContext,
) -> str:
    """Current map and path options.

    Returns map information including node layout, current position,
    and available paths. Returns null status if no map is available.
    """
    app_ctx = ctx.request_context.lifespan_context
    result = resource_impl.get_map_resource(app_ctx.state_manager)
    if result is None:
        return json.dumps({"status": "no_map", "message": "No map data available"})
    return json.dumps(result)


# ==============================================================================
# MCP Prompt Registration
# ==============================================================================


@mcp.prompt()
def analyze_combat(
    ctx: MCPContext,
) -> str:
    """Analyze the current combat situation.

    Provides structured context about the current combat including hand,
    energy, monsters, and strategic guidance for turn planning.
    """
    app_ctx = ctx.request_context.lifespan_context
    state = app_ctx.state_manager.get_current_state()
    if state is None:
        return "No game state available. Cannot analyze combat."
    return prompt_impl.analyze_combat(state)


@mcp.prompt()
def evaluate_card_reward(
    ctx: MCPContext,
) -> str:
    """Evaluate card reward choices.

    Provides structured context about available card choices, current deck
    composition, and strategic guidance for card selection.
    """
    app_ctx = ctx.request_context.lifespan_context
    state = app_ctx.state_manager.get_current_state()
    if state is None:
        return "No game state available. Cannot evaluate card reward."
    return prompt_impl.evaluate_card_reward(state)


@mcp.prompt()
def plan_path(
    ctx: MCPContext,
) -> str:
    """Plan the map path.

    Provides structured context about available path options, current HP,
    resources, and strategic guidance for route selection.
    """
    app_ctx = ctx.request_context.lifespan_context
    state = app_ctx.state_manager.get_current_state()
    if state is None:
        return "No game state available. Cannot plan path."
    return prompt_impl.plan_path(state)


@mcp.prompt()
def evaluate_event(
    ctx: MCPContext,
) -> str:
    """Evaluate event options.

    Provides structured context about event choices, current resources,
    and risk/reward analysis for event decisions.
    """
    app_ctx = ctx.request_context.lifespan_context
    state = app_ctx.state_manager.get_current_state()
    if state is None:
        return "No game state available. Cannot evaluate event."
    return prompt_impl.evaluate_event(state)
