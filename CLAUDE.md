# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## STOP — Read Before Any Edit

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MAIN THREAD: DO NOT EDIT src/ FILES                                   │
│                                                                         │
│  Before touching ANY code file, ask yourself:                           │
│                                                                         │
│  □ Am I the main conversation thread? → SPAWN A SUBAGENT               │
│  □ Is this "just a quick fix"? → SPAWN A SUBAGENT (it never is)        │
│  □ Will I run tests after? → SPAWN A SUBAGENT                          │
│                                                                         │
│  The main thread orchestrates. Subagents implement.                     │
│  See "Agent Workflow" section below for how to spawn.                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Build & Development Commands

This is a monorepo with multiple Python packages. Each package has its own virtual environment.

### MCP Server (server/)

```bash
cd server
uv sync                              # Install/sync dependencies
uv run python -m pytest              # Run tests
uv run python -m mypy src            # Type checking
uv run ruff check src                # Lint
uv run ruff format src               # Format code
uv run python -m slay_the_spire_mcp  # Run the MCP server directly
```

### Bridge (bridge/)

```bash
cd bridge
uv sync                              # Install/sync dependencies
uv run python -m pytest              # Run tests
uv run python -m mypy src            # Type checking
uv run ruff check src                # Lint
uv run ruff format src               # Format code
uv run python -m spire_bridge        # Run the bridge directly
```

### Root-Level Tests (tests/)

```bash
# From project root, using server's venv (which has pytest)
cd server && uv run python -m pytest ../tests
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

### Spawning Agents via Task Tool

The custom agents in `.claude/agents/` work with auto-delegation ("use the architect agent"), but when spawning explicitly via the Task tool, use `subagent_type: general-purpose` and reference the agent definition in the prompt:

```
Task(
  subagent_type="general-purpose",
  prompt="""You are the Architect agent.

First, read .claude/agents/architect.md for your role, constraints, and deliverables.
Then read CLAUDE.md for project context.

Your task: [specific task here]
"""
)
```

**Agent prompt prefixes:**
- **Architect**: "You are the Architect agent. Read `.claude/agents/architect.md` for your role and constraints."
- **Implementer**: "You are the Implementer agent. Read `.claude/agents/implementer.md` for your role and constraints."
- **Verifier**: "You are the Verifier agent. Read `.claude/agents/verifier.md` for your role and constraints."
- **Refactor**: "You are the Refactor agent. Read `.claude/agents/refactor.md` for your role and constraints."

**Why not use built-in subagent types?**
- Built-in types like `Plan` are read-only (can't write files)
- `general-purpose` has full tool access
- Including agent instructions in the prompt preserves the role/constraints

> **Note**: Tool restrictions listed in `.claude/agents/` are advisory when using Task tool — the agent has access to all tools but should follow its documented constraints.

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

**COMMIT SAFEGUARD — Read This Before Any Commit**

```
┌─────────────────────────────────────────────────────────────┐
│  STOP! Before committing, verify ALL of these:              │
│                                                             │
│  □ Verifier agent said "Ship it!" on the FINAL state        │
│  □ ONE verifier reviewed ALL changes together (not separate │
│    verifiers per component — they miss integration issues)  │
│  □ All tests pass                                           │
│  □ No uncommitted changes were skipped                      │
│  □ USER APPROVED — Got explicit thumbs up from the user     │
│                                                             │
│  If ANY box is unchecked → DO NOT COMMIT                    │
└─────────────────────────────────────────────────────────────┘
```

**Why ONE verifier?** Multiple verifiers each only see their piece. A single verifier reviewing all changes together catches:
- Integration bugs between components
- Inconsistent patterns across files
- Missing cross-component tests
- Shared state issues

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

- **`mcp`** - Official Python MCP SDK (server/)
- **`pydantic`** - Data validation and models (server/)
- **`websockets`** - WebSocket communication (server/)

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

### MCP Tools (To Be Implemented)

```python
# Read-only (primary use case - advisory)
"get_state"             # Full game state
"get_deck"              # Current deck contents
"get_map"               # Map data with paths
"get_run_context"       # Run timeline and history

# Action tools (optional - for full control if desired)
"play_card"             # { card_index, target_index? }
"end_turn"              # {}
"use_potion"            # { slot, target_index? }
"choose"                # { choice }
"start_run"             # { class, ascension?, seed? }
```

### MCP Resources (To Be Implemented)

```
"slay://state"          # Current game state (subscribable)
"slay://deck"           # Current deck
"slay://run"            # Run context and history
```

**Note**: Tools and resources are defined but not yet implemented. See `server/src/slay_the_spire_mcp/tools.py` and `resources.py`.

## Key Conventions

- **Python 3.10+** with type hints throughout
- **src layout** with pyproject.toml (PEP 517/518)
- **Async-first** - MCP SDK uses asyncio
- **Explicit error handling** - No silent failures
- **Single Source of Truth** - Game state models defined once, used everywhere
- **Test-Driven Development** - Write tests first, then implement

## Test-Driven Development (TDD)

This project practices TDD. The workflow integrates testing into the agent phases:

### TDD in the Agent Workflow

1. **Architect Phase**: Specifies **acceptance tests** as part of the plan
   - What tests must exist and pass for the feature to be complete
   - Test cases for happy paths, edge cases, and error conditions
   - These become the implementer's acceptance criteria

2. **Implementer Phase**: Follows Red-Green-Refactor
   - **Red**: Write the tests first (they will fail)
   - **Green**: Write minimal code to make tests pass
   - **Refactor**: Clean up while keeping tests green
   - Implementation is not complete until all specified tests pass

3. **Verifier Phase**: Confirms test quality
   - Are all acceptance tests from the plan implemented?
   - Do tests actually test the right behavior (not just pass)?
   - Is coverage adequate for the changed code?

### Test Organization

```
tests/
├── unit/                 # Fast, isolated tests
│   ├── test_models.py
│   └── test_detection.py
├── integration/          # Tests with real dependencies
│   └── test_bridge.py
└── fixtures/             # Shared test data
    └── game_states/      # Sample JSON states
```

### Writing Good Acceptance Tests

In architect plans, specify tests like:

```markdown
## Acceptance Tests

### Happy Path
- `test_parse_combat_state`: Given valid combat JSON, returns CombatState with correct monsters
- `test_detect_card_reward`: Given card reward screen state, detects decision point

### Edge Cases
- `test_parse_empty_deck`: Given state with no cards, returns empty deck (not error)
- `test_detect_no_decision`: Given combat mid-turn, returns None (no decision point)

### Error Conditions
- `test_parse_invalid_json`: Given malformed JSON, raises ParseError with context
- `test_connection_timeout`: Given no response in 5s, raises ConnectionTimeout
```

Implementers write these tests first, watch them fail, then implement.

## Monorepo Structure

```
slay-the-spire-mcp/
├── CLAUDE.md              # This file
├── docker-compose.yml     # Container orchestration
├── README.md              # Project overview
├── .claude/               # Claude Code configuration
│   ├── agents/            # Agent definitions
│   ├── skills/            # Custom skills
│   ├── locks/             # File locking for parallel agents
│   └── plans/             # Architect plans
├── mod/                   # Java mod for Slay the Spire
│   ├── pom.xml            # Maven build
│   └── src/               # Java source
├── bridge/                # Python relay bridge
│   ├── pyproject.toml     # Bridge dependencies (minimal)
│   └── src/spire_bridge/  # Bridge source
├── server/                # MCP server (main Python package)
│   ├── pyproject.toml     # Server dependencies (mcp, pydantic, websockets)
│   └── src/slay_the_spire_mcp/
│       ├── __init__.py
│       ├── __main__.py    # Entry point
│       ├── server.py      # MCP server setup
│       ├── state.py       # Game state management
│       ├── models.py      # Pydantic game state models
│       ├── tools.py       # MCP tool implementations
│       ├── resources.py   # MCP resource implementations
│       └── ...
├── shared/                # Shared resources
│   └── card_database/     # Card data
└── tests/                 # Root-level integration tests
    ├── fixtures/          # Shared test data
    └── integration/       # Cross-component tests
```

Each Python package (bridge/, server/) has its own virtual environment and pyproject.toml.
