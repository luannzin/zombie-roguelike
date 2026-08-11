/**
 * Purely visual, short-lived effects. Holds no authoritative state — safe to
 * drop or replay at will.
 */

import { expDamp, normalize } from '../lib/math';
import { palette } from '../theme/palette';

export interface Tracer {
  x: number;
  y: number;
  dx: number;
  dy: number;
  dist: number;
  color: string;
  age: number;
  life: number;
}

export interface Flash {
  x: number;
  y: number;
  dx: number;
  dy: number;
  age: number;
  life: number;
}

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  age: number;
  life: number;
  /** Optional gravity (world px/s²). Dust uses a tiny lift then fall. */
  gy?: number;
}

export interface DamageFloat {
  x: number;
  y: number;
  value: number;
  age: number;
  life: number;
}

/** Air drag rate for impact debris vs. the heavier, slower footstep dust. */
const PARTICLE_DRAG = 6;
const DUST_DRAG = 4.5;
/** Damage numbers drift upward at this many world px per second. */
const FLOAT_RISE = 18;

function pick(colors: readonly string[]): string {
  return colors[(Math.random() * colors.length) | 0];
}

export class Effects {
  tracers: Tracer[] = [];
  flashes: Flash[] = [];
  particles: Particle[] = [];
  /** Footstep / walk puffs — drawn under entities. */
  dust: Particle[] = [];
  damageFloats: DamageFloat[] = [];

  spawnShot(
    x: number,
    y: number,
    dx: number,
    dy: number,
    dist: number,
    color: string,
    hit: boolean,
    damage?: number,
  ): void {
    this.tracers.push({ x, y, dx, dy, dist, color, age: 0, life: 0.09 });
    this.flashes.push({ x, y, dx, dy, age: 0, life: 0.06 });

    const ix = x + dx * dist;
    const iy = y + dy * dist;
    this.spawnImpact(ix, iy, dx, dy, hit);

    if (hit && damage !== undefined && damage > 0) {
      this.spawnDamage(ix, iy, damage);
    }
  }

  spawnImpact(x: number, y: number, dx: number, dy: number, hit: boolean): void {
    const fx = palette().effects;
    const count = hit ? 10 : 5;
    const colors = hit ? fx.hitParticles : fx.missParticles;
    const speedBase = hit ? 55 : 28;
    const lifeBase = hit ? 0.28 : 0.18;

    for (let i = 0; i < count; i++) {
      // Spray mostly back along the incoming shot, with a cone of noise.
      const spread = (Math.random() - 0.5) * (hit ? 2.2 : 1.6);
      const cos = Math.cos(spread);
      const sin = Math.sin(spread);
      const bx = -dx * cos - dy * sin;
      const by = -dy * cos + dx * sin;
      const speed = speedBase * (0.45 + Math.random() * 0.9);
      this.particles.push({
        x,
        y,
        vx: bx * speed,
        vy: by * speed,
        size: hit ? 1.2 + Math.random() * 1.6 : 0.8 + Math.random() * 1.1,
        color: pick(colors),
        age: 0,
        life: lifeBase * (0.7 + Math.random() * 0.5),
      });
    }

    // Tiny core spark so the impact reads even if particles fan wide.
    this.particles.push({
      x,
      y,
      vx: 0,
      vy: 0,
      size: hit ? 2.4 : 1.6,
      color: hit ? fx.hitCore : fx.missCore,
      age: 0,
      life: hit ? 0.1 : 0.07,
    });
  }

  /**
   * Footfall puff at the feet. `vx/vy` = move direction; `side` = -1/1 for
   * left/right foot so puffs straddle the path.
   */
  spawnDust(x: number, y: number, vx: number, vy: number, side: number): void {
    const fx = palette().effects;
    const { x: nx, y: ny } = normalize(vx, vy);
    // Perpendicular for left/right foot offset.
    const px = -ny * side;
    const py = nx * side;

    const count = 3 + ((Math.random() * 2) | 0);
    for (let i = 0; i < count; i++) {
      const back = 8 + Math.random() * 14;
      const scatter = (Math.random() - 0.5) * 12;
      this.dust.push({
        x: x + px * (1.6 + Math.random() * 1.2) + nx * scatter * 0.15,
        y: y + py * (1.6 + Math.random() * 1.2) + ny * scatter * 0.15,
        vx: -nx * back + px * (4 + Math.random() * 6) + (Math.random() - 0.5) * 8,
        vy: -ny * back + py * (4 + Math.random() * 6) + (Math.random() - 0.5) * 6 - 6,
        size: 1.1 + Math.random() * 2.2,
        color: pick(fx.dust),
        age: 0,
        life: 0.28 + Math.random() * 0.22,
        gy: 18,
      });
    }

    // Soft ground smear that blooms then fades.
    this.dust.push({
      x: x + px * 1.2,
      y: y + py * 1.2,
      vx: -nx * 4,
      vy: -ny * 4,
      size: 2.8 + Math.random() * 1.4,
      color: fx.dustSmear,
      age: 0,
      life: 0.2,
      gy: 0,
    });
  }

  spawnDamage(x: number, y: number, value: number): void {
    this.damageFloats.push({
      x: x + (Math.random() - 0.5) * 4,
      y: y - 4,
      value: Math.round(value),
      age: 0,
      life: 0.55,
    });
  }

  update(dt: number): void {
    this.tracers = advance(this.tracers, dt);
    this.flashes = advance(this.flashes, dt);
    this.particles = stepParticles(this.particles, dt, PARTICLE_DRAG);
    this.dust = stepParticles(this.dust, dt, DUST_DRAG);
    this.damageFloats = advance(this.damageFloats, dt, (d) => {
      d.y -= FLOAT_RISE * dt;
    });
  }

  /** Drop every live effect — used on disconnect and when switching rooms. */
  clear(): void {
    this.tracers.length = 0;
    this.flashes.length = 0;
    this.particles.length = 0;
    this.dust.length = 0;
    this.damageFloats.length = 0;
  }
}

/**
 * Age every item by `dt`, drop the expired ones, and run `step` on survivors.
 * One loop serves tracers, flashes, particles, dust and damage floats.
 */
function advance<T extends { age: number; life: number }>(
  items: T[],
  dt: number,
  step?: (item: T) => void,
): T[] {
  const out: T[] = [];
  for (const item of items) {
    item.age += dt;
    if (item.age >= item.life) continue;
    step?.(item);
    out.push(item);
  }
  return out;
}

function stepParticles(items: Particle[], dt: number, dragRate: number): Particle[] {
  const drag = expDamp(dragRate, dt);
  return advance(items, dt, (p) => {
    if (p.gy) p.vy += p.gy * dt;
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    p.vx *= drag;
    p.vy *= drag;
  });
}
