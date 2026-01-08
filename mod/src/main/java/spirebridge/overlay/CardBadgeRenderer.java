package spirebridge.overlay;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.math.Vector2;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.helpers.FontHelper;
import com.megacrit.cardcrawl.helpers.ImageMaster;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Renders colored badges on cards in hand showing Claude's recommendation scores.
 *
 * Badges are small colored circles positioned at the top-right corner of each card,
 * with colors indicating recommendation strength:
 * - Green (high scores 70-100): Play this card
 * - Yellow (medium scores 40-69): Maybe play
 * - Red (low scores 0-39): Avoid playing
 *
 * Optionally displays the score as a number (1-10 scale) on the badge.
 *
 * Implements OverlayListener to respond to recommendation updates and overlay toggles.
 */
public class CardBadgeRenderer implements OverlayListener {

    private static final Logger logger = LogManager.getLogger(CardBadgeRenderer.class.getName());

    // Badge sizing constants (scaled by Settings.scale)
    private static final float BADGE_RADIUS = 20.0f;
    private static final float BADGE_OUTLINE_WIDTH = 2.0f;

    // Badge positioning offset from card center (scaled by card.drawScale and Settings.scale)
    // Positioned at top-right corner of the card
    private static final float BADGE_OFFSET_X = 100.0f;
    private static final float BADGE_OFFSET_Y = 140.0f;

    // Color thresholds for score-based coloring (0-100 scale)
    private static final int HIGH_SCORE_THRESHOLD = 70;
    private static final int LOW_SCORE_THRESHOLD = 40;

    // Colors for badge backgrounds
    private static final Color COLOR_HIGH = new Color(0.2f, 0.8f, 0.2f, 0.9f);    // Green
    private static final Color COLOR_MEDIUM = new Color(0.9f, 0.8f, 0.1f, 0.9f);  // Yellow
    private static final Color COLOR_LOW = new Color(0.8f, 0.2f, 0.2f, 0.9f);     // Red
    private static final Color COLOR_OUTLINE = new Color(0.1f, 0.1f, 0.1f, 0.9f); // Dark outline
    private static final Color COLOR_TEXT = Color.WHITE.cpy();

    // Whether to show the numeric score on badges
    private boolean showScoreNumbers = true;

    // Reference to the overlay manager
    private final OverlayManager overlayManager;

    // Cached state for efficient rendering
    private volatile boolean needsUpdate = true;

    /**
     * Creates a new CardBadgeRenderer and registers it with the OverlayManager.
     */
    public CardBadgeRenderer() {
        this.overlayManager = OverlayManager.getInstance();
        this.overlayManager.addListener(this);
        logger.info("CardBadgeRenderer initialized");
    }

    /**
     * Renders badges on all cards in the player's hand.
     * Should be called during the game's render phase (PostRenderSubscriber).
     *
     * @param sb The SpriteBatch to use for rendering
     */
    public void renderCardBadges(SpriteBatch sb) {
        // Check if overlay is enabled
        if (!overlayManager.isEnabled()) {
            return;
        }

        // Check if we have recommendations to display
        if (!overlayManager.hasRecommendations()) {
            return;
        }

        // Check if player and hand exist
        if (AbstractDungeon.player == null || AbstractDungeon.player.hand == null) {
            return;
        }

        // Render badge for each card in hand
        for (AbstractCard card : AbstractDungeon.player.hand.group) {
            int score = overlayManager.getCardScore(card.cardID);
            if (score >= 0) {
                renderBadge(sb, card, score);
            }
        }
    }

    /**
     * Renders a single badge on a card.
     *
     * @param sb The SpriteBatch to use for rendering
     * @param card The card to render the badge on
     * @param score The score to display (0-100)
     */
    public void renderBadge(SpriteBatch sb, AbstractCard card, float score) {
        if (card == null || sb == null) {
            return;
        }

        // Get badge position
        Vector2 position = getBadgePosition(card);

        // Get color based on score
        Color badgeColor = getColorForScore(score);

        // Calculate scaled radius
        float scaledRadius = BADGE_RADIUS * Settings.scale * card.drawScale;
        float scaledOutline = BADGE_OUTLINE_WIDTH * Settings.scale;

        // Draw the badge background (filled circle)
        drawFilledCircle(sb, position.x, position.y, scaledRadius, scaledOutline, badgeColor, COLOR_OUTLINE);

        // Draw the score number if enabled
        if (showScoreNumbers) {
            // Convert 0-100 score to 1-10 display scale
            int displayScore = Math.max(1, Math.min(10, (int) Math.ceil(score / 10.0f)));
            String scoreText = String.valueOf(displayScore);

            // Render the text centered on the badge
            FontHelper.renderFontCentered(
                sb,
                FontHelper.cardEnergyFont_L,
                scoreText,
                position.x,
                position.y,
                COLOR_TEXT
            );
        }
    }

    /**
     * Calculates the badge position for a card.
     * Positions the badge at the top-right corner of the card,
     * accounting for card position, scale, and rotation.
     *
     * @param card The card to calculate position for
     * @return A Vector2 containing the badge's screen coordinates
     */
    public Vector2 getBadgePosition(AbstractCard card) {
        // Base offset (scaled)
        float offsetX = BADGE_OFFSET_X * Settings.scale * card.drawScale;
        float offsetY = BADGE_OFFSET_Y * Settings.scale * card.drawScale;

        // Apply card rotation to the offset
        float rotationRad = (float) Math.toRadians(card.angle);
        float rotatedOffsetX = offsetX * (float) Math.cos(rotationRad) - offsetY * (float) Math.sin(rotationRad);
        float rotatedOffsetY = offsetX * (float) Math.sin(rotationRad) + offsetY * (float) Math.cos(rotationRad);

        // Calculate final position
        float posX = card.current_x + rotatedOffsetX;
        float posY = card.current_y + rotatedOffsetY;

        return new Vector2(posX, posY);
    }

    /**
     * Returns the badge color based on the score.
     * Uses a gradient from red (low) through yellow (medium) to green (high).
     *
     * @param score The score (0-100)
     * @return The color to use for the badge
     */
    public Color getColorForScore(float score) {
        if (score >= HIGH_SCORE_THRESHOLD) {
            // High score: green
            return COLOR_HIGH.cpy();
        } else if (score >= LOW_SCORE_THRESHOLD) {
            // Medium score: blend between yellow and green
            float t = (score - LOW_SCORE_THRESHOLD) / (HIGH_SCORE_THRESHOLD - LOW_SCORE_THRESHOLD);
            return blendColors(COLOR_MEDIUM, COLOR_HIGH, t);
        } else {
            // Low score: blend between red and yellow
            float t = score / LOW_SCORE_THRESHOLD;
            return blendColors(COLOR_LOW, COLOR_MEDIUM, t);
        }
    }

    /**
     * Blends two colors together based on a factor.
     *
     * @param from The starting color (factor = 0)
     * @param to The ending color (factor = 1)
     * @param factor The blend factor (0-1)
     * @return The blended color
     */
    private Color blendColors(Color from, Color to, float factor) {
        factor = Math.max(0, Math.min(1, factor));
        return new Color(
            from.r + (to.r - from.r) * factor,
            from.g + (to.g - from.g) * factor,
            from.b + (to.b - from.b) * factor,
            from.a + (to.a - from.a) * factor
        );
    }

    /**
     * Draws a filled circle with an outline.
     * Uses simple geometry rendering through the SpriteBatch.
     *
     * @param sb The SpriteBatch to use
     * @param x Center X coordinate
     * @param y Center Y coordinate
     * @param radius Circle radius
     * @param outlineWidth Width of the outline
     * @param fillColor Color for the fill
     * @param outlineColor Color for the outline
     */
    private void drawFilledCircle(SpriteBatch sb, float x, float y, float radius, float outlineWidth,
                                  Color fillColor, Color outlineColor) {
        // StS doesn't have a built-in circle renderer, so we use a square approximation.
        // The visual difference is minimal at small sizes, and we can enhance with
        // circle textures later if needed.

        int segments = 16; // Reserved for future circle rendering

        // Store current batch color
        Color oldColor = sb.getColor().cpy();

        // Draw outline (larger square)
        sb.setColor(outlineColor);
        drawCircleApproximation(sb, x, y, radius + outlineWidth, segments);

        // Draw fill (smaller square on top)
        sb.setColor(fillColor);
        drawCircleApproximation(sb, x, y, radius, segments);

        // Restore batch color
        sb.setColor(oldColor);
    }

    /**
     * Draws a circle approximation using the white square texture.
     * This is a simplified rendering that creates a rounded appearance.
     *
     * @param sb The SpriteBatch
     * @param x Center X
     * @param y Center Y
     * @param radius Radius
     * @param segments Number of segments (unused in this simple implementation)
     */
    private void drawCircleApproximation(SpriteBatch sb, float x, float y, float radius, int segments) {
        // Use ImageMaster's white square for simple rendering
        // Draw as a square centered at (x, y)
        // The SpriteBatch color is already set by the caller via sb.setColor()
        // The visual difference is minimal at small sizes, and we can enhance with textures later
        float size = radius * 2;
        sb.draw(
            ImageMaster.WHITE_SQUARE_IMG,
            x - radius,
            y - radius,
            size,
            size
        );
    }

    /**
     * Sets whether to show numeric scores on badges.
     *
     * @param show true to show scores, false to hide them
     */
    public void setShowScoreNumbers(boolean show) {
        this.showScoreNumbers = show;
    }

    /**
     * Returns whether numeric scores are shown on badges.
     *
     * @return true if scores are shown, false otherwise
     */
    public boolean isShowScoreNumbers() {
        return showScoreNumbers;
    }

    /**
     * Called when recommendations are updated.
     * Marks the renderer as needing an update.
     */
    @Override
    public void onRecommendationsUpdated() {
        this.needsUpdate = true;
        logger.debug("CardBadgeRenderer: recommendations updated");
    }

    /**
     * Called when the overlay is toggled.
     *
     * @param enabled true if overlay is now enabled
     */
    @Override
    public void onOverlayToggled(boolean enabled) {
        logger.debug("CardBadgeRenderer: overlay toggled to " + enabled);
    }

    /**
     * Cleans up resources and unregisters from the overlay manager.
     * Should be called when the renderer is no longer needed.
     */
    public void dispose() {
        overlayManager.removeListener(this);
        logger.info("CardBadgeRenderer disposed");
    }
}
