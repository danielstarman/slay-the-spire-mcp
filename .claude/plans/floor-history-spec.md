# Floor History Implementation Specification

## Problem Statement
Without knowing the path taken through the map, Claude makes incorrect assumptions about the source of relics and cards. We need to track the sequence of nodes visited during a run.

## Solution Overview
Track visited nodes as a list of floor history entries in the GameStateManager and expose them via the get_game_state tool.

## Data Model

### FloorHistory Model (in models.py)
```python
class FloorHistory(BaseGameModel):
    """A record of a visited node/floor in the current run."""
    floor: int
    symbol: str
    details: str | None = None
```

### Node Symbols
- `M` = Monster (hallway fight)
- `E` = Elite
- `?` = Event (unknown)
- `R` = Rest site
- `$` = Shop
- `T` = Treasure

## Implementation Changes

### 1. models.py
- Add `FloorHistory` class (see Data Model above)
- Import and use in `GameState` if needed (optional - history will be added separately)

### 2. state.py - GameStateManager
Add floor history tracking to the GameStateManager class:

```python
class GameStateManager:
    def __init__(self) -> None:
        # ... existing fields ...
        self._floor_history: list[FloorHistory] = []
    
    def get_floor_history(self) -> list[FloorHistory]:
        """Get the history of visited nodes in the current run."""
        return self._floor_history.copy()
    
    async def update_state(self, new_state: GameState) -> None:
        # ... existing code ...
        # After updating state, check for floor transitions
        await self._track_floor_transition(new_state)
    
    def update_state_sync(self, new_state: GameState) -> None:
        # ... existing code ...
        # After updating state, check for floor transitions
        self._track_floor_transition_sync(new_state)
    
    async def _track_floor_transition(self, new_state: GameState) -> None:
        """Track floor transitions and record visited nodes."""
        self._track_floor_transition_sync(new_state)
    
    def _track_floor_transition_sync(self, new_state: GameState) -> None:
        """Synchronously track floor transitions."""
        # If this is a new run (floor resets to 0 or 1), clear history
        if new_state.floor <= 1 and self._previous_state and self._previous_state.floor > new_state.floor:
            self._floor_history.clear()
        
        # If floor increased, record the previous floor's node
        if self._previous_state and new_state.floor > self._previous_state.floor:
            # Try to get node symbol from previous state
            symbol = self._extract_node_symbol(self._previous_state)
            if symbol:
                entry = FloorHistory(
                    floor=self._previous_state.floor,
                    symbol=symbol,
                    details=None  # Can be enhanced later
                )
                self._floor_history.append(entry)
    
    def _extract_node_symbol(self, state: GameState) -> str | None:
        """Extract the node symbol from game state.
        
        Tries multiple approaches:
        1. If map data exists with current_node, look up the symbol
        2. If screen_state has current_node, use that
        3. Infer from screen_type/room_type
        """
        # Try to get from map data with current_node
        if state.map and state.current_node:
            x, y = state.current_node
            for row in state.map:
                for node in row:
                    if node.x == x and node.y == y:
                        return node.symbol
        
        # Try to get from screen_state
        if isinstance(state.screen_state, dict):
            current_node_data = state.screen_state.get("current_node")
            if isinstance(current_node_data, dict):
                symbol = current_node_data.get("symbol")
                if symbol:
                    return symbol
        
        # Fallback: infer from screen_type or room_type
        # This is less reliable but better than nothing
        screen_state_dict = state.screen_state if isinstance(state.screen_state, dict) else {}
        room_type = screen_state_dict.get("room_type", "")
        
        if "Monster" in room_type or "Combat" in str(state.screen_type):
            return "M"
        elif "Elite" in room_type:
            return "E"
        elif "Event" in room_type or "Event" in str(state.screen_type):
            return "?"
        elif "Rest" in room_type or "REST" in str(state.screen_type):
            return "R"
        elif "Shop" in room_type or "SHOP" in str(state.screen_type):
            return "$"
        elif "Treasure" in room_type or "TREASURE" in str(state.screen_type):
            return "T"
        
        return None
    
    def clear_state(self) -> None:
        """Clear the current state and floor history."""
        self._current_state = None
        self._previous_state = None
        self._floor_history.clear()
```

### 3. tools.py - get_game_state
Update the get_game_state function to include floor history:

```python
async def get_game_state(
    state_manager: GameStateManager,
    tcp_listener: TCPListener | None,
) -> dict[str, Any] | None:
    """Get the current game state including floor history."""
    state = state_manager.get_current_state()
    if state is None:
        return None
    
    # Convert to dict using Pydantic's model_dump
    state_dict = state.model_dump()
    
    # Add floor history
    floor_history = state_manager.get_floor_history()
    state_dict["floor_history"] = [entry.model_dump() for entry in floor_history]
    
    return state_dict
```

## Acceptance Tests

Create tests in `/home/runner/work/slay-the-spire-mcp/slay-the-spire-mcp/tests/test_state.py`:

### Test: Floor history records visits
```python
def test_floor_history_records_visits():
    """Test that floor transitions are recorded in history."""
    manager = GameStateManager()
    
    # Floor 1 - Monster
    state1 = GameState(floor=1, screen_type="COMBAT", in_game=True)
    manager.update_state_sync(state1)
    
    # Floor 2 - Event (transition from floor 1)
    state2 = GameState(floor=2, screen_type="EVENT", in_game=True)
    manager.update_state_sync(state2)
    
    # Check history recorded floor 1
    history = manager.get_floor_history()
    assert len(history) == 1
    assert history[0].floor == 1
```

### Test: Floor history with map data
```python
def test_floor_history_with_map_data():
    """Test that floor history extracts symbols from map data."""
    manager = GameStateManager()
    
    # Floor 1 with map showing current node as 'M'
    node = MapNode(x=3, y=0, symbol="M")
    state1 = GameState(
        floor=1, 
        in_game=True,
        current_node=(3, 0),
        map=[[node]]
    )
    manager.update_state_sync(state1)
    
    # Floor 2
    state2 = GameState(floor=2, in_game=True)
    manager.update_state_sync(state2)
    
    history = manager.get_floor_history()
    assert len(history) == 1
    assert history[0].floor == 1
    assert history[0].symbol == "M"
```

### Test: Floor history resets on new run
```python
def test_floor_history_resets_on_new_run():
    """Test that floor history clears when starting a new run."""
    manager = GameStateManager()
    
    # First run
    state1 = GameState(floor=1, in_game=True)
    manager.update_state_sync(state1)
    state2 = GameState(floor=2, in_game=True)
    manager.update_state_sync(state2)
    
    assert len(manager.get_floor_history()) >= 1
    
    # New run (floor resets to 1)
    state_new = GameState(floor=1, in_game=True)
    manager.update_state_sync(state_new)
    
    history = manager.get_floor_history()
    # History should be cleared
    assert len(history) == 0
```

### Test: Floor history in get_game_state
```python
async def test_floor_history_in_get_game_state():
    """Test that floor history is included in get_game_state output."""
    manager = GameStateManager()
    
    # Create some history
    state1 = GameState(floor=1, in_game=True)
    manager.update_state_sync(state1)
    state2 = GameState(floor=2, in_game=True)
    manager.update_state_sync(state2)
    
    # Get state via tool
    result = await get_game_state(manager, None)
    
    assert result is not None
    assert "floor_history" in result
    assert isinstance(result["floor_history"], list)
```

### Test: Clear state clears history
```python
def test_clear_state_clears_history():
    """Test that clear_state also clears floor history."""
    manager = GameStateManager()
    
    state1 = GameState(floor=1, in_game=True)
    manager.update_state_sync(state1)
    state2 = GameState(floor=2, in_game=True)
    manager.update_state_sync(state2)
    
    assert len(manager.get_floor_history()) >= 1
    
    manager.clear_state()
    
    assert len(manager.get_floor_history()) == 0
```

## Test Fixtures
The existing fixtures in `tests/fixtures/game_states/` can be used for integration testing.

## Success Criteria
1. ✅ FloorHistory model added to models.py
2. ✅ GameStateManager tracks floor transitions
3. ✅ Floor history persists within a run
4. ✅ Floor history resets on new run (floor decreases)
5. ✅ Floor history included in get_game_state output
6. ✅ All tests pass
7. ✅ Type checking passes (mypy)
8. ✅ Linting passes (ruff)

## Implementation Notes
- Use TDD: Write tests first, then implement
- Follow existing code style and conventions
- Keep changes minimal and focused
- Preserve async/sync pattern used in update_state methods
- Import FloorHistory in models.py __all__ if it exists
