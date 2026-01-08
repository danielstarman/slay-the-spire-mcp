package spirebridge.overlay;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Singleton manager for overlay state and Claude's recommendations.
 *
 * Coordinates overlay visibility, stores current recommendations (card scores,
 * action suggestions), and notifies renderers when state changes.
 *
 * Receives updates via WebSocket from the MCP server containing Claude's
 * analysis of the current game state.
 *
 * Thread-safe: Uses CopyOnWriteArrayList for listeners and synchronized
 * access to mutable state. WebSocket messages may arrive on different threads.
 */
public class OverlayManager {

    private static final Logger logger = LogManager.getLogger(OverlayManager.class.getName());

    // Singleton instance
    private static OverlayManager instance;

    // Overlay visibility state
    private volatile boolean enabled = true;

    // Card scores from Claude's analysis: cardId -> score (0-100)
    private final Map<String, Integer> cardScores;

    // Current recommended action from Claude
    private volatile String recommendedAction;

    // Additional context/explanation for the recommendation
    private volatile String recommendationReason;

    // Raw JSON of the last recommendations (for debugging/advanced use)
    private volatile JsonObject lastRecommendations;

    // Listeners to notify on state changes
    private final List<OverlayListener> listeners;

    /**
     * Private constructor for singleton pattern.
     */
    private OverlayManager() {
        this.cardScores = new HashMap<>();
        this.listeners = new CopyOnWriteArrayList<>();
        this.recommendedAction = null;
        this.recommendationReason = null;
        this.lastRecommendations = null;
        logger.info("OverlayManager initialized");
    }

    /**
     * Gets the singleton instance of OverlayManager.
     * Creates the instance if it doesn't exist.
     *
     * @return The OverlayManager singleton instance
     */
    public static synchronized OverlayManager getInstance() {
        if (instance == null) {
            instance = new OverlayManager();
        }
        return instance;
    }

    /**
     * Sets the overlay visibility state.
     * Notifies all listeners of the change.
     *
     * @param enabled true to enable the overlay, false to disable
     */
    public void setEnabled(boolean enabled) {
        if (this.enabled != enabled) {
            this.enabled = enabled;
            logger.info("Overlay " + (enabled ? "enabled" : "disabled"));
            notifyOverlayToggled(enabled);
        }
    }

    /**
     * Returns whether the overlay is currently enabled.
     *
     * @return true if the overlay is enabled, false otherwise
     */
    public boolean isEnabled() {
        return enabled;
    }

    /**
     * Toggles the overlay visibility state.
     * Convenience method that inverts the current state.
     *
     * @return The new enabled state after toggling
     */
    public boolean toggleEnabled() {
        setEnabled(!enabled);
        return enabled;
    }

    /**
     * Updates recommendations from Claude based on incoming JSON data.
     *
     * Expected JSON format:
     * {
     *   "type": "recommendations",
     *   "cardScores": {
     *     "cardId1": 85,
     *     "cardId2": 42,
     *     ...
     *   },
     *   "recommendedAction": "Play Strike on Jaw Worm",
     *   "reason": "Maximizes damage while preserving block for next turn"
     * }
     *
     * @param recommendations The JSON object containing Claude's recommendations
     */
    public void updateRecommendations(JsonObject recommendations) {
        if (recommendations == null) {
            logger.warn("Received null recommendations");
            return;
        }

        this.lastRecommendations = recommendations;
        logger.debug("Updating recommendations: " + recommendations.toString());

        // Parse card scores
        synchronized (cardScores) {
            cardScores.clear();

            if (recommendations.has("cardScores")) {
                JsonElement scoresElement = recommendations.get("cardScores");
                if (scoresElement.isJsonObject()) {
                    JsonObject scores = scoresElement.getAsJsonObject();
                    for (Map.Entry<String, JsonElement> entry : scores.entrySet()) {
                        try {
                            int score = entry.getValue().getAsInt();
                            cardScores.put(entry.getKey(), score);
                        } catch (Exception e) {
                            logger.warn("Failed to parse score for card " + entry.getKey() + ": " + e.getMessage());
                        }
                    }
                }
            }
        }

        // Parse recommended action
        if (recommendations.has("recommendedAction")) {
            try {
                this.recommendedAction = recommendations.get("recommendedAction").getAsString();
            } catch (Exception e) {
                logger.warn("Failed to parse recommendedAction: " + e.getMessage());
                this.recommendedAction = null;
            }
        } else {
            this.recommendedAction = null;
        }

        // Parse reason/explanation
        if (recommendations.has("reason")) {
            try {
                this.recommendationReason = recommendations.get("reason").getAsString();
            } catch (Exception e) {
                logger.warn("Failed to parse reason: " + e.getMessage());
                this.recommendationReason = null;
            }
        } else {
            this.recommendationReason = null;
        }

        logger.info("Updated recommendations: " + cardScores.size() + " card scores, action: " + recommendedAction);

        // Notify listeners
        notifyRecommendationsUpdated();
    }

    /**
     * Parses and updates recommendations from a JSON string.
     * Convenience method for WebSocket message handling.
     *
     * @param jsonString The JSON string containing recommendations
     * @return true if parsing succeeded, false otherwise
     */
    public boolean updateRecommendationsFromString(String jsonString) {
        if (jsonString == null || jsonString.trim().isEmpty()) {
            logger.warn("Received empty recommendations string");
            return false;
        }

        try {
            JsonParser parser = new JsonParser();
            JsonElement element = parser.parse(jsonString);

            if (!element.isJsonObject()) {
                logger.warn("Recommendations JSON is not an object");
                return false;
            }

            JsonObject recommendations = element.getAsJsonObject();

            // Check if this is a recommendations message
            if (recommendations.has("type")) {
                String type = recommendations.get("type").getAsString();
                if (!"recommendations".equals(type)) {
                    logger.debug("Ignoring non-recommendations message of type: " + type);
                    return false;
                }
            }

            updateRecommendations(recommendations);
            return true;

        } catch (Exception e) {
            logger.error("Failed to parse recommendations JSON: " + e.getMessage());
            return false;
        }
    }

    /**
     * Gets Claude's score for a specific card.
     *
     * @param cardId The card identifier (typically card.uuid or card.cardID)
     * @return The score (0-100) or -1 if no score is available for this card
     */
    public int getCardScore(String cardId) {
        if (cardId == null) {
            return -1;
        }

        synchronized (cardScores) {
            Integer score = cardScores.get(cardId);
            return score != null ? score : -1;
        }
    }

    /**
     * Gets all current card scores.
     *
     * @return A copy of the card scores map (cardId -> score)
     */
    public Map<String, Integer> getAllCardScores() {
        synchronized (cardScores) {
            return new HashMap<>(cardScores);
        }
    }

    /**
     * Gets the current recommended action from Claude.
     *
     * @return The recommended action string, or null if none available
     */
    public String getRecommendedAction() {
        return recommendedAction;
    }

    /**
     * Gets the explanation/reason for the current recommendation.
     *
     * @return The recommendation reason, or null if none available
     */
    public String getRecommendationReason() {
        return recommendationReason;
    }

    /**
     * Returns whether there are any current recommendations.
     *
     * @return true if recommendations are available, false otherwise
     */
    public boolean hasRecommendations() {
        synchronized (cardScores) {
            return !cardScores.isEmpty() || recommendedAction != null;
        }
    }

    /**
     * Clears all current recommendations.
     * Useful when transitioning between game states.
     */
    public void clearRecommendations() {
        synchronized (cardScores) {
            cardScores.clear();
        }
        this.recommendedAction = null;
        this.recommendationReason = null;
        this.lastRecommendations = null;
        logger.debug("Recommendations cleared");
        notifyRecommendationsUpdated();
    }

    /**
     * Gets the raw JSON of the last recommendations.
     * Useful for debugging or advanced use cases.
     *
     * @return The last recommendations JsonObject, or null if none
     */
    public JsonObject getLastRecommendations() {
        return lastRecommendations;
    }

    /**
     * Adds a listener to receive overlay state updates.
     *
     * @param listener The listener to add
     */
    public void addListener(OverlayListener listener) {
        if (listener != null && !listeners.contains(listener)) {
            listeners.add(listener);
            logger.debug("Added overlay listener: " + listener.getClass().getSimpleName());
        }
    }

    /**
     * Removes a listener from receiving overlay state updates.
     *
     * @param listener The listener to remove
     */
    public void removeListener(OverlayListener listener) {
        if (listener != null) {
            listeners.remove(listener);
            logger.debug("Removed overlay listener: " + listener.getClass().getSimpleName());
        }
    }

    /**
     * Gets the count of registered listeners.
     *
     * @return Number of registered listeners
     */
    public int getListenerCount() {
        return listeners.size();
    }

    /**
     * Notifies all listeners that recommendations have been updated.
     */
    private void notifyRecommendationsUpdated() {
        for (OverlayListener listener : listeners) {
            try {
                listener.onRecommendationsUpdated();
            } catch (Exception e) {
                logger.error("Error notifying listener of recommendations update: " + e.getMessage());
            }
        }
    }

    /**
     * Notifies all listeners that the overlay has been toggled.
     *
     * @param enabled The new enabled state
     */
    private void notifyOverlayToggled(boolean enabled) {
        for (OverlayListener listener : listeners) {
            try {
                listener.onOverlayToggled(enabled);
            } catch (Exception e) {
                logger.error("Error notifying listener of overlay toggle: " + e.getMessage());
            }
        }
    }

    /**
     * Resets the singleton instance.
     * Primarily for testing purposes.
     */
    public static synchronized void resetInstance() {
        if (instance != null) {
            instance.listeners.clear();
            instance.cardScores.clear();
            instance = null;
            LogManager.getLogger(OverlayManager.class.getName()).debug("OverlayManager instance reset");
        }
    }
}
