"""Entry point for the Slay the Spire MCP server.

Usage:
    python -m slay_the_spire_mcp
    uv run python -m slay_the_spire_mcp

Environment Variables:
    STS_TCP_HOST: TCP host for bridge connection (default: 127.0.0.1)
    STS_TCP_PORT: TCP port for bridge connection (default: 7777)
    STS_HTTP_PORT: HTTP port for MCP server (default: 8000)
    STS_WS_PORT: WebSocket port (default: 31337)
    STS_LOG_LEVEL: Logging level (default: INFO)
    STS_TRANSPORT: MCP transport type: 'http' or 'stdio' (default: http)
    STS_MOCK_MODE: Enable mock mode (default: false)
    STS_MOCK_FIXTURE: Path to fixture file/directory for mock mode
    STS_MOCK_DELAY_MS: Delay between states in mock replay (default: 100)

Legacy environment variables (deprecated, use STS_ prefix instead):
    MOCK_MODE: Set to "1" to enable mock mode
    MOCK_FIXTURE: Path to fixture file or directory
    MOCK_DELAY_MS: Delay between states in sequence replay
"""

from __future__ import annotations

import logging
import os
import sys
from functools import partial
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import ValidationError

from slay_the_spire_mcp.config import Config, get_config, reset_config, set_config
from slay_the_spire_mcp.mock import MockModeError
from slay_the_spire_mcp.server import (
    AppContext,
    PreInitializedContext,
    _create_terminal_display_callback,
    app_lifespan,
    set_pre_initialized_context,
)
from slay_the_spire_mcp.state import GameStateManager, TCPListener

# Type alias for MCP Context with our AppContext - must be at module level
# for FastMCP decorator to evaluate type annotations correctly
MCPContext = Context[ServerSession, AppContext]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _migrate_legacy_env_vars() -> None:
    """Migrate legacy environment variables to new STS_ prefixed versions.

    This provides backward compatibility with the old MOCK_MODE, MOCK_FIXTURE,
    and MOCK_DELAY_MS environment variables.
    """
    legacy_mappings = {
        "MOCK_MODE": "STS_MOCK_MODE",
        "MOCK_FIXTURE": "STS_MOCK_FIXTURE",
        "MOCK_DELAY_MS": "STS_MOCK_DELAY_MS",
        "LOG_LEVEL": "STS_LOG_LEVEL",
    }

    for legacy_var, new_var in legacy_mappings.items():
        legacy_value = os.environ.get(legacy_var)
        if legacy_value is not None and os.environ.get(new_var) is None:
            # Convert MOCK_MODE=1 to STS_MOCK_MODE=true
            if legacy_var == "MOCK_MODE":
                legacy_value = "true" if legacy_value.strip() == "1" else "false"
            os.environ[new_var] = legacy_value


def run_stdin_server(config: Config) -> int:
    """Run the MCP server in stdin mode (unified process).

    This mode:
    - Reads game state from stdin
    - Writes commands to stdout
    - Serves MCP over HTTP (NOT stdio - stdout is for game)
    - Sends 'ready\\n' on startup per CommunicationMod protocol

    Args:
        config: Application configuration with stdin_mode=True

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    import asyncio

    logger = logging.getLogger(__name__)

    async def run_with_stdin_listener() -> int:
        """Async wrapper that starts stdin listener then runs MCP server."""
        from slay_the_spire_mcp.stdin_io import StdinListener

        state_manager = GameStateManager()
        stdin_listener = StdinListener(state_manager)

        # Register terminal display callback
        state_manager.on_state_change(_create_terminal_display_callback())

        try:
            # Start stdin listener (sends "ready\n")
            await stdin_listener.start()
            logger.info("Stdin listener started")

            # Set pre-initialized context
            set_pre_initialized_context(
                PreInitializedContext(
                    state_manager=state_manager,
                    tcp_listener=stdin_listener,  # Type: StdinListener implements GameListener
                    config=config,
                )
            )

            # Create a lifespan bound to our config
            bound_lifespan = partial(app_lifespan, config=config)

            # Create a new FastMCP server with app lifespan
            from mcp.server.fastmcp import FastMCP

            server = FastMCP(
                name="slay-the-spire",
                host=config.tcp_host,
                port=config.http_port,
                log_level=config.log_level,
                lifespan=bound_lifespan,
            )

            # Register all tools, resources, and prompts on the server
            _register_handlers(server)

            # Note: Must use HTTP, not stdio (stdout is for game commands)
            logger.info(
                f"Starting MCP server on http://{config.tcp_host}:{config.http_port}"
            )
            # Log to stderr - stdout is reserved for game commands
            print(
                f"MCP server running at http://{config.tcp_host}:{config.http_port}/mcp",
                file=sys.stderr,
            )

            await server.run_streamable_http_async()

            return 0

        finally:
            # Clean up pre-initialized context
            set_pre_initialized_context(None)

            # Stop stdin listener on shutdown
            await stdin_listener.stop()

    try:
        return asyncio.run(run_with_stdin_listener())

    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_mock_server(config: Config) -> int:
    """Run the MCP server in mock mode.

    This starts the FastMCP server with:
    - Mock lifespan that loads fixtures instead of connecting to TCP
    - Configurable transport (HTTP or stdio)
    - All tools, resources, and prompts registered

    Args:
        config: Application configuration with mock_mode=True

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = logging.getLogger(__name__)

    # Determine transport type
    use_stdio = config.transport == "stdio"

    try:
        # Import here to avoid circular imports and to allow lazy loading
        from slay_the_spire_mcp.server import mock_lifespan

        # Create a mock-aware lifespan bound to our config
        bound_lifespan = partial(mock_lifespan, config=config)

        # Create a new FastMCP server with mock lifespan
        # We need to recreate the server with the lifespan and re-register tools
        from mcp.server.fastmcp import FastMCP

        mock_server = FastMCP(
            name="slay-the-spire",
            host=config.tcp_host,
            port=config.http_port,
            log_level=config.log_level,
            lifespan=bound_lifespan,
        )

        # Register all tools, resources, and prompts on the mock server
        _register_handlers(mock_server)

        if use_stdio:
            # stdio mode: no print to stdout (would interfere with protocol)
            # Log to stderr instead
            logger.info("Starting MCP server in mock mode with stdio transport")
            print("MCP server starting with stdio transport...", file=sys.stderr)

            # Run the server with stdio transport
            mock_server.run(transport="stdio")
        else:
            # HTTP mode: safe to print to stdout
            logger.info(
                f"Starting MCP server in mock mode on http://{config.tcp_host}:{config.http_port}"
            )
            print(
                f"MCP server running at http://{config.tcp_host}:{config.http_port}/mcp"
            )
            print("Press Ctrl+C to stop.")

            # Run the server with streamable-http transport
            mock_server.run(transport="streamable-http")

        return 0

    except MockModeError as e:
        logger.error(f"Mock mode error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if not use_stdio:
            print("\nServer stopped.")
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def _start_tcp_listener(
    config: Config,
) -> tuple[GameStateManager, TCPListener]:
    """Start the TCP listener before the MCP server.

    This ensures port 7777 is listening immediately on startup,
    not waiting for the first MCP request.

    Args:
        config: Application configuration

    Returns:
        Tuple of (state_manager, tcp_listener)
    """
    logger = logging.getLogger(__name__)

    # Create state manager
    state_manager = GameStateManager()
    logger.info("GameStateManager initialized")

    # Register terminal display callback
    state_manager.on_state_change(_create_terminal_display_callback())
    logger.info("Terminal display callback registered")

    # Create and start TCP listener
    tcp_listener = TCPListener(
        state_manager, host=config.tcp_host, port=config.tcp_port
    )
    await tcp_listener.start()
    logger.info(f"TCP listener started on {config.tcp_host}:{config.tcp_port}")

    return state_manager, tcp_listener


async def _stop_tcp_listener(tcp_listener: TCPListener) -> None:
    """Stop the TCP listener cleanly.

    Args:
        tcp_listener: The TCP listener to stop
    """
    logger = logging.getLogger(__name__)
    if tcp_listener.is_running:
        await tcp_listener.stop()
        logger.info("TCP listener stopped")


def run_server(config: Config) -> int:
    """Run the MCP server in normal mode.

    This starts the FastMCP server with:
    - TCP listener started BEFORE the MCP server (for immediate availability)
    - App lifespan that uses pre-initialized context
    - Configurable transport (HTTP or stdio)
    - All tools, resources, and prompts registered

    Args:
        config: Application configuration with mock_mode=False

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    import asyncio

    logger = logging.getLogger(__name__)

    # Determine transport type
    use_stdio = config.transport == "stdio"

    # We need to start the TCP listener before the MCP server runs.
    # Since server.run() is blocking and synchronous, we use asyncio.run()
    # to start the TCP listener first, then run the MCP server in the same loop.

    async def run_with_tcp_listener() -> int:
        """Async wrapper that starts TCP listener then runs MCP server."""
        state_manager: GameStateManager | None = None
        tcp_listener: TCPListener | None = None

        try:
            # Start TCP listener first
            state_manager, tcp_listener = await _start_tcp_listener(config)

            # Set the pre-initialized context so app_lifespan can use it
            set_pre_initialized_context(
                PreInitializedContext(
                    state_manager=state_manager,
                    tcp_listener=tcp_listener,
                    config=config,
                )
            )

            # Create a lifespan bound to our config
            bound_lifespan = partial(app_lifespan, config=config)

            # Create a new FastMCP server with app lifespan
            from mcp.server.fastmcp import FastMCP

            server = FastMCP(
                name="slay-the-spire",
                host=config.tcp_host,
                port=config.http_port,
                log_level=config.log_level,
                lifespan=bound_lifespan,
            )

            # Register all tools, resources, and prompts on the server
            _register_handlers(server)

            if use_stdio:
                # stdio mode: no print to stdout (would interfere with protocol)
                logger.info("Starting MCP server with stdio transport")
                print("MCP server starting with stdio transport...", file=sys.stderr)

                # Run the server with stdio transport (async version)
                await server.run_stdio_async()
            else:
                # HTTP mode: safe to print to stdout
                logger.info(
                    f"Starting MCP server on http://{config.tcp_host}:{config.http_port}"
                )
                print(
                    f"MCP server running at http://{config.tcp_host}:{config.http_port}/mcp"
                )
                print(f"TCP listener for bridge on {config.tcp_host}:{config.tcp_port}")
                print("Press Ctrl+C to stop.")

                # Run the server with streamable-http transport (async version)
                await server.run_streamable_http_async()

            return 0

        finally:
            # Clean up pre-initialized context
            set_pre_initialized_context(None)

            # Stop TCP listener on shutdown
            if tcp_listener is not None:
                await _stop_tcp_listener(tcp_listener)

    try:
        return asyncio.run(run_with_tcp_listener())

    except KeyboardInterrupt:
        if not use_stdio:
            print("\nServer stopped.")
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _register_handlers(server: FastMCP[AppContext]) -> None:
    """Register all MCP tools, resources, and prompts on a server.

    This duplicates the registrations from server.py but on a new server instance
    configured with a different lifespan.

    Args:
        server: FastMCP server instance to register handlers on
    """
    import json

    from slay_the_spire_mcp import prompts as prompt_impl
    from slay_the_spire_mcp import resources as resource_impl
    from slay_the_spire_mcp import tools as tool_impl

    # ==============================================================================
    # MCP Tool Registration
    # ==============================================================================

    @server.tool()
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
        # In mock mode, tcp_listener is None, so we pass it but the tool handles it
        result = await tool_impl.get_game_state(
            app_ctx.state_manager, app_ctx.tcp_listener
        )
        if result is None:
            return json.dumps(
                {"status": "no_state", "message": "No game state available"}
            )
        return json.dumps(result)

    @server.tool()
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
            return json.dumps(
                {
                    "success": False,
                    "error": "Cannot play cards in mock mode (no bridge connection)",
                }
            )
        try:
            result = await tool_impl.play_card(
                app_ctx.state_manager, app_ctx.tcp_listener, card_index, target_index
            )
            return json.dumps(result)
        except tool_impl.ToolError as e:
            return json.dumps({"success": False, "error": str(e)})

    @server.tool()
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
            return json.dumps(
                {
                    "success": False,
                    "error": "Cannot end turn in mock mode (no bridge connection)",
                }
            )
        try:
            result = await tool_impl.end_turn(
                app_ctx.state_manager, app_ctx.tcp_listener
            )
            return json.dumps(result)
        except tool_impl.ToolError as e:
            return json.dumps({"success": False, "error": str(e)})

    @server.tool()
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
            return json.dumps(
                {
                    "success": False,
                    "error": "Cannot make choices in mock mode (no bridge connection)",
                }
            )
        try:
            result = await tool_impl.choose(
                app_ctx.state_manager, app_ctx.tcp_listener, choice
            )
            return json.dumps(result)
        except tool_impl.ToolError as e:
            return json.dumps({"success": False, "error": str(e)})

    @server.tool()
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
            return json.dumps(
                {
                    "success": False,
                    "error": "Cannot use potions in mock mode (no bridge connection)",
                }
            )
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

    @server.resource("game://state")
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
            return json.dumps(
                {"status": "no_state", "message": "No game state available"}
            )
        return json.dumps(result)

    @server.resource("game://player")
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
            return json.dumps(
                {"status": "no_state", "message": "No game state available"}
            )
        return json.dumps(result)

    @server.resource("game://combat")
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

    @server.resource("game://map")
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

    @server.prompt()
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

    @server.prompt()
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

    @server.prompt()
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

    @server.prompt()
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


def main() -> int:
    """Main entry point."""
    # Migrate legacy environment variables first
    _migrate_legacy_env_vars()

    # Reset config to pick up any migrated env vars
    reset_config()

    try:
        config = get_config()
    except ValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Setup logging from config
    config.setup_logging()

    # Set the config singleton so the lifespan can access it
    set_config(config)

    # For stdio transport, redirect all startup prints to stderr
    # to avoid interfering with the JSON-RPC protocol on stdout
    use_stdio = config.transport == "stdio"
    out = sys.stderr if use_stdio else sys.stdout

    print("Slay the Spire MCP Server v0.1.0", file=out)
    print("Configuration:", file=out)
    print(f"  TCP: {config.tcp_host}:{config.tcp_port}", file=out)
    print(f"  HTTP: {config.http_port}", file=out)
    print(f"  WebSocket: {config.ws_port}", file=out)
    print(f"  Log level: {config.log_level}", file=out)
    print(f"  Transport: {config.transport}", file=out)

    if config.stdin_mode:
        print("  Stdin mode: enabled (unified process)", file=out)
        return run_stdin_server(config)

    if config.mock_mode:
        print(f"  Mock mode: enabled (fixture: {config.mock_fixture})", file=out)
        return run_mock_server(config)

    # Normal mode - run with app_lifespan (TCP listener for bridge)
    return run_server(config)


if __name__ == "__main__":
    sys.exit(main())
