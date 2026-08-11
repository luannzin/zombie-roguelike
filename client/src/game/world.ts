/**
 * Client-side tile map. Mirror of server/app/world.py.
 *
 * `moveAxis` MUST stay numerically identical to the Python version, otherwise
 * client prediction and the server disagree near walls and the local player
 * rubber-bands.
 */

import type { MapPayload } from '../net/protocol';

export const FLOOR = 0;
export const WALL = 1;

const EPS = 1e-4;

export class TileMap {
  readonly tiles: number[][];
  readonly width: number;
  readonly height: number;
  readonly tileSize: number;
  readonly pixelWidth: number;
  readonly pixelHeight: number;

  constructor(payload: MapPayload) {
    this.tiles = payload.tiles;
    this.width = payload.width;
    this.height = payload.height;
    this.tileSize = payload.tileSize;
    this.pixelWidth = this.width * this.tileSize;
    this.pixelHeight = this.height * this.tileSize;
  }

  isSolidTile(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return true;
    return this.tiles[ty][tx] === WALL;
  }

  boxBlocked(cx: number, cy: number, r: number): boolean {
    const ts = this.tileSize;
    const x0 = Math.floor((cx - r) / ts);
    const x1 = Math.floor((cx + r) / ts);
    const y0 = Math.floor((cy - r) / ts);
    const y1 = Math.floor((cy + r) / ts);
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        if (this.isSolidTile(tx, ty)) return true;
      }
    }
    return false;
  }

  /** axis: 0 = x, 1 = y. Returns the new coordinate on that axis. */
  moveAxis(x: number, y: number, r: number, delta: number, axis: 0 | 1): number {
    const ts = this.tileSize;
    if (delta === 0) return axis === 0 ? x : y;

    if (axis === 0) {
      const nx = x + delta;
      if (!this.boxBlocked(nx, y, r)) return nx;
      if (delta > 0) {
        const col = Math.floor((nx + r) / ts);
        return col * ts - r - EPS;
      }
      const col = Math.floor((nx - r) / ts);
      return (col + 1) * ts + r + EPS;
    }

    const ny = y + delta;
    if (!this.boxBlocked(x, ny, r)) return ny;
    if (delta > 0) {
      const row = Math.floor((ny + r) / ts);
      return row * ts - r - EPS;
    }
    const row = Math.floor((ny - r) / ts);
    return (row + 1) * ts + r + EPS;
  }

  /** DDA ray march against solid tiles. Used for local shot tracers. */
  raycastTiles(ox: number, oy: number, dx: number, dy: number, maxDist: number): number {
    const ts = this.tileSize;
    let tx = Math.floor(ox / ts);
    let ty = Math.floor(oy / ts);
    if (this.isSolidTile(tx, ty)) return 0;

    const stepX = dx > 0 ? 1 : -1;
    const stepY = dy > 0 ? 1 : -1;
    const invDx = dx === 0 ? Infinity : Math.abs(1 / dx);
    const invDy = dy === 0 ? Infinity : Math.abs(1 / dy);

    let tMaxX =
      dx > 0 ? ((tx + 1) * ts - ox) * invDx : dx < 0 ? (ox - tx * ts) * invDx : Infinity;
    let tMaxY =
      dy > 0 ? ((ty + 1) * ts - oy) * invDy : dy < 0 ? (oy - ty * ts) * invDy : Infinity;

    const tDeltaX = ts * invDx;
    const tDeltaY = ts * invDy;

    let travelled = 0;
    while (travelled <= maxDist) {
      if (tMaxX < tMaxY) {
        travelled = tMaxX;
        tx += stepX;
        tMaxX += tDeltaX;
      } else {
        travelled = tMaxY;
        ty += stepY;
        tMaxY += tDeltaY;
      }
      if (travelled > maxDist) break;
      if (this.isSolidTile(tx, ty)) return travelled;
    }
    return maxDist;
  }
}
