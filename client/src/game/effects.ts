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
  /** Width multiplier. 1 is the original tracer. */
  width: number;
}

export interface Flash {
  x: number;
  y: number;
  dx: number;
  dy: number;
  age: number;
  life: number;
  size: number;
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

/** An enemy melee swing: an arc sweeping through the victim. */
export interface Slash {
  x: number;
  y: number;
  /** Swing direction, attacker -> victim. */
  dx: number;
  dy: number;
  /** True when the victim's i-frames ate it — drawn as a thin deflect. */
  blocked: boolean;
  age: number;
  life: number;
}

/**
 * A short-lived light in the world: muzzle flash, death pop, coin glint.
 *
 * These are the reason the scene feels reactive rather than lit. A gunshot in a
 * dark forest should briefly light the forest — the flash is not a sprite drawn
 * near the barrel, it is a light source that the ground around it responds to,
 * and it decays over a few frames.
 */
export interface ShotFeel {
  tracerLife?: number;
  tracerWidth?: number;
  flash?: number;
  casings?: number;
  lightRadius?: number;
  lightLife?: number;
}

export interface PointLight {
  x: number;
  y: number;
  /** World px at which the light has fallen to nothing. */
  radius: number;
  /** Peak brightness, 0..1. */
  strength: number;
  color: string;
  age: number;
  life: number;
}

/**
 * A boot print left in the ground.
 *
 * The one effect here that is not short-lived, and the exception is on
 * purpose. Prints last long enough to be NAVIGATION: on an extraction run the
 * dangerous half is the walk back with your pockets full, and the trail you
 * laid on the way out is how you find the way you came. That also closes a
 * loop with the map's own storytelling — the abandoned trails the generator
 * lays down (`server/app/scenery.py`) are drawn from the same sheet, so the
 * marks you read and the marks you make are the same kind of mark.
 *
 * `depth` is the soil talking: mud takes a print, leaf litter barely does.
 */
export interface Footprint {
  x: number;
  y: number;
  /** Compass frame in the tracks sheet — mirrors `track_frame` on the server. */
  frame: number;
  /** 0..1 how well this ground holds a print. Scales the alpha. */
  depth: number;
  /**
   * 0..1 blood on this print. Set after walking through a pool, decaying
   * each stride — a trail of red that dries out behind you.
   */
  blood: number;
  age: number;
  life: number;
}

/** Damage numbers and pickup/reward text share one rising-float list. */
export type FloatTone = 'damage' | 'reward' | 'gold';

export interface TextFloat {
  x: number;
  y: number;
  text: string;
  tone: FloatTone;
  age: number;
  life: number;
}

/**
 * Prints alive at once, across everybody.
 *
 * Generous, because the point is that a trail outlives the walk that made it.
 * At a stride of ~0.9 tiles and player speed this is a couple of minutes for
 * one player and correspondingly less for a party — which is the right way for
 * it to degrade, since a crowded map is one where you have teammates to
 * navigate by instead.
 */
const FOOTPRINT_LIMIT = 420;

/**
 * Compass frames in the tracks sheet. Mirrors `TRACK_DIRECTIONS` in
 * server/app/scenery.py and server/tools/make_scenery.py — the sheet has one
 * baked frame per direction, so this has to land on the frame that actually
 * points that way, and the server's abandoned trails and the player's own
 * prints have to agree or they will read as two different kinds of mark.
 */
const TRACK_DIRECTIONS = 8;

function trackFrame(dx: number, dy: number): number {
  const step = Math.round((Math.atan2(dx, dy) / (Math.PI * 2)) * TRACK_DIRECTIONS);
  return ((step % TRACK_DIRECTIONS) + TRACK_DIRECTIONS) % TRACK_DIRECTIONS;
}

/** Air drag rate for impact debris vs. the heavier, slower footstep dust. */
const PARTICLE_DRAG = 6;
const DUST_DRAG = 4.5;
/** Damage numbers drift upward at this many world px per second. */
const FLOAT_RISE = 18;

function pick(colors: readonly string[]): string {
  return colors[(Math.random() * colors.length) | 0];
}

/** Same ladder as `hitPower` in entity-visuals — Glock under 1, AWP at the cap. */
function shotPower(damage?: number): number {
  if (damage == null || damage <= 0) return 1;
  return Math.min(3.2, Math.max(0.5, damage / 10));
}

/** A crate playing its smash sheet. Gone from the live list; this is the juice. */
export interface CrateSmash {
  x: number;
  y: number;
  variant: number;
  flip: boolean;
  age: number;
  life: number;
  empty: boolean;
}

/** One-shot wind puff. Played when a crate held nothing. */
export interface WindPuff {
  x: number;
  y: number;
  age: number;
  life: number;
}

/** One-shot death burst. The greyscale sheet, tinted with blood at draw time. */
export interface DeathBurst {
  x: number;
  y: number;
  age: number;
  life: number;
}

export class Effects {
  tracers: Tracer[] = [];
  flashes: Flash[] = [];
  particles: Particle[] = [];
  /** Footstep / walk puffs — drawn under entities. */
  dust: Particle[] = [];
  slashes: Slash[] = [];
  textFloats: TextFloat[] = [];
  /** Transient world lights — see PointLight. */
  lights: PointLight[] = [];
  /** Boot prints. Long-lived; see Footprint. */
  footprints: Footprint[] = [];
  crateSmashes: CrateSmash[] = [];
  winds: WindPuff[] = [];
  deaths: DeathBurst[] = [];

  /**
   * Leave one print. `dx`/`dy` is the heading it was walking.
   *
   * Capped by dropping the OLDEST, not by refusing new ones: a trail that
   * stopped being extended because a budget filled up would point the player
   * back the way they came and then simply end, which is worse than a trail
   * that fades from the far end like a real one.
   */
  spawnFootprint(
    x: number,
    y: number,
    dx: number,
    dy: number,
    depth: number,
    life: number,
    blood = 0,
  ): void {
    if (depth <= 0.02) return;
    if (this.footprints.length >= FOOTPRINT_LIMIT) {
      this.footprints.splice(0, this.footprints.length - FOOTPRINT_LIMIT + 1);
    }
    this.footprints.push({
      x,
      y,
      frame: trackFrame(dx, dy),
      depth,
      blood,
      age: 0,
      life,
    });
  }

  spawnLight(
    x: number,
    y: number,
    radius: number,
    strength: number,
    color: string,
    life: number,
  ): void {
    this.lights.push({ x, y, radius, strength, color, age: 0, life });
  }

  spawnShot(
    x: number,
    y: number,
    dx: number,
    dy: number,
    dist: number,
    color: string,
    hit: boolean,
    damage?: number,
    /** The thing hit was a BODY. Wood and stone throw debris but do not bleed. */
    flesh = false,
    feel?: ShotFeel,
  ): void {
    const fx = palette().effects;
    const tracerLife = feel?.tracerLife ?? 0.09;
    const tracerWidth = feel?.tracerWidth ?? 1;
    const flashScale = feel?.flash ?? 1;
    const lightRadius = feel?.lightRadius ?? 74;
    const lightLife = feel?.lightLife ?? 0.09;
    this.tracers.push({
      x,
      y,
      dx,
      dy,
      dist,
      color,
      age: 0,
      life: tracerLife,
      width: tracerWidth,
    });
    this.flashes.push({
      x,
      y,
      dx,
      dy,
      age: 0,
      life: 0.06 * (0.7 + 0.3 * flashScale),
      size: flashScale,
    });
    // The muzzle throws light, not just a sprite: brief, warm, and wide enough
    // that a shot in the dark shows you the ground you are standing on.
    this.spawnLight(x, y, lightRadius, 0.85 * Math.min(1.3, flashScale), fx.muzzleFlash, lightLife);

    const ix = x + dx * dist;
    const iy = y + dy * dist;
    const power = shotPower(damage);
    this.spawnImpact(ix, iy, dx, dy, hit, power);
    if (hit) this.spawnLight(ix, iy, 26 + power * 10, 0.42 + power * 0.12, fx.hitCore, 0.07 + power * 0.03);
    if (flesh) this.spawnBlood(ix, iy, dx, dy, 0.5 + power * 0.95);

    if (hit && damage !== undefined && damage > 0) {
      this.spawnDamage(ix, iy, damage);
    }

    const casings = feel?.casings ?? 1;
    if (casings > 0) this.spawnCasings(x, y, dx, dy, casings);
  }

  /** Brass kicked out perpendicular to the shot, falling with weight. */
  spawnCasings(x: number, y: number, dx: number, dy: number, count: number): void {
    const fx = palette().effects;
    const side = Math.random() < 0.5 ? 1 : -1;
    const px = -dy * side;
    const py = dx * side;
    for (let i = 0; i < count; i++) {
      const spread = (Math.random() - 0.5) * 0.5;
      const cx = px + dx * spread;
      const cy = py + dy * spread;
      const speed = 28 + Math.random() * 22;
      this.particles.push({
        x,
        y,
        vx: cx * speed,
        vy: cy * speed - 18,
        size: 0.7 + Math.random() * 0.5,
        color: fx.casing[i % fx.casing.length],
        age: 0,
        life: 0.28 + Math.random() * 0.12,
        gy: 220,
      });
    }
  }

  /**
   * Blood off a body that was just hit at `(x, y)` by something travelling
   * along `(dx, dy)`. `amount` scales the volume — a Glock is ~1, a Deagle
   * more, a death more still.
   *
   * It sprays with the bullet, not back at the shooter. The debris in
   * `spawnImpact` already kicks BACK along the ray, which is what a round does
   * to the surface it strikes; blood is what comes out the far side, so the two
   * together read as a shot passing THROUGH something instead of stopping on
   * it. A narrow cone forward carries most of it, a little sprays back off the
   * entry, and all of it falls — blood has weight, and the arc down to the
   * ground is what separates it from a spark.
   */
  spawnBlood(x: number, y: number, dx: number, dy: number, amount = 1): void {
    const fx = palette().effects;
    const count = Math.round((7 + Math.random() * 4) * amount);

    for (let i = 0; i < count; i++) {
      // Mostly forward, in a tight cone; every fifth drop kicks back out of
      // the entry wound.
      const back = i % 5 === 4;
      const spread = (Math.random() - 0.5) * (back ? 2.0 : 1.1);
      const cos = Math.cos(spread);
      const sin = Math.sin(spread);
      const sign = back ? -1 : 1;
      const bx = (dx * cos - dy * sin) * sign;
      const by = (dy * cos + dx * sin) * sign;
      const speed = (back ? 34 : 70) * (0.5 + Math.random() * 0.9) * (0.88 + 0.1 * amount);
      this.particles.push({
        x,
        y,
        vx: bx * speed,
        vy: by * speed - Math.random() * 14,
        size: 1 + Math.random() * 1.8,
        color: pick(fx.blood),
        age: 0,
        life: 0.34 * (0.7 + Math.random() * 0.7),
        gy: 190,
      });
    }

    // A dark mist right at the wound, going nowhere. Without it the spray
    // starts from nothing and the hit reads as a spark rather than a wound.
    this.particles.push({
      x,
      y,
      vx: dx * 6,
      vy: dy * 6,
      size: 2.6 + Math.random() * 1.2 + amount * 0.55,
      color: fx.bloodMist,
      age: 0,
      life: 0.16 + amount * 0.04,
      gy: 40,
    });

    // Heavy rounds throw a few fat drops that hang and fall. A Glock spray
    // without these is a sting; a Deagle without them is the same sting louder.
    if (amount > 1.6) {
      const chunks = 1 + Math.round((amount - 1.6) * 1.4);
      for (let i = 0; i < chunks; i++) {
        const spread = (Math.random() - 0.5) * 0.9;
        const cos = Math.cos(spread);
        const sin = Math.sin(spread);
        const bx = dx * cos - dy * sin;
        const by = dy * cos + dx * sin;
        const speed = 38 + Math.random() * 28;
        this.particles.push({
          x,
          y,
          vx: bx * speed,
          vy: by * speed - 8,
          size: 2.4 + Math.random() * 1.8,
          color: pick(fx.blood),
          age: 0,
          life: 0.42 + Math.random() * 0.18,
          gy: 240,
        });
      }
    }
  }

  spawnImpact(x: number, y: number, dx: number, dy: number, hit: boolean, power = 1): void {
    const fx = palette().effects;
    const count = Math.round((hit ? 10 : 5) * (0.7 + 0.45 * power));
    const colors = hit ? fx.hitParticles : fx.missParticles;
    const speedBase = (hit ? 55 : 28) * (0.85 + 0.2 * power);
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
        size: (hit ? 1.2 + Math.random() * 1.6 : 0.8 + Math.random() * 1.1) * (0.85 + 0.12 * power),
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
  spawnDust(
    x: number,
    y: number,
    vx: number,
    vy: number,
    side: number,
    burden = 0,
  ): void {
    const fx = palette().effects;
    const { x: nx, y: ny } = normalize(vx, vy);
    // Perpendicular for left/right foot offset.
    const px = -ny * side;
    const py = nx * side;
    const load = Math.min(1.4, Math.max(0, burden));

    const count = 3 + ((Math.random() * 2) | 0) + Math.round(load * 3);
    for (let i = 0; i < count; i++) {
      const back = 8 + Math.random() * 14 + load * 6;
      const scatter = (Math.random() - 0.5) * (12 + load * 6);
      this.dust.push({
        x: x + px * (1.6 + Math.random() * 1.2) + nx * scatter * 0.15,
        y: y + py * (1.6 + Math.random() * 1.2) + ny * scatter * 0.15,
        vx: -nx * back + px * (4 + Math.random() * 6) + (Math.random() - 0.5) * 8,
        vy: -ny * back + py * (4 + Math.random() * 6) + (Math.random() - 0.5) * 6 - 6,
        size: (1.1 + Math.random() * 2.2) * (1 + 0.5 * load),
        color: pick(fx.dust),
        age: 0,
        life: 0.28 + Math.random() * 0.22 + load * 0.08,
        gy: 18,
      });
    }

    // Soft ground smear that blooms then fades. Heavier feet press a wider one.
    this.dust.push({
      x: x + px * 1.2,
      y: y + py * 1.2,
      vx: -nx * 4,
      vy: -ny * 4,
      size: (2.8 + Math.random() * 1.4) * (1 + 0.55 * load),
      color: fx.dustSmear,
      age: 0,
      life: 0.2 + load * 0.08,
      gy: 0,
    });
  }

  /**
   * An enemy melee hit landing on `(x, y)`, swung along `(dx, dy)`.
   *
   * A blocked swing still draws — the player must be able to tell "it hit me
   * and my i-frames ate it" from "nothing happened" — but only as a thin
   * deflect arc with no debris and no number.
   */
  spawnMelee(x: number, y: number, dx: number, dy: number, damage: number, blocked: boolean): void {
    this.slashes.push({ x, y, dx, dy, blocked, age: 0, life: blocked ? 0.14 : 0.2 });
    if (blocked) return;

    const fx = palette().effects;
    for (let i = 0; i < 8; i++) {
      // Spray forward along the swing, in a wide cone.
      const spread = (Math.random() - 0.5) * 2.4;
      const cos = Math.cos(spread);
      const sin = Math.sin(spread);
      const speed = 40 * (0.4 + Math.random());
      this.particles.push({
        x,
        y,
        vx: (dx * cos - dy * sin) * speed,
        vy: (dy * cos + dx * sin) * speed,
        size: 1 + Math.random() * 1.6,
        color: pick(fx.hitParticles),
        age: 0,
        life: 0.22 * (0.7 + Math.random() * 0.6),
      });
    }
    // A claw that got through opens something. Half a shot's worth: a swipe
    // is not a hole punched clean through the body.
    this.spawnBlood(x, y, dx, dy, 0.5);
    if (damage > 0) this.spawnDamage(x, y, damage);
  }

  /** A crate coming apart: splinters, a puff of dust, and the sheet to play. */
  spawnCrateSmash(
    x: number,
    y: number,
    variant: number,
    flip: boolean,
    empty: boolean,
    life: number,
  ): void {
    this.crateSmashes.push({ x, y, variant, flip, age: 0, life, empty });
    const fx = palette().effects;
    for (let i = 0; i < 10; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 18 + Math.random() * 36;
      this.particles.push({
        x,
        y: y - 4,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed * 0.55 - 8,
        size: 0.9 + Math.random() * 1.6,
        color: pick(fx.hitParticles),
        age: 0,
        life: 0.28 + Math.random() * 0.22,
        gy: 50,
      });
    }
    this.spawnDust(x, y, 0, 1, 1);
  }

  spawnWind(x: number, y: number, life: number): void {
    this.winds.push({ x, y, age: 0, life });
  }

  spawnDeathBurst(x: number, y: number, life: number): void {
    this.deaths.push({ x, y, age: 0, life });
  }

  /**
   * Something died here. `dx`/`dy` is the direction the last hit came from, so
   * the burst leans the way the shot was going.
   */
  spawnDeath(x: number, y: number, dx = 0, dy = 0): void {
    const fx = palette().effects;
    let nx = 0;
    let ny = 0;
    if (dx !== 0 || dy !== 0) {
      const len = Math.hypot(dx, dy) || 1;
      nx = dx / len;
      ny = dy / len;
    }
    for (let i = 0; i < 28; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 28 + Math.random() * 70;
      const along = 0.35 + Math.random() * 0.65;
      this.particles.push({
        x,
        y: y - 2,
        vx: Math.cos(angle) * speed * (1 - along * 0.35) + nx * speed * along,
        vy: Math.sin(angle) * speed * 0.65 * (1 - along * 0.35) + ny * speed * along * 0.55 - 12,
        size: 1.1 + Math.random() * 2.4,
        color: i % 3 === 0 ? pick(fx.blood) : pick(fx.hitParticles),
        age: 0,
        life: 0.38 + Math.random() * 0.42,
        gy: 55 + Math.random() * 30,
      });
    }
    // Chunks: heavier, fewer, they are the body coming apart.
    for (let i = 0; i < 6; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 18 + Math.random() * 28;
      this.particles.push({
        x,
        y: y - 3,
        vx: Math.cos(angle) * speed + nx * 22,
        vy: Math.sin(angle) * speed * 0.5 - 20,
        size: 2.2 + Math.random() * 1.8,
        color: pick(fx.blood),
        age: 0,
        life: 0.5 + Math.random() * 0.3,
        gy: 90,
      });
    }
    if (dx !== 0 || dy !== 0) {
      this.spawnBlood(x, y, dx, dy, 3.2);
    } else {
      const angle = Math.random() * Math.PI * 2;
      this.spawnBlood(x, y, Math.cos(angle), Math.sin(angle), 3.2);
    }
    this.spawnDust(x, y, 0, 1, 1, 1.2);
    this.spawnLight(x, y, 62, 0.72, fx.hitCore, 0.22);
  }

  spawnDamage(x: number, y: number, value: number): void {
    this.pushFloat(x, y, String(Math.round(value)), 'damage', 0.55);
  }

  /** Kill reward, e.g. "+12 xp". Lives longer and rises further than damage. */
  spawnReward(x: number, y: number, text: string): void {
    this.pushFloat(x, y - 6, text, 'reward', 0.9);
  }

  /** Gold pickup float + sparkle burst. */
  spawnGoldPickup(x: number, y: number, amount: number): void {
    this.pushFloat(x, y - 4, `+${amount}`, 'gold', 0.7);
    const fx = palette().effects;
    for (let i = 0; i < 8; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 25 + Math.random() * 40;
      this.particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed * 0.75,
        size: 0.9 + Math.random() * 1.4,
        color: pick(fx.goldParticles),
        age: 0,
        life: 0.22 + Math.random() * 0.2,
        gy: 30,
      });
    }
    this.particles.push({
      x,
      y,
      vx: 0,
      vy: 0,
      size: 2.2,
      color: fx.goldCore,
      age: 0,
      life: 0.08,
    });
    this.spawnLight(x, y, 34, 0.42, fx.goldCore, 0.14);
  }

  private pushFloat(x: number, y: number, text: string, tone: FloatTone, life: number): void {
    this.textFloats.push({
      x: x + (Math.random() - 0.5) * 4,
      y: y - 4,
      text,
      tone,
      age: 0,
      life,
    });
  }

  update(dt: number): void {
    this.tracers = advance(this.tracers, dt);
    this.flashes = advance(this.flashes, dt);
    this.slashes = advance(this.slashes, dt);
    this.lights = advance(this.lights, dt);
    this.footprints = advance(this.footprints, dt);
    this.crateSmashes = advance(this.crateSmashes, dt);
    this.winds = advance(this.winds, dt);
    this.deaths = advance(this.deaths, dt);
    this.particles = stepParticles(this.particles, dt, PARTICLE_DRAG);
    this.dust = stepParticles(this.dust, dt, DUST_DRAG);
    this.textFloats = advance(this.textFloats, dt, (d) => {
      d.y -= FLOAT_RISE * dt;
    });
  }

  /** Drop every live effect — used on disconnect and when switching rooms. */
  clear(): void {
    this.tracers.length = 0;
    this.flashes.length = 0;
    this.slashes.length = 0;
    this.particles.length = 0;
    this.dust.length = 0;
    this.textFloats.length = 0;
    this.lights.length = 0;
    this.footprints.length = 0;
    this.crateSmashes.length = 0;
    this.winds.length = 0;
    this.deaths.length = 0;
  }
}

/**
 * Age every item by `dt`, drop the expired ones, and run `step` on survivors.
 * One loop serves tracers, flashes, particles, dust and damage floats.
 *
 * Compacts IN PLACE and hands the same array back: a death burst is 16
 * particles and this runs on seven lists every frame, so building seven
 * replacement arrays 60 times a second is pure garbage. The write index never
 * overtakes the read index, so survivors can be shifted down as we go.
 */
function advance<T extends { age: number; life: number }>(
  items: T[],
  dt: number,
  step?: (item: T) => void,
): T[] {
  let kept = 0;
  for (const item of items) {
    item.age += dt;
    if (item.age >= item.life) continue;
    step?.(item);
    items[kept++] = item;
  }
  items.length = kept;
  return items;
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
