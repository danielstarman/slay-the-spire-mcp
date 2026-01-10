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
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from slay_the_spire_mcp import prompts as prompt_impl
from slay_the_spire_mcp import resources as resource_impl
from slay_the_spire_mcp import tools as tool_impl
from slay_the_spire_mcp.config import Config, get_config
from slay_the_spire_mcp.detection import detect_decision_point
from slay_the_spire_mcp.models import GameState
from slay_the_spire_mcp.state import GameStateManager, TCPListener
from slay_the_spire_mcp.stdin_io import StdinListener
from slay_the_spire_mcp.terminal import Colors, render_game_state

logger = logging.getLogger(__name__)


# ==============================================================================
# Pre-initialized Context for TCP Listener
# ==============================================================================


@dataclass
class PreInitializedContext:
    """Holds pre-initialized state_manager and game listener.

    This allows the listener (TCP or stdin) to be started BEFORE the MCP server runs,
    ensuring the connection is ready immediately on startup rather than
    waiting for the first MCP request to trigger the lifespan.
    """

    state_manager: GameStateManager
    tcp_listener: TCPListener | StdinListener | None  # GameListener implementations
    config: Config


# Module-level holder for pre-initialized context
# Set by run_server() before the MCP server starts
_pre_initialized_context: PreInitializedContext | None = None


def set_pre_initialized_context(ctx: PreInitializedContext | None) -> None:
    """Set the pre-initialized context for the lifespan to use.

    Args:
        ctx: The pre-initialized context, or None to clear it
    """
    global _pre_initialized_context
    _pre_initialized_context = ctx


def get_pre_initialized_context() -> PreInitializedContext | None:
    """Get the pre-initialized context.

    Returns:
        The pre-initialized context, or None if not set
    """
    return _pre_initialized_context


# Separator for terminal output
SEPARATOR = "=" * 67


def _create_terminal_display_callback() -> Callable[[GameState], None]:
    """Create a callback function for displaying state changes to terminal.

    Returns:
        A callback function that renders game state and decision points to stderr.
    """

    def display_state_change(state: GameState) -> None:
        """Display state change to terminal via stderr.

        This callback:
        1. Prints a separator and header with floor/act/screen info
        2. Renders the full game state using terminal.render_game_state()
        3. Detects and displays decision points if any

        Args:
            state: The new game state
        """
        try:
            # Print separator and header
            print(SEPARATOR, file=sys.stderr)
            print(
                f"{Colors.BOLD}[STATE UPDATE]{Colors.RESET} "
                f"Floor {state.floor} | Act {state.act} | {state.screen_type}",
                file=sys.stderr,
            )
            print(SEPARATOR, file=sys.stderr)

            # Render the full game state
            rendered = render_game_state(state)
            print(rendered, file=sys.stderr)
            print(file=sys.stderr)

            # Detect and display decision point
            decision = detect_decision_point(state)
            if decision is not None:
                choices_str = ", ".join(decision.choices[:5])
                if len(decision.choices) > 5:
                    choices_str += f", ... (+{len(decision.choices) - 5} more)"

                print(
                    f"{Colors.CYAN}[DECISION POINT]{Colors.RESET} "
                    f"{Colors.BOLD}{decision.decision_type.value}{Colors.RESET}",
                    file=sys.stderr,
                )
                print(f"  Choices: {choices_str}", file=sys.stderr)

            print(SEPARATOR, file=sys.stderr)
            print(file=sys.stderr)  # Extra blank line for readability

        except Exception as e:
            # Log errors but don't crash - this is a display callback
            logger.error(f"Error in terminal display callback: {e}", exc_info=True)

    return display_state_change


@dataclass
class AppContext:
    """Application context shared across MCP server lifecycle.

    This context is created during server startup and available to all
    tools and resources via the lifespan context.

    Attributes:
        state_manager: GameStateManager instance that maintains current game state
        tcp_listener: Listener for game I/O (TCPListener or StdinListener, may be None)
        config: Application configuration
    """

    state_manager: GameStateManager
    tcp_listener: TCPListener | StdinListener | None  # GameListener implementations
    config: Config


# Type alias for MCP Context with our AppContext
MCPContext = Context[ServerSession, AppContext]


@asynccontextmanager
async def app_lifespan(
    server: FastMCP,  # noqa: ARG001 - Required by FastMCP lifespan signature
    config: Config | None = None,
) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context.

    This context manager uses the pre-initialized context if available,
    which allows the TCP listener to be started before the MCP server runs.

    The lifespan does NOT stop the TCP listener on shutdown - that is handled
    by the caller (run_server) to ensure clean shutdown order.

    Args:
        server: FastMCP server instance (required by lifespan protocol)
        config: Application configuration (default: from get_config())

    Yields:
        AppContext containing state_manager, tcp_listener, and config
    """
    # Check for pre-initialized context first
    pre_ctx = get_pre_initialized_context()
    if pre_ctx is not None:
        # Use pre-initialized context - TCP listener already started
        logger.info("Using pre-initialized context (TCP listener already running)")
        yield AppContext(
            state_manager=pre_ctx.state_manager,
            tcp_listener=pre_ctx.tcp_listener,
            config=pre_ctx.config,
        )
        # Don't stop TCP listener here - caller handles shutdown
        return

    # Fallback: create fresh context (for testing or when not pre-initialized)
    cfg = config if config is not None else get_config()

    # Create state manager
    state_manager = GameStateManager()
    logger.info("GameStateManager initialized (fallback mode)")

    # Register terminal display callback
    state_manager.on_state_change(_create_terminal_display_callback())
    logger.info("Terminal display callback registered")

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
        # Stop TCP listener on shutdown (only in fallback mode)
        if tcp_listener.is_running:
            await tcp_listener.stop()
            logger.info("TCP listener stopped")


@asynccontextmanager
async def mock_lifespan(
    server: FastMCP,  # noqa: ARG001 - Required by FastMCP lifespan signature
    config: Config | None = None,
) -> AsyncIterator[AppContext]:
    """Manage application lifecycle for mock mode.

    This context manager:
    1. Creates a GameStateManager on startup
    2. Initializes MockStateProvider with fixtures
    3. Yields AppContext for tools/resources to access (tcp_listener is None)

    Args:
        server: FastMCP server instance (required by lifespan protocol)
        config: Application configuration (must have mock_mode=True and mock_fixture set)

    Yields:
        AppContext containing state_manager (with loaded state), None tcp_listener, and config
    """
    from pathlib import Path

    from slay_the_spire_mcp.mock import MockStateProvider

    # Use provided config or get from singleton
    cfg = config if config is not None else get_config()

    # Create state manager
    state_manager = GameStateManager()
    logger.info("GameStateManager initialized (mock mode)")

    # Register terminal display callback
    state_manager.on_state_change(_create_terminal_display_callback())
    logger.info("Terminal display callback registered (mock mode)")

    # Create and initialize mock provider
    mock_provider = MockStateProvider(
        state_manager=state_manager,
        fixture_path=Path(cfg.mock_fixture) if cfg.mock_fixture else None,
        delay_ms=cfg.mock_delay_ms,
    )

    await mock_provider.initialize()
    logger.info(f"Mock state provider initialized from {cfg.mock_fixture}")

    # Log the loaded state
    current_state = state_manager.get_current_state()
    if current_state:
        logger.info(
            f"Mock state loaded: floor={current_state.floor}, "
            f"screen={current_state.screen_type}, "
            f"hp={current_state.hp}/{current_state.max_hp}"
        )

    yield AppContext(
        state_manager=state_manager,
        tcp_listener=None,  # No TCP listener in mock mode
        config=cfg,
    )


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
