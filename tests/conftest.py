"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add both server and bridge src directories to Python path
# This enables integration tests to import from both packages
_repo_root = Path(__file__).parent.parent
_server_src = _repo_root / "server" / "src"
_bridge_src = _repo_root / "bridge" / "src"

if str(_server_src) not in sys.path:
    sys.path.insert(0, str(_server_src))
if str(_bridge_src) not in sys.path:
    sys.path.insert(0, str(_bridge_src))


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def game_states_dir(fixtures_dir: Path) -> Path:
    """Return the path to the game states fixtures directory."""
    return fixtures_dir / "game_states"


@pytest.fixture
def sample_game_state(game_states_dir: Path) -> dict[str, Any]:
    """Load and return a sample game state fixture."""
    fixture_path = game_states_dir / "card_reward.json"
    if fixture_path.exists():
        with open(fixture_path) as f:
            return json.load(f)
    # Return minimal state if fixture doesn't exist yet
    return {
        "in_game": True,
        "screen_type": "CARD_REWARD",
        "floor": 5,
        "act": 1,
        "hp": 65,
        "max_hp": 80,
        "gold": 99,
        "deck": [],
        "relics": [],
        "potions": [],
        "choice_list": ["Strike", "Pommel Strike", "Anger"],
        "seed": 123456789,
    }
