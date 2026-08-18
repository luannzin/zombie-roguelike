/**
 * What comes out of the backpack, and what it becomes: cargo on the deck.
 *
 * THIS IS THE PAYOFF OF THE WHOLE NIGHT AND IT HAS TO BE VISIBLE. Loading a
 * platform used to be a number going up. What it is now is a body tipping a
 * pack over an iron floor and a pile growing on that floor, item by item, in
 * the exact order and at the exact rate the server emptied the pocket — one
 * `PourEvent` in, one thing thrown, one thing landed, forever.
 *
 * TWO LISTS AND ONE ARROW BETWEEN THEM. `tosses` is what is in the air: a
 * ballistic arc out of the bag's mouth, a spin, a short bounce on contact.
 * `piles` is what has come to rest, keyed by pad — settled, unlit, uncollectable
 * furniture that belongs to the platform from that frame on. Nothing ever
 * leaves a pile: the items are gone from the world's economy the moment they
 * left the bag, and a crate you can walk over and not pick up is the clearest
 * way to say so.
 *
 * EVERY POSITION IN A PILE IS RELATIVE TO THE DECK'S CONTACT POINT, never
 * absolute. That is what lets the load ride the skid: when four drones pick the
 * thing up, `layers/rift.ts` draws the pile through the same flight transform
 * as the platform under it and a night's work climbs out of the map still
 * sitting where it was stacked.
 *
 * THE PILE IS THE SERVER'S, not this client's. `n` on the event is the pad's
 * own running count, so two players watching one pour watch the same crate land
 * in the same square of the same deck — a local counter would drift the instant
 * one client dropped a packet.
 */

/** One item at rest on a deck. Offsets are from the deck's CONTACT point. */
export interface PadCargo {
  /** Loot atlas frame. Resolved when it was thrown; never looked up again. */
  frame: number;
  /** Across the deck, in world px from its contact. */
  dx: number;
  /** Into the deck, in world px from its contact (negative is further back). */
  dy: number;
  /** How far up the stack it came to rest, in world px. */
  z: number;
  /** Settled lean, radians. Nothing lands perfectly square. */
  rot: number;
  /** Drawn size against the 16px atlas frame. A condensed core comes in big. */
  scale: number;
}

/** One item between the bag and the deck. */
export interface PadToss {
  frame: number;
  rift: string;
  /** Where it left the bag, in world px. */
  fromX: number;
  fromY: number;
  /** Seconds since it left. */
  age: number;
  /** Peak of the throw over the straight line, in world px. */
  rise: number;
  /** Radians per second while it is turning over. */
  spin: number;
  /** Where it is going to end up — the pile entry it becomes. */
  rest: PadCargo;
  /** The deck it is falling into, so the flight can be resolved in world px. */
  deckX: number;
  deckY: number;
}

/**
 * THE DECK'S FLOOR, as fractions of the skid's own sprite.
 *
 * Mirrors `_rows` / `_half` in server/tools/make_platform.py: the floor runs
 * from `deck_far` (0.453 of the frame height, half-width 0.416 of its width) to
 * `deck_near` (0.797, half-width 0.4625), and the contact point is the bottom
 * edge. Fractions rather than pixels so a re-rendered atlas at another tile
 * size still stacks inside the box instead of on the grass beside it.
 */
const FLOOR_FAR = 0.453 - 1;
const FLOOR_NEAR = 0.797 - 1;
const HALF_FAR = 0.416;
const HALF_NEAR = 0.4625;

/** Cargo is kept off the walls and off the front lip. Fractions of the floor. */
const INSET_DEPTH = 0.14;
const INSET_ACROSS = 0.78;

/** How the floor is filled before anything is stacked on top of it. */
const COLS = 6;
const ROWS = 3;
const PER_LAYER = COLS * ROWS;
/** How much a full layer lifts the next one, in world px. */
const LAYER_LIFT = 4.5;

/**
 * The pour's beats, as the server numbers them (`server/app/entities.py`).
 *
 * The stow is not named because nothing reads it directly: the pose eases back
 * to a worn pack for every beat that is not LIFT or DUMP, which covers the walk
 * up, the stow, and a pour that was cancelled halfway through.
 */
export const POUR_WALK = 0;
export const POUR_LIFT = 1;
export const POUR_DUMP = 2;

/**
 * How long the pack takes to come off and to go back on, in seconds.
 *
 * Mirrors `POUR_LIFT` / `POUR_STOW` in server/app/rift.py — the server holds
 * the body still for exactly this long, and a pose that finished early would
 * leave a character standing to attention with a bag in mid-air.
 */
export const POUR_LIFT_TIME = 0.42;
export const POUR_STOW_TIME = 0.40;

/** Draw size of a deck item against the 16px loot frame. */
export const CARGO_SCALE = 0.62;

/** The throw. Long enough to watch, short enough that a pour still pours. */
const TOSS_TIME = 0.42;
/** The hop off the floor when it lands. The beat that makes the deck iron. */
const BOUNCE_TIME = 0.16;
const BOUNCE_RISE = 3.2;

const tosses: PadToss[] = [];
const piles = new Map<string, PadCargo[]>();

/**
 * Deterministic scatter from the pile index.
 *
 * The grid is what keeps a pile inside the box; this is what stops it reading
 * as a spreadsheet. Hashed off `n` rather than rolled, because every client in
 * the room builds the same pile out of the same indices.
 */
function jitter(n: number, salt: number): number {
  const h = Math.sin(n * 12.9898 + salt * 78.233) * 43758.5453;
  return (h - Math.floor(h)) * 2 - 1;
}

/** Where item `n` comes to rest on a deck of this sprite size. */
function restingSpot(n: number, frameW: number, frameH: number, scale: number): PadCargo {
  const layer = Math.floor(n / PER_LAYER);
  const cell = n % PER_LAYER;
  const col = cell % COLS;
  const row = Math.floor(cell / COLS);

  // Across and into the box, 0..1 over the usable floor.
  const v = INSET_DEPTH + ((row + 0.5) / ROWS) * (1 - INSET_DEPTH * 2);
  const u = ((col + 0.5) / COLS) * 2 - 1;

  const depth = (FLOOR_FAR + (FLOOR_NEAR - FLOOR_FAR) * v) * frameH;
  const half = (HALF_FAR + (HALF_NEAR - HALF_FAR) * v) * frameW * INSET_ACROSS;
  // A stacked layer is packed tighter — a pile narrows as it rises, and a
  // second row sitting exactly over the first reads as a texture, not a heap.
  const squeeze = 1 - Math.min(0.35, layer * 0.12);

  return {
    frame: 0,
    dx: u * half * squeeze + jitter(n, 1) * frameW * 0.03,
    dy: depth + jitter(n, 2) * frameH * 0.02,
    z: layer * LAYER_LIFT + Math.abs(jitter(n, 3)) * 1.2,
    rot: jitter(n, 4) * 0.5,
    scale,
  };
}

/**
 * One item out of the bag. `n` is the pad's own pile index — the server's.
 *
 * `fromX/fromY` is the bag's mouth, not the body's feet: the arc has to start
 * where the sprite of the pack is, or the items appear out of the character's
 * shins and the whole ceremony reads as a spawner.
 */
export function tipPadItem(spec: {
  rift: string;
  frame: number;
  n: number;
  scale: number;
  fromX: number;
  fromY: number;
  deckX: number;
  deckY: number;
  frameW: number;
  frameH: number;
}): void {
  const rest = restingSpot(spec.n, spec.frameW, spec.frameH, spec.scale);
  rest.frame = spec.frame;
  tosses.push({
    frame: spec.frame,
    rift: spec.rift,
    fromX: spec.fromX,
    fromY: spec.fromY,
    age: 0,
    // Tipped, not thrown: the arc clears the skid's front lip and no more.
    rise: spec.frameH * 0.22 + Math.abs(jitter(spec.n, 5)) * 5,
    spin: jitter(spec.n, 6) * 9,
    rest,
    deckX: spec.deckX,
    deckY: spec.deckY,
  });
}

/** Where a toss is on this frame, in world px, plus how it is turned. */
export interface TossPose {
  x: number;
  y: number;
  rot: number;
  frame: number;
  scale: number;
}

export function tossPose(toss: PadToss): TossPose {
  const restX = toss.deckX + toss.rest.dx;
  const restY = toss.deckY + toss.rest.dy - toss.rest.z;
  if (toss.age < TOSS_TIME) {
    const t = toss.age / TOSS_TIME;
    // Linear across, parabolic up: 4t(1-t) peaks at exactly 1 halfway, so
    // `rise` is a height in world px rather than a number tuned by eye.
    return {
      x: toss.fromX + (restX - toss.fromX) * t,
      y: toss.fromY + (restY - toss.fromY) * t - toss.rise * 4 * t * (1 - t),
      rot: toss.spin * toss.age,
      frame: toss.frame,
      scale: toss.rest.scale,
    };
  }
  // The bounce. Small, short, and the only thing on screen that says the floor
  // it just hit is made of iron.
  const u = Math.min(1, (toss.age - TOSS_TIME) / BOUNCE_TIME);
  const settled = toss.rest.rot;
  const spun = toss.spin * TOSS_TIME;
  return {
    x: restX,
    y: restY - BOUNCE_RISE * 4 * u * (1 - u),
    rot: spun + (settled - spun) * u,
    frame: toss.frame,
    scale: toss.rest.scale,
  };
}

/**
 * Advance every throw. `onLand` fires once, on the frame a thing hits the deck
 * — that is where the thud and the dust belong, not where it left the bag.
 */
export function stepPadCargo(
  dt: number,
  onLand?: (x: number, y: number) => void,
): void {
  for (let i = tosses.length - 1; i >= 0; i--) {
    const toss = tosses[i]!;
    const before = toss.age;
    toss.age += dt;
    if (before < TOSS_TIME && toss.age >= TOSS_TIME) {
      onLand?.(toss.deckX + toss.rest.dx, toss.deckY + toss.rest.dy - toss.rest.z);
    }
    if (toss.age < TOSS_TIME + BOUNCE_TIME) continue;
    tosses.splice(i, 1);
    const pile = piles.get(toss.rift);
    if (pile) pile.push(toss.rest);
    else piles.set(toss.rift, [toss.rest]);
  }
}

/** What is in the air right now. Drawn over the deck, under nothing. */
export function padTosses(): readonly PadToss[] {
  return tosses;
}

/**
 * What has come to rest on one pad, back to front.
 *
 * Insertion order IS the draw order: the grid fills the far row first and
 * climbs a layer at a time, so a pile drawn in the order it was built already
 * has the near items over the far ones and the top of the heap over its base.
 */
export function padPile(rift: string): readonly PadCargo[] {
  return piles.get(rift) ?? EMPTY;
}

const EMPTY: readonly PadCargo[] = [];

/** New map, new decks. Called on every zone swap. */
export function clearPadCargo(): void {
  tosses.length = 0;
  piles.clear();
}
