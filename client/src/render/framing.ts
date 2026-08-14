/**
 * How much of the world a shot frames.
 *
 * Two scales live here, and the whole lobby→run transition is the move between
 * them. The lobby holds the camp WIDE, with the fire off to one side so the
 * menu is not standing on top of it. Starting the run pushes in to `ARENA_ZOOM`
 * and centres the player. Because the lobby is the thing that performs that
 * move (see `game/lobby-scene.ts`), both ends of it have to be stated in one
 * place — the arena then simply opens on the frame the lobby handed it, and the
 * cut between two canvases is invisible.
 *
 * The title screen is the same wide shot. It and the lobby share the rest
 * anchor below, so walking into a room does not jump the fire. Two call sites
 * with two numbers is how that jump got in.
 *
 * The wide shot is therefore never allowed to be as tight as the arena: it is
 * clamped to a step below, so however big the window is there is always a push
 * to see.
 */

import { clamp } from '../lib/math';

/** The scale the game is played at. Integer — this is pixel art. */
export const ARENA_ZOOM = 4;

/** How many tiles of forest the wide shot tries to hold. Decides the zoom. */
export const CAMP_VIEW_TILES_W = 30;
export const CAMP_VIEW_TILES_H = 20;

/**
 * Where the fire sits in the wide shot, as 0..1 viewport fractions.
 *
 * Desktop: right of centre, into the space the left chrome leaves.
 * Phone: below centre, into the space a top sheet leaves.
 * The launch takes whichever of these is live back to dead centre.
 */
export const CAMP_FIRE_ANCHOR = { x: 0.63, y: 0.48 } as const;
export const CAMP_FIRE_ANCHOR_MOBILE = { x: 0.5, y: 0.66 } as const;

export function campFireAnchor(mobile: boolean): { x: number; y: number } {
  return mobile ? CAMP_FIRE_ANCHOR_MOBILE : CAMP_FIRE_ANCHOR;
}

/** Below this the party stops being readable as people. */
const MIN_ZOOM = 2;

/**
 * Integer zoom for the wide shot, in CSS pixels.
 *
 * Integer only: a fractional scale puts the sprite grid between screen pixels
 * and the whole scene goes soft. The launch is allowed to pass through
 * fractional scales on its way to `ARENA_ZOOM` because it is moving, and motion
 * hides softness that a still frame would not.
 *
 * Pass the canvas's CSS size, not its backing store — multiply the result by
 * the device pixel ratio afterwards, or a hidpi screen silently frames half as
 * much world as a normal one.
 */
export function campZoom(cssWidth: number, cssHeight: number, tileSize: number): number {
  const fit = Math.floor(
    Math.min(
      cssWidth / (CAMP_VIEW_TILES_W * tileSize),
      cssHeight / (CAMP_VIEW_TILES_H * tileSize),
    ),
  );
  // Never as tight as the game itself: the push-in is the point.
  return clamp(fit, MIN_ZOOM, ARENA_ZOOM - 1);
}
