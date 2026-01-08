# Slay the Spire MCP

An MCP server that bridges Claude to Slay the Spire, providing real-time game analysis and strategic advice.

## What It Does

Claude watches your Slay the Spire gameplay and analyzes decision points in real-time. When you encounter card rewards, relics, paths, or events, Claude provides:
- Preference percentages for each option
- Concise strategic commentary
- Context-aware analysis of your current run

This is an advisory co-pilot, not an AI that plays for you—you make all decisions.

## Architecture

```
Claude (MCP Client)
    ↓
MCP Server (Python) ← Analyzes game state
    ↓
Bridge Process (Python) ← Relays game state & commands
    ↓
SpireBridge Mod (Java) ← Manages overlay & game hooks
    ↓
Slay the Spire Game
```

**Data flow**: Game → SpireBridge Mod → Bridge Process → MCP Server → Claude → Analysis → Overlay

## Status

Currently in **MVP development** (Phase 1-3). The foundation is being built to support live game state analysis with terminal output initially, and in-game overlay rendering as the north star feature.

## Components

- **`mod/`** - SpireBridge: Java/Kotlin fork of CommunicationMod with overlay capabilities
- **`bridge/`** - Python relay process that connects the mod to the MCP server
- **`server/`** - MCP server with game state management and Claude integration

See individual README.md files in each directory for details.

## Quick Start

Installation instructions coming soon. For now, see CLAUDE.md and `.claude/plans/mvp-architecture.md` for detailed development and architecture documentation.

## License

MIT
