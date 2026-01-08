# Architecture Plan: Slay the Spire MCP Server

**Status**: Finalized after interview
**Date**: 2026-01-07

---

## 1. Vision

An MCP server that lets Claude watch Slay the Spire gameplay and provide automatic strategic commentary. Claude sees the live game state, analyzes decision points, and displays preference percentages + concise commentary. This is an advisory co-pilot, not an AI that plays for you.

**North Star**: In-game overlay showing Claude's percentages on cards/relics/paths.
**MVP**: Terminal output with same analysis.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SLAY THE SPIRE                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    SpireBridge Mod (Java/Kotlin)                     │   │
│  │                    (Fork of CommunicationMod)                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────────┐ │   │
│  │  │ State       │  │ WebSocket   │  │ Overlay Renderer             │ │   │
│  │  │ Serializer  │  │ Server      │──│ (PostRenderSubscriber)       │ │   │
│  │  │ (JSON)      │  │ (NanoHTTPD) │  │ - Card badges (%)            │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  │ - Commentary panel           │ │   │
│  │         │                │         │ - Toggle button              │ │   │
│  │         │                │         └──────────────────────────────┘ │   │
│  └─────────┼────────────────┼──────────────────────────────────────────┘   │
└────────────┼────────────────┼───────────────────────────────────────────────┘
             │ stdin/stdout   │ WebSocket (:31337)
             │ (JSON)         │ (display commands)
             ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Bridge Process (Python)                            │
│                           slay-the-spire-mcp/bridge/                         │
│  - Launched by SpireBridge mod as subprocess                                 │
│  - Relays game state to MCP server via TCP                                   │
│  - Thin async relay, minimal logic                                           │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ TCP localhost:7777
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MCP Server (Python)                                │
│                           slay-the-spire-mcp/server/                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         FastMCP Server                                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │   │
│  │  │  Tools     │  │ Resources  │  │  Prompts   │  │ State Manager  │  │   │
│  │  │ get_state  │  │ slay://    │  │ analyze_*  │  │ (singleton)    │  │   │
│  │  │ get_deck   │  │ subscribe  │  │            │  │                │  │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Bridge Handler (TCP :7777)  │  Overlay Pusher (WS to mod :31337)    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Terminal UI (MVP) - Simple list output with percentages             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ MCP Protocol
                                 │ (Streamable HTTP :8000)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Claude (MCP Client)                             │
│  - Subscribes to slay://state resource                                       │
│  - Receives decision point notifications                                     │
│  - Analyzes and returns percentages + commentary                             │
│  - Concise output (1-2 sentences)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Repository Structure (Monorepo with Separation)

```
slay-the-spire-mcp/
├── README.md
├── CLAUDE.md
├── docker-compose.yml           # Orchestrates Python services
├── .claude/
│   ├── agents/
│   ├── skills/
│   ├── plans/
│   └── locks/
│
├── mod/                         # SpireBridge - Java/Kotlin StS mod
│   ├── pom.xml                  # Maven build (migrating to Gradle+Kotlin)
│   ├── src/main/java/
│   │   └── spirebridge/
│   │       ├── SpireBridge.java          # Main mod entry point
│   │       ├── state/
│   │       │   ├── GameStateConverter.java
│   │       │   ├── GameStateListener.java
│   │       │   └── ChoiceScreenUtils.java
│   │       ├── command/
│   │       │   └── CommandExecutor.java
│   │       ├── network/
│   │       │   ├── WebSocketServer.java   # NanoHTTPD
│   │       │   └── OverlayProtocol.java
│   │       ├── overlay/
│   │       │   ├── OverlayManager.java
│   │       │   ├── OverlayRenderer.java   # PostRenderSubscriber
│   │       │   ├── CardBadge.java
│   │       │   └── ToggleButton.java
│   │       ├── io/
│   │       │   ├── DataReader.java
│   │       │   └── DataWriter.java
│   │       └── patches/                   # SpirePatch files
│   └── src/main/resources/
│       └── ModTheSpire.json
│
├── bridge/                      # Python bridge process
│   ├── pyproject.toml           # Standalone, minimal deps
│   └── src/
│       └── spire_bridge/
│           ├── __init__.py
│           ├── __main__.py      # Entry point (launched by mod)
│           ├── relay.py         # stdin/stdout ↔ TCP relay
│           └── protocol.py      # Message framing
│
├── server/                      # Python MCP server
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/
│       └── slay_the_spire_mcp/
│           ├── __init__.py
│           ├── __main__.py      # Entry point
│           ├── server.py        # FastMCP setup
│           ├── state.py         # GameStateManager
│           ├── models.py        # Data models (Card, Relic, etc.)
│           ├── tools.py         # MCP tools
│           ├── resources.py     # MCP resources
│           ├── prompts.py       # MCP prompts
│           ├── detection.py     # Decision point detection
│           ├── context.py       # Run context tracking
│           ├── overlay.py       # Push analysis to mod
│           └── terminal.py      # MVP terminal output
│
├── shared/                      # Shared schemas/contracts
│   ├── schemas/
│   │   ├── game_state.json      # JSON schema for game state
│   │   └── overlay.json         # JSON schema for overlay commands
│   └── card_database/
│       └── cards.json           # Static card data
│
└── tests/
    ├── fixtures/
    │   └── game_states/         # Sample JSON states
    ├── test_models.py
    ├── test_state.py
    └── test_detection.py
```

---

## 4. Component Responsibilities

### 4.1 SpireBridge Mod (`mod/`)

**Language**: Java initially, migrating to Kotlin before v1.0

**Responsibilities**:
- Fork of CommunicationMod with added capabilities
- Serialize game state to JSON (existing)
- Detect stable game states (existing)
- Execute commands from external process (existing)
- **NEW**: WebSocket server for receiving overlay commands
- **NEW**: Render overlay badges on cards/relics
- **NEW**: Toggle button to show/hide overlay

**Key Files**:
| File | Purpose |
|------|---------|
| `SpireBridge.java` | Entry point, BaseMod hooks |
| `GameStateConverter.java` | State → JSON (from CommunicationMod) |
| `WebSocketServer.java` | NanoHTTPD WebSocket listener |
| `OverlayRenderer.java` | PostRenderSubscriber for drawing |
| `CardBadge.java` | Renders "73%" on cards |

### 4.2 Bridge Process (`bridge/`)

**Language**: Python

**Responsibilities**:
- Launched by SpireBridge mod as subprocess
- Send "ready\n" on startup (CommunicationMod protocol)
- Relay game state JSON from stdin → TCP socket
- Relay commands from TCP socket → stdout
- Thin, minimal logic - just async relay

**Why separate from server?**
- CommunicationMod launches us as subprocess (it's the parent)
- MCP clients expect to launch MCP servers as subprocess
- Can't be child of both → two processes

### 4.3 MCP Server (`server/`)

**Language**: Python

**Responsibilities**:
- Expose MCP protocol via Streamable HTTP (:8000)
- Accept bridge connection on TCP (:7777)
- Maintain game state singleton
- Detect decision points, track run context
- Push analysis to mod via WebSocket (:31337)
- MVP: Terminal output

**Key Files**:
| File | Purpose |
|------|---------|
| `server.py` | FastMCP setup, HTTP transport |
| `state.py` | GameStateManager singleton |
| `models.py` | Card, Relic, Monster dataclasses |
| `detection.py` | Decision point identification |
| `context.py` | Run timeline tracking |
| `overlay.py` | WebSocket client to push to mod |
| `terminal.py` | MVP terminal output |

### 4.4 Shared (`shared/`)

**Purpose**: Contracts between components

- `game_state.json` - Schema for state JSON from mod
- `overlay.json` - Schema for overlay commands to mod
- `cards.json` - Static card database for Claude reference

---

## 5. Data Flow Scenarios

### 5.1 Startup

```
1. User runs: docker-compose up
   → MCP server starts, listens on :8000 (MCP), :7777 (bridge)

2. User launches Slay the Spire with SpireBridge mod
   → Mod reads config, launches bridge subprocess
   → Bridge sends "ready\n" to stdout
   → Bridge connects to MCP server on :7777
   → Mod starts WebSocket server on :31337

3. MCP server connects to mod's WebSocket (:31337)
   → Ready to push overlay commands

4. User configures Claude with MCP server
   → Claude subscribes to slay://state resource
```

### 5.2 Decision Point Flow

```
Game reaches card reward screen
        │
        ▼
SpireBridge detects stable state
        │
        ▼ stdout (JSON)
Bridge receives state, relays to MCP server
        │
        ▼ TCP :7777
MCP Server:
  1. Parse state
  2. Detect: new decision point (CARD_REWARD)
  3. Record in run context
  4. Notify Claude via resource subscription
        │
        ▼ MCP Protocol
Claude:
  1. Analyzes deck, relics, options
  2. Returns percentages + commentary
        │
        ▼
MCP Server:
  1. Format for terminal (MVP): print to stdout
  2. Format for overlay: push via WebSocket
        │
        ▼ WebSocket :31337
SpireBridge Mod:
  1. OverlayManager receives analysis
  2. OverlayRenderer draws badges on cards
```

### 5.3 User Makes Choice Before Analysis Complete

```
Claude is mid-analysis...
        │
User picks a card in game
        │
        ▼
SpireBridge sends new state (screen changed)
        │
        ▼
MCP Server:
  1. Detect: decision point changed
  2. Cancel pending analysis
  3. Clear overlay
  4. Process new state
```

---

## 6. Protocol Specifications

### 6.1 Bridge ↔ MCP Server (TCP :7777)

**Game state** (mod → bridge → server):
```json
{
  "type": "state",
  "data": {
    "in_game": true,
    "screen_type": "CARD_REWARD",
    "floor": 5,
    "act": 1,
    "hp": 65,
    "max_hp": 80,
    "gold": 99,
    "deck": [...],
    "relics": [...],
    "potions": [...],
    "choice_list": ["Strike", "Pommel Strike", "Anger"],
    "seed": 123456789,
    ...
  }
}
```

**Commands** (server → bridge → mod):
```json
{
  "type": "command",
  "command": "CHOOSE 1"
}
```

### 6.2 MCP Server → Mod Overlay (WebSocket :31337)

**Simple JSON** (not JSON-RPC):

```json
{
  "type": "analysis",
  "decision_type": "CARD_REWARD",
  "options": [
    {"name": "Strike", "pct": 15},
    {"name": "Pommel Strike", "pct": 73},
    {"name": "Anger", "pct": 12}
  ],
  "commentary": "Pommel Strike gives draw, which we need.",
  "skip_pct": 0
}
```

**Clear overlay**:
```json
{
  "type": "clear"
}
```

### 6.3 MCP Tools

```python
@mcp.tool()
async def get_state() -> dict:
    """Get full game state"""

@mcp.tool()
async def get_deck() -> list[dict]:
    """Get current deck contents"""

@mcp.tool()
async def get_map() -> dict | None:
    """Get map data with paths"""

@mcp.tool()
async def get_run_context() -> dict | None:
    """Get run timeline: decisions made, deck evolution"""
```

### 6.4 MCP Resources

```python
@mcp.resource("slay://state")
async def state_resource() -> str:
    """Current game state (subscribable)"""

@mcp.resource("slay://deck")
async def deck_resource() -> str:
    """Current deck"""

@mcp.resource("slay://run")
async def run_resource() -> str:
    """Run context and history"""
```

---

## 7. Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mod approach | Fork CommunicationMod | Hard problems solved, 2-3 weeks vs 3-6 |
| Mod language | Java → Kotlin (north star) | Start with working Java, convert before v1.0 |
| Mod name | SpireBridge | Emphasizes bridge/connection role |
| Repo structure | Monorepo with separation | `mod/`, `bridge/`, `server/`, `shared/` |
| Bridge ↔ Server | TCP localhost:7777 | Cross-platform, debuggable |
| Server → Mod | WebSocket :31337 | Push-based, simple JSON |
| MCP transport | Streamable HTTP :8000 | Allows independent server process |
| Overlay protocol | Simple JSON | No need for JSON-RPC complexity |
| MVP output | Terminal | Simplest first, overlay is north star |
| Card badges | Percentage only | "73%" - minimal, clean |
| Overlay toggle | In-game button | User can hide when not wanted |
| Run context | Memory only | No disk persistence, reset on char select |
| Commentary | Concise (1-2 sentences) | Quick take, not lengthy analysis |
| Percentages | Claude decides freely | No rigid formula |
| Game knowledge | Card database | Accurate stats, Claude reasons freely |
| Characters | All four base | Ironclad, Silent, Defect, Watcher |
| Seed | Visible to Claude | For reproducibility discussions |
| Docker | Yes | For Python services |

---

## 8. Implementation Phases

### Phase 1: Foundation
- [ ] Fork CommunicationMod as SpireBridge
- [ ] Set up monorepo structure (`mod/`, `bridge/`, `server/`)
- [ ] Verify SpireBridge builds and works unchanged
- [ ] Create bridge Python package with relay logic
- [ ] Create server Python package skeleton
- [ ] Docker + docker-compose setup

### Phase 2: Bridge Communication
- [ ] Implement bridge stdin → TCP relay
- [ ] Implement server TCP listener
- [ ] State flows from game → bridge → server
- [ ] Test with mock game states

### Phase 3: MCP Integration
- [ ] FastMCP server setup with Streamable HTTP
- [ ] Implement tools: get_state, get_deck, get_map
- [ ] Implement resources: slay://state, slay://deck
- [ ] Test with Claude as MCP client

### Phase 4: Decision Detection
- [ ] Implement decision point detection
- [ ] Implement run context tracking
- [ ] MCP resource subscription notifications
- [ ] Terminal output (MVP)

### Phase 5: Overlay Foundation
- [ ] Add NanoHTTPD WebSocket to SpireBridge
- [ ] Implement OverlayRenderer (PostRenderSubscriber)
- [ ] Card badge rendering (percentage only)
- [ ] Toggle button
- [ ] Server → mod WebSocket push

### Phase 6: Polish
- [ ] Error handling throughout
- [ ] Card database integration
- [ ] Configuration (env vars, mod config)
- [ ] Documentation
- [ ] Testing

### Phase 7: Kotlin Migration (Pre-v1.0)
- [ ] Set up Gradle + Kotlin build
- [ ] Convert incrementally, module by module
- [ ] Full Kotlin before v1.0 release

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CommunicationMod patches break on StS update | High | Track game updates, test quickly |
| NanoHTTPD in StS environment | Medium | Test early, fallback to file-based |
| Overlay performance | Medium | Cache renders, profile early |
| Kotlin conversion takes longer | Low | Java works fine, Kotlin is polish |
| Two-mod confusion for users | Low | Clear docs, consider bundled installer |
| Claude analysis too slow | Medium | Cancel on state change, show "thinking" |

---

## 10. Open Items (Post-Interview)

- [ ] Commentary placement in overlay (prototype and iterate)
- [ ] Exact card badge positioning (over card? corner?)
- [ ] Map path highlighting design
- [ ] Relic badge design
- [ ] Settings/config UI in mod

---

## 11. References

- [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) - Fork base
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [BaseMod Hooks](https://github.com/daviscook477/BaseMod/wiki/Hooks)
- [InfoMod2](https://github.com/casey-c/infomod2) - Overlay patterns
- [NanoHTTPD](https://github.com/NanoHttpd/nanohttpd) - WebSocket server
- [Exacting](https://github.com/demoran23/Exacting) - Kotlin mod example
