# Architecture Decision Records

This document captures key architectural decisions and their rationale. Understanding *why* decisions were made helps future contributors avoid re-debating settled issues and provides context for the codebase's structure.

**Last Updated**: 2026-01-09

---

## ADR-001: Fork CommunicationMod vs Build From Scratch

**Status**: Accepted
**Date**: 2025-12 (project inception)

### Decision

Fork CommunicationMod as "SpireBridge" rather than building a mod from scratch.

### Context

We need a mod that serializes Slay the Spire game state and accepts commands. CommunicationMod already does this.

### Options Considered

1. **Build from scratch (Kotlin)**: 3-6 weeks, higher risk but cleaner design
2. **Fork CommunicationMod**: 2-3 weeks, battle-tested code
3. **Fork + Kotlin conversion**: 3-5 weeks, medium risk
4. **Companion mod (no fork)**: Limited to triggers, not rich data

### Rationale

- CommunicationMod's state serialization and command handling are battle-tested
- The codebase is clean (7/10 quality), well-architected with clear separation
- MIT license allows forking freely
- Estimated 1-3 weeks faster than from-scratch

### Risks

- CommunicationMod is dormant (last commit Jan 2023)
- 27 patches to maintain across game updates
- Heavy coupling to game internals via ReflectionHacks

### Mitigation

Minimize changes to fork; add only what's needed (overlay capabilities).

---

## ADR-002: Bridge Process Architecture

**Status**: Accepted
**Date**: 2025-12

### Decision

Use a separate Python bridge process relaying between mod stdio and MCP server TCP.

### Context

- CommunicationMod launches external processes as subprocess (mod is parent)
- MCP clients expect to launch MCP servers as subprocess
- A single process cannot be a child of both

### Solution

```
Mod (parent) → Bridge (child) → [TCP] → MCP Server (independent)
```

- Mod launches bridge as subprocess
- Bridge connects to MCP server via TCP (localhost:7777)
- Bridge sends "ready\n" on startup (CommunicationMod protocol requirement)
- Relay is bidirectional: stdin→TCP (game state) and TCP→stdout (commands)

### Consequences

- Two Python processes instead of one
- Extra hop adds minimal latency (<1ms local TCP)
- Bridge is thin async relay (~200 LOC)

---

## ADR-003: Overlay Communication Protocol

**Status**: Accepted
**Date**: 2025-12

### Decision

WebSocket from MCP server to mod (port 31337) for overlay updates.

### Context

The mod needs to receive analysis results to render an in-game overlay with Claude's recommendations.

### Options Considered

1. **WebSocket push**: Real-time, bidirectional
2. **HTTP polling**: Simpler but latency issues
3. **Shared file**: No network but complex synchronization
4. **Extend stdio protocol**: Would complicate bridge

### Rationale

- Push-based for immediate overlay updates
- Simple JSON protocol (not JSON-RPC)
- NanoHTTPD provides embedded WebSocket server in single Java file
- TelnetTheSpire proves TCP works reliably in StS mod environment

### Protocol Format

```json
{
  "type": "analysis",
  "decision_type": "CARD_REWARD",
  "options": [
    {"name": "Strike", "pct": 15},
    {"name": "Pommel Strike", "pct": 73}
  ],
  "commentary": "Pommel Strike gives draw, which we need.",
  "skip_pct": 0
}
```

---

## ADR-004: MCP Transport

**Status**: Accepted
**Date**: 2025-12

### Decision

Streamable HTTP on port 8000 for MCP protocol.

### Rationale

- Allows MCP server to run as independent process
- Works with Claude Desktop MCP client configuration
- Standard HTTP transport is well-supported by MCP SDK

---

## ADR-005: Kotlin Migration Timeline

**Status**: Planned
**Date**: 2025-12

### Decision

Start with Java, migrate to Kotlin before v1.0.

### Rationale

- Java works fine and is proven (CommunicationMod)
- Kotlin offers modern language features, null safety, coroutines
- Exacting mod proves Kotlin works in StS modding environment
- Lower initial risk; Kotlin migration is polish for v1.0

### Prerequisites

- Gradle build system (replace Maven)
- Kotlin plugin configured
- Module-by-module conversion

---

## Lessons Learned

### Issue #13: Bidirectional Communication Gap

**Problem**: Tests specified stdin→TCP relay but forgot TCP→stdout. Tests passed but feature was half-implemented.

**Root Cause**:
- One-directional thinking in test design
- No bidirectional integration test
- Incomplete acceptance criteria

**Prevention Checklist** (now in architect.md):
- [ ] Bidirectional: If data goes in, does it also come out?
- [ ] Start and End: If we detect start, do we detect end?
- [ ] Integration: Component talks to its neighbors correctly?
- [ ] Full pipeline: Data flows from source to destination?

---

## Technology Stack

| Component | Language | Key Dependencies |
|-----------|----------|------------------|
| **Mod (SpireBridge)** | Java 8 → Kotlin | ModTheSpire, BaseMod, NanoHTTPD |
| **Bridge** | Python 3.10+ | None (pure stdlib) |
| **Server** | Python 3.10+ | FastMCP, pydantic, uvicorn |

---

## References

- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) - Original mod we forked
- [InfoMod2](https://github.com/Skrelpoid/InfoMod2) - Overlay rendering patterns
- [Exacting](https://github.com/JohnnyBazooka89/StSExacting) - Kotlin modding reference
