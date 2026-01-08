package spirebridge.overlay;

import basemod.BaseMod;
import basemod.interfaces.PostRenderSubscriber;
import basemod.interfaces.PostUpdateSubscriber;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.megacrit.cardcrawl.core.CardCrawlGame;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.Hitbox;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import com.megacrit.cardcrawl.helpers.TipHelper;
import com.megacrit.cardcrawl.helpers.input.InputHelper;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * In-game toggle button for the overlay display.
 *
 * Renders a button in a configurable screen corner that allows users to
 * toggle the overlay visibility on/off. Supports both mouse click and
 * keyboard shortcut (F8 by default).
 *
 * Implements PostUpdateSubscriber for input handling and PostRenderSubscriber
 * for drawing the button.
 */
public class OverlayToggleButton implements PostUpdateSubscriber, PostRenderSubscriber {

    private static final Logger logger = LogManager.getLogger(OverlayToggleButton.class.getName());

    // Singleton instance
    private static OverlayToggleButton instance;

    // Button dimensions (before scaling)
    private static final float BUTTON_WIDTH = 48f;
    private static final float BUTTON_HEIGHT = 48f;

    // Margin from screen edge
    private static final float MARGIN = 20f;

    // Keyboard shortcut key code (F8)
    private static final int TOGGLE_KEY = Input.Keys.F8;

    // Position configuration
    public enum ScreenCorner {
        TOP_LEFT,
        TOP_RIGHT,
        BOTTOM_LEFT,
        BOTTOM_RIGHT
    }

    // Current button position
    private ScreenCorner corner = ScreenCorner.TOP_RIGHT;
    private float x;
    private float y;

    // Button state
    private final Hitbox hitbox;
    private boolean isHovered = false;
    private boolean wasKeyPressed = false;

    // Colors for visual feedback
    private static final Color ENABLED_COLOR = new Color(0.4f, 1.0f, 0.4f, 1.0f);  // Green glow when enabled
    private static final Color DISABLED_COLOR = new Color(0.6f, 0.6f, 0.6f, 0.8f); // Gray when disabled
    private static final Color HOVER_COLOR = new Color(1.0f, 1.0f, 0.6f, 1.0f);    // Yellow highlight on hover

    // Tooltip text
    private static final String TOOLTIP_HEADER = "Claude Overlay";
    private static final String TOOLTIP_BODY_ENABLED = "Click or press F8 to HIDE Claude's recommendations.";
    private static final String TOOLTIP_BODY_DISABLED = "Click or press F8 to SHOW Claude's recommendations.";

    // Animation state
    private float glowPulse = 0f;

    /**
     * Private constructor for singleton pattern.
     * Initializes the button position and hitbox.
     */
    private OverlayToggleButton() {
        updatePosition();
        this.hitbox = new Hitbox(
                BUTTON_WIDTH * Settings.scale,
                BUTTON_HEIGHT * Settings.scale
        );
        updateHitboxPosition();
        logger.info("OverlayToggleButton initialized at " + corner);
    }

    /**
     * Gets the singleton instance of OverlayToggleButton.
     * Creates and registers the instance if it doesn't exist.
     *
     * @return The OverlayToggleButton singleton instance
     */
    public static synchronized OverlayToggleButton getInstance() {
        if (instance == null) {
            instance = new OverlayToggleButton();
        }
        return instance;
    }

    /**
     * Registers the button with BaseMod to receive update and render callbacks.
     * Should be called during mod initialization (PostInitialize).
     */
    public void register() {
        BaseMod.subscribe(this);
        logger.info("OverlayToggleButton registered with BaseMod");
    }

    /**
     * Unregisters the button from BaseMod.
     */
    public void unregister() {
        BaseMod.unsubscribe(this);
        logger.info("OverlayToggleButton unregistered from BaseMod");
    }

    /**
     * Sets the screen corner where the button is displayed.
     *
     * @param corner The corner to position the button
     */
    public void setCorner(ScreenCorner corner) {
        if (corner != null && corner != this.corner) {
            this.corner = corner;
            updatePosition();
            updateHitboxPosition();
            logger.info("OverlayToggleButton moved to " + corner);
        }
    }

    /**
     * Gets the current screen corner position.
     *
     * @return The current corner position
     */
    public ScreenCorner getCorner() {
        return corner;
    }

    /**
     * Updates the button position based on the current corner setting.
     */
    private void updatePosition() {
        float scaledWidth = BUTTON_WIDTH * Settings.scale;
        float scaledHeight = BUTTON_HEIGHT * Settings.scale;
        float scaledMargin = MARGIN * Settings.scale;

        switch (corner) {
            case TOP_LEFT:
                x = scaledMargin;
                y = Settings.HEIGHT - scaledMargin - scaledHeight;
                break;
            case TOP_RIGHT:
                x = Settings.WIDTH - scaledMargin - scaledWidth;
                y = Settings.HEIGHT - scaledMargin - scaledHeight;
                break;
            case BOTTOM_LEFT:
                x = scaledMargin;
                y = scaledMargin;
                break;
            case BOTTOM_RIGHT:
                x = Settings.WIDTH - scaledMargin - scaledWidth;
                y = scaledMargin;
                break;
        }
    }

    /**
     * Updates the hitbox position to match the button position.
     */
    private void updateHitboxPosition() {
        hitbox.move(
                x + (BUTTON_WIDTH * Settings.scale) / 2f,
                y + (BUTTON_HEIGHT * Settings.scale) / 2f
        );
    }

    /**
     * Handles the click/toggle action.
     * Toggles the overlay via OverlayManager.
     */
    private void onClick() {
        boolean newState = OverlayManager.getInstance().toggleEnabled();
        logger.info("Overlay toggled via button: " + (newState ? "enabled" : "disabled"));

        // Play a click sound for feedback
        CardCrawlGame.sound.play("UI_CLICK_1");
    }

    /**
     * Checks if the mouse is currently hovering over the button.
     *
     * @return true if the mouse is over the button, false otherwise
     */
    public boolean isHovered() {
        return hitbox.hovered;
    }

    /**
     * PostUpdateSubscriber callback - handles input (mouse and keyboard).
     */
    @Override
    public void receivePostUpdate() {
        // Update hitbox for hover detection
        hitbox.update();
        isHovered = hitbox.hovered;

        // Handle mouse click
        if (isHovered && InputHelper.justClickedLeft) {
            onClick();
            InputHelper.justClickedLeft = false; // Consume the click
        }

        // Handle keyboard shortcut (F8)
        boolean keyPressed = Gdx.input.isKeyPressed(TOGGLE_KEY);
        if (keyPressed && !wasKeyPressed) {
            onClick();
        }
        wasKeyPressed = keyPressed;

        // Update glow animation
        glowPulse += Gdx.graphics.getDeltaTime() * 2f;
        if (glowPulse > Math.PI * 2) {
            glowPulse -= Math.PI * 2;
        }
    }

    /**
     * PostRenderSubscriber callback - draws the button.
     *
     * @param sb The SpriteBatch used for rendering
     */
    @Override
    public void receivePostRender(SpriteBatch sb) {
        boolean enabled = OverlayManager.getInstance().isEnabled();

        // Calculate scaled dimensions
        float scaledWidth = BUTTON_WIDTH * Settings.scale;
        float scaledHeight = BUTTON_HEIGHT * Settings.scale;

        // Determine color based on state
        Color buttonColor;
        if (isHovered) {
            buttonColor = HOVER_COLOR;
        } else if (enabled) {
            // Pulsing glow when enabled
            float pulse = 0.8f + 0.2f * (float) Math.sin(glowPulse);
            buttonColor = new Color(
                    ENABLED_COLOR.r * pulse,
                    ENABLED_COLOR.g * pulse,
                    ENABLED_COLOR.b,
                    ENABLED_COLOR.a
            );
        } else {
            buttonColor = DISABLED_COLOR;
        }

        // Draw button background (rounded rectangle appearance)
        sb.setColor(buttonColor);

        // Use the game's panel texture for a consistent look
        Texture panelTexture = ImageMaster.WHITE_SQUARE_IMG;
        if (panelTexture != null) {
            sb.draw(
                    panelTexture,
                    x,
                    y,
                    scaledWidth,
                    scaledHeight
            );
        }

        // Draw border/outline
        sb.setColor(isHovered ? Color.WHITE : new Color(0.2f, 0.2f, 0.2f, 1f));
        float borderWidth = 2f * Settings.scale;

        // Top border
        sb.draw(panelTexture, x, y + scaledHeight - borderWidth, scaledWidth, borderWidth);
        // Bottom border
        sb.draw(panelTexture, x, y, scaledWidth, borderWidth);
        // Left border
        sb.draw(panelTexture, x, y, borderWidth, scaledHeight);
        // Right border
        sb.draw(panelTexture, x + scaledWidth - borderWidth, y, borderWidth, scaledHeight);

        // Draw icon/text inside button
        sb.setColor(Color.WHITE);
        String iconText = enabled ? "AI" : "ai";
        FontHelper.renderFontCentered(
                sb,
                FontHelper.buttonLabelFont,
                iconText,
                x + scaledWidth / 2f,
                y + scaledHeight / 2f,
                enabled ? Color.WHITE : Color.DARK_GRAY
        );

        // Show tooltip when hovered
        if (isHovered) {
            String tooltipBody = enabled ? TOOLTIP_BODY_ENABLED : TOOLTIP_BODY_DISABLED;
            TipHelper.renderGenericTip(
                    InputHelper.mX + 20f * Settings.scale,
                    InputHelper.mY - 20f * Settings.scale,
                    TOOLTIP_HEADER,
                    tooltipBody
            );
        }

        // Draw keyboard shortcut hint below button
        if (isHovered) {
            FontHelper.renderFontCentered(
                    sb,
                    FontHelper.tipBodyFont,
                    "[F8]",
                    x + scaledWidth / 2f,
                    y - 15f * Settings.scale,
                    Color.LIGHT_GRAY
            );
        }
    }

    /**
     * Resets the singleton instance.
     * Primarily for testing purposes.
     */
    public static synchronized void resetInstance() {
        if (instance != null) {
            instance.unregister();
            instance = null;
            LogManager.getLogger(OverlayToggleButton.class.getName()).debug("OverlayToggleButton instance reset");
        }
    }
}
