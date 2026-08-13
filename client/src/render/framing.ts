/**
 * How much of the world a shot frames.
 *
 * One number lives here — the WIDE shot of the camp — because two different
 * things have to agree on it. The lobby draws the clearing at this scale while
 * the party gathers, and the arena's arrival opens at the same scale before it
 * pushes in onto the player. If they disagreed, pressing start would cut to a
 * visibly different picture of the same place and the push-in would read as a
 * scene change rather than as a camera move.
 */

import { clamp } from '../lib/math';

/** How many tiles of forest the wide shot holds. Decides the zoom. */
export const CAMP_VIEW_TILES_W = 26;
export const CAMP_VIEW_TILES_H = 17;

/** Pixel art has no half scales; anything outside this stops being readable. */
const MIN_ZOOM = 2;
const MAX_ZOOM = 6;

/**
 * Integer zoom that fits `CAMP_VIEW_TILES` into a canvas of this size.
 *
 * Integer only: a fractional scale puts the sprite grid between screen pixels
 * and the whole scene goes soft. The arrival is allowed to pass through
 * fractional scales on its way out of this one because it is moving — see
 * `Camera.beginArrival`.
 */
export function campZoom(canvasWidth: number, canvasHeight: number, tileSize: number): number {
  return clamp(
    Math.floor(
      Math.min(
        canvasWidth / (CAMP_VIEW_TILES_W * tileSize),
        canvasHeight / (CAMP_VIEW_TILES_H * tileSize),
      ),
    ),
    MIN_ZOOM,
    MAX_ZOOM,
  );
}
