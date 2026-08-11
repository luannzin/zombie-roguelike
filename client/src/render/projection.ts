/**
 * World -> screen mapping for one frame.
 *
 * Entities are placed in SCREEN space with integer rounding, so motion is
 * quantized to 1 screen pixel instead of 1 world pixel (= `zoom` screen
 * pixels). That is what makes 60 fps movement look smooth at zoom 3.
 *
 * Previously this arithmetic was written out at a dozen call sites in the
 * renderer; getting one of them wrong is a subpixel shimmer that is very hard
 * to spot, so it is expressed exactly once here.
 */

import type { Camera } from './camera';

export interface Projection {
  readonly zoom: number;
  readonly offsetX: number;
  readonly offsetY: number;
  /** Rounded screen X for a world X. */
  x(worldX: number): number;
  /** Rounded screen Y for a world Y. */
  y(worldY: number): number;
  /** Unrounded screen X — for arcs and lines where rounding would wobble. */
  rawX(worldX: number): number;
  rawY(worldY: number): number;
  /** Scale a world-space length into screen pixels. */
  size(worldLength: number): number;
}

export function projectionFor(camera: Camera): Projection {
  const { zoom } = camera;
  const offsetX = Math.round(-camera.renderX * zoom);
  const offsetY = Math.round(-camera.renderY * zoom);

  return {
    zoom,
    offsetX,
    offsetY,
    x: (worldX) => Math.round(worldX * zoom + offsetX),
    y: (worldY) => Math.round(worldY * zoom + offsetY),
    rawX: (worldX) => worldX * zoom + offsetX,
    rawY: (worldY) => worldY * zoom + offsetY,
    size: (worldLength) => worldLength * zoom,
  };
}
