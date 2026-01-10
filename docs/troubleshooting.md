# Troubleshooting Guide

Common issues and their solutions when running the Slay the Spire MCP server.

**Last Updated**: 2026-01-09

---

## Quick Diagnostic Commands

Before diving into specific issues, these commands help diagnose problems:

```bash
# Check if server is running
curl http://localhost:8000/health 2>/dev/null || echo "Server not responding"

# Check if ports are in use
# Linux/macOS
lsof -i :7777 -i :8000 -i :31337

# Windows (PowerShell)
netstat -ano | findstr "7777 8000 31337"

# Run with debug logging
STS_LOG_LEVEL=DEBUG uv run python -m slay_the_spire_mcp
```

---

## Connection Issues

### "No game state available"

**Symptom**: Claude reports no game state, or `get_game_state` returns empty/null.

**Cause**: The MCP server hasn't received any game state from the bridge.

**Solutions**:

1. **Check if the game is running**:
   - Is Slay the Spire running?
   - Is the SpireBridge mod enabled in ModTheSpire?

2. **Check if the bridge is connected**:
   - Look for "Bridge connected" in server logs
   - Run with `STS_LOG_LEVEL=DEBUG` for detailed connection info

3. **Verify the game is in a state that sends data**:
   - The mod only sends state at "stable" moments (after entering a room, combat ready, etc.)
   - Try navigating to a new room or starting combat

4. **Check network connectivity**:
   ```bash
   # Test if server is listening on TCP port
   nc -zv localhost 7777
   ```

### "State may be stale" Warning

**Symptom**: Claude mentions state might be outdated.

**Cause**: The bridge connection was lost or hasn't sent updates recently.

**Solutions**:

1. Check if the game is still running
2. Check if the bridge process is still running
3. The game may be in a transitional state (loading, animations)
4. Navigate to a new room to trigger a state update

### "Address already in use" on Port 7777

**Symptom**: Server fails to start with "Address already in use" error.

**Cause**: Another process is using port 7777, often a zombie server from a previous run.

**Solutions**:

1. **Find and kill the existing process**:
   ```bash
   # Linux/macOS
   lsof -i :7777
   kill <PID>

   # Windows (PowerShell) - find process
   netstat -ano | findstr :7777
   # Then kill by PID
   taskkill /PID <PID> /F
   ```

2. **Use a different port**:
   ```bash
   STS_TCP_PORT=7778 uv run python -m slay_the_spire_mcp
   ```

3. **Wait and retry**: The OS may need a few seconds to release the port after a crash.

> **Note**: Recent versions include automatic cleanup of zombie processes on startup.

### "Connection refused" Errors

**Symptom**: Bridge or Claude can't connect to the server.

**Cause**: Server isn't running, or firewall is blocking connections.

**Solutions**:

1. **Verify server is running**:
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check server logs** for startup errors

3. **Check firewall settings**:
   - Windows Firewall may block new ports
   - Allow Python through the firewall, or add port exceptions

4. **Verify correct port configuration**:
   - Claude config must match `STS_HTTP_PORT` (default: 8000)
   - Bridge must connect to `STS_TCP_PORT` (default: 7777)

---

## Mock Mode Issues

### "mock_fixture must be set when mock_mode is enabled"

**Symptom**: Server fails to start in mock mode.

**Cause**: `STS_MOCK_MODE=true` but `STS_MOCK_FIXTURE` not set.

**Solution**: Provide a fixture path:

```bash
STS_MOCK_MODE=true \
STS_MOCK_FIXTURE=../tests/fixtures/game_states/combat_basic.json \
uv run python -m slay_the_spire_mcp
```

### "Fixture file not found" or Invalid JSON

**Symptom**: Server fails with file not found or JSON parse errors.

**Solutions**:

1. **Check the path exists**:
   ```bash
   ls -la ../tests/fixtures/game_states/
   ```

2. **Use absolute path** if relative paths cause issues:
   ```bash
   STS_MOCK_FIXTURE=/full/path/to/fixture.json
   ```

3. **Validate the JSON**:
   ```bash
   python -m json.tool < fixture.json
   ```

### Mock State Not Updating

**Symptom**: Same state returned repeatedly in mock mode.

**Cause**: Single fixture file only provides one state.

**Solution**: Use a directory of fixtures for sequence replay:

```bash
STS_MOCK_FIXTURE=../tests/fixtures/game_states/ \
STS_MOCK_DELAY_MS=1000 \
uv run python -m slay_the_spire_mcp
```

---

## Claude Connection Issues

### Claude Can't Find the MCP Server

**Symptom**: "slay-the-spire" doesn't appear in Claude's MCP tools.

**Solutions**:

1. **Verify MCP configuration**:
   - Check config file location (see [Installation Guide](installation.md))
   - Ensure JSON is valid
   - Restart Claude Desktop after config changes

2. **Verify server is running** and accessible on port 8000

3. **Check URL matches**:
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

### Claude Gets Errors Calling Tools

**Symptom**: Claude sees the server but tool calls fail.

**Solutions**:

1. **Check server logs** for error details (run with `STS_LOG_LEVEL=DEBUG`)

2. **Verify game is connected** for action tools (play_card, etc.)

3. **Test with read-only tools first** (`get_game_state`)

---

## Mod Issues

### SpireBridge Mod Not Loading

**Symptom**: Game runs but mod doesn't work.

**Solutions**:

1. **Verify mod is enabled** in ModTheSpire
2. **Check mod dependencies** (BaseMod must be installed)
3. **Check ModTheSpire logs** for errors
4. **Verify JAR is in correct location** (see [Installation Guide](installation.md))

### Bridge Process Not Starting

**Symptom**: Game runs, mod loads, but bridge doesn't connect.

**Solutions**:

1. **Check mod configuration** for bridge path
2. **Verify Python is in PATH**
3. **Check mod logs** for subprocess errors
4. **Try running bridge manually**:
   ```bash
   cd bridge
   uv run python -m spire_bridge
   ```

---

## Performance Issues

### High CPU Usage

**Symptom**: Server using excessive CPU.

**Solutions**:

1. **Check log level**: DEBUG logging is expensive
   ```bash
   STS_LOG_LEVEL=INFO  # or WARNING
   ```

2. **Check for connection loops**: Bridge reconnecting rapidly

### Memory Growth

**Symptom**: Server memory usage increases over time.

**Solutions**:

1. **Restart periodically** for long sessions
2. **Check for state accumulation** (future runs should be independent)

---

## Getting Help

If these solutions don't help:

1. **Gather diagnostic info**:
   ```bash
   # Server version and config
   uv run python -m slay_the_spire_mcp --version

   # Full debug logs
   STS_LOG_LEVEL=DEBUG uv run python -m slay_the_spire_mcp 2>&1 | tee debug.log
   ```

2. **Check GitHub Issues** for similar problems

3. **Open a new issue** with:
   - Operating system and Python version
   - Steps to reproduce
   - Relevant log output
   - Configuration (redact any sensitive info)

---

## Related Documentation

- [Installation Guide](installation.md) - Setup instructions
- [Configuration Reference](configuration.md) - All settings
- [Architecture Decisions](architecture-decisions.md) - Understanding the design
