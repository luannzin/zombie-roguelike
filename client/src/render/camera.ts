/**
 * 2D camera. Position is the top-left corner in world pixels; `zoom` is an
 * integer pixel-art scale factor.
 *
 * Trauma shake offsets rendering only — `x`/`y` stay logical so aim
 * (`screenToWorld`) never jitters with the punch.
 *
 * ARRIVAL is the one thing that moves the camera other than the player. When a
 * run enters a zone the camera opens on the whole place, wide, and pushes in
 * onto the character over a couple of seconds — the shot that says "here is
 * where you are, and that one is you". While it runs the zoom is FRACTIONAL,
 * which is the only time this game breaks its own integer-zoom rule: a push-in
 * that steps between whole scales judders, and a moving image hides the
 * softness that a still one would not. It lands exactly on `baseZoom`.
 */

import type { TileMap } from '../game/world';
import { clamp, clamp01, expDamp, lerp } from '../lib/math';

/** Higher = less camera lag behind the predicted local player. */
const FOLLOW_RATE = 24;
/** How fast trauma drains toward zero (units per second). */
const TRAUMA_DECAY = 1.75;
/** Max shake amplitude in world pixels at trauma = 1. */
const MAX_SHAKE = 3.5;

/**
 * Fraction of the arrival spent holding the wide shot before the push starts.
 * Without it the camera is already moving on the first frame the player sees,
 * and the establishing shot never establishes anything.
 */
const ARRIVAL_HOLD = 0.22;

interface Arrival {
  /** Where the wide shot is centred, in world pixels. */
  x: number;
  y: number;
  zoom: number;
  elapsed: number;
  duration: number;
}

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
  /** The scale the camera rests at. `zoom` only differs during an arrival. */
  private baseZoom = 3;
  private arrival: Arrival | null = null;

  /**
   * Open wide on `(x, y)` at `zoom`, then push in onto whatever `follow` is
   * tracking over `duration` seconds. Call it immediately before the first
   * frame of a zone — it takes effect on the next `follow`.
   *
   * The scale it lands on is whatever the camera was resting at when this was
   * called, so the arrival always ends at the game's normal framing without the
   * caller having to know what that is.
   */
  beginArrival(x: number, y: number, zoom: number, duration: number): void {
    this.baseZoom = this.zoom;
    this.arrival = { x, y, zoom, elapsed: 0, duration };
    this.zoom = zoom;
    this.recomputeView();
    this.x = x - this.viewWidth / 2;
    this.y = y - this.viewHeight / 2;
    this.trauma = 0;
    this.shakeX = 0;
    this.shakeY = 0;
  }

  /** True while the establishing shot is still moving. */
  get arriving(): boolean {
    return this.arrival !== null;
  }

  resize(canvasWidth: number, canvasHeight: number): void {
    this.canvasWidth = canvasWidth;
    this.canvasHeight = canvasHeight;
    this.recomputeView();
  }

  /** Canvas size in screen pixels, kept so an arrival can rescale the view. */
  private canvasWidth = 0;
  private canvasHeight = 0;

  private recomputeView(): void {
    this.viewWidth = this.canvasWidth / this.zoom;
    this.viewHeight = this.canvasHeight / this.zoom;
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
    if (this.arrival) {
      this.pushIn(targetX, targetY, world, dt);
      return;
    }
    const desiredX = targetX - this.viewWidth / 2;
    const desiredY = targetY - this.viewHeight / 2;
    const k = 1 - expDamp(FOLLOW_RATE, dt);
    this.x += (desiredX - this.x) * k;
    this.y += (desiredY - this.y) * k;
    this.clamp(world);
    this.tickShake(dt);
  }

  /**
   * One frame of the establishing shot.
   *
   * Both the framing and the scale are driven off the same eased progress
   * rather than off a spring: this is a camera move somebody wrote, not the
   * camera reacting to the player, and it has to land on the same beat every
   * time so the title card can be cut to it. Zoom is interpolated in LOG space
   * — scale is multiplicative, and a linear ramp between 6 and 3 spends most of
   * its time near the wide end and then lunges.
   */
  private pushIn(targetX: number, targetY: number, world: TileMap, dt: number): void {
    const arrival = this.arrival;
    if (!arrival) return;

    arrival.elapsed += dt;
    const raw = clamp01(arrival.elapsed / arrival.duration);
    const k = easeInOut(clamp01((raw - ARRIVAL_HOLD) / (1 - ARRIVAL_HOLD)));

    this.zoom = Math.exp(lerp(Math.log(arrival.zoom), Math.log(this.baseZoom), k));
    // Re-derive the view from the zoom we just set, or the framing lags a frame
    // behind the scale and the push visibly slides sideways.
    this.recomputeView();

    const centreX = lerp(arrival.x, targetX, k);
    const centreY = lerp(arrival.y, targetY, k);
    this.x = centreX - this.viewWidth / 2;
    this.y = centreY - this.viewHeight / 2;
    this.clamp(world);
    this.tickShake(dt);

    if (raw >= 1) {
      this.arrival = null;
      this.zoom = this.baseZoom;
      this.recomputeView();
      this.x = targetX - this.viewWidth / 2;
      this.y = targetY - this.viewHeight / 2;
      this.clamp(world);
    }
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

/** Symmetric ease. Slow out of the hold, slow into the landing. */
function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

/** Keep the view inside the map, or centre it when the map is smaller. */
function clampAxis(value: number, worldSize: number, viewSize: number): number {
  if (worldSize <= viewSize) return (worldSize - viewSize) / 2;
  return clamp(value, 0, worldSize - viewSize);
}
