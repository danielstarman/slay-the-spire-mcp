# Slay the Spire MCP Server

An MCP (Model Context Protocol) server that bridges Claude to Slay the Spire, providing real-time game analysis and strategic advice.

## What It Does

Claude watches your Slay the Spire gameplay and analyzes decision points in real-time. When you encounter card rewards, relics, paths, or events, Claude provides:

- **Preference percentages** for each option
- **Concise strategic commentary** (1-2 sentences)
- **Context-aware analysis** based on your current run (deck, relics, HP, floor)

This is an **advisory co-pilot**, not an AI that plays for you. You make all decisions.

## Architecture

```
                                    ┌─────────────────────────────┐
                                    │    Claude (MCP Client)      │
                                    │    Analyzes & advises       │
                                    └─────────────┬───────────────┘
                                                  │ MCP Protocol
                                                  │ (HTTP :8000)
                                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server (Python)                          │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │  Tools     │  │ Resources  │  │  Prompts   │  │   State   │ │
│  │ get_state  │  │ game://    │  │ analyze_*  │  │  Manager  │ │
│  │ play_card  │  │ subscribe  │  │            │  │           │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
│                                                                  │
│  Bridge Handler (TCP :7777)     Overlay Pusher (WS :31337)      │
└──────────────────┬──────────────────────────────────────────────┘
                   │ TCP localhost:7777
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Bridge Process (Python)                       │
│    Launched by mod as subprocess, relays game state via TCP      │
└──────────────────┬──────────────────────────────────────────────┘
                   │ stdin/stdout (JSON)
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              Slay the Spire + SpireBridge Mod (Java)             │
│    Serializes game state, renders overlay, executes commands     │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow**: Game state flows up (Game -> Mod -> Bridge -> MCP Server -> Claude), analysis flows down.

## Quick Start

### Prerequisites

- **Python 3.10+** - [Download](https://www.python.org/downloads/)
- **uv** - Fast Python package manager - [Install](https://docs.astral.sh/uv/)
- **Slay the Spire** with mods enabled
- **SpireBridge mod** (fork of CommunicationMod)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourrepo/slay-the-spire-mcp.git
   cd slay-the-spire-mcp
   ```

2. **Install the MCP server:**
   ```bash
   cd server
   uv sync
   ```

3. **Install the bridge (optional, for testing):**
   ```bash
   cd bridge
   uv sync
   ```

4. **Install SpireBridge mod:**
   - Copy the SpireBridge mod JAR to your Slay the Spire mods folder
   - Enable it in ModTheSpire

### Running the Server

**Option A: Direct execution**
```bash
cd server
uv run python -m slay_the_spire_mcp
```

**Option B: Docker (recommended for production)**
```bash
docker-compose up
```

### Running in Mock Mode (Testing without the game)

Test the server with sample game states:

```bash
cd server
STS_MOCK_MODE=true STS_MOCK_FIXTURE=../tests/fixtures/game_states/combat_basic.json \
  uv run python -m slay_the_spire_mcp
```

### Configuring Claude

Add the MCP server to your Claude configuration:

```json
{
  "mcpServers": {
    "slay-the-spire": {
      "url": "http://localhost:8000",
      "transport": "streamable-http"
    }
  }
}
```

## Configuration

All settings are configured via environment variables with the `STS_` prefix.

| Variable | Default | Description |
|----------|---------|-------------|
| `STS_TCP_HOST` | `127.0.0.1` | TCP host for bridge connection |
| `STS_TCP_PORT` | `7777` | TCP port for bridge connection |
| `STS_HTTP_PORT` | `8000` | HTTP port for MCP server |
| `STS_WS_PORT` | `31337` | WebSocket port for overlay |
| `STS_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `STS_MOCK_MODE` | `false` | Enable mock mode for testing |
| `STS_MOCK_FIXTURE` | - | Path to fixture file/directory (required if mock mode) |
| `STS_MOCK_DELAY_MS` | `100` | Delay between states in mock sequence replay |

You can also use a `.env` file in the server directory:

```bash
# .env
STS_LOG_LEVEL=DEBUG
STS_TCP_PORT=7777
STS_HTTP_PORT=8000
```

## MCP Tools

The server exposes these tools for Claude to interact with the game:

### Read-Only Tools (Primary Use Case)

| Tool | Description |
|------|-------------|
| `get_game_state` | Get the full current game state |
| `get_player_resource` | Get player stats (HP, gold, deck, relics) |
| `get_combat_resource` | Get combat state (monsters, hand, energy) |
| `get_map_resource` | Get map data with paths and nodes |

### Action Tools (Optional - for full control)

| Tool | Parameters | Description |
|------|------------|-------------|
| `play_card` | `card_index`, `target_index?` | Play a card from hand |
| `end_turn` | - | End the current turn |
| `choose` | `choice` (index or name) | Make a choice (card reward, event, etc.) |
| `potion` | `action`, `slot`, `target_index?` | Use or discard a potion |

## MCP Resources

Subscribable resources for real-time game state:

| Resource | Description |
|----------|-------------|
| `game://state` | Full game state (subscribable for updates) |
| `game://player` | Player stats (HP, gold, deck, relics) |
| `game://combat` | Combat state (monsters, hand, energy) |
| `game://map` | Map layout and current position |

## Project Structure

```
slay-the-spire-mcp/
├── server/                 # MCP server (main Python package)
│   ├── src/slay_the_spire_mcp/
│   │   ├── __main__.py     # Entry point
│   │   ├── server.py       # FastMCP setup
│   │   ├── config.py       # Configuration management
│   │   ├── state.py        # Game state manager
│   │   ├── models.py       # Pydantic data models
│   │   ├── tools.py        # MCP tool implementations
│   │   ├── resources.py    # MCP resource implementations
│   │   ├── detection.py    # Decision point detection
│   │   └── mock.py         # Mock mode for testing
│   └── pyproject.toml
├── bridge/                 # Python relay process
│   ├── src/spire_bridge/
│   │   ├── __main__.py     # Entry point
│   │   ├── relay.py        # stdin/stdout <-> TCP relay
│   │   └── protocol.py     # Message framing
│   └── pyproject.toml
├── mod/                    # SpireBridge Java mod (WIP)
├── tests/                  # Integration tests
│   └── fixtures/           # Sample game states
└── docker-compose.yml      # Container orchestration
```

## Development Setup

### Running Tests

```bash
# Server tests
cd server
uv run python -m pytest

# Bridge tests
cd bridge
uv run python -m pytest

# Integration tests (from root)
cd server && uv run python -m pytest ../tests
```

### Type Checking and Linting

```bash
cd server
uv run python -m mypy src      # Type checking
uv run ruff check src          # Lint
uv run ruff format src         # Format code
```

### Development Commands Summary

| Package | Command | Description |
|---------|---------|-------------|
| server | `uv sync` | Install dependencies |
| server | `uv run python -m slay_the_spire_mcp` | Run server |
| server | `uv run python -m pytest` | Run tests |
| bridge | `uv sync` | Install dependencies |
| bridge | `uv run python -m spire_bridge` | Run bridge |
| bridge | `uv run python -m pytest` | Run tests |

## Troubleshooting

### "No game state available"

The MCP server hasn't received any game state from the bridge. Check:
1. Is Slay the Spire running with the SpireBridge mod?
2. Is the bridge process connected to the MCP server?
3. Check logs: `STS_LOG_LEVEL=DEBUG uv run python -m slay_the_spire_mcp`

### Connection Refused on Port 7777

The MCP server isn't listening for bridge connections:
1. Ensure the server is running
2. Check if another process is using port 7777
3. Try a different port: `STS_TCP_PORT=7778 uv run python -m slay_the_spire_mcp`

### Mock Mode Errors

When using mock mode:
1. Ensure `STS_MOCK_FIXTURE` points to a valid JSON file or directory
2. Check the fixture file is valid JSON matching the expected game state schema
3. Use `STS_LOG_LEVEL=DEBUG` to see detailed error messages

### Claude Can't Connect

1. Verify the MCP server is running on port 8000
2. Check your Claude MCP configuration matches the server URL
3. Ensure no firewall is blocking local connections

## Status

Currently in **MVP development**. The foundation supports:
- Game state management and parsing
- MCP tools and resources
- Mock mode for testing without the game
- Terminal output (MVP)

Coming soon:
- In-game overlay rendering
- Full bridge integration
- SpireBridge mod completion

## License

MIT
