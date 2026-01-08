# Phase 6 Polish Plan

**Status**: In Progress
**Issues**: #29, #30, #31, #32, #33, #36, #37, #38

## Overview

This phase addresses polish items to improve code quality, documentation, and testing infrastructure. These issues are mostly independent and can be worked on in parallel.

## Issue Status

| Issue | Title | Status | Priority |
|-------|-------|--------|----------|
| #38 | Generate uv.lock file | DONE | Critical |
| #37 | Integrate or remove shared schemas | DONE | Medium |
| #36 | Update fixtures to match real output | TODO | High |
| #33 | Test coverage improvements | TODO | High |
| #32 | User documentation | TODO | Medium |
| #31 | Configuration system | TODO | Medium |
| #29 | Error handling audit | TODO | High |
| #30 | Create card database | TODO | Low (deprioritized) |

## Detailed Plans

---

### Issue #37: Integrate or Remove Shared Schemas

**Status**: DONE

**Decision**: REMOVE the orphaned schemas.

**Rationale**:
- Schemas were planned but never created (`shared/schemas/` directory did not exist)
- Pydantic models already provide runtime validation
- JSON Schema validation adds complexity without clear benefit for this project
- Removed references to non-existent schemas from documentation

**Changes Made**:
- UPDATED: `CLAUDE.md` - Removed `schemas/` from monorepo structure diagram
- UPDATED: `.claude/plans/mvp-architecture.md` - Removed schema files from directory tree, updated Section 4.4 to reflect reality
- KEPT: `shared/card_database/cards.json` (placeholder, separate issue #30)

**Verification**:
- `shared/schemas/` directory confirmed to not exist
- No code references `shared/schemas/` or the planned schema files
- Documentation now accurately reflects the repository structure

---

### Issue #36: Update Fixtures to Match Real CommunicationMod Output

**Problem**: Current fixtures use simplified format that doesn't match actual mod output.

**Current Issues**:
- Fixtures use `upgraded` (boolean) but mod uses `upgrades` (int)
- Missing: `screen_name`, `is_screen_up`, `room_phase`, `action_phase`
- Missing: `room_type`, `act_boss`
- Missing: Card UUIDs, `is_playable`, `has_target`
- Combat fixture has flat structure, should have nested `combat_state`

**File Touch Map**:
- MODIFY: `tests/fixtures/game_states/card_reward.json`
- MODIFY: `tests/fixtures/game_states/combat.json`
- CREATE: `tests/fixtures/game_states/map.json`
- CREATE: `tests/fixtures/game_states/rest.json`
- CREATE: `tests/fixtures/game_states/shop.json`
- CREATE: `tests/fixtures/game_states/event.json`

**Key Changes**:
1. Update `upgraded: false` to `upgrades: 0` in all card objects
2. Add `uuid` field to cards
3. Add combat-specific cards with `is_playable`, `has_target`
4. Wrap combat data in proper message format: `{"type": "state", "data": {...}}`
5. Add missing screen types as new fixtures

**Acceptance Tests**:
- `test_fixture_uses_upgrades_int`: Fixtures use `upgrades` (int) not `upgraded` (bool)
- `test_fixture_matches_message_format`: Fixtures wrap data in `{"type": "state", "data": ...}`
- `test_fixture_parses_with_models`: All fixtures can be parsed by `parse_game_state_from_message`
- `test_map_fixture_exists`: Map screen fixture exists
- `test_rest_fixture_exists`: Rest screen fixture exists
- `test_shop_fixture_exists`: Shop screen fixture exists
- `test_event_fixture_exists`: Event screen fixture exists

---

### Issue #33: Test Coverage Improvements

**Problem**: Tests are mostly placeholders with minimal actual coverage.

**Current State**:
- `test_models.py`: Only tests module import and fixture loading
- `test_detection.py`: Only tests module import
- `test_state.py`: Only tests module import

**Target Coverage**:
Focus on the modules that have actual implementation:
1. `models.py` - Pydantic models and `parse_game_state_from_message`
2. `detection.py` - Decision point detection
3. `state.py` - GameStateManager and TCPListener

**File Touch Map**:
- MODIFY: `tests/test_models.py` - Add actual model tests
- MODIFY: `tests/test_detection.py` - Add detection tests
- MODIFY: `tests/test_state.py` - Add state manager tests

**Acceptance Tests to Add**:

**test_models.py**:
- `test_card_from_dict`: Card parses from dict correctly
- `test_card_defaults`: Card has correct defaults
- `test_card_extra_fields_ignored`: Extra fields don't cause errors
- `test_relic_from_dict`: Relic parses correctly
- `test_potion_from_dict`: Potion parses correctly
- `test_monster_from_dict`: Monster parses correctly
- `test_game_state_from_dict`: GameState parses correctly
- `test_parse_game_state_from_message_valid`: Valid message parses to GameState
- `test_parse_game_state_from_message_wrong_type`: Non-state message returns None
- `test_parse_game_state_from_message_empty_data`: Empty data returns None
- `test_parse_game_state_screen_state_string`: String screen_state normalized to dict

**test_detection.py**:
- `test_detect_card_reward`: CARD_REWARD screen detected
- `test_detect_combat`: Combat state detected from screen_state
- `test_detect_event`: EVENT screen detected
- `test_detect_shop`: SHOP_SCREEN detected
- `test_detect_campfire`: REST screen detected
- `test_detect_map`: MAP screen detected
- `test_detect_no_game`: Returns None when not in_game
- `test_detect_main_menu`: Returns None for MAIN_MENU
- `test_detect_combat_has_choices`: Combat decision has hand cards as choices

**test_state.py**:
- `test_game_state_manager_initial`: Initial state is None
- `test_game_state_manager_update`: State updates correctly
- `test_game_state_manager_previous`: Previous state tracked
- `test_game_state_manager_callback`: Callbacks called on update
- `test_game_state_manager_clear`: Clear resets state

---

### Issue #32: User Documentation

**Goal**: Create minimal but useful documentation for end users.

**File Touch Map**:
- CREATE: `docs/installation.md` - How to install and set up
- CREATE: `docs/configuration.md` - Environment variables and options
- CREATE: `docs/troubleshooting.md` - Common issues and solutions

**Content Outline**:

**docs/installation.md**:
- Prerequisites (Python 3.10+, uv, Slay the Spire with mods)
- Installation steps for MCP server
- Installation steps for SpireBridge mod
- Claude Desktop configuration

**docs/configuration.md**:
- Environment variables (STS_TCP_PORT, STS_TCP_HOST)
- Default values
- Docker configuration

**docs/troubleshooting.md**:
- Bridge connection issues
- MCP server won't start
- Game state not updating
- Common error messages

**Acceptance Tests**:
- `test_installation_doc_exists`: docs/installation.md exists
- `test_configuration_doc_exists`: docs/configuration.md exists
- `test_troubleshooting_doc_exists`: docs/troubleshooting.md exists

---

### Issue #31: Configuration System

**Problem**: Configuration is scattered and not well documented.

**Current State**:
- `STS_TCP_PORT` and `STS_TCP_HOST` read from environment in `server.py`
- Bridge uses hardcoded defaults in `protocol.py`
- No unified configuration approach

**Solution**: Use pydantic-settings for server configuration.

**File Touch Map**:
- CREATE: `server/src/slay_the_spire_mcp/config.py` - Configuration module
- MODIFY: `server/src/slay_the_spire_mcp/server.py` - Use config module
- MODIFY: `server/pyproject.toml` - Add pydantic-settings dependency (already present per imports)

**Config Class Design**:
```python
from pydantic_settings import BaseSettings

class ServerConfig(BaseSettings):
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 7777
    log_level: str = "INFO"

    class Config:
        env_prefix = "STS_"
```

**Acceptance Tests**:
- `test_config_defaults`: Config has correct defaults
- `test_config_env_override`: Environment variables override defaults
- `test_config_invalid_port`: Invalid port value handled gracefully

---

### Issue #29: Error Handling Audit

**Problem**: Need to ensure errors are visible, not silent.

**Areas to Review**:
1. Bridge connection failures
2. TCP listener errors
3. State parsing errors
4. MCP tool errors

**Current Error Handling Analysis**:
- `state.py`: Logs errors but continues - GOOD
- `models.py`: Uses Pydantic validation - GOOD
- `relay.py`: Logs and handles connection errors - GOOD
- `server.py`: Returns JSON error responses - GOOD

**Improvements Needed**:
1. Add structured error logging with context
2. Ensure MCP tools return meaningful error messages
3. Add timeout handling for bridge communication
4. Document error recovery procedures

**File Touch Map**:
- CREATE: `server/src/slay_the_spire_mcp/errors.py` - Custom exception hierarchy
- MODIFY: `server/src/slay_the_spire_mcp/state.py` - Use custom exceptions
- MODIFY: `server/src/slay_the_spire_mcp/tools.py` - Better error messages

**Custom Exceptions**:
```python
class SpireMCPError(Exception):
    """Base exception for Spire MCP."""
    pass

class BridgeConnectionError(SpireMCPError):
    """Failed to connect to bridge."""
    pass

class StateParseError(SpireMCPError):
    """Failed to parse game state."""
    pass

class NotInGameError(SpireMCPError):
    """Operation requires active game."""
    pass

class NotInCombatError(SpireMCPError):
    """Operation requires combat state."""
    pass
```

**Acceptance Tests**:
- `test_bridge_disconnect_logged`: Bridge disconnect is logged
- `test_parse_error_logged_with_context`: Parse errors include context
- `test_tool_error_returns_message`: Tool errors return user-friendly messages
- `test_not_in_game_error`: Operations fail gracefully when not in game

---

### Issue #30: Create Card Database (Deprioritized)

**Status**: LOW PRIORITY - Placeholder exists, full database can be added later.

**Reason for Deprioritization**:
- Claude has knowledge of Slay the Spire cards
- Database requires significant effort to compile accurately
- Not blocking for MVP functionality
- Can be crowd-sourced or generated from game files later

**Current State**: `shared/card_database/cards.json` contains placeholder structure.

**Future Work** (not this phase):
- Extract card data from game files or wiki
- Include all ~300+ cards with stats, effects, upgrade info
- Add character associations
- Validate against actual game

---

## Implementation Order

Given dependencies and priorities:

1. **#37 Shared Schemas** (independent, quick) - Remove unused files
2. **#36 Fixtures** (independent) - Update test fixtures
3. **#33 Test Coverage** (depends on #36 for fixtures) - Add real tests
4. **#29 Error Handling** (independent) - Add error infrastructure
5. **#31 Configuration** (independent) - Add config system
6. **#32 Documentation** (depends on #31) - Document configuration

These can largely be done in parallel, with #33 waiting for #36 fixture updates.

## Acceptance Criteria

Phase 6 is complete when:
- [x] Shared schemas removed (#37)
- [ ] Fixtures updated to match real format (#36)
- [ ] Test coverage improved with meaningful tests (#33)
- [ ] User documentation created (#32)
- [ ] Configuration system centralized (#31)
- [ ] Error handling audited and improved (#29)
- [ ] All tests pass
- [ ] Types pass
- [ ] Lints pass
