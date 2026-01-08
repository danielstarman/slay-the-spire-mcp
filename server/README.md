# Slay the Spire MCP Server

MCP server that bridges Claude to Slay the Spire for game state analysis and strategic advisory.

## Overview

This package provides an MCP server that:
- Exposes game state via MCP tools and resources
- Accepts connections from the bridge process on TCP port 7777
- Serves MCP protocol via Streamable HTTP on port 8000
- Pushes analysis results to the mod overlay via WebSocket

## Installation

```bash
uv sync
```

## Usage

```bash
uv run python -m slay_the_spire_mcp
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
