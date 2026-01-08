# Architectural Decisions and Research

**Last Updated**: 2026-01-08
**Status**: Historical context for project decisions

This document consolidates research and decision rationale from the project's planning phase. For the authoritative architecture specification, see `mvp-architecture.md`.

---

## 1. Current Project Status

### Overall Health: FAIR (Early MVP with Critical Gaps)

The project has a solid architectural foundation but significant gaps between specification and implementation.

**What's Working**:
- Well-structured monorepo (mod/, bridge/, server/, shared/)
- Solid async Python patterns in bridge/server
- Working stdin->TCP relay with reconnection logic
- Good test infrastructure (pytest, fixtures)

**Critical Gaps**:
- Bidirectional communication incomplete (TCP->stdout missing)
- MCP server is placeholder only
- Java mod cannot compile (dependency JARs not present)
- Shared schemas exist but aren't validated

**Implementation Progress**:
| Phase | Status | Completeness |
|-------|--------|--------------|
| Phase 1: Foundation | Partial | 60% |
| Phase 2: Bridge Communication | Partial | 50% |
| Phase 3: MCP Integration | Not Started | 5% |
| Phase 4: Decision Detection | Not Started | 0% |
| Phase 5: Overlay Foundation | Not Started | 0% |
| Phase 6: Polish | Not Started | 0% |

---

## 2. Key Architectural Decisions

### Decision: Fork CommunicationMod vs Build From Scratch

**Choice**: Fork CommunicationMod as "SpireBridge"

**Rationale**:
- CommunicationMod's state serialization and command handling are battle-tested
- Reimplementing from scratch estimated at 3-6 weeks vs 2-3 weeks for fork
- The codebase is clean (7/10 quality), well-architected with clear separation
- MIT license allows forking freely

**Alternatives Considered**:
1. **Build from scratch (Kotlin)**: 3-6 weeks, higher risk but cleaner design
2. **Fork + Kotlin conversion**: 3-5 weeks, medium risk
3. **Companion mod (no fork)**: Would avoid fork maintenance but limited to triggers, not rich data

**Key Factors**:
- CommunicationMod is dormant (last commit Jan 2023, 3 years stale)
- 27 patches to maintain across game updates
- Heavy coupling to game internals via ReflectionHacks

**Risk Mitigation**: Minimize changes to fork; add only what's needed (overlay capabilities).

---

### Decision: Separate Overlay Mod vs Extending CommunicationMod

**Choice**: Build overlay capability INTO the SpireBridge fork (single mod)

**Rationale**:
- Originally considered a separate overlay mod that coexists with CommunicationMod
- Decided instead to fork CommunicationMod and add overlay features directly
- Single mod simplifies user installation
- Overlay features (WebSocket server, PostRenderSubscriber) integrate cleanly with existing architecture

**Alternatives Considered**:
1. **Companion overlay mod**: No fork needed, but two mods to manage and coordinate
2. **Extend via CommunicationMod PR**: Maintainer dormant (2+ years without merges), PRs unlikely to be accepted
3. **Shared memory/IPC**: More complex, platform-specific

**Key Finding from Research**:
- CommunicationMod has no plugin system or extension points for display logic
- Building a companion mod would still require implementing the same rendering logic
- Fork gives us full control without waiting for upstream

---

### Decision: Bridge Process Architecture

**Choice**: Separate bridge process (Python) relaying between mod stdio and MCP server TCP

**Rationale**:
- CommunicationMod launches external process as subprocess (it's the parent)
- MCP clients expect to launch MCP servers as subprocess
- Cannot be child of both -> need two processes
- Bridge is thin async relay with minimal logic

**Technical Details**:
- Mod launches bridge as subprocess
- Bridge connects to MCP server via TCP (localhost:7777)
- Bridge sends "ready\n" on startup (CommunicationMod protocol)
- Relay is bidirectional: stdin->TCP (game state) and TCP->stdout (commands)

---

### Decision: Overlay Communication Protocol

**Choice**: WebSocket from MCP server to mod (port 31337)

**Rationale**:
- Push-based for immediate overlay updates
- Simple JSON protocol (not JSON-RPC)
- NanoHTTPD provides embedded WebSocket server in single Java file
- Works reliably in StS mod environment (TelnetTheSpire proves TCP works)

**Protocol Format**:
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

### Decision: MCP Transport

**Choice**: Streamable HTTP on port 8000

**Rationale**:
- Allows MCP server to run as independent process
- Works with Claude Desktop MCP client configuration
- Standard HTTP transport is well-supported

---

### Decision: Kotlin Migration Timeline

**Choice**: Start with Java, migrate to Kotlin before v1.0

**Rationale**:
- Java works fine and is proven (CommunicationMod)
- Kotlin offers modern language features, null safety, coroutines
- Exacting mod proves Kotlin works in StS modding environment
- Incremental migration possible (mixed Java/Kotlin compilation)
- Lower initial risk, Kotlin is polish for v1.0

**Prerequisites for Migration**:
- Gradle build system (replace Maven)
- Kotlin plugin configured
- Module-by-module conversion

---

## 3. Technology Stack Decisions

### Mod (SpireBridge)
- **Language**: Java 8 (migrating to Kotlin)
- **Build**: Maven (migrating to Gradle)
- **Dependencies**: ModTheSpire, BaseMod, NanoHTTPD (for WebSocket)
- **Rendering**: libGDX (bundled with StS), PostRenderSubscriber hooks

### Bridge
- **Language**: Python 3.11+
- **Dependencies**: None (pure stdlib) - minimal footprint
- **Pattern**: Async relay with reconnection

### Server
- **Language**: Python 3.11+
- **Framework**: FastMCP
- **Dependencies**: mcp, httpx, starlette, uvicorn
- **Container**: Docker + docker-compose

---

## 4. Prior Art and References

### CommunicationMod Analysis
- **Repository**: https://github.com/ForgottenArbiter/CommunicationMod
- **Quality Score**: 7/10 (professional hobbyist level)
- **Code Size**: ~3,500-4,000 LOC (core + 27 patches)
- **Strengths**: Clean separation (commands, state, UI, patches), simple protocol
- **Weaknesses**: ChoiceScreenUtils is 800-line god class, heavy reflection use

### InfoMod2 Patterns (Overlay Reference)
- Demonstrates PostRenderSubscriber usage
- Shows non-intrusive UI overlay rendering
- Provides patterns for card/relic badge positioning

### Exacting (Kotlin Reference)
- Proves Kotlin viable for StS modding
- Shows Gradle + Kotlin build configuration
- 85% Kotlin, 15% Java composition

---

## 5. Lessons Learned

### Issue #13: Bidirectional Communication Gap

**Problem**: Tests specified stdin->TCP relay but forgot TCP->stdout. Tests passed but feature was half-implemented.

**Root Cause**:
- One-directional thinking in test design
- No bidirectional integration test
- Incomplete acceptance criteria

**Prevention Strategies**:
1. For any communication channel, always test both directions
2. Every component interface needs full round-trip integration test
3. Map each architecture requirement to at least one test

**Checklist for Future Issues**:
- [ ] Bidirectional: If data goes in, does it also come out?
- [ ] Start and End: If we detect start, do we detect end?
- [ ] Integration: Component talks to its neighbors correctly?
- [ ] Full pipeline: Data flows from source to destination?

---

## 6. Risk Register Summary

### Critical Risks
| Risk | Mitigation |
|------|------------|
| Mod cannot build without external JARs | Document JAR acquisition, consider Maven repository |
| Bidirectional communication incomplete | Implement TCP->stdout in bridge |
| CommunicationMod patches break on StS update | Track game updates, test quickly |

### High Risks
| Risk | Mitigation |
|------|------------|
| Decision detection not implemented | Must be done for MVP |
| NanoHTTPD in StS environment | Test early, fallback to file-based |
| Overlay performance | Cache renders, profile early |

---

## Document History

This document consolidates findings from:
- `communicationmod-audit.md` - CommunicationMod fork viability analysis
- `overlay-approach.md` - Overlay implementation strategy research
- `mod-from-scratch.md` - Build vs fork analysis
- `full-project-audit.md` - Project status audit (executive summary)
- `requirements-gap-analysis.md` - Test coverage gap analysis (key findings)
- `acceptance-test-audit.md` - Issue-by-issue test coverage review

Original documents archived: 2026-01-08
