# File Locking for Parallel Subagents

This document defines the coordination protocol for parallel Implementer (and Refactor) subagents to avoid stepping on each other's edits.

## Overview

When multiple subagents run in parallel, they may attempt to edit the same file. This lock system provides:
- **Visibility** into what files are being worked on
- **Conflict detection** before edits happen
- **Graceful resolution** without blocking the orchestrator

## Lock Files

Locks live in `.claude/locks/` (gitignored). Each lock is a single file:

```
.claude/locks/
  src__slay_the_spire_mcp__server.py.lock
  src__slay_the_spire_mcp__bridge.py.lock
```

**Naming convention:** Replace path separators with `__` (double underscore).
- `src/slay_the_spire_mcp/server.py` → `src__slay_the_spire_mcp__server.py.lock`

**Lock file content:** Single line with the agent identifier.
```
implementer-3cf
```

## Lifecycle

### Claiming a Lock

Before editing any file, the agent MUST:

1. **Check** if `.claude/locks/<encoded-path>.lock` exists
2. **If not locked:** Create the lock file with your agent ID, then proceed with edit
3. **If locked:** Follow the Conflict Resolution Protocol below

### Releasing Locks

**Release timing:** Hold all locks until task completion, then bulk-release.

When your task is complete (success or failure):
1. Delete all lock files you created
2. Report which files were edited in your summary

## Conflict Resolution Protocol

When a file you need is locked by another agent:

```
┌─────────────────────────────────────────────────────────┐
│  1. WORK AROUND (preferred)                             │
│     Continue with other files that aren't locked.       │
│     The blocker may clear by the time you need it.      │
│     ↓ (only if truly blocked - no other work possible)  │
├─────────────────────────────────────────────────────────┤
│  2. WAIT                                                │
│     Poll every 2 minutes, up to 20 minutes max.         │
│     Other agent might be finishing up.                  │
│     ↓ (timeout exceeded, still locked)                  │
├─────────────────────────────────────────────────────────┤
│  3. ESCALATE                                            │
│     Report to main thread:                              │
│     "Blocked on X.py (held by <agent> for N minutes).   │
│      Cannot proceed without this file."                 │
│     Main thread decides: wait longer, reassign, abort.  │
└─────────────────────────────────────────────────────────┘
```

**Key principle:** Maximize self-resolution before escalating. Often you *can* make progress on other parts of the task while waiting.

## Agent Instructions

Include this in Implementer/Refactor subagent prompts:

```
BEFORE editing any file, check for locks:
  1. ls .claude/locks/ to see current locks
  2. If your target file is locked, follow LOCKS.md conflict resolution
  3. If not locked, create: echo "<your-agent-id>" > .claude/locks/<path>.lock
  4. Proceed with edit

AFTER completing your task:
  1. Delete all lock files you created
  2. List the files you edited in your summary
```

## Example Session

Two parallel implementers start:

```
Agent A (implementing MCP tools):
  → Claims: src__slay_the_spire_mcp__tools.py.lock
  → Claims: src__slay_the_spire_mcp__models.py.lock
  → Edits files...
  → Completes, releases both locks

Agent B (implementing bridge):
  → Claims: src__slay_the_spire_mcp__bridge.py.lock
  → Needs src/slay_the_spire_mcp/models.py (for game state types)
  → Sees it's locked by Agent A
  → Works on other files first
  → Checks again in 2 min — still locked
  → Checks again in 2 min — lock gone!
  → Claims and proceeds
```

## Edge Cases

### Stale Locks

If an agent crashes without releasing locks, locks become stale. Indicators:
- Lock age > 25 minutes with no agent activity
- Main thread knows agent completed but locks remain

**Resolution:** Main thread manually deletes stale locks.

### Same File, Non-Conflicting Edits

If two agents need to edit different parts of the same file, they still conflict under this system. This is intentional — merge conflicts in agent output are worse than sequential edits.

## Maintenance

Lock files are gitignored and ephemeral. The `locks/` directory should be empty between sessions. If you see locks at session start, they're stale and can be deleted.
