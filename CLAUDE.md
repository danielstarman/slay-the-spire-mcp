# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
uv sync                    # Install/sync dependencies
uv run python -m pytest    # Run tests
uv run python -m mypy src  # Type checking
uv run ruff check src      # Lint
uv run ruff format src     # Format code
uv run python -m slay_the_spire_mcp  # Run the MCP server directly
```

**Prerequisites**: Python 3.10+ and uv (https://docs.astral.sh/uv/)

**Shell syntax (Windows)**: Claude Code uses bash (Git Bash/MSYS2), not cmd. Use `/dev/null` for null redirection, NOT `nul`. Example: `command 2>/dev/null` not `command 2>nul`.

## Agent Workflow (Multi-Phase Development)

For non-trivial tasks, use a structured multi-agent workflow to separate concerns and catch issues early.

**IMPORTANT**: All phases run as **subagents** to preserve main conversation context. The main conversation orchestrates but doesn't do the heavy lifting.

**Context Preservation Rule**: The main conversation must protect its context for orchestration, not burn it on implementation details.

**Main thread CAN do:**
- Read files to understand context
- Run simple commands, `git status`, simple git operations
- Edit config/docs (CLAUDE.md, pyproject.toml) when directly relevant to conversation
- Discuss, plan, and orchestrate with user
- Spawn and monitor subagents

**Main thread CANNOT do (spawn subagent instead):**
- Edit any `src/` files — even "one small fix"
- Run `pytest/mypy/ruff` to verify changes
- Debug errors or investigate crashes
- Any work that might expand (one fix → test failure → another fix → ...)

**The trap to avoid:** *"This is simple, I'll just do it quickly"* — that's exactly when you should spawn. Implementation work expands unpredictably; what looks like one edit often becomes a multi-step fix cycle that burns context on details the main thread doesn't need to remember.

### The Four Agents

Agent definitions live in **`.claude/agents/`**:

| Agent | File | Tools (Advisory) | Role |
|-------|------|------------------|------|
| **Architect** | `architect.md` | Read, Write, Glob, Grep | Design & planning (no implementation) |
| **Implementer** | `implementer.md` | Read, Write, Edit, Bash, Glob, Grep | Code to spec |
| **Verifier** | `verifier.md` | Read, Bash, Glob, Grep, Task | Review & spawn fixers |
| **Refactor** | `refactor.md` | Read, Write, Edit, Bash, Glob, Grep | Simplify (no behavior changes) |

See individual agent files for detailed instructions and checklists.

> **Note**: Tool restrictions in `.claude/agents/` are enforced during auto-delegation and text-based invocation ("use the architect agent"), but NOT when spawning via Task tool with `subagent_type: general-purpose`. The agents still serve as documented conventions and work well with auto-delegation.

### Workflow Sequence

```
┌─────────────────────────────────────────────────────────────┐
│  1. ARCHITECT PHASE (subagent)                              │
│     User ↔ Architect iterate until design approved          │
│     Main conversation presents results, user approves       │
│     Outputs: design doc, file touch map, risks              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  1b. INTERVIEW PHASE (/interview skill)                     │
│     Invoke: /interview <plan-file.md>                       │
│     Deep-dive questions on implementation, UX, tradeoffs    │
│     Continues until all ambiguities resolved                │
│     Updates plan file with finalized spec                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. IMPLEMENTER PHASE (subagent)                            │
│     Subagent codes until complete                           │
│     Follows architect's plan exactly                        │
│     Main conversation monitors progress                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. VERIFIER PHASE (subagent)                               │
│     Subagent reviews like a cranky maintainer               │
│     ├─ Behavioral issues? → Spawn Implementer → loop back   │
│     ├─ Complexity issues? → Spawn Refactor → loop back      │
│     └─ All good? → Report "Ship it!" to main conversation   │
└─────────────────────────────────────────────────────────────┘
                            ↑__________________|
```

**CRITICAL: Verifier Always Gets Final Say**

The Verifier phase is a loop, not a one-shot check:

1. Verifier reviews implementation
2. If issues found → spawn Implementer or Refactor to fix
3. **After fixes complete → Verifier reviews AGAIN**
4. Repeat until Verifier says "Ship it!"

Never declare "Ship it!" without a Verifier pass on the final state. The main conversation should not approve changes that the Verifier hasn't reviewed.

### Why Subagents for Everything

- **Context preservation** — Main conversation stays lean, retains history
- **Fresh perspectives** — Each subagent starts with clean context, no accumulated assumptions
- **Parallel work** — Multiple subagents can run simultaneously when independent
- **Separation of concerns** — Each agent has a single job

### File Locking (Parallel Agents)

When running as a parallel Implementer or Refactor, you **MUST** coordinate file edits to avoid conflicts:

1. **Before editing any file**, check `.claude/locks/` for existing locks
2. **If not locked**, claim it: `echo "your-agent-id" > .claude/locks/<encoded-path>.lock`
   - Path encoding: `src/foo/bar.py` → `src__foo__bar.py.lock`
3. **If locked by another agent**, follow conflict resolution:
   - **Work around** — continue with other unlocked files first
   - **Wait** — poll every 2 minutes, up to 10 minutes max
   - **Escalate** — report blocking conflict to main thread if still stuck
4. **On task completion**, delete all lock files you created

See `.claude/LOCKS.md` for full protocol details and edge cases.

### Invoking the Workflow

When starting a task, say: *"Use the agent workflow"* or *"Let's architect this first"*

The architect phase produces:
1. **Design summary** — what we're building and why
2. **File touch map** — exactly which files will be created/modified
3. **Risks** — what could go wrong, edge cases, compatibility concerns
4. **Invariants** — what must remain true after implementation

### User Feedback & Clarification

**Prefer the `AskUserQuestion` tool** when gathering feedback, clarifying requirements, or presenting options.

Use it for:
- Presenting feature options (e.g., "Which approach should we take?")
- Clarifying ambiguous requirements
- Getting approval before major changes
- Offering design alternatives

When it doesn't fit (fall back to plain text):
- Complex explanations requiring prose
- Showing code samples or diffs
- Situations needing open-ended discussion

### Custom Skills

Skills live in **`.claude/skills/`**:

| Skill | Invocation | When to Use |
|-------|------------|-------------|
| `/interview` | `/interview <plan-file.md>` | **Automatically** after Architect produces a plan, before Implementer |

The interview skill runs in a forked context (isolated from main conversation) and exhaustively questions the design to surface hidden assumptions, edge cases, and decisions.

**Auto-invoke rule**: Claude should run `/interview` without being asked after any Architect phase completes. Skip only if user says "skip the interview" or the task is trivially simple.

## Project Overview

This is an MCP (Model Context Protocol) server that bridges Claude to Slay the Spire via the existing CommunicationMod. It enables Claude to see live game state and provide context-aware strategic advice as a co-pilot companion.

### Architecture

```
Claude (MCP Client)
    ↕ MCP Protocol (JSON-RPC over stdio)
MCP Server (this project - Python)
    ↕ CommunicationMod Protocol (JSON over stdio)
Slay the Spire + CommunicationMod (existing mod)
```

### Key Dependencies

- **`mcp`** - Official Python MCP SDK
- **`spirecomm`** - Python wrapper for CommunicationMod protocol

### CommunicationMod Protocol

- Mod launches our server as subprocess
- We send "ready\n" on startup
- Mod sends JSON game state when stable
- We send commands, mod replies with updated state

**Commands:**
- `START PlayerClass [Ascension] [Seed]` - New run
- `PLAY CardIndex [TargetIndex]` - Play card (1-indexed)
- `END` - End turn
- `POTION Use|Discard Slot [Target]` - Use/discard potion
- `CHOOSE Index|Name` - Select option (rewards, events, etc.)
- `PROCEED` / `RETURN` - Navigation buttons
- `STATE` - Force state update

### MCP Tools (Planned)

```python
# Read-only (primary use case - advisory)
"slay_the_spire/get_state"      # Full game state
"slay_the_spire/get_combat"     # Combat-specific state
"slay_the_spire/get_deck"       # Current deck
"slay_the_spire/get_map"        # Act map with paths

# Action tools (optional - for full control if desired)
"slay_the_spire/play_card"      # { card_index, target_index? }
"slay_the_spire/end_turn"       # {}
"slay_the_spire/use_potion"     # { slot, target_index? }
"slay_the_spire/choose"         # { choice }
"slay_the_spire/start_run"      # { class, ascension?, seed? }
```

### MCP Resources (Planned)

```
"slay://state"          # Current full state (subscribe for updates)
"slay://combat"         # Combat state
"slay://deck"           # Deck contents
"slay://map"            # Map data
```

## Key Conventions

- **Python 3.10+** with type hints throughout
- **src layout** with pyproject.toml (PEP 517/518)
- **Async-first** - MCP SDK uses asyncio
- **Explicit error handling** - No silent failures
- **Single Source of Truth** - Game state models defined once, used everywhere

## Project Structure (Planned)

```
slay-the-spire-mcp/
├── pyproject.toml
├── CLAUDE.md
├── .claude/
│   ├── agents/
│   ├── skills/
│   ├── locks/
│   └── plans/
├── src/
│   └── slay_the_spire_mcp/
│       ├── __init__.py
│       ├── __main__.py      # Entry point
│       ├── server.py        # MCP server setup
│       ├── bridge.py        # CommunicationMod bridge
│       ├── models.py        # Game state models
│       └── tools.py         # MCP tool implementations
└── tests/
    └── ...
```
