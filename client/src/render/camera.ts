/**
 * 2D camera. Position is the top-left corner in world pixels; `zoom` is an
 * integer pixel-art scale factor.
 *
 * Trauma shake offsets rendering only — `x`/`y` stay logical so aim
 * (`screenToWorld`) never jitters with the punch.
 */

import type { TileMap } from '../game/world';
import { clamp, clamp01, expDamp } from '../lib/math';

/** Higher = less camera lag behind the predicted local player. */
const FOLLOW_RATE = 24;
/** How fast trauma drains toward zero (units per second). */
const TRAUMA_DECAY = 1.75;
/** Max shake amplitude in world pixels at trauma = 1. */
const MAX_SHAKE = 3.5;

export class Camera {
  x = 0;
  y = 0;
  zoom = 3;
  viewWidth = 0;
  viewHeight = 0;

  /** 0..1 accumulated screen trauma. */
  trauma = 0;
  private shakeX = 0;
  private shakeY = 0;

  resize(canvasWidth: number, canvasHeight: number): void {
    this.viewWidth = canvasWidth / this.zoom;
    this.viewHeight = canvasHeight / this.zoom;
  }

  /** Add camera punch. Amount is trauma units; values stack and clamp to 1. */
  addTrauma(amount: number): void {
    this.trauma = clamp01(this.trauma + amount);
  }

  snapTo(targetX: number, targetY: number, world: TileMap): void {
    this.x = targetX - this.viewWidth / 2;
    this.y = targetY - this.viewHeight / 2;
    this.trauma = 0;
    this.shakeX = 0;
    this.shakeY = 0;
    this.clamp(world);
  }

  follow(targetX: number, targetY: number, world: TileMap, dt: number): void {
    const desiredX = targetX - this.viewWidth / 2;
    const desiredY = targetY - this.viewHeight / 2;
    const k = 1 - expDamp(FOLLOW_RATE, dt);
    this.x += (desiredX - this.x) * k;
    this.y += (desiredY - this.y) * k;
    this.clamp(world);
    this.tickShake(dt);
  }

  /** World-space top-left used for drawing (includes shake). */
  get renderX(): number {
    return this.x + this.shakeX;
  }

  get renderY(): number {
    return this.y + this.shakeY;
  }

  private tickShake(dt: number): void {
    this.trauma = Math.max(0, this.trauma - TRAUMA_DECAY * dt);
    const mag = this.trauma * this.trauma * MAX_SHAKE;
    if (mag < 0.01) {
      this.shakeX = 0;
      this.shakeY = 0;
      return;
    }
    this.shakeX = (Math.random() * 2 - 1) * mag;
    this.shakeY = (Math.random() * 2 - 1) * mag;
  }

  private clamp(world: TileMap): void {
    this.x = clampAxis(this.x, world.pixelWidth, this.viewWidth);
    this.y = clampAxis(this.y, world.pixelHeight, this.viewHeight);
  }

  /** sx/sy are canvas-relative CSS pixels (the canvas backing store is 1:1). */
  screenToWorld(sx: number, sy: number): { x: number; y: number } {
    return {
      x: this.x + sx / this.zoom,
      y: this.y + sy / this.zoom,
    };
  }
}

/** Keep the view inside the map, or centre it when the map is smaller. */
function clampAxis(value: number, worldSize: number, viewSize: number): number {
  if (worldSize <= viewSize) return (worldSize - viewSize) / 2;
  return clamp(value, 0, worldSize - viewSize);
}
