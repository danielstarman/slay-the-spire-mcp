# Configuration Reference

All MCP server settings are configured via environment variables with the `STS_` prefix. This document provides a complete reference.

**Last Updated**: 2026-01-09

---

## Environment Variables

### Network Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STS_TCP_HOST` | string | `127.0.0.1` | Host address for bridge TCP connection |
| `STS_TCP_PORT` | int | `7777` | Port for bridge TCP connection |
| `STS_HTTP_PORT` | int | `8000` | Port for MCP HTTP server (Claude connects here) |
| `STS_WS_PORT` | int | `31337` | Port for WebSocket overlay communication |

### Transport Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STS_TRANSPORT` | string | `http` | MCP transport type: `http` or `stdio` |

- **http**: Streamable HTTP transport on `STS_HTTP_PORT`. Use for Claude Desktop.
- **stdio**: Standard input/output transport. Use when launched as subprocess.

### Logging Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STS_LOG_LEVEL` | string | `INFO` | Logging verbosity level |

Valid log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

### Mock Mode Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STS_MOCK_MODE` | bool | `false` | Enable mock mode (testing without the game) |
| `STS_MOCK_FIXTURE` | string | - | Path to fixture file or directory (required if mock mode enabled) |
| `STS_MOCK_DELAY_MS` | int | `100` | Delay between states when replaying a sequence (milliseconds) |

---

## Configuration Methods

### Method 1: Environment Variables

Set variables directly in your shell:

```bash
# Bash/Zsh
export STS_LOG_LEVEL=DEBUG
export STS_TCP_PORT=7778
uv run python -m slay_the_spire_mcp

# Or inline
STS_LOG_LEVEL=DEBUG uv run python -m slay_the_spire_mcp
```

```powershell
# PowerShell
$env:STS_LOG_LEVEL = "DEBUG"
$env:STS_TCP_PORT = "7778"
uv run python -m slay_the_spire_mcp
```

### Method 2: .env File

Create a `.env` file in the `server/` directory:

```bash
# server/.env
STS_LOG_LEVEL=DEBUG
STS_TCP_PORT=7777
STS_HTTP_PORT=8000
STS_WS_PORT=31337
```

The server automatically loads this file on startup.

### Method 3: Docker Environment

In `docker-compose.yml`, set variables under `environment`:

```yaml
services:
  server:
    environment:
      - STS_TCP_HOST=0.0.0.0
      - STS_TCP_PORT=7777
      - STS_HTTP_PORT=8000
      - STS_LOG_LEVEL=INFO
```

---

## Configuration Examples

### Development Mode

Verbose logging for debugging:

```bash
STS_LOG_LEVEL=DEBUG \
STS_HTTP_PORT=8000 \
uv run python -m slay_the_spire_mcp
```

### Mock Mode for Testing

Test with sample game states without running the game:

```bash
# Single fixture file
STS_MOCK_MODE=true \
STS_MOCK_FIXTURE=../tests/fixtures/game_states/combat_basic.json \
uv run python -m slay_the_spire_mcp

# Directory of fixtures (cycles through states)
STS_MOCK_MODE=true \
STS_MOCK_FIXTURE=../tests/fixtures/game_states/ \
STS_MOCK_DELAY_MS=500 \
uv run python -m slay_the_spire_mcp
```

### Alternative Port Configuration

If default ports conflict with other services:

```bash
STS_TCP_PORT=7778 \
STS_HTTP_PORT=8001 \
STS_WS_PORT=31338 \
uv run python -m slay_the_spire_mcp
```

### Docker Production Mode

```bash
docker-compose up server
```

Uses settings from `docker-compose.yml`:
- TCP host bound to `0.0.0.0` (accepts external connections)
- Standard ports (7777, 8000, 31337)
- INFO log level

### Docker Mock Mode

```bash
docker-compose --profile mock up server-mock
```

Mounts `tests/fixtures/game_states/` as fixture directory.

---

## Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| **7777** | TCP | Bridge connection (game mod -> server) |
| **8000** | HTTP | MCP server (Claude -> server) |
| **31337** | WebSocket | Overlay updates (server -> game mod) |

### Port Conflicts

If a port is already in use:

1. Check what's using it:
   ```bash
   # Linux/macOS
   lsof -i :7777

   # Windows (PowerShell)
   netstat -ano | findstr :7777
   ```

2. Either stop the conflicting process or configure a different port via `STS_TCP_PORT`, `STS_HTTP_PORT`, or `STS_WS_PORT`.

---

## Validation

Configuration is validated on startup using Pydantic. Invalid values produce clear error messages:

```
pydantic_settings.ValidationError: 1 validation error for Config
tcp_port
  Input should be greater than or equal to 1 [type=greater_than_equal, input_value=-1]
```

### Mock Mode Validation

When `STS_MOCK_MODE=true`, `STS_MOCK_FIXTURE` must also be set:

```
ValueError: mock_fixture must be set when mock_mode is enabled.
Set STS_MOCK_FIXTURE environment variable.
```

---

## Programmatic Configuration

For testing or embedding, create a `Config` object directly:

```python
from slay_the_spire_mcp.config import Config, set_config

# Create custom config
test_config = Config(
    tcp_port=8888,
    mock_mode=True,
    mock_fixture="path/to/fixture.json",
    log_level="DEBUG"
)

# Use it
set_config(test_config)
```

---

## Related Documentation

- [Installation Guide](installation.md) - Getting started
- [Troubleshooting](troubleshooting.md) - Common issues
- [Architecture Decisions](architecture-decisions.md) - Design rationale
