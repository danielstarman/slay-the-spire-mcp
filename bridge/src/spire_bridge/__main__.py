"""Entry point for the Spire Bridge relay.

Launched by SpireBridge mod as subprocess. Sends "ready\n" on startup
per CommunicationMod protocol.

Usage:
    python -m spire_bridge
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from spire_bridge.protocol import DEFAULT_HOST, DEFAULT_PORT
from spire_bridge.relay import run_relay


def setup_logging() -> None:
    """Configure logging for the bridge process."""
    # Log to stderr so stdout is reserved for protocol messages
    log_level = os.environ.get("SPIRE_BRIDGE_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def main() -> int:
    """Main entry point."""
    setup_logging()

    # Get host/port from environment or use defaults
    host = os.environ.get("SPIRE_BRIDGE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("SPIRE_BRIDGE_PORT", str(DEFAULT_PORT)))

    # Run the async relay
    return asyncio.run(run_relay(host=host, port=port))


if __name__ == "__main__":
    sys.exit(main())
