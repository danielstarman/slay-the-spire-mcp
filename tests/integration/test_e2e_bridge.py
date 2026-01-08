"""End-to-end integration tests for bridge-to-server communication.

Tests the full pipeline:
1. Server TCP listener starts on :7777
2. Bridge relay connects and sends "ready"
3. Mock game state JSON is fed to bridge stdin
4. Server receives and parses the state correctly
"""

from __future__ import annotations

import asyncio
import copy
import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from slay_the_spire_mcp.state import GameStateManager, TCPListener
from spire_bridge.relay import Relay

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def combat_state_json(game_states_dir: Path) -> dict[str, Any]:
    """Load the combat game state fixture."""
    fixture_path = game_states_dir / "combat.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def card_reward_state_json(game_states_dir: Path) -> dict[str, Any]:
    """Load the card reward game state fixture."""
    fixture_path = game_states_dir / "card_reward.json"
    with open(fixture_path) as f:
        return json.load(f)


def wrap_as_state_message(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap game state data in the expected message format.

    If the data is already in CommunicationMod format (has game_state),
    return it as-is. Otherwise wrap in legacy format.
    """
    if "game_state" in data:
        # Already in CommunicationMod format
        return data
    return {"type": "state", "data": data}


# =============================================================================
# Happy Path Tests
# =============================================================================


class TestStateFlowsStdinToServer:
    """Test that state flows correctly from bridge stdin to server."""

    async def test_state_flows_stdin_to_server(
        self,
        combat_state_json: dict[str, Any],
    ) -> None:
        """Verify a single state flows from bridge stdin to server.

        Pipeline:
        1. Start server TCP listener
        2. Start bridge relay (connect to server)
        3. Feed game state JSON to bridge stdin
        4. Verify server's GameStateManager has the parsed state
        """
        # Setup state manager and TCP listener
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7778)

        # Capture stdout from relay
        stdout_capture = StringIO()

        # Create relay
        relay = Relay(
            host="127.0.0.1",
            port=7778,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            # Start the TCP listener
            await listener.start()

            # Give listener time to start
            await asyncio.sleep(0.1)

            # Connect relay to server
            connected = await relay.connect()
            assert connected, "Relay failed to connect to server"

            # Verify relay sent ready message
            relay.send_ready()
            assert stdout_capture.getvalue() == "ready\n"

            # Wrap state data in message format
            message = wrap_as_state_message(combat_state_json)
            message_json = json.dumps(message)

            # Send state through relay
            sent = await relay.send_to_server(message_json)
            assert sent, "Failed to send state to server"

            # Wait for server to process
            await asyncio.sleep(0.2)

            # Verify state reached the server
            current_state = state_manager.get_current_state()
            assert current_state is not None, "Server did not receive state"
            assert current_state.floor == 3
            assert current_state.screen_type == "NONE"
            assert current_state.hp == 70
            assert current_state.max_hp == 80
            assert current_state.gold == 50
            assert current_state.in_game is True

        finally:
            await relay.close()
            await listener.stop()

    async def test_multiple_states_flow_correctly(
        self,
        combat_state_json: dict[str, Any],
        card_reward_state_json: dict[str, Any],
    ) -> None:
        """Verify multiple sequential states flow correctly.

        Each state update should be received by the server in order.
        """
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7779)

        received_states: list[tuple[int, str]] = []

        # Track state changes
        def on_state_change(state: Any) -> None:
            received_states.append((state.floor, state.screen_type))

        state_manager.on_state_change(on_state_change)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7779,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected, "Relay failed to connect to server"

            # Send first state (combat)
            message1 = wrap_as_state_message(combat_state_json)
            await relay.send_to_server(json.dumps(message1))
            await asyncio.sleep(0.2)

            # Send second state (card reward)
            message2 = wrap_as_state_message(card_reward_state_json)
            await relay.send_to_server(json.dumps(message2))
            await asyncio.sleep(0.2)

            # Verify both states were received in order
            assert len(received_states) == 2
            assert received_states[0] == (3, "NONE")  # Combat state
            assert received_states[1] == (5, "CARD_REWARD")  # Card reward state

            # Verify current state is the most recent
            current = state_manager.get_current_state()
            assert current is not None
            assert current.floor == 5
            assert current.screen_type == "CARD_REWARD"

            # Verify previous state is stored
            previous = state_manager.get_previous_state()
            assert previous is not None
            assert previous.floor == 3

        finally:
            await relay.close()
            await listener.stop()


# =============================================================================
# Error Recovery Tests
# =============================================================================


class TestErrorRecovery:
    """Test error recovery scenarios."""

    async def test_bridge_reconnects_after_server_restart(
        self,
        combat_state_json: dict[str, Any],
    ) -> None:
        """Verify bridge can reconnect after server restarts.

        Sequence:
        1. Start server, start bridge
        2. Stop server
        3. Restart server
        4. Send state through bridge
        5. Verify state reaches new server instance
        """
        # First server instance
        state_manager1 = GameStateManager()
        listener1 = TCPListener(state_manager1, host="127.0.0.1", port=7780)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7780,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=10,  # More attempts to allow for timing
        )

        try:
            # Start first server
            await listener1.start()
            await asyncio.sleep(0.1)

            # Connect relay
            connected = await relay.connect()
            assert connected, "Initial connection failed"

            # Stop first server - this will break the existing connection
            await listener1.stop()
            await asyncio.sleep(0.2)

            # Start second server instance on same port
            state_manager2 = GameStateManager()
            listener2 = TCPListener(state_manager2, host="127.0.0.1", port=7780)
            await listener2.start()
            await asyncio.sleep(0.1)

            try:
                # Send state - this should trigger reconnection
                message = wrap_as_state_message(combat_state_json)
                message_json = json.dumps(message)

                # The first send may appear to succeed (data goes to OS buffer)
                # but the connection is broken. Try multiple sends with retries.
                state_received = False

                for attempt in range(5):
                    sent = await relay.send_to_server(message_json)
                    await asyncio.sleep(0.3)

                    current_state = state_manager2.get_current_state()
                    if current_state is not None:
                        state_received = True
                        break

                    # If send failed, the relay should have detected the broken
                    # connection and will try to reconnect on next send

                assert state_received, "State did not reach new server after retries"
                assert current_state is not None
                assert current_state.floor == 3
                assert current_state.hp == 70

            finally:
                await listener2.stop()

        finally:
            await relay.close()

    async def test_relay_handles_invalid_json_gracefully(self) -> None:
        """Verify the server handles invalid JSON without crashing."""
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7781)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7781,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected

            # Send invalid JSON
            await relay.send_to_server("not valid json{{{")
            await asyncio.sleep(0.1)

            # Server should still be running
            assert listener.is_running

            # Send valid state after invalid
            valid_message = wrap_as_state_message({
                "in_game": True,
                "screen_type": "NONE",
                "floor": 1,
                "act": 1,
                "hp": 80,
                "max_hp": 80,
                "gold": 0,
                "deck": [],
                "relics": [],
                "potions": [],
            })
            await relay.send_to_server(json.dumps(valid_message))
            await asyncio.sleep(0.2)

            # Verify valid state was received
            current = state_manager.get_current_state()
            assert current is not None
            assert current.floor == 1

        finally:
            await relay.close()
            await listener.stop()

    async def test_relay_handles_empty_messages(self) -> None:
        """Verify empty messages are skipped without error."""
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7782)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7782,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected

            # Empty messages should be skipped
            result = await relay.send_to_server("")
            assert result is True  # No error, just skipped

            result = await relay.send_to_server("   \n")
            assert result is True  # No error, just skipped

            # Server should have no state
            assert state_manager.get_current_state() is None

        finally:
            await relay.close()
            await listener.stop()


# =============================================================================
# Command Flow Tests (server -> TCP -> bridge -> stdout)
# =============================================================================


class TestCommandFlowsServerToStdout:
    """Test that commands flow correctly from server to bridge stdout."""

    async def test_command_flows_server_to_stdout(self) -> None:
        """Verify a command sent by server reaches bridge stdout.

        Pipeline:
        1. Start server TCP listener
        2. Start bridge relay (connect to server)
        3. Start TCP->stdout relay task
        4. Server calls send_command() with a command
        5. Verify command arrives at bridge stdout
        """
        # Setup state manager and TCP listener
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7783)

        # Capture stdout from relay
        stdout_capture = StringIO()

        # Create relay
        relay = Relay(
            host="127.0.0.1",
            port=7783,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            # Start the TCP listener
            await listener.start()

            # Give listener time to start
            await asyncio.sleep(0.1)

            # Connect relay to server
            connected = await relay.connect()
            assert connected, "Relay failed to connect to server"

            # Verify relay sent ready message
            relay.send_ready()
            initial_output = stdout_capture.getvalue()
            assert initial_output == "ready\n", f"Expected 'ready\\n', got {initial_output!r}"

            # Start TCP->stdout relay in background
            tcp_to_stdout_task = asyncio.create_task(relay.run_tcp_to_stdout())

            # Wait a moment for the relay task to start
            await asyncio.sleep(0.1)

            # Server sends a command
            command = {"type": "command", "action": "PLAY", "card_index": 1}
            await listener.send_command(command)

            # Wait for command to propagate
            await asyncio.sleep(0.3)

            # Cancel the relay task
            tcp_to_stdout_task.cancel()
            try:
                await tcp_to_stdout_task
            except asyncio.CancelledError:
                pass

            # Verify command reached stdout
            final_output = stdout_capture.getvalue()
            assert "ready\n" in final_output

            # The command should appear after "ready\n"
            command_output = final_output[len("ready\n"):]
            assert command_output.strip() != "", "No command received at stdout"

            # Parse the command and verify contents
            received_command = json.loads(command_output.strip())
            assert received_command["type"] == "command"
            assert received_command["action"] == "PLAY"
            assert received_command["card_index"] == 1

        finally:
            await relay.close()
            await listener.stop()

    async def test_multiple_commands_flow_correctly(self) -> None:
        """Verify multiple commands flow correctly to stdout."""
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7784)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7784,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected

            relay.send_ready()

            # Start TCP->stdout relay in background
            tcp_to_stdout_task = asyncio.create_task(relay.run_tcp_to_stdout())
            await asyncio.sleep(0.1)

            # Send multiple commands
            command1 = {"type": "command", "action": "PLAY", "card_index": 1}
            command2 = {"type": "command", "action": "END"}
            command3 = {"type": "command", "action": "CHOOSE", "choice": "potion"}

            await listener.send_command(command1)
            await asyncio.sleep(0.1)
            await listener.send_command(command2)
            await asyncio.sleep(0.1)
            await listener.send_command(command3)
            await asyncio.sleep(0.3)

            # Cancel the relay task
            tcp_to_stdout_task.cancel()
            try:
                await tcp_to_stdout_task
            except asyncio.CancelledError:
                pass

            # Verify all commands reached stdout
            final_output = stdout_capture.getvalue()
            lines = final_output.strip().split("\n")

            # First line is "ready", then 3 commands
            assert len(lines) >= 4, f"Expected at least 4 lines, got {len(lines)}: {lines}"
            assert lines[0] == "ready"

            # Parse and verify commands
            received_commands = [json.loads(line) for line in lines[1:4]]
            assert received_commands[0]["action"] == "PLAY"
            assert received_commands[1]["action"] == "END"
            assert received_commands[2]["action"] == "CHOOSE"

        finally:
            await relay.close()
            await listener.stop()


# =============================================================================
# Bidirectional Flow Tests
# =============================================================================


class TestBidirectionalFlow:
    """Test simultaneous bidirectional communication."""

    async def test_bidirectional_simultaneous(
        self,
        combat_state_json: dict[str, Any],
    ) -> None:
        """Verify state and commands can flow simultaneously.

        Both directions should work concurrently:
        - State: stdin -> bridge -> TCP -> server
        - Commands: server -> TCP -> bridge -> stdout
        """
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7785)

        received_states: list[int] = []

        def on_state_change(state: Any) -> None:
            received_states.append(state.floor)

        state_manager.on_state_change(on_state_change)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7785,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected

            relay.send_ready()

            # Start TCP->stdout relay in background
            tcp_to_stdout_task = asyncio.create_task(relay.run_tcp_to_stdout())
            await asyncio.sleep(0.1)

            # Interleave state sends and command sends
            # Send state
            message1 = wrap_as_state_message(combat_state_json)
            await relay.send_to_server(json.dumps(message1))

            # Send command while state is being processed
            command1 = {"type": "command", "action": "PLAY", "card_index": 1}
            await listener.send_command(command1)

            # Send another state with different floor
            # Use deep copy since fixture has nested game_state
            modified_state = copy.deepcopy(combat_state_json)
            if "game_state" in modified_state:
                modified_state["game_state"]["floor"] = 4
            else:
                modified_state["floor"] = 4
            message2 = wrap_as_state_message(modified_state)
            await relay.send_to_server(json.dumps(message2))

            # Send another command
            command2 = {"type": "command", "action": "END"}
            await listener.send_command(command2)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Cancel the relay task
            tcp_to_stdout_task.cancel()
            try:
                await tcp_to_stdout_task
            except asyncio.CancelledError:
                pass

            # Verify states were received
            assert len(received_states) == 2
            assert 3 in received_states
            assert 4 in received_states

            # Verify commands were received
            final_output = stdout_capture.getvalue()
            lines = final_output.strip().split("\n")

            # Should have "ready" + 2 commands
            assert len(lines) >= 3, f"Expected at least 3 lines, got {len(lines)}"

            # Parse command lines (skip "ready")
            command_lines = [l for l in lines[1:] if l.strip()]
            assert len(command_lines) >= 2, f"Expected 2 commands, got {len(command_lines)}"

            commands = [json.loads(l) for l in command_lines[:2]]
            actions = [c["action"] for c in commands]
            assert "PLAY" in actions
            assert "END" in actions

        finally:
            await relay.close()
            await listener.stop()

    async def test_full_round_trip(
        self,
        combat_state_json: dict[str, Any],
    ) -> None:
        """Verify full round trip: state in, command out.

        This simulates the complete flow:
        1. Game sends state to server
        2. Server processes state
        3. Server sends command back
        4. Command reaches bridge stdout
        """
        state_manager = GameStateManager()
        listener = TCPListener(state_manager, host="127.0.0.1", port=7786)

        # Track when state is received
        state_received = asyncio.Event()
        received_state: list[Any] = []

        def on_state_change(state: Any) -> None:
            received_state.append(state)
            state_received.set()

        state_manager.on_state_change(on_state_change)

        stdout_capture = StringIO()
        relay = Relay(
            host="127.0.0.1",
            port=7786,
            stdout=stdout_capture,
            reconnect_delay=0.1,
            max_reconnect_attempts=3,
        )

        try:
            await listener.start()
            await asyncio.sleep(0.1)

            connected = await relay.connect()
            assert connected

            relay.send_ready()

            # Start TCP->stdout relay in background
            tcp_to_stdout_task = asyncio.create_task(relay.run_tcp_to_stdout())
            await asyncio.sleep(0.1)

            # Step 1: Game sends state to server
            message = wrap_as_state_message(combat_state_json)
            await relay.send_to_server(json.dumps(message))

            # Wait for state to be received
            await asyncio.wait_for(state_received.wait(), timeout=2.0)

            # Step 2: Verify server has state
            current_state = state_manager.get_current_state()
            assert current_state is not None
            assert current_state.floor == 3

            # Step 3: Server sends command based on state
            # (In real use, this would be based on MCP tool call)
            response_command = {
                "type": "command",
                "action": "PLAY",
                "card_index": 1,
                "reason": f"Playing card on floor {current_state.floor}",
            }
            await listener.send_command(response_command)

            # Wait for command to propagate
            await asyncio.sleep(0.3)

            # Cancel the relay task
            tcp_to_stdout_task.cancel()
            try:
                await tcp_to_stdout_task
            except asyncio.CancelledError:
                pass

            # Step 4: Verify command reached stdout
            final_output = stdout_capture.getvalue()
            lines = final_output.strip().split("\n")

            assert len(lines) >= 2, f"Expected at least 2 lines, got {len(lines)}"
            assert lines[0] == "ready"

            # Parse the command
            received_command = json.loads(lines[1])
            assert received_command["type"] == "command"
            assert received_command["action"] == "PLAY"
            assert received_command["card_index"] == 1
            assert "floor 3" in received_command["reason"]

        finally:
            await relay.close()
            await listener.stop()
