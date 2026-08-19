/**
 * 2D camera. Position is the top-left corner in world pixels; `zoom` is a
 * pixel-art scale factor (resting value `ARENA_ZOOM`). Game may ease it
 * toward a weapon's `scopeZoom` while an AWP is aimed; Camera does not
 * decide that.
 *
 * Trauma shake offsets rendering only — `x`/`y` stay logical so aim
 * (`screenToWorld`) never jitters with the punch.
 *
 * A CAMERA, NOT A VIEWPORT. Three things sit on top of the follow, and none of
 * them is meant to be noticed on its own:
 *
 *   BREATH    a permanent sub-pixel drift on two slow, incommensurate sines.
 *             A frame that is perfectly still between two footsteps reads as a
 *             screenshot; a frame that never quite settles reads as something
 *             holding the shot.
 *   IMPULSE   a directional kick with a spring under it. Recoil goes BACK
 *             along the shot and a hit shoves along the blow, which is
 *             information — random shake in both cases is only noise.
 *   SHAKE     trauma, but on summed sines rather than `Math.random()`. White
 *             noise at 60 Hz is television static; two detuned sines are a
 *             hand that got hit.
 *
 * Nothing here performs the arrival into a zone. That move belongs to the
 * LOBBY, which is already showing the same place when it starts (see
 * `game/lobby-scene.ts`); by the time this camera exists the push-in has
 * finished, and it opens on the frame the lobby handed it. A second cinematic
 * here would replay a shot the player has just watched.
 */

import type { TileMap } from '../game/world';
import { clamp, clamp01, expDamp } from '../lib/math';
import { ARENA_ZOOM } from './framing';

/** Higher = less camera lag behind the predicted local player. */
const FOLLOW_RATE = 24;
/** How fast trauma drains toward zero (units per second). */
const TRAUMA_DECAY = 1.75;
/** Max shake amplitude in world pixels at trauma = 1. */
const MAX_SHAKE = 3.5;
/** Shake frequencies, Hz. Deliberately not multiples of each other. */
const SHAKE_HZ_X = 27.3;
const SHAKE_HZ_Y = 19.7;
/** Breath: amplitude in world pixels, and seconds for one cycle. */
const BREATH_AMPLITUDE = 0.42;
const BREATH_PERIOD = 4.7;
/** The slower sway under the breath. */
const SWAY_AMPLITUDE = 0.55;
const SWAY_PERIOD = 11.3;
/** Impulse spring: how hard it pulls back, and how fast it stops ringing. */
const IMPULSE_STIFFNESS = 190;
const IMPULSE_DAMPING = 19;
/** Max impulse offset, world px. A kick that leaves the room is a bug. */
const MAX_IMPULSE = 5;

export class Camera {
  x = 0;
  y = 0;
  zoom = ARENA_ZOOM;
  viewWidth = 0;
  viewHeight = 0;

  /** 0..1 accumulated screen trauma. */
  trauma = 0;
  private shakeX = 0;
  private shakeY = 0;
  /** Directional kick and its velocity — a spring, not a decay. */
  private kickX = 0;
  private kickY = 0;
  private kickVx = 0;
  private kickVy = 0;
  /** Wall clock for the breath and the shake. Advanced by `follow`. */
  private clock = 0;

  resize(canvasWidth: number, canvasHeight: number): void {
    this.viewWidth = canvasWidth / this.zoom;
    this.viewHeight = canvasHeight / this.zoom;
  }

  /** Add camera punch. Amount is trauma units; values stack and clamp to 1. */
  addTrauma(amount: number): void {
    this.trauma = clamp01(this.trauma + amount);
  }

  /**
   * Kick the camera along a direction — recoil, a landed hit, a rig touching
   * down. `dx`/`dy` need not be normalised; `amount` is world pixels at the
   * top of the throw.
   *
   * Separate from trauma on purpose: trauma says how violent, an impulse says
   * which way, and the two answer different questions. A shotgun going off is
   * both — a shove back down the barrel AND a rattle.
   */
  addImpulse(dx: number, dy: number, amount: number): void {
    const length = Math.hypot(dx, dy);
    if (length <= 1e-4 || amount <= 0) return;
    this.kickVx += (dx / length) * amount * IMPULSE_STIFFNESS * 0.02;
    this.kickVy += (dy / length) * amount * IMPULSE_STIFFNESS * 0.02;
  }

  snapTo(targetX: number, targetY: number, world: TileMap): void {
    this.x = targetX - this.viewWidth / 2;
    this.y = targetY - this.viewHeight / 2;
    this.trauma = 0;
    this.shakeX = 0;
    this.shakeY = 0;
    this.kickX = 0;
    this.kickY = 0;
    this.kickVx = 0;
    this.kickVy = 0;
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

  /** World-space top-left used for drawing (shake, kick and breath included). */
  get renderX(): number {
    return this.x + this.shakeX + this.kickX + this.breathX;
  }

  get renderY(): number {
    return this.y + this.shakeY + this.kickY + this.breathY;
  }

  private get breathX(): number {
    return (
      Math.sin((this.clock / BREATH_PERIOD) * Math.PI * 2) * BREATH_AMPLITUDE +
      Math.sin((this.clock / SWAY_PERIOD) * Math.PI * 2 + 1.7) * SWAY_AMPLITUDE
    );
  }

  private get breathY(): number {
    return (
      Math.cos((this.clock / BREATH_PERIOD) * Math.PI * 2 + 0.9) * BREATH_AMPLITUDE * 0.7 +
      Math.cos((this.clock / SWAY_PERIOD) * Math.PI * 2) * SWAY_AMPLITUDE * 0.6
    );
  }

  private tickShake(dt: number): void {
    this.clock += dt;

    // The kick, as a critically-ish damped spring back to rest.
    this.kickVx += (-IMPULSE_STIFFNESS * this.kickX - IMPULSE_DAMPING * this.kickVx) * dt;
    this.kickVy += (-IMPULSE_STIFFNESS * this.kickY - IMPULSE_DAMPING * this.kickVy) * dt;
    this.kickX = clamp(this.kickX + this.kickVx * dt, -MAX_IMPULSE, MAX_IMPULSE);
    this.kickY = clamp(this.kickY + this.kickVy * dt, -MAX_IMPULSE, MAX_IMPULSE);
    if (Math.abs(this.kickX) < 0.002 && Math.abs(this.kickVx) < 0.02) {
      this.kickX = 0;
      this.kickVx = 0;
    }
    if (Math.abs(this.kickY) < 0.002 && Math.abs(this.kickVy) < 0.02) {
      this.kickY = 0;
      this.kickVy = 0;
    }

    this.trauma = Math.max(0, this.trauma - TRAUMA_DECAY * dt);
    const mag = this.trauma * this.trauma * MAX_SHAKE;
    if (mag < 0.01) {
      this.shakeX = 0;
      this.shakeY = 0;
      return;
    }
    // Two detuned sines per axis. Summed they never repeat inside a shake, so
    // the pattern is unreadable, but every sample is next to the last one —
    // which is the difference between a camera being hit and TV snow.
    const t = this.clock;
    this.shakeX =
      mag *
      (Math.sin(t * SHAKE_HZ_X) * 0.65 + Math.sin(t * SHAKE_HZ_X * 0.37 + 2.1) * 0.35);
    this.shakeY =
      mag *
      (Math.cos(t * SHAKE_HZ_Y) * 0.65 + Math.cos(t * SHAKE_HZ_Y * 0.41 + 1.3) * 0.35);
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
