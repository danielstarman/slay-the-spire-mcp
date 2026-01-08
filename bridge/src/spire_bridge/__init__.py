"""Spire Bridge - Relay between SpireBridge mod and MCP server.

A thin async relay that:
- Is launched by SpireBridge mod as subprocess
- Reads game state JSON from stdin (mod -> bridge)
- Relays state to MCP server via TCP on port 7777
- Relays commands from MCP server back to mod via stdout
"""

__version__ = "0.1.0"
