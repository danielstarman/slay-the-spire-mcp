# SpireBridge

A fork of [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) with overlay capabilities for Claude MCP integration.

SpireBridge enables Slay the Spire to communicate with external processes, providing live game state data for AI analysis and strategic advice.

## Requirements

- **Java 8** (JDK 1.8) - Required for compilation
- **Maven** - Build tool
- **Slay the Spire** - The game itself
- **ModTheSpire** - Mod loader for Slay the Spire
- **BaseMod** - Required dependency mod

## Dependencies Setup

Before building, you need to set up the dependency JARs. The build expects them in a `lib/` directory at the repository root (one level up from `mod/`).

### Required JARs

1. **desktop-1.0.jar** - The Slay the Spire game JAR
   - Location: `{Steam}/steamapps/common/SlayTheSpire/desktop-1.0.jar`
   - Copy to: `../lib/desktop-1.0.jar` (relative to `mod/`)

2. **ModTheSpire.jar** - The mod loader
   - Download from: https://github.com/kiooeht/ModTheSpire/releases
   - Copy to: `../lib/ModTheSpire.jar`

3. **BaseMod.jar** - Required dependency mod
   - Download from: https://github.com/daviscook477/BaseMod/releases
   - Copy to: `../lib/BaseMod.jar`

### Setup Script (Manual Steps)

```bash
# Create lib directory at repo root
mkdir -p ../lib

# Copy game JAR (adjust path for your Steam installation)
# Windows:
cp "C:/Program Files (x86)/Steam/steamapps/common/SlayTheSpire/desktop-1.0.jar" ../lib/

# macOS:
# cp ~/Library/Application\ Support/Steam/steamapps/common/SlayTheSpire/desktop-1.0.jar ../lib/

# Linux:
# cp ~/.steam/steam/steamapps/common/SlayTheSpire/desktop-1.0.jar ../lib/

# Download and copy ModTheSpire.jar and BaseMod.jar from their releases
```

## Building

Once dependencies are in place:

```bash
cd mod/
mvn clean package
```

The built mod JAR will be at `target/SpireBridge.jar`.

## Installation

1. Copy `target/SpireBridge.jar` to your ModTheSpire mods directory
2. Launch the game using ModTheSpire
3. Enable SpireBridge in the mod list

## Configuration

SpireBridge uses a SpireConfig file for configuration. After first run, edit the config file to set your external process command.

Config file location (see [SpireConfig wiki](https://github.com/kiooeht/ModTheSpire/wiki/SpireConfig)):
- **Windows**: `%LOCALAPPDATA%/ModTheSpire/SpireBridge/config.properties`
- **macOS**: `~/Library/Preferences/ModTheSpire/SpireBridge/config.properties`
- **Linux**: `~/.config/ModTheSpire/SpireBridge/config.properties`

Example config:
```properties
command=python C:\\Path\\To\\bridge\\main.py
runAtGameStart=true
verbose=false
maxInitializationTimeout=10
```

## Protocol

SpireBridge uses the same protocol as CommunicationMod:

1. SpireBridge launches the configured subprocess
2. Subprocess sends `ready\n` to stdout when ready
3. SpireBridge sends JSON game state to subprocess stdin when stable
4. Subprocess sends commands to stdout
5. SpireBridge executes commands and sends updated state

### Available Commands

| Command | Description |
|---------|-------------|
| `START PlayerClass [Ascension] [Seed]` | Start a new run |
| `PLAY CardIndex [TargetIndex]` | Play a card (1-indexed) |
| `END` | End turn |
| `POTION Use\|Discard Slot [Target]` | Use or discard potion |
| `CHOOSE Index\|Name` | Make a selection |
| `PROCEED` / `CONFIRM` | Click proceed button |
| `RETURN` / `SKIP` / `CANCEL` | Click return/cancel button |
| `KEY Keyname [Timeout]` | Press a game key |
| `CLICK Left\|Right X Y [Timeout]` | Mouse click |
| `WAIT Timeout` | Wait for state change |
| `STATE` | Force state update |

### Game State JSON

The game state includes:
- Current screen type and state
- Combat state (hand, draw pile, discard pile, monsters, etc.)
- Deck, relics, potions
- Map data
- Player HP, gold, floor, act
- Available commands

See the original [CommunicationMod documentation](https://github.com/ForgottenArbiter/CommunicationMod) for detailed protocol information.

## Development

### Project Structure

```
mod/
├── pom.xml                 # Maven build configuration
├── src/main/java/spirebridge/
│   ├── SpireBridge.java            # Main mod entry point
│   ├── GameStateConverter.java     # State serialization
│   ├── GameStateListener.java      # State change detection
│   ├── CommandExecutor.java        # Command parsing/execution
│   ├── ChoiceScreenUtils.java      # Choice screen utilities
│   ├── DataReader.java             # Subprocess input reader
│   ├── DataWriter.java             # Subprocess output writer
│   └── patches/                    # SpirePatch files
└── src/main/resources/
    ├── ModTheSpire.json            # Mod metadata
    └── Icon.png                    # Mod icon
```

### Building for Development

```bash
# Build without tests
mvn package -DskipTests

# Install to local Maven repo
mvn install
```

## Future Enhancements (Planned)

- WebSocket server for overlay commands
- In-game overlay rendering (card badges, commentary)
- Toggle button to show/hide AI suggestions

## Credits

- **Original Author**: [Forgotten Arbiter](https://github.com/ForgottenArbiter) - Created CommunicationMod
- **SpireBridge Fork**: slay-the-spire-mcp project

## License

This project maintains the same license as the original CommunicationMod.
