package spirebridge;

import basemod.*;
import basemod.interfaces.PostDungeonUpdateSubscriber;
import basemod.interfaces.PostInitializeSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import basemod.interfaces.PreUpdateSubscriber;
import com.evacipated.cardcrawl.modthespire.lib.SpireConfig;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import com.google.gson.Gson;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import spirebridge.overlay.OverlayManager;
import spirebridge.overlay.OverlayRenderer;
import spirebridge.overlay.OverlayToggleButton;
import spirebridge.patches.InputActionPatch;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.IOException;
import java.lang.ProcessBuilder;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Properties;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

@SpireInitializer
public class SpireBridge implements PostInitializeSubscriber, PostUpdateSubscriber, PostDungeonUpdateSubscriber, PreUpdateSubscriber, OnStateChangeSubscriber {

    private static Process listener;
    private static StringBuilder inputBuffer = new StringBuilder();
    public static boolean messageReceived = false;
    private static final Logger logger = LogManager.getLogger(SpireBridge.class.getName());
    private static Thread writeThread;
    private static BlockingQueue<String> writeQueue;
    private static Thread readThread;
    private static BlockingQueue<String> readQueue;
    private static final String MODNAME = "SpireBridge";
    private static final String AUTHOR = "slay-the-spire-mcp (forked from Forgotten Arbiter)";
    private static final String DESCRIPTION = "A fork of CommunicationMod with overlay capabilities for Claude MCP integration.";
    public static boolean mustSendGameState = false;
    private static ArrayList<OnStateChangeSubscriber> onStateChangeSubscribers;

    // WebSocket server for overlay communication
    private static WebSocketServer webSocketServer;
    private static final String WEBSOCKET_PORT_OPTION = "websocketPort";

    // Overlay renderer for drawing Claude's recommendations
    private static OverlayRenderer overlayRenderer;
    private static final String WEBSOCKET_ENABLED_OPTION = "websocketEnabled";
    private static final String OVERLAY_ENABLED_OPTION = "overlayEnabled";
    private static final int DEFAULT_WEBSOCKET_PORT = WebSocketServer.DEFAULT_PORT;
    private static final boolean DEFAULT_WEBSOCKET_ENABLED = true;
    private static final boolean DEFAULT_OVERLAY_ENABLED = true;

    private static SpireConfig communicationConfig;
    private static final String COMMAND_OPTION = "command";
    private static final String GAME_START_OPTION = "runAtGameStart";
    private static final String VERBOSE_OPTION = "verbose";
    private static final String INITIALIZATION_TIMEOUT_OPTION = "maxInitializationTimeout";
    private static final String DEFAULT_COMMAND = "";
    private static final long DEFAULT_TIMEOUT = 10L;
    private static final boolean DEFAULT_VERBOSITY = true;

    public SpireBridge(){
        BaseMod.subscribe(this);
        onStateChangeSubscribers = new ArrayList<>();
        SpireBridge.subscribe(this);
        readQueue = new LinkedBlockingQueue<>();

        // Initialize and register the overlay renderer
        overlayRenderer = new OverlayRenderer();
        BaseMod.subscribe(overlayRenderer);
        try {
            Properties defaults = new Properties();
            defaults.put(GAME_START_OPTION, Boolean.toString(false));
            defaults.put(INITIALIZATION_TIMEOUT_OPTION, Long.toString(DEFAULT_TIMEOUT));
            defaults.put(VERBOSE_OPTION, Boolean.toString(DEFAULT_VERBOSITY));
            defaults.put(WEBSOCKET_PORT_OPTION, Integer.toString(DEFAULT_WEBSOCKET_PORT));
            defaults.put(WEBSOCKET_ENABLED_OPTION, Boolean.toString(DEFAULT_WEBSOCKET_ENABLED));
            defaults.put(OVERLAY_ENABLED_OPTION, Boolean.toString(DEFAULT_OVERLAY_ENABLED));
            communicationConfig = new SpireConfig("SpireBridge", "config", defaults);
            String command = communicationConfig.getString(COMMAND_OPTION);
            // I want this to always be saved to the file so people can set it more easily.
            if (command == null) {
                communicationConfig.setString(COMMAND_OPTION, DEFAULT_COMMAND);
                communicationConfig.save();
            }
            communicationConfig.save();
        } catch (IOException e) {
            e.printStackTrace();
        }

        if(getRunOnGameStartOption()) {
            boolean success = startExternalProcess();
        }

        // Start WebSocket server if enabled
        if(getWebSocketEnabledOption()) {
            startWebSocketServer();
        }

        // Initialize overlay enabled state from config
        OverlayManager.getInstance().setEnabled(getOverlayEnabledOption());
    }

    public static void initialize() {
        SpireBridge mod = new SpireBridge();
    }

    public void receivePreUpdate() {
        if(listener != null && !listener.isAlive() && writeThread != null && writeThread.isAlive()) {
            logger.info("Child process has died...");
            writeThread.interrupt();
            readThread.interrupt();
        }
        if(messageAvailable()) {
            try {
                boolean stateChanged = CommandExecutor.executeCommand(readMessage());
                if(stateChanged) {
                    GameStateListener.registerCommandExecution();
                }
            } catch (InvalidCommandException e) {
                HashMap<String, Object> jsonError = new HashMap<>();
                jsonError.put("error", e.getMessage());
                jsonError.put("ready_for_command", GameStateListener.isWaitingForCommand());
                Gson gson = new Gson();
                sendMessage(gson.toJson(jsonError));
            }
        }
    }

    public static void subscribe(OnStateChangeSubscriber sub) {
        onStateChangeSubscribers.add(sub);
    }

    public static void publishOnGameStateChange() {
        for(OnStateChangeSubscriber sub : onStateChangeSubscribers) {
            sub.receiveOnStateChange();
        }
    }

    public void receiveOnStateChange() {
        sendGameState();
        // Also broadcast to WebSocket clients
        broadcastToWebSocket();
    }

    public static void queueCommand(String command) {
        readQueue.add(command);
    }

    public void receivePostInitialize() {
        setUpOptionsMenu();
        // Register the overlay toggle button for in-game control
        OverlayToggleButton.getInstance().register();
    }

    public void receivePostUpdate() {
        if(!mustSendGameState && GameStateListener.checkForMenuStateChange()) {
            mustSendGameState = true;
        }
        if(mustSendGameState) {
            publishOnGameStateChange();
            mustSendGameState = false;
        }
        InputActionPatch.doKeypress = false;
    }

    public void receivePostDungeonUpdate() {
        if (GameStateListener.checkForDungeonStateChange()) {
            mustSendGameState = true;
        }
        if(AbstractDungeon.getCurrRoom().isBattleOver) {
            GameStateListener.signalTurnEnd();
        }
    }

    private void setUpOptionsMenu() {
        ModPanel settingsPanel = new ModPanel();
        ModLabeledToggleButton gameStartOptionButton = new ModLabeledToggleButton(
                "Start external process at game launch",
                350, 550, Settings.CREAM_COLOR, FontHelper.charDescFont,
                getRunOnGameStartOption(), settingsPanel, modLabel -> {},
                modToggleButton -> {
                    if (communicationConfig != null) {
                        communicationConfig.setBool(GAME_START_OPTION, modToggleButton.enabled);
                        try {
                            communicationConfig.save();
                        } catch (IOException e) {
                            e.printStackTrace();
                        }
                    }
                });
        settingsPanel.addUIElement(gameStartOptionButton);

        ModLabel externalCommandLabel = new ModLabel(
                "", 350, 600, Settings.CREAM_COLOR, FontHelper.charDescFont,
                settingsPanel, modLabel -> {
                    modLabel.text = String.format("External Process Command: %s", getSubprocessCommandString());
                });
        settingsPanel.addUIElement(externalCommandLabel);

        ModButton startProcessButton = new ModButton(
                350, 650, settingsPanel, modButton -> {
                    BaseMod.modSettingsUp = false;
                    startExternalProcess();
                });
        settingsPanel.addUIElement(startProcessButton);

        ModLabel startProcessLabel = new ModLabel(
                "(Re)start external process",
                475, 700, Settings.CREAM_COLOR, FontHelper.charDescFont,
                settingsPanel, modLabel -> {
                    if(listener != null && listener.isAlive()) {
                        modLabel.text = "Restart external process";
                    } else {
                        modLabel.text = "Start external process";
                    }
                });
        settingsPanel.addUIElement(startProcessLabel);

        ModButton editProcessButton = new ModButton(
                850, 650, settingsPanel, modButton -> {});
        settingsPanel.addUIElement(editProcessButton);

        ModLabel editProcessLabel = new ModLabel(
                "Set command (not implemented)",
                975, 700, Settings.CREAM_COLOR, FontHelper.charDescFont,
                settingsPanel, modLabel -> {});
        settingsPanel.addUIElement(editProcessLabel);

        ModLabeledToggleButton verbosityOption = new ModLabeledToggleButton(
                "Suppress verbose log output",
                350, 500, Settings.CREAM_COLOR, FontHelper.charDescFont,
                getVerbosityOption(), settingsPanel, modLabel -> {},
                modToggleButton -> {
                    if (communicationConfig != null) {
                        communicationConfig.setBool(VERBOSE_OPTION, modToggleButton.enabled);
                        try {
                            communicationConfig.save();
                        } catch (IOException e) {
                            e.printStackTrace();
                        }
                    }
                });
        settingsPanel.addUIElement(verbosityOption);

        // WebSocket server toggle
        ModLabeledToggleButton websocketEnabledOption = new ModLabeledToggleButton(
                "Enable WebSocket server for overlay",
                350, 450, Settings.CREAM_COLOR, FontHelper.charDescFont,
                getWebSocketEnabledOption(), settingsPanel, modLabel -> {},
                modToggleButton -> {
                    if (communicationConfig != null) {
                        communicationConfig.setBool(WEBSOCKET_ENABLED_OPTION, modToggleButton.enabled);
                        try {
                            communicationConfig.save();
                        } catch (IOException e) {
                            e.printStackTrace();
                        }
                        // Start or stop server based on toggle
                        if (modToggleButton.enabled) {
                            startWebSocketServer();
                        } else {
                            stopWebSocketServer();
                        }
                    }
                });
        settingsPanel.addUIElement(websocketEnabledOption);

        // WebSocket status label
        ModLabel websocketStatusLabel = new ModLabel(
                "", 350, 400, Settings.CREAM_COLOR, FontHelper.charDescFont,
                settingsPanel, modLabel -> {
                    if (isWebSocketServerRunning()) {
                        int clients = getWebSocketClientCount();
                        modLabel.text = String.format("WebSocket: Running on port %d (%d client%s)",
                                getWebSocketPortOption(), clients, clients == 1 ? "" : "s");
                    } else {
                        modLabel.text = "WebSocket: Not running";
                    }
                });
        settingsPanel.addUIElement(websocketStatusLabel);

        // Overlay visibility toggle
        ModLabeledToggleButton overlayEnabledOption = new ModLabeledToggleButton(
                "Show Claude's overlay recommendations",
                350, 350, Settings.CREAM_COLOR, FontHelper.charDescFont,
                getOverlayEnabledOption(), settingsPanel, modLabel -> {},
                modToggleButton -> {
                    if (communicationConfig != null) {
                        communicationConfig.setBool(OVERLAY_ENABLED_OPTION, modToggleButton.enabled);
                        try {
                            communicationConfig.save();
                        } catch (IOException e) {
                            e.printStackTrace();
                        }
                        // Update OverlayManager state
                        OverlayManager.getInstance().setEnabled(modToggleButton.enabled);
                    }
                });
        settingsPanel.addUIElement(overlayEnabledOption);

        BaseMod.registerModBadge(ImageMaster.loadImage("Icon.png"), MODNAME, AUTHOR, DESCRIPTION, settingsPanel);
    }

    private void startCommunicationThreads() {
        writeQueue = new LinkedBlockingQueue<>();
        writeThread = new Thread(new DataWriter(writeQueue, listener.getOutputStream(), getVerbosityOption()));
        writeThread.start();
        readThread = new Thread(new DataReader(readQueue, listener.getInputStream(), getVerbosityOption()));
        readThread.start();
    }

    private static void sendGameState() {
        String state = GameStateConverter.getCommunicationState();
        sendMessage(state);
    }

    public static void dispose() {
        logger.info("Shutting down child process...");
        if(listener != null) {
            listener.destroy();
        }
        stopWebSocketServer();

        // Clean up overlay renderer
        if (overlayRenderer != null) {
            overlayRenderer.dispose();
            overlayRenderer = null;
        }
    }

    private static void sendMessage(String message) {
        if(writeQueue != null && writeThread.isAlive()) {
            writeQueue.add(message);
        }
    }

    private static boolean messageAvailable() {
        return readQueue != null && !readQueue.isEmpty();
    }

    private static String readMessage() {
        if(messageAvailable()) {
            return readQueue.remove();
        } else {
            return null;
        }
    }

    private static String readMessageBlocking() {
        try {
            return readQueue.poll(getInitializationTimeoutOption(), TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            throw new RuntimeException("Interrupted while trying to read message from subprocess.");
        }
    }

    private static String[] getSubprocessCommand() {
        if (communicationConfig == null) {
            return new String[0];
        }
        return communicationConfig.getString(COMMAND_OPTION).trim().split("\\s+");
    }

    private static String getSubprocessCommandString() {
        if (communicationConfig == null) {
            return "";
        }
        return communicationConfig.getString(COMMAND_OPTION).trim();
    }

    private static boolean getRunOnGameStartOption() {
        if (communicationConfig == null) {
            return false;
        }
        return communicationConfig.getBool(GAME_START_OPTION);
    }

    private static long getInitializationTimeoutOption() {
        if (communicationConfig == null) {
            return DEFAULT_TIMEOUT;
        }
        return (long)communicationConfig.getInt(INITIALIZATION_TIMEOUT_OPTION);
    }

    private static boolean getVerbosityOption() {
        if (communicationConfig == null) {
            return DEFAULT_VERBOSITY;
        }
        return communicationConfig.getBool(VERBOSE_OPTION);
    }

    private static int getWebSocketPortOption() {
        if (communicationConfig == null) {
            return DEFAULT_WEBSOCKET_PORT;
        }
        return communicationConfig.getInt(WEBSOCKET_PORT_OPTION);
    }

    private static boolean getWebSocketEnabledOption() {
        if (communicationConfig == null) {
            return DEFAULT_WEBSOCKET_ENABLED;
        }
        return communicationConfig.getBool(WEBSOCKET_ENABLED_OPTION);
    }

    private static boolean getOverlayEnabledOption() {
        if (communicationConfig == null) {
            return DEFAULT_OVERLAY_ENABLED;
        }
        return communicationConfig.getBool(OVERLAY_ENABLED_OPTION);
    }

    /**
     * Starts the WebSocket server for overlay communication.
     * @return true if server started successfully, false otherwise
     */
    public static boolean startWebSocketServer() {
        if (webSocketServer != null && webSocketServer.isRunning()) {
            logger.info("WebSocket server already running");
            return true;
        }

        int port = getWebSocketPortOption();
        webSocketServer = new WebSocketServer(port);
        boolean success = webSocketServer.startServer();

        if (success) {
            logger.info("WebSocket server started on port " + port);
        } else {
            logger.error("Failed to start WebSocket server on port " + port);
        }

        return success;
    }

    /**
     * Stops the WebSocket server.
     */
    public static void stopWebSocketServer() {
        if (webSocketServer != null) {
            webSocketServer.stopServer();
            webSocketServer = null;
            logger.info("WebSocket server stopped");
        }
    }

    /**
     * Broadcasts the current game state to all connected WebSocket clients.
     */
    private static void broadcastToWebSocket() {
        if (webSocketServer != null && webSocketServer.isRunning()) {
            String state = GameStateConverter.getCommunicationState();
            webSocketServer.broadcast(state);
        }
    }

    /**
     * Returns the number of connected WebSocket clients.
     * @return Number of connected clients, or 0 if server is not running
     */
    public static int getWebSocketClientCount() {
        if (webSocketServer != null && webSocketServer.isRunning()) {
            return webSocketServer.getClientCount();
        }
        return 0;
    }

    /**
     * Returns whether the WebSocket server is currently running.
     * @return true if server is running, false otherwise
     */
    public static boolean isWebSocketServerRunning() {
        return webSocketServer != null && webSocketServer.isRunning();
    }

    private boolean startExternalProcess() {
        if(readThread != null) {
            readThread.interrupt();
        }
        if(writeThread != null) {
            writeThread.interrupt();
        }
        if(listener != null) {
            listener.destroy();
            try {
                boolean success = listener.waitFor(2, TimeUnit.SECONDS);
                if (!success) {
                    listener.destroyForcibly();
                }
            } catch (InterruptedException e) {
                e.printStackTrace();
                listener.destroyForcibly();
            }
        }
        ProcessBuilder builder = new ProcessBuilder(getSubprocessCommand());
        File errorLog = new File("communication_mod_errors.log");
        builder.redirectError(ProcessBuilder.Redirect.appendTo(errorLog));
        try {
            listener = builder.start();
        } catch (IOException e) {
            logger.error("Could not start external process.");
            e.printStackTrace();
        }
        if(listener != null) {
            startCommunicationThreads();
            // We wait for the child process to signal it is ready before we proceed. Note that the game
            // will hang while this is occurring, and it will time out after a specified waiting time.
            String message = readMessageBlocking();
            if(message == null) {
                // The child process waited too long to respond, so we kill it.
                readThread.interrupt();
                writeThread.interrupt();
                listener.destroy();
                logger.error("Timed out while waiting for signal from external process.");
                logger.error("Check communication_mod_errors.log for stderr from the process.");
                return false;
            } else {
                logger.info(String.format("Received message from external process: %s", message));
                if (GameStateListener.isWaitingForCommand()) {
                    mustSendGameState = true;
                }
                return true;
            }
        }
        return false;
    }

}
