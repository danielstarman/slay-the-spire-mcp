# Spire Bridge

Thin async relay between the SpireBridge mod and the MCP server.

## Overview

This package provides a bridge process that:
- Is launched by the SpireBridge mod as a subprocess
- Sends "ready\n" on startup per CommunicationMod protocol
- Relays game state JSON from stdin (mod) to TCP socket (MCP server)
- Relays commands from TCP socket back to stdout (mod)

## Why a Separate Process?

- CommunicationMod (and SpireBridge) launches external processes as subprocesses
- MCP clients also expect to launch MCP servers as subprocesses
- The MCP server cannot be a child of both simultaneously
- This thin relay bridges the two

## Installation

```bash
uv sync
```

## Usage

The bridge is typically launched by the SpireBridge mod, not run directly.

```bash
# For testing only
uv run python -m spire_bridge
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Type check
uv run mypy src

# Lint
uv run ruff check src
```

## Architecture

See `CLAUDE.md` and `.claude/plans/mvp-architecture.md` in the repository root for the full architecture documentation.
