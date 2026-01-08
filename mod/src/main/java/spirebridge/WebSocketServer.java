package spirebridge;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.nanohttpd.protocols.http.IHTTPSession;
import org.nanohttpd.protocols.websockets.CloseCode;
import org.nanohttpd.protocols.websockets.NanoWSD;
import org.nanohttpd.protocols.websockets.WebSocket;
import org.nanohttpd.protocols.websockets.WebSocketFrame;

import java.io.IOException;
import java.util.Collections;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket server for SpireBridge that enables real-time communication
 * with overlay clients (e.g., MCP server pushing analysis results).
 *
 * Broadcasts game state updates to all connected clients and receives
 * commands for future use.
 */
public class WebSocketServer extends NanoWSD {

    private static final Logger logger = LogManager.getLogger(WebSocketServer.class.getName());

    public static final int DEFAULT_PORT = 7778;

    private final Set<SpireBridgeWebSocket> connectedClients;
    private volatile boolean running = false;

    /**
     * Creates a WebSocket server on the specified port.
     * @param port The port to listen on
     */
    public WebSocketServer(int port) {
        super(port);
        this.connectedClients = Collections.newSetFromMap(new ConcurrentHashMap<>());
        logger.info("WebSocket server created on port " + port);
    }

    /**
     * Creates a WebSocket server on the default port (7778).
     */
    public WebSocketServer() {
        this(DEFAULT_PORT);
    }

    @Override
    protected WebSocket openWebSocket(IHTTPSession handshake) {
        return new SpireBridgeWebSocket(handshake);
    }

    /**
     * Starts the WebSocket server.
     * @return true if server started successfully, false otherwise
     */
    public boolean startServer() {
        try {
            start(0); // 0 means use default socket timeout
            running = true;
            logger.info("WebSocket server started on port " + getListeningPort());
            return true;
        } catch (IOException e) {
            logger.error("Failed to start WebSocket server: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Stops the WebSocket server and disconnects all clients.
     */
    public void stopServer() {
        running = false;

        // Close all connected clients
        for (SpireBridgeWebSocket client : connectedClients) {
            try {
                client.close(CloseCode.GoingAway, "Server shutting down", false);
            } catch (IOException e) {
                logger.warn("Error closing client connection: " + e.getMessage());
            }
        }
        connectedClients.clear();

        stop();
        logger.info("WebSocket server stopped");
    }

    /**
     * Broadcasts a message to all connected clients.
     * @param message The message to broadcast (typically JSON game state)
     */
    public void broadcast(String message) {
        if (!running) {
            return;
        }

        for (SpireBridgeWebSocket client : connectedClients) {
            try {
                client.send(message);
            } catch (IOException e) {
                logger.warn("Failed to send message to client: " + e.getMessage());
                // Client will be removed when onClose is called
            }
        }
    }

    /**
     * Returns the number of currently connected clients.
     * @return Number of connected clients
     */
    public int getClientCount() {
        return connectedClients.size();
    }

    /**
     * Returns whether the server is currently running.
     * @return true if server is running, false otherwise
     */
    public boolean isRunning() {
        return running;
    }

    /**
     * Inner class representing a single WebSocket connection.
     */
    private class SpireBridgeWebSocket extends WebSocket {

        public SpireBridgeWebSocket(IHTTPSession handshakeRequest) {
            super(handshakeRequest);
        }

        @Override
        protected void onOpen() {
            connectedClients.add(this);
            logger.info("WebSocket client connected. Total clients: " + connectedClients.size());

            // Send current game state to newly connected client
            if (GameStateListener.isWaitingForCommand()) {
                try {
                    String state = GameStateConverter.getCommunicationState();
                    send(state);
                } catch (IOException e) {
                    logger.warn("Failed to send initial state to client: " + e.getMessage());
                }
            }
        }

        @Override
        protected void onClose(CloseCode code, String reason, boolean initiatedByRemote) {
            connectedClients.remove(this);
            logger.info("WebSocket client disconnected (code: " + code + ", reason: " + reason +
                       ", remote: " + initiatedByRemote + "). Total clients: " + connectedClients.size());
        }

        @Override
        protected void onMessage(WebSocketFrame message) {
            String payload = message.getTextPayload();
            logger.debug("Received WebSocket message: " + payload);

            // Queue the command for processing by the main game thread
            // This ensures thread safety with the game's update loop
            SpireBridge.queueCommand(payload);
        }

        @Override
        protected void onPong(WebSocketFrame pong) {
            // Pong received, connection is alive
            logger.debug("Received pong from client");
        }

        @Override
        protected void onException(IOException exception) {
            logger.error("WebSocket exception: " + exception.getMessage());
            connectedClients.remove(this);
        }
    }
}
