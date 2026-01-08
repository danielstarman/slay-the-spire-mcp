package spirebridge.overlay;

/**
 * Listener interface for overlay state changes.
 * Renderers implement this to receive updates when recommendations change
 * or when the overlay is toggled on/off.
 */
public interface OverlayListener {

    /**
     * Called when Claude's recommendations have been updated.
     * This includes card scores, action suggestions, and other analysis results.
     */
    void onRecommendationsUpdated();

    /**
     * Called when the overlay visibility is toggled.
     * @param enabled true if the overlay is now enabled, false if disabled
     */
    void onOverlayToggled(boolean enabled);
}
