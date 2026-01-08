package spirebridge.overlay;

import basemod.interfaces.PostRenderSubscriber;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.GlyphLayout;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.helpers.FontHelper;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Renders Claude's recommendations as an overlay on the game screen.
 *
 * Implements PostRenderSubscriber to draw after the game's normal rendering.
 * Draws:
 * - Recommendation panel showing Claude's advice and commentary
 * - Card badges showing scores/percentages on cards in hand (delegated to CardBadgeRenderer)
 * - Action hints suggesting next move
 *
 * Uses libGDX SpriteBatch for text and ShapeRenderer for backgrounds.
 * Respects overlay enabled/disabled state from OverlayManager.
 */
public class OverlayRenderer implements PostRenderSubscriber, OverlayListener {

    private static final Logger logger = LogManager.getLogger(OverlayRenderer.class.getName());

    // Panel positioning and sizing
    private static final float PANEL_X = 20f;
    private static final float PANEL_Y_OFFSET = 300f; // Offset from top
    private static final float PANEL_WIDTH = 350f;
    private static final float PANEL_PADDING = 15f;
    private static final float LINE_HEIGHT = 25f;

    // Colors
    private static final Color PANEL_BACKGROUND = new Color(0.1f, 0.1f, 0.15f, 0.85f);
    private static final Color PANEL_BORDER = new Color(0.4f, 0.6f, 0.9f, 0.9f);
    private static final Color TEXT_COLOR = new Color(0.95f, 0.95f, 0.95f, 1f);
    private static final Color HIGHLIGHT_COLOR = new Color(0.4f, 0.8f, 1f, 1f);

    // Shape renderer for drawing backgrounds and boxes
    private ShapeRenderer shapeRenderer;

    // Layout helper for text measurement
    private final GlyphLayout glyphLayout;

    // Reference to the overlay manager
    private final OverlayManager overlayManager;

    // Delegate renderer for card badges
    private final CardBadgeRenderer cardBadgeRenderer;

    // Cache for whether we need to render (avoids unnecessary checks)
    private volatile boolean needsRender = false;

    /**
     * Creates a new OverlayRenderer.
     * Registers itself with the OverlayManager for updates.
     */
    public OverlayRenderer() {
        this.overlayManager = OverlayManager.getInstance();
        this.glyphLayout = new GlyphLayout();
        this.shapeRenderer = null; // Lazy init in render thread
        this.cardBadgeRenderer = new CardBadgeRenderer();

        // Register for updates from OverlayManager
        overlayManager.addListener(this);

        logger.info("OverlayRenderer initialized");
    }

    /**
     * Main render hook called after the game's normal rendering.
     * Draws overlay elements when enabled and recommendations are available.
     *
     * @param sb The SpriteBatch used for rendering
     */
    @Override
    public void receivePostRender(SpriteBatch sb) {
        // Skip if overlay is disabled
        if (!overlayManager.isEnabled()) {
            return;
        }

        // Skip if no recommendations to show
        if (!overlayManager.hasRecommendations()) {
            return;
        }

        // Skip if not in dungeon
        if (AbstractDungeon.player == null) {
            return;
        }

        try {
            // Ensure shape renderer is initialized (must be done on render thread)
            if (shapeRenderer == null) {
                shapeRenderer = new ShapeRenderer();
            }

            // Render the recommendation panel
            renderRecommendationPanel(sb);

            // Render card badges during combat (delegated to CardBadgeRenderer)
            if (AbstractDungeon.getCurrRoom() != null &&
                AbstractDungeon.getCurrRoom().phase == com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase.COMBAT) {
                cardBadgeRenderer.renderCardBadges(sb);
            }

            // Render action hint
            renderActionHint(sb);

        } catch (Exception e) {
            logger.error("Error during overlay rendering: " + e.getMessage());
        }
    }

    /**
     * Renders the main recommendation panel showing Claude's advice.
     *
     * @param sb The SpriteBatch for rendering
     */
    private void renderRecommendationPanel(SpriteBatch sb) {
        String action = overlayManager.getRecommendedAction();
        String reason = overlayManager.getRecommendationReason();

        // Calculate panel height based on content
        float panelHeight = PANEL_PADDING * 2 + LINE_HEIGHT; // Title line
        if (action != null && !action.isEmpty()) {
            panelHeight += LINE_HEIGHT * 1.5f;
        }
        if (reason != null && !reason.isEmpty()) {
            // Estimate wrapped text height
            int estimatedLines = (int) Math.ceil(reason.length() / 40.0) + 1;
            panelHeight += LINE_HEIGHT * estimatedLines;
        }

        float panelX = PANEL_X * Settings.scale;
        float panelY = Settings.HEIGHT - PANEL_Y_OFFSET * Settings.scale;

        // Draw panel background
        drawRoundedBox(panelX, panelY - panelHeight, PANEL_WIDTH * Settings.scale, panelHeight,
                      PANEL_BACKGROUND, PANEL_BORDER);

        // Resume sprite batch for text rendering
        sb.begin();

        float textX = panelX + PANEL_PADDING * Settings.scale;
        float textY = panelY - PANEL_PADDING * Settings.scale;

        // Draw title
        FontHelper.renderFontLeft(sb, FontHelper.tipHeaderFont, "Claude's Advice",
                                 textX, textY, HIGHLIGHT_COLOR);
        textY -= LINE_HEIGHT * 1.5f * Settings.scale;

        // Draw recommended action
        if (action != null && !action.isEmpty()) {
            FontHelper.renderFontLeft(sb, FontHelper.tipBodyFont, action,
                                     textX, textY, TEXT_COLOR);
            textY -= LINE_HEIGHT * 1.5f * Settings.scale;
        }

        // Draw reason/explanation with word wrap
        if (reason != null && !reason.isEmpty()) {
            float maxWidth = (PANEL_WIDTH - PANEL_PADDING * 2) * Settings.scale;
            FontHelper.renderSmartText(sb, FontHelper.tipBodyFont, reason,
                                      textX, textY, maxWidth, LINE_HEIGHT * Settings.scale,
                                      new Color(0.8f, 0.8f, 0.8f, 1f));
        }

        sb.end();
    }

    /**
     * Renders an action hint at the bottom of the screen.
     *
     * @param sb The SpriteBatch for rendering
     */
    private void renderActionHint(SpriteBatch sb) {
        String action = overlayManager.getRecommendedAction();
        if (action == null || action.isEmpty()) {
            return;
        }

        // Position at bottom center of screen
        float hintY = 120f * Settings.scale;
        float hintWidth = 400f * Settings.scale;
        float hintHeight = 40f * Settings.scale;
        float hintX = (Settings.WIDTH - hintWidth) / 2;

        // Draw hint background
        drawRoundedBox(hintX, hintY, hintWidth, hintHeight,
                      new Color(0.1f, 0.1f, 0.2f, 0.75f), HIGHLIGHT_COLOR);

        // Draw hint text
        sb.begin();
        FontHelper.renderFontCentered(sb, FontHelper.tipBodyFont, action,
                                     Settings.WIDTH / 2f, hintY + hintHeight / 2,
                                     HIGHLIGHT_COLOR);
        sb.end();
    }

    /**
     * Draws a rounded rectangle with fill and border.
     *
     * @param x X position
     * @param y Y position
     * @param width Width of the box
     * @param height Height of the box
     * @param fillColor Color for the fill
     * @param borderColor Color for the border
     */
    private void drawRoundedBox(float x, float y, float width, float height,
                                Color fillColor, Color borderColor) {
        // Enable blending for transparency
        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);

        shapeRenderer.begin(ShapeRenderer.ShapeType.Filled);
        shapeRenderer.setColor(fillColor);
        shapeRenderer.rect(x, y, width, height);
        shapeRenderer.end();

        // Draw border
        shapeRenderer.begin(ShapeRenderer.ShapeType.Line);
        shapeRenderer.setColor(borderColor);
        shapeRenderer.rect(x, y, width, height);
        shapeRenderer.end();

        Gdx.gl.glDisable(GL20.GL_BLEND);
    }

    /**
     * Draws a simple box without rounding (for performance).
     *
     * @param x X position
     * @param y Y position
     * @param width Width of the box
     * @param height Height of the box
     * @param color Fill color
     */
    private void drawBox(float x, float y, float width, float height, Color color) {
        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);

        shapeRenderer.begin(ShapeRenderer.ShapeType.Filled);
        shapeRenderer.setColor(color);
        shapeRenderer.rect(x, y, width, height);
        shapeRenderer.end();

        Gdx.gl.glDisable(GL20.GL_BLEND);
    }

    /**
     * Draws text with a shadow effect for better readability.
     *
     * @param sb The SpriteBatch for rendering
     * @param font The font to use
     * @param text The text to render
     * @param x X position
     * @param y Y position
     * @param color Text color
     */
    private void drawTextWithShadow(SpriteBatch sb, BitmapFont font, String text,
                                    float x, float y, Color color) {
        // Draw shadow
        FontHelper.renderFontLeft(sb, font, text, x + 2 * Settings.scale, y - 2 * Settings.scale,
                                 new Color(0, 0, 0, 0.5f));
        // Draw main text
        FontHelper.renderFontLeft(sb, font, text, x, y, color);
    }

    // OverlayListener implementation

    /**
     * Called when recommendations are updated.
     * Triggers a re-render on next frame.
     */
    @Override
    public void onRecommendationsUpdated() {
        needsRender = true;
        logger.debug("Recommendations updated, will render on next frame");
    }

    /**
     * Called when overlay is toggled on/off.
     *
     * @param enabled The new enabled state
     */
    @Override
    public void onOverlayToggled(boolean enabled) {
        needsRender = enabled;
        logger.debug("Overlay toggled: " + enabled);
    }

    /**
     * Cleans up resources when the renderer is no longer needed.
     */
    public void dispose() {
        if (shapeRenderer != null) {
            shapeRenderer.dispose();
            shapeRenderer = null;
        }
        if (cardBadgeRenderer != null) {
            cardBadgeRenderer.dispose();
        }
        overlayManager.removeListener(this);
        logger.info("OverlayRenderer disposed");
    }

    /**
     * Gets the CardBadgeRenderer used by this renderer.
     * Useful for configuration (e.g., toggling score numbers).
     *
     * @return The CardBadgeRenderer instance
     */
    public CardBadgeRenderer getCardBadgeRenderer() {
        return cardBadgeRenderer;
    }
}
