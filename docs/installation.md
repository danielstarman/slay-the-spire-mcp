# Installation Guide

This guide walks through installing and configuring the Slay the Spire MCP server, which enables Claude to analyze your gameplay in real-time.

**Last Updated**: 2026-01-09

---

## Prerequisites

Before installation, ensure you have:

### Required Software

| Requirement | Minimum Version | Installation |
|-------------|-----------------|--------------|
| **Python** | 3.10+ | [python.org/downloads](https://www.python.org/downloads/) |
| **uv** | Latest | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **Slay the Spire** | Any | Steam or GOG |

### Mod Requirements

The game needs modding support enabled:

1. **ModTheSpire** - Mod loader for Slay the Spire
2. **BaseMod** - Core modding library
3. **SpireBridge** - Bridge mod (included in this project)

> **Note**: SpireBridge is a fork of CommunicationMod specifically for this project.

---

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/yourrepo/slay-the-spire-mcp.git
cd slay-the-spire-mcp
```

### 2. Install the MCP Server

The MCP server is the main Python package that Claude connects to.

```bash
cd server
uv sync
```

This creates a virtual environment and installs all dependencies (mcp, pydantic, websockets, etc.).

### 3. Install the Bridge

The bridge relays communication between the game mod and the MCP server.

```bash
cd bridge
uv sync
```

### 4. Install SpireBridge Mod

> **Status**: The SpireBridge mod is currently in development. These are placeholder instructions.

1. Build the mod JAR:
   ```bash
   cd mod
   mvn package
   ```

2. Copy the JAR to your Slay the Spire mods folder:
   - **Windows**: `%LOCALAPPDATA%\ModTheSpire\mods\`
   - **macOS**: `~/Library/Application Support/Steam/steamapps/common/SlayTheSpire/mods/`
   - **Linux**: `~/.local/share/Steam/steamapps/common/SlayTheSpire/mods/`

3. Enable the mod in ModTheSpire launcher

### 5. Verify Installation

Test that the server runs correctly:

```bash
cd server
uv run python -m slay_the_spire_mcp --help
```

You should see the server help output.

---

## Running the Server

### Option A: Direct Execution

```bash
cd server
uv run python -m slay_the_spire_mcp
```

The server starts on:
- **HTTP (MCP)**: port 8000
- **TCP (Bridge)**: port 7777
- **WebSocket (Overlay)**: port 31337

### Option B: Docker (Recommended for Production)

```bash
docker-compose up server
```

For mock mode (testing without the game):

```bash
docker-compose --profile mock up server-mock
```

---

## Claude Configuration

### Claude Desktop

Add the MCP server to your Claude Desktop configuration file.

**Location**:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Configuration**:

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

### Claude Code (CLI)

Add to your MCP settings file or configure via the CLI:

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

### Verifying Connection

After configuration:

1. Start the MCP server
2. Open Claude Desktop or Claude Code
3. Check that "slay-the-spire" appears in available MCP tools
4. Try calling `get_game_state` - it should respond (even without the game connected)

---

## Testing with Mock Mode

You can test the full setup without running Slay the Spire:

```bash
cd server
STS_MOCK_MODE=true STS_MOCK_FIXTURE=../tests/fixtures/game_states/combat_basic.json \
  uv run python -m slay_the_spire_mcp
```

This loads a sample game state for testing Claude's analysis capabilities.

See [Configuration](configuration.md) for more mock mode options.

---

## Next Steps

- [Configuration Reference](configuration.md) - Environment variables and settings
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [Architecture Decisions](architecture-decisions.md) - Understanding the design
