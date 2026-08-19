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

/**
 * The fire at the barrel: one per TRIGGER PULL, never one per pellet.
 *
 * Drawn from `weapon-vfx`'s oriented sheets — a bloom with petals, a lance
 * down the shot and a collar of smoke — with the canvas primitive it
 * replaced kept as the fallback for a client whose atlas failed to load.
 * `kind` picks which sheet: a shotgun throws a CONE, everything else a
 * muzzle flash, and that difference is most of what makes the two weapons
 * feel like different objects rather than one object with a different
 * number on it.
 *
 * `size` is the weapon's own `flash`, which scales the art about the barrel
 * so a P90 and an AWP draw the same fire at the sizes their rounds deserve.
 */
export type FlashKind = 'muzzle' | 'blast';

export interface Flash {
  x: number;
  y: number;
  dx: number;
  dy: number;
  age: number;
  /**
   * EVICTION ONLY. The art owns how long it is visible — the effects layer
   * stops drawing once `age` passes the sheet's own duration, and the frames
   * fade themselves out, so nothing here has to keep a second copy of a
   * timing that lives in the generator. This just has to outlast the longest
   * sheet, or a blast would be swept out of the list mid-cone.
   */
  life: number;
  kind: FlashKind;
  size: number;
}

/**
 * A round arriving: a shrinking star at the point of contact.
 *
 * Separate from the debris `spawnImpact` throws, and deliberately: the
 * particles carry the DIRECTION (they kick back along the ray) and this
 * carries the ENERGY. Together they read as something being struck; either
 * one alone reads as a puff of dust.
 */
export interface ImpactBurst {
  x: number;
  y: number;
  age: number;
  /** Eviction only, same contract as `Flash.life`. */
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
 * A PLAYER's blade going through the air: a white path swept out of the
 * body, not an arc parked on a victim.
 *
 * This is the opposite object to `Slash` and the difference is the whole
 * reason there are two. A claw arc is drawn ON the thing it hit, because
 * what the player has to read is "that one got me". A knife swing is drawn
 * FROM THE HAND THAT THREW IT, whether or not it landed, because what the
 * player has to read is where their own reach just went — and the answer
 * has to arrive on the frame they clicked rather than a round trip later.
 *
 * The path is not a static arc either: it is drawn as the leading edge of
 * the blade at `age`, with a tail behind it, so the mark travels across the
 * swing the way the blade did. `sweep` says which way around, which is what
 * makes the two slashes read as an X instead of as the same swing twice.
 */
export interface Swing {
  x: number;
  y: number;
  /** Aim the arc is centred on. */
  dx: number;
  dy: number;
  /** World px from the body centre to the outer edge of the path. */
  reach: number;
  /** Full width of the arc, in radians. */
  arc: number;
  /** +1 / -1 — the direction the edge travels through the arc. */
  sweep: number;
  /** `cut` is the finisher: thicker, brighter, and it throws a second edge. */
  cut: boolean;
  /** True when the swing opened something. A whiff draws thinner. */
  landed: boolean;
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
  /**
   * More than one ray came out of this pull — the shotgun. Switches the
   * muzzle art to the CONE sheet and tells `spawnShot` that the rays it is
   * being handed are pellets of one shell rather than separate shots.
   */
  pellets?: number;
}

/**
 * One ray of a trigger pull: where it went and how far it got.
 *
 * A pistol hands `spawnShot` one of these and a shell hands it six. Sharing
 * the shape is what keeps the two weapons one code path — the only thing
 * that actually differs between a Glock shot and an XM1014 shell is how many
 * rows are in this array and which sheet burns at the barrel.
 */
export interface ShotRay {
  dx: number;
  dy: number;
  dist: number;
  /** True when it stopped on something rather than running out of range. */
  hit: boolean;
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

/**
 * Damage numbers and pickup/reward text share one rising-float list.
 *
 * There is no `gold` tone, and that is not an omission: group gold is never
 * picked up off the ground, so nothing in the world ever floats a number in it.
 * `darkGold` is the purple coin, the only currency with a sprite.
 */
export type FloatTone = 'damage' | 'reward' | 'darkGold';

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

/**
 * An object playing its one-shot. Gone from the live list; this is the juice.
 *
 * `sheet` is carried rather than looked up because by the time this plays the
 * object is no longer in `world.crates` — there is nothing left to ask what
 * kind it was.
 */
export interface CrateSmash {
  sheet: string;
  x: number;
  y: number;
  variant: number;
  flip: boolean;
  age: number;
  life: number;
  empty: boolean;
  /** `open` holds its last frame; `break` ends near-empty and can just stop. */
  verb: 'break' | 'open';
}

/**
 * An item leaping out of something that was just opened.
 *
 * The ONE piece of juice in this file that exists purely so a reward lands as
 * an event. A drop that simply appeared on the floor under the lid is
 * information; a drop that pops up, hangs for a beat and falls is a moment,
 * and the beat at the top is where the player reads the rarity colour before
 * they have walked a step. It is drawn by `layers/loot.ts` from the same atlas
 * frame the ground drop uses, so nothing about it can disagree with the thing
 * it becomes.
 */
export interface LootPop {
  x: number;
  y: number;
  /** Catalog key, for the atlas frame and the rarity tint. */
  key: string;
  age: number;
  life: number;
  /** Peak height of the arc, in world px. */
  rise: number;
  /** Sideways drift over the whole arc, in world px. */
  drift: number;
  /** Radians per second. A rare thing turning over reads as worth looking at. */
  spin: number;
}

/** One-shot wind puff. Played when a crate held nothing. */
export interface WindPuff {
  x: number;
  y: number;
  age: number;
  life: number;
}

/** One-shot death puff. Greyscale sheet, same family as the empty-crate gust. */
export interface DeathBurst {
  x: number;
  y: number;
  age: number;
  life: number;
}

/**
 * How long a muzzle flash and an impact stay in their lists.
 *
 * Not how long they are VISIBLE — see `Flash.life`. Both are set above the
 * longest sheet either one can draw so the art always gets to finish, and
 * the cost of being generous is a handful of objects living an extra tenth
 * of a second in an array that is walked once a frame.
 */
const FLASH_HOLD = 0.34;
const BURST_HOLD = 0.22;

export class Effects {
  tracers: Tracer[] = [];
  flashes: Flash[] = [];
  /** Sprite bursts at the point of contact. See ImpactBurst. */
  bursts: ImpactBurst[] = [];
  particles: Particle[] = [];
  /** Footstep / walk puffs — drawn under entities. */
  dust: Particle[] = [];
  slashes: Slash[] = [];
  /** Player blade paths. See Swing — a different object to `slashes`. */
  swings: Swing[] = [];
  textFloats: TextFloat[] = [];
  /** Transient world lights — see PointLight. */
  lights: PointLight[] = [];
  /** Boot prints. Long-lived; see Footprint. */
  footprints: Footprint[] = [];
  crateSmashes: CrateSmash[] = [];
  lootPops: LootPop[] = [];
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

  /**
   * One trigger pull, drawn: fire at the barrel, a ray (or six) down range,
   * and whatever each one arrived at.
   *
   * `rays` IS THE SHOTGUN. Everything that used to take a single `dx, dy,
   * dist` now takes a list, and the pistol is the case where the list has
   * one row in it. Nothing else about a shell is special-cased here — one
   * muzzle event, one bang, one set of brass, and per-ray tracers and
   * impacts — which is what stops a shotgun looking like six pistols going
   * off in a fan.
   *
   * `damage` is what the WHOLE pull put into the primary victim, so the
   * number that floats over a body is the number that body actually lost.
   * It is drawn once, at the deepest ray that connected, rather than once
   * per pellet.
   */
  spawnShot(
    x: number,
    y: number,
    dx: number,
    dy: number,
    rays: ShotRay[],
    color: string,
    damage?: number,
    /** The thing hit was a BODY. Wood and stone throw debris but do not bleed. */
    flesh = false,
    feel?: ShotFeel,
  ): void {
    if (rays.length === 0) return;
    const fx = palette().effects;
    const tracerLife = feel?.tracerLife ?? 0.09;
    const tracerWidth = feel?.tracerWidth ?? 1;
    const flashScale = feel?.flash ?? 1;
    const lightRadius = feel?.lightRadius ?? 74;
    const lightLife = feel?.lightLife ?? 0.09;
    const shell = (feel?.pellets ?? 1) > 1;
    const power = shotPower(damage);

    // A pellet's streak is thinner and shorter than a bullet's: six tracers
    // at full weight is a fan of searchlights, and what a shell should leave
    // behind is a scatter of sparks that are gone before you can count them.
    const rayWidth = shell ? tracerWidth * 0.55 : tracerWidth;
    const rayLife = shell ? tracerLife * 0.7 : tracerLife;

    for (const ray of rays) {
      this.tracers.push({
        x,
        y,
        dx: ray.dx,
        dy: ray.dy,
        dist: ray.dist,
        color,
        age: 0,
        life: rayLife,
        width: rayWidth,
      });
      const ix = x + ray.dx * ray.dist;
      const iy = y + ray.dy * ray.dist;
      // Debris per pellet, but scaled down so a cone does not throw six
      // shots' worth of gravel out of one body.
      this.spawnImpact(ix, iy, ray.dx, ray.dy, ray.hit, shell ? power * 0.4 : power);
      if (ray.hit) {
        this.bursts.push({ x: ix, y: iy, age: 0, life: BURST_HOLD, size: shell ? 0.7 : 1 });
        this.spawnLight(
          ix,
          iy,
          26 + power * 10,
          (0.42 + power * 0.12) * (shell ? 0.5 : 1),
          fx.hitCore,
          0.07 + power * 0.03,
        );
        if (flesh) this.spawnBlood(ix, iy, ray.dx, ray.dy, (0.5 + power * 0.95) / rays.length);
      }
    }

    // --- one per PULL, whatever the ray count ------------------------------
    this.flashes.push({
      x,
      y,
      dx,
      dy,
      age: 0,
      life: FLASH_HOLD,
      kind: shell ? 'blast' : 'muzzle',
      size: flashScale,
    });
    // The muzzle throws light, not just a sprite: brief, warm, and wide enough
    // that a shot in the dark shows you the ground you are standing on.
    this.spawnLight(x, y, lightRadius, 0.85 * Math.min(1.3, flashScale), fx.muzzleFlash, lightLife);

    if (damage !== undefined && damage > 0) {
      // At the deepest ray that CONNECTED, so a shell's number lands on the
      // body it came off rather than out at the mouth of the cone.
      let best = rays[0];
      for (const ray of rays) {
        if (ray.hit && (!best.hit || ray.dist > best.dist)) best = ray;
      }
      this.spawnDamage(x + best.dx * best.dist, y + best.dy * best.dist, damage);
    }

    const casings = feel?.casings ?? 1;
    if (casings > 0) this.spawnCasings(x, y, dx, dy, casings);
  }

  /** The single-ray call, for everything that is not counting pellets. */
  spawnSingleShot(
    x: number,
    y: number,
    dx: number,
    dy: number,
    dist: number,
    color: string,
    hit: boolean,
    damage?: number,
    flesh = false,
    feel?: ShotFeel,
  ): void {
    this.spawnShot(x, y, dx, dy, [{ dx, dy, dist, hit }], color, damage, flesh, feel);
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
   * more. Death does not call this: the pool and the wounds already bleed.
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

  /**
   * A knife swing thrown from `(x, y)` along `(dx, dy)`.
   *
   * Spawned whether or not it landed, and spawned by the SWINGER rather than
   * by whatever it hit: the path is a statement about reach, and a whiff has
   * to draw or the player never learns how short the weapon is.
   *
   * The finisher gets a few sparks off the leading edge; the slashes get
   * none. Two quick white strokes and then one that throws light is the
   * cheapest possible way to make three swings read as a sentence.
   */
  spawnSwing(
    x: number,
    y: number,
    dx: number,
    dy: number,
    reach: number,
    arcDegrees: number,
    sweep: number,
    cut: boolean,
    landed: boolean,
    /**
     * Seconds the path takes to play — the step's own `swingTime`.
     *
     * PASSED IN RATHER THAN PICKED HERE, because the held sprite runs on
     * exactly this clock (`EntityVisuals.startSwing`) and two hard-coded
     * durations that happened to be close is how the steel and its own slash
     * came apart in the first place. The fallback is the old pair, for a
     * server too old to send the field.
     */
    life = cut ? 0.26 : 0.18,
  ): void {
    const arc = (arcDegrees * Math.PI) / 180;
    this.swings.push({
      x,
      y,
      dx,
      dy,
      reach,
      arc,
      sweep: sweep < 0 ? -1 : 1,
      cut,
      landed,
      age: 0,
      life,
    });
    if (!cut) return;

    const fx = palette().effects;
    // Struck off the edge at the far end of the sweep, thrown along the aim.
    for (let i = 0; i < 7; i++) {
      const along = 0.45 + Math.random() * 0.55;
      const spread = (Math.random() - 0.5) * arc;
      const cos = Math.cos(spread);
      const sin = Math.sin(spread);
      const bx = dx * cos - dy * sin;
      const by = dy * cos + dx * sin;
      const speed = 30 + Math.random() * 46;
      this.particles.push({
        x: x + bx * reach * along * 0.7,
        y: y + by * reach * along * 0.7,
        vx: bx * speed,
        vy: by * speed - 10,
        size: 0.7 + Math.random() * 1.1,
        color: i % 3 === 0 ? fx.bladeCore : fx.blade,
        age: 0,
        life: 0.16 + Math.random() * 0.12,
        gy: 120,
      });
    }
  }

  /**
   * An object being used: splinters, a puff of dust, and the sheet to play.
   *
   * Both verbs come through here and the particles are deliberately the same
   * for both — dust off the ground either way. What separates a barrel from a
   * boot is the SHEET (one bursts, one hinges) and the sound, and adding a
   * second particle vocabulary on top would be saying the same thing twice.
   */
  spawnCrateSmash(
    sheet: string,
    x: number,
    y: number,
    variant: number,
    flip: boolean,
    empty: boolean,
    life: number,
    verb: 'break' | 'open' = 'break',
  ): void {
    this.crateSmashes.push({ sheet, x, y, variant, flip, age: 0, life, empty, verb });
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

  /**
   * The item jumping out of an opened container.
   *
   * Aimed slightly toward the camera (down the screen), because the whole
   * point is that it lands somewhere the player can see and walk to rather
   * than behind the thing they just opened.
   */
  spawnLootPop(x: number, y: number, key: string, life: number): void {
    this.lootPops.push({
      x,
      y,
      key,
      age: 0,
      life,
      rise: 13 + Math.random() * 5,
      drift: (Math.random() - 0.5) * 10,
      spin: (Math.random() < 0.5 ? -1 : 1) * (2.4 + Math.random() * 1.6),
    });
  }

  spawnWind(x: number, y: number, life: number): void {
    this.winds.push({ x, y, age: 0, life });
  }

  spawnDeathBurst(x: number, y: number, life: number): void {
    this.deaths.push({ x, y, age: 0, life });
  }

  /**
   * A body hitting the floor. `dx`/`dy` is the killing blow, used to throw
   * dirt along the fall. Dust and wind, not blood — the pool and the wounds
   * already say that.
   */
  spawnDeath(x: number, y: number, dx = 0, dy = 0): void {
    const fx = palette().effects;
    let nx = 0;
    let ny = 1;
    if (dx !== 0 || dy !== 0) {
      const len = Math.hypot(dx, dy) || 1;
      nx = dx / len;
      ny = dy / len;
    }
    const footY = y + 4;
    this.spawnDust(x, footY, nx, ny, 1, 1.5);
    this.spawnDust(x, footY, -ny, nx, -1, 1.1);
    this.spawnDust(x, footY, ny, -nx, 1, 1.1);
    for (let i = 0; i < 12; i++) {
      const side = i % 2 === 0 ? -1 : 1;
      const along = 0.25 + Math.random() * 0.75;
      const speed = 16 + Math.random() * 32;
      this.dust.push({
        x,
        y: footY,
        vx: (side * (1 - along) + nx * along) * speed,
        vy: ny * speed * 0.35 * along - 10 - Math.random() * 14,
        size: 1.0 + Math.random() * 2.2,
        color: pick(fx.dust),
        age: 0,
        life: 0.3 + Math.random() * 0.28,
        gy: 55 + Math.random() * 35,
      });
    }
  }

  spawnDamage(x: number, y: number, value: number): void {
    this.pushFloat(x, y, String(Math.round(value)), 'damage', 0.55);
  }

  /** Kill reward, e.g. "+12 xp". Lives longer and rises further than damage. */
  spawnReward(x: number, y: number, text: string): void {
    this.pushFloat(x, y - 6, text, 'reward', 0.9);
  }

  /**
   * Dark gold pickup: float + sparkle burst, in the coin's own purple.
   *
   * The burst is the disc's ramp rather than a generic sparkle — it is the
   * coin coming apart, so it has to be made of the coin.
   */
  spawnDarkGoldPickup(x: number, y: number, amount: number): void {
    this.pushFloat(x, y - 4, `+${amount}`, 'darkGold', 0.7);
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
        color: pick(fx.darkGoldParticles),
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
      color: fx.darkGoldCore,
      age: 0,
      life: 0.08,
    });
    this.spawnLight(x, y, 34, 0.42, fx.darkGoldCore, 0.14);
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
    this.bursts = advance(this.bursts, dt);
    this.slashes = advance(this.slashes, dt);
    this.swings = advance(this.swings, dt);
    this.lights = advance(this.lights, dt);
    this.footprints = advance(this.footprints, dt);
    this.crateSmashes = advance(this.crateSmashes, dt);
    this.lootPops = advance(this.lootPops, dt);
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
    this.bursts.length = 0;
    this.slashes.length = 0;
    this.swings.length = 0;
    this.particles.length = 0;
    this.dust.length = 0;
    this.textFloats.length = 0;
    this.lights.length = 0;
    this.footprints.length = 0;
    this.crateSmashes.length = 0;
    this.lootPops.length = 0;
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
