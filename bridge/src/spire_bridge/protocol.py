"""Protocol constants and message handling for the bridge.

Handles:
- Protocol constants (host, port, ready message)
- Newline-delimited JSON message framing
- Message validation
"""

from __future__ import annotations

# =============================================================================
# Protocol Constants
# =============================================================================

# Default MCP server connection settings
DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 7777

# CommunicationMod protocol ready message
READY_MESSAGE: str = "ready\n"

# Reconnection settings
DEFAULT_RECONNECT_DELAY: float = 1.0  # seconds
DEFAULT_MAX_RECONNECT_ATTEMPTS: int = 5

# Buffer sizes
READ_BUFFER_SIZE: int = 65536  # 64KB read buffer


# =============================================================================
# Message Validation
# =============================================================================


def is_valid_message(line: str) -> bool:
    """Check if a line is a valid message to relay.

    Empty lines and whitespace-only lines are not valid messages.

    Args:
        line: The line to check

    Returns:
        True if the line is a valid message to relay
    """
    return bool(line.strip())


def normalize_line(line: str) -> str:
    """Normalize a line for transmission.

    Ensures the line ends with exactly one newline.

    Args:
        line: The line to normalize

    Returns:
        The line with a trailing newline
    """
    stripped = line.rstrip("\n\r")
    if not stripped:
        return ""
    return stripped + "\n"
