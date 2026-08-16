/**
 * Extraction exit arrow. A small chevron over the local player, pointing
 * at the mouth the party has to reach.
 *
 * Drawn AFTER the darkness pass on purpose: the lamps are dead and this is
 * how you still know where to run. Pixel rectangles, same language as the
 * hunt diamond — it lives in the forest, not on the HUD.
 */

import { palette } from '../../theme/palette';
import type { EntityContext } from './entities';

const SCALE = 0.5;
/** Half-widths per row from the tip: a 5-wide, 5-tall chevron at scale 1. */
const ROWS = [0, 1, 2, 1, 0] as const;
const LIFT = 14;

/**
 * World-space chevron above `(fromX, fromY)`, rotated toward `(toX, toY)`.
 */
export function drawGuide(
  entity: EntityContext,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
): void {
  const dx = toX - fromX;
  const dy = toY - fromY;
  const length = Math.hypot(dx, dy);
  if (length < 1) return;

  const { ctx, config } = entity;
  const unit = (config.tileSize / 16) * SCALE;
  const angle = Math.atan2(dy, dx);
  const cx = Math.round(fromX);
  const cy = Math.round(fromY - LIFT * unit);
  const [r, g, b] = palette().scene.beacon;
  const fill = `rgb(${r} ${g} ${b})`;
  const shadow = palette().entity.labelShadow;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  const mid = (ROWS.length - 1) / 2;
  for (let row = 0; row < ROWS.length; row++) {
    const half = ROWS[row];
    const y = Math.round((row - mid) * unit);
    for (let col = -half; col <= half; col++) {
      const x = Math.round(col * unit);
      ctx.fillStyle = shadow;
      ctx.fillRect(x + 1, y + 1, Math.max(1, Math.round(unit)), Math.max(1, Math.round(unit)));
      ctx.fillStyle = fill;
      ctx.fillRect(x, y, Math.max(1, Math.round(unit)), Math.max(1, Math.round(unit)));
    }
  }
  ctx.restore();
}
