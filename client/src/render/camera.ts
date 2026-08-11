/**
 * 2D camera. Position is the top-left corner in world pixels; `zoom` is an
 * integer pixel-art scale factor.
 */

import type { TileMap } from '../game/world';

const FOLLOW_RATE = 10;

export class Camera {
  x = 0;
  y = 0;
  zoom = 3;
  viewWidth = 0;
  viewHeight = 0;

  resize(canvasWidth: number, canvasHeight: number): void {
    this.viewWidth = canvasWidth / this.zoom;
    this.viewHeight = canvasHeight / this.zoom;
  }

  snapTo(targetX: number, targetY: number, world: TileMap): void {
    this.x = targetX - this.viewWidth / 2;
    this.y = targetY - this.viewHeight / 2;
    this.clamp(world);
  }

  follow(targetX: number, targetY: number, world: TileMap, dt: number): void {
    const desiredX = targetX - this.viewWidth / 2;
    const desiredY = targetY - this.viewHeight / 2;
    const k = 1 - Math.exp(-FOLLOW_RATE * dt);
    this.x += (desiredX - this.x) * k;
    this.y += (desiredY - this.y) * k;
    this.clamp(world);
  }

  private clamp(world: TileMap): void {
    if (world.pixelWidth <= this.viewWidth) {
      this.x = (world.pixelWidth - this.viewWidth) / 2;
    } else {
      this.x = Math.min(Math.max(this.x, 0), world.pixelWidth - this.viewWidth);
    }
    if (world.pixelHeight <= this.viewHeight) {
      this.y = (world.pixelHeight - this.viewHeight) / 2;
    } else {
      this.y = Math.min(Math.max(this.y, 0), world.pixelHeight - this.viewHeight);
    }
  }

  /** sx/sy are canvas-relative CSS pixels (the canvas backing store is 1:1). */
  screenToWorld(sx: number, sy: number): { x: number; y: number } {
    return {
      x: this.x + sx / this.zoom,
      y: this.y + sy / this.zoom,
    };
  }
}
