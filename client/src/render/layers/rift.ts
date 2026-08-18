/**
 * The extraction point: an abandoned cargo skid, four lift drones on ropes, a
 * console, and a torch that has been burning since the map was built.
 *
 * THIS FILE OWNS THE RIG'S TIMING and nothing else does. `riftPhase` turns two
 * numbers — seconds since the console was pressed, and the moment each drone
 * woke — into where every piece of this machine is on this frame, and the draw
 * functions only read it. Splitting "what is happening" from "what is drawn"
 * is what keeps the drone that is turning on screen the drone the server
 * thinks woke: both sides run the same arithmetic off the same constants in
 * `server/app/rift.py`, shipped through `config.rift`.
 *
 * THE DRONES ARE THE METER. One is turning the moment the pad is awake, and
 * each overfeed tier wakes another, so how much a party has poured into a
 * platform is legible from across the clearing without a number on screen.
 * They wake in the DIAGONAL order the server places them, so a rig running on
 * two is running on opposite corners and hangs level.
 *
 * THE ROPES ARE DRAWN, NOT BAKED. A line between a fixed eye on the skid and a
 * drone that climbs, strains and then flies off cannot be a sprite — so the
 * art ships the eye positions (`layout.eyes`) and how much line each drone was
 * rigged with (`layout.rope`), and this file draws the catenary between them.
 * Slack while a drone is parked, straight once it has taken up its station,
 * and it is the STRAIGHTENING that says the machine is about to pull.
 *
 * The passes go in four different places in the frame, because they are four
 * different kinds of thing:
 *   `drawRiftGround`  with the boot prints, under everybody — the imprint the
 *                     skid uncovers when it finally comes free
 *   `riftStanding`    merged into the entity depth sort, so a player walks
 *                     behind the platform and disappears behind it
 *   `drawRiftAir`     after that sort and before the darkness: ropes, drones
 *                     in the air, and a platform that is no longer on the
 *                     ground. Still dimmed by the night, which is what lets it
 *                     fade into the sky as it climbs
 *   `drawRiftGlow`    after the darkness pass, additive — rotor discs, nav
 *                     lights, rotor wash, the burst, the console's band
 */

import { FLOOR, VOID, type Rift, type TileMap } from '../../game/world';
import type { RiftTimingConfig } from '../../net/protocol';
import { palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import {
  platformFrame,
  platformPropFrame,
  type PlatformAtlas,
  type PlatformEffectSheet,
  type PlatformPoint,
} from '../platform';
import {
  riftFrame,
  riftImage,
  riftPropFrame,
  type RiftAtlas,
  type RiftEffectSheet,
} from '../rift';

/**
 * Tile size, for turning authored tile distances into world pixels.
 *
 * The flight is authored in TILES because every distance in this game is; the
 * positions it produces are world pixels.
 */
const TILE_PX = 16;

/** Prop states. The index is the contract with the generators. */
const COLD_FRAME = 0;
const LIVE_FRAME = 1;
/** Console only: quota paid, plunger gold, pressing now LAUNCHES the platform. */
const READY_FRAME = 2;
/** Console only: driven home, every lamp on it dead. */
const SPENT_FRAME = 3;

/**
 * How high the rig climbs before it is out of sight, in tiles.
 *
 * Far more than the screen is tall on purpose: the platform has to leave
 * through the TOP of the frame while it is still visibly accelerating, because
 * a departure that decelerates into a fade reads as the animation running out
 * rather than as something flying away.
 */
const CLIMB_TILES = 34;
/** How far it travels along its heading in the same time, in tiles. */
const DRIFT_TILES = 16;
/**
 * How much a tile of ground distance is worth vertically on screen.
 *
 * The same foreshortening every other ground quantity in this game uses: the
 * camera looks down at an angle, so a step north moves you less far up the
 * screen than a step east moves you across it.
 */
const GROUND_SQUASH = 0.6;
/** Smallest the skid gets before it is gone. Distance, not a shrink effect. */
const FLIGHT_MIN_SCALE = 0.42;
/** How far outboard of its eye a drone stations itself, as a fraction of rope. */
const STATION_SPREAD = 0.34;
/** Extra climb a straining drone steals from a rope that will not stretch. */
const STRAIN_PULL = 0.13;

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

function easeOut(t: number): number {
  return 1 - (1 - t) ** 3;
}

function easeIn(t: number): number {
  return t * t;
}

/**
 * The rig's clock, if the server did not send one.
 *
 * Mirrors `server/app/rift.py`. It exists so a client talking to an older
 * server animates a plausible machine instead of dividing by undefined — the
 * server's numbers win whenever they arrive, and they always do in practice.
 */
export const RIFT_FALLBACK: RiftTimingConfig = {
  consoleLag: 0.3,
  droneSpool: 0.85,
  droneRise: 0.85,
  drones: 4,
  openAt: 2.0,
  lightTiles: 4.0,
  liftStrain: 1.1,
  liftBreak: 0.45,
  liftClimb: 3.3,
  openTime: null,
  collapseAt: null,
  collapseTime: 4.85,
  spentAt: null,
};

/** One drone, on this frame. */
export interface DronePhase {
  /** Corner index — into `rift.drones` and the atlas's eye list. */
  index: number;
  /** Seconds since it started spooling. */
  age: number;
  /** Rotors turning. A drone the party never paid for is dead weight. */
  live: boolean;
  /** Rotor speed, 0..1. Below 1 it is still winding up. */
  spool: number;
  /** How far along its climb to station, 0..1. */
  rise: number;
  /** World position of its skids. */
  x: number;
  y: number;
  /** The eye its rope is tied to, in world pixels. */
  eyeX: number;
  eyeY: number;
  /** Off the ground: draw it in the air pass, not in the depth sort. */
  flying: boolean;
}

export interface RiftPhase {
  /** The deck's lamps and strip are lit. */
  powered: boolean;
  /** The console's own frame. */
  consoleState: number;
  /** Every drone that has woken, in corner order. */
  drones: DronePhase[];
  /** Where the platform's contact point is drawn, in world pixels. */
  deckX: number;
  deckY: number;
  /** Sprite scale and opacity, for a skid that is on its way out. */
  scale: number;
  alpha: number;
  /** A small lean into the heading. Radians. */
  tilt: number;
  /** The skid has left the ground: it draws in the air pass. */
  airborne: boolean;
  /** How high off the ground it is, in world pixels. Feeds the shadow. */
  altitude: number;
  /** 0..1 through the strain — rotors at maximum, ropes straight, stuck. */
  strain: number;
  /** Seconds since the ground let go, or -1 before it does. */
  sinceBreak: number;
  /** Opacity of the imprint. 0 while the skid is still covering it. */
  imprint: number;
  /** Overfeed tier, 0..3. */
  level: number;
  /** Quota paid and still on the ground: gold console, band turning. */
  ready: boolean;
  /** The pad is finished with. */
  spent: boolean;
  /** Finished, and it finished by FLYING. A pad the night simply killed did not. */
  launched: boolean;
}

/**
 * Nothing has happened yet — and the ropes are already tied.
 *
 * A dormant pad is not an empty pad: four dead drones are parked at the
 * corners on the lines they were rigged with, and those lines are what tell a
 * player who has never seen one what this machine is going to do. So the
 * dormant phase carries the same four drone rows the running one does, all of
 * them on the ground with the slack still in their rope.
 */
function dormantPhase(rift: Rift, eyes: readonly PlatformPoint[], rope: number): RiftPhase {
  return {
    powered: false,
    consoleState: COLD_FRAME,
    drones: rift.drones.map((parked, i) => {
      const eye = eyes[i] ?? { dx: 0, dy: -rope * 0.5 };
      return {
        index: i,
        age: 0,
        live: false,
        spool: 0,
        rise: 0,
        x: parked.x,
        y: parked.y,
        eyeX: rift.deckX + eye.dx,
        eyeY: rift.deckY + eye.dy,
        flying: false,
      };
    }),
    deckX: rift.deckX,
    deckY: rift.deckY,
    scale: 1,
    alpha: 1,
    tilt: 0,
    airborne: false,
    altitude: 0,
    strain: 0,
    sinceBreak: -1,
    imprint: 0,
    level: 0,
    ready: false,
    spent: false,
    launched: false,
  };
}

/**
 * What every piece is doing, from the clock the server and client share.
 *
 * `time` is wall time and is only used for the SHUDDER — a rig straining
 * against ground that will not let go has to be visibly vibrating, and a
 * vibration keyed off the pad's own elapsed seconds would be identical on
 * every pad in the night.
 */
export function riftPhase(
  rift: Rift,
  timing: RiftTimingConfig,
  atlas: PlatformAtlas | null,
  time: number,
): RiftPhase {
  const layout = atlas?.layout;
  const rope = layout?.ropeLength ?? 64;
  const eyes = layout?.eyes ?? [];

  if (rift.state === 'dormant') return dormantPhase(rift, eyes, rope);

  // SPENT is not a moment, it is a condition. A pad that flew before this
  // player even arrived has to look the same as one they watched leave ten
  // minutes ago: no skid, no drones, a dead console, and the hole in the
  // ground. A pad the END OF THE NIGHT killed never flew at all — its
  // platform is still sitting there, cold, and its ground is still under it.
  if (rift.state === 'spent') {
    const launched = rift.closeAt !== null || rift.elapsed > 0;
    const base = dormantPhase(rift, eyes, rope);
    return {
      ...base,
      drones: launched ? [] : base.drones,
      consoleState: SPENT_FRAME,
      imprint: launched ? 1 : 0,
      airborne: launched,
      alpha: 0,
      level: rift.level,
      spent: true,
      launched,
    };
  }

  const elapsed = rift.elapsed;

  // --- the launch ----------------------------------------------------------
  const sinceLaunch = rift.closeAt === null ? -1 : elapsed - rift.closeAt;
  const strain = sinceLaunch < 0 ? 0 : clamp01(sinceLaunch / Math.max(timing.liftStrain, 1e-6));
  const sinceBreak = sinceLaunch < 0 ? -1 : sinceLaunch - timing.liftStrain;
  const flightSpan = Math.max(timing.liftBreak + timing.liftClimb, 1e-6);
  const flight = sinceBreak <= 0 ? 0 : clamp01(sinceBreak / flightSpan);

  // Up and away, ACCELERATING. `easeIn` is the whole read: something heavy
  // that has just come unstuck starts slowly and is still speeding up when it
  // leaves the frame, and easing out instead makes it look like it is being
  // lowered on a wire.
  const travel = easeIn(flight);
  const altitude = travel * CLIMB_TILES * TILE_PX;
  const drift = travel * DRIFT_TILES * TILE_PX;
  const driftX = Math.cos(rift.heading) * drift;
  const driftY = Math.sin(rift.heading) * drift * GROUND_SQUASH;

  // The shudder. It GROWS through the strain and is gone the instant the
  // ground lets go — the release is the point, and a skid that keeps rattling
  // after it is airborne reads as a broken sprite.
  const shake = strain * (sinceBreak > 0 ? 0 : 1) * 1.7;
  const shakeX = Math.sin(time * 71) * shake;
  const shakeY = Math.sin(time * 53.3) * shake * 0.6;

  const deckX = rift.deckX + driftX + shakeX;
  const deckY = rift.deckY + driftY - altitude + shakeY;

  // --- the drones ----------------------------------------------------------
  //
  // ALL FOUR, ALWAYS — not only the ones the party paid for. A drone nobody
  // woke is still tied to the skid, so when the skid leaves it goes with it,
  // hanging off its own rope as dead weight. That detail is free and it is the
  // thing that makes the rig read as ONE machine somebody rigged rather than
  // as four independent sprites that happen to be nearby.
  const airborne = sinceBreak > 0;
  const drones: DronePhase[] = [];
  for (let i = 0; i < rift.drones.length; i++) {
    const woke = i < rift.woke.length ? rift.woke[i] : null;
    const local = woke === null ? -1 : elapsed - woke;
    const live = local >= 0;
    const eye = eyes[i] ?? { dx: 0, dy: -rope * 0.5 };
    const eyeX = deckX + eye.dx;
    const eyeY = deckY + eye.dy;
    // Station: mostly straight above its own eye and a little outboard, at
    // exactly the rope's length away — which is what makes the line come
    // STRAIGHT at the top of the climb instead of the drone stopping at an
    // arbitrary height with slack still in it.
    const spread = rope * STATION_SPREAD * (eye.dx >= 0 ? 1 : -1);
    const parked = rift.drones[i];

    if (!live) {
      if (!airborne) {
        drones.push({
          index: i, age: 0, live: false, spool: 0, rise: 0,
          x: parked.x, y: parked.y, eyeX, eyeY, flying: false,
        });
        continue;
      }
      // Dragged. It swings under its own eye on the full length of the rope,
      // on a slow beat of its own — a dead weight on a line does not hang
      // still under something that is accelerating away.
      const swing = Math.sin(time * 2.1 + i * 1.7) * 0.42 + (eye.dx >= 0 ? 0.22 : -0.22);
      drones.push({
        index: i, age: 0, live: false, spool: 0, rise: 1,
        x: eyeX + Math.sin(swing) * rope,
        y: eyeY + Math.cos(swing) * rope,
        eyeX, eyeY, flying: true,
      });
      continue;
    }

    const spool = clamp01(local / Math.max(timing.droneSpool, 1e-6));
    const rise = clamp01((local - timing.droneSpool) / Math.max(timing.droneRise, 1e-6));
    const lift = Math.sqrt(Math.max(0, rope * rope - spread * spread));
    // A straining drone steals height the rope cannot give it. The platform
    // has not moved yet, so the only place that pull can go is upward — and
    // seeing the drones climb while the skid stays put is the picture.
    const pull = 1 + strain * STRAIN_PULL * (airborne ? 0 : 1);
    const t = easeOut(rise);
    drones.push({
      index: i,
      age: local,
      live: true,
      spool,
      rise,
      x: parked.x + (eyeX + spread - parked.x) * t,
      y: parked.y + (eyeY - lift * pull - parked.y) * t,
      eyeX,
      eyeY,
      flying: rise > 0,
    });
  }

  const powered = elapsed >= timing.consoleLag;
  return {
    powered,
    consoleState: rift.ready && rift.closeAt === null
      ? READY_FRAME
      : powered ? LIVE_FRAME : COLD_FRAME,
    drones,
    deckX,
    deckY,
    // It recedes as it climbs. Scale, not a fade, is what carries DISTANCE —
    // an object that only dims looks like it is being switched off.
    scale: 1 - travel * (1 - FLIGHT_MIN_SCALE),
    alpha: 1 - clamp01((flight - 0.62) / 0.38),
    tilt: Math.cos(rift.heading) * 0.09 * travel,
    airborne,
    altitude,
    strain,
    sinceBreak,
    imprint: sinceBreak <= 0 ? 0 : clamp01(sinceBreak / 0.30),
    level: rift.level,
    // A pad already launching is not waiting on anybody, so the gold console
    // and the band both stop the instant it is sent.
    ready: rift.ready && rift.closeAt === null,
    spent: false,
    launched: rift.closeAt !== null,
  };
}

export interface RiftStanding {
  sheet: 'console' | 'torch' | 'platform' | 'drone';
  x: number;
  y: number;
  shape: number;
  state: number;
}

/**
 * The exit's torches, as standing pieces for the entity depth sort.
 *
 * They are in that sort and not baked into the terrain for the same reason a
 * bonfire is: the party walks past them, and a torch that a body could not
 * disappear behind would flatten the threshold into a backdrop. Already
 * sorted, because the server ships them rank by rank and nothing moves.
 */
export function egressTorches(
  egress: { torches: readonly { x: number; y: number }[] } | null,
): RiftStanding[] {
  if (!egress) return [];
  const pieces = egress.torches.map((torch) => ({
    sheet: 'torch' as const,
    x: torch.x,
    y: torch.y,
    shape: 0,
    state: 0,
  }));
  pieces.sort((a, b) => a.y - b.y);
  return pieces;
}

/**
 * The structure's pieces that are still standing ON something, ascending in `y`.
 *
 * Handed to the renderer to merge into the entity depth sort. THE TORCH AND
 * THE CONSOLE ARE ALWAYS HERE, in every state including spent: the console is
 * the thing a player walks up to and the torch is how they found the place,
 * and neither leaves with the platform. The skid and its parked drones drop
 * out of this list the moment they are in the air — `drawRiftAir` takes them,
 * because something twenty tiles up has no business being sorted against the
 * feet of people standing on the ground.
 */
export function riftStanding(rift: Rift, phase: RiftPhase): RiftStanding[] {
  const pieces: RiftStanding[] = [
    {
      sheet: 'console',
      x: rift.consoleX,
      y: rift.consoleY,
      shape: 0,
      state: phase.consoleState,
    },
    { sheet: 'torch', x: rift.torchX, y: rift.torchY, shape: 0, state: 0 },
  ];
  if (!phase.airborne) {
    pieces.push({
      sheet: 'platform',
      x: phase.deckX,
      y: phase.deckY,
      shape: 0,
      state: phase.powered ? LIVE_FRAME : COLD_FRAME,
    });
  }
  // Only what is still on the ground. A drone at station is `drawRiftAir`'s,
  // and a pad that has FLOWN hands back no drone rows at all — every one of
  // them went with the skid, including the ones nobody woke, because they were
  // tied to it. There is deliberately no fallback to "draw them where the map
  // parked them": that would leave four airframes sitting on the ground beside
  // the hole they are supposed to have left in.
  for (const drone of phase.drones) {
    if (drone.flying) continue;
    pieces.push({
      sheet: 'drone',
      x: drone.x,
      y: drone.y,
      shape: 0,
      state: drone.live ? LIVE_FRAME : COLD_FRAME,
    });
  }
  pieces.sort((a, b) => a.y - b.y);
  return pieces;
}

/**
 * One standing piece, bottom-anchored on its contact point.
 *
 * SCREEN SPACE, through the projection — this runs inside the entity depth
 * sort, which is a screen-space pass, and every sprite in it is placed with
 * `view.x/y` and scaled by `view.zoom`. Drawing world pixels here instead pins
 * the structure near the screen origin and it rides the camera like a HUD
 * element, which is exactly what it looks like.
 *
 * TWO ATLASES, because the pad is made of two generators' output: the console
 * and the torch are `make_rift.py`'s (the pad borrows the exit's torch on
 * purpose — one torch, one meaning: a threshold), the skid and its drones are
 * `make_platform.py`'s.
 */
export function drawRiftProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  rift: RiftAtlas | null,
  platform: PlatformAtlas | null,
  piece: RiftStanding,
  shadow: string,
): void {
  if (piece.sheet === 'platform' || piece.sheet === 'drone') {
    const sheet = piece.sheet === 'platform' ? platform?.platform : platform?.drone;
    if (!sheet) return;
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, piece.state) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      piece.x, piece.y, 1, 1, 0, shadow,
      piece.sheet === 'platform' ? 0.74 : 0.5,
    );
    return;
  }
  const sheet = piece.sheet === 'torch' ? rift?.torch : rift?.console;
  if (!sheet) return;
  drawSprite(
    ctx, view, sheet.image,
    riftPropFrame(sheet, piece.shape, piece.state) * sheet.frameWidth,
    sheet.frameWidth, sheet.frameHeight,
    piece.x, piece.y, 1, 1, 0, shadow, RIFT_SHADOW_WIDTH,
  );
}

/**
 * Everything about the rig that is OFF THE GROUND: the ropes, the drones that
 * have taken up station, and a skid that has broken free.
 *
 * Screen space, run right after the entity depth sort and BEFORE the darkness.
 * Both halves of that matter. After the sort, because nothing standing on the
 * floor can plausibly be in front of a machine hanging over it. Before the
 * darkness, because a platform is a lit object and not a light — which is also
 * what lets it dissolve into the night as it climbs out of the party's own
 * lantern reach, instead of staying crisp and bright at twenty tiles up.
 */
export function drawRiftAir(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  phase: RiftPhase,
  atlas: PlatformAtlas | null,
  shadow: string,
): void {
  // No state guard beyond the atlas. A pad that has flown hands back an empty
  // drone list and `alpha` 0, so every block below skips itself; a pad the end
  // of the night killed never flew and still has four dead drones tied to it,
  // and its slack ropes are part of that picture. Testing `spent` here would
  // take those ropes away and leave the rig looking untied.
  if (!atlas) return;

  // The shadow the rig throws on the ground it is leaving. It stays on the
  // FLOOR while the platform goes up, which is the only cue in a 2D scene that
  // separates "rising" from "sliding up the screen".
  if (phase.airborne && phase.alpha > 0.02) {
    const shrink = Math.max(0.25, 1 - (phase.altitude / (CLIMB_TILES * TILE_PX)) * 1.6);
    const ground = view.y(phase.deckY + phase.altitude);
    const width = (atlas.platform?.frameWidth ?? 80) * view.zoom * shrink * 0.86;
    ctx.save();
    ctx.globalAlpha = 0.34 * shrink * phase.alpha;
    ctx.fillStyle = shadow;
    ctx.beginPath();
    ctx.ellipse(view.x(phase.deckX), ground, width / 2, width * 0.10, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  for (const drone of phase.drones) {
    drawRope(ctx, view, drone, atlas.layout.ropeLength, phase.alpha);
  }

  if (phase.airborne && atlas.platform) {
    const sheet = atlas.platform;
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, LIVE_FRAME) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      phase.deckX, phase.deckY, phase.scale, phase.alpha, phase.tilt, null, 0,
    );
  }

  const sheet = atlas.drone;
  if (!sheet) return;
  for (const drone of phase.drones) {
    if (!drone.flying) continue;
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, drone.live ? LIVE_FRAME : COLD_FRAME) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      drone.x, drone.y, phase.airborne ? phase.scale : 1, phase.alpha, 0, null, 0,
    );
  }
}

/**
 * One rope, eye to airframe.
 *
 * A CATENARY, not a straight line, and the sag is the difference between the
 * rope length and how far apart the two ends actually are. That single number
 * does the whole job: a parked drone sits well inside its own rope and the
 * line pools between them, a drone at station has used all of it and the line
 * is dead straight, and the frames in between are the rope coming up off the
 * ground. It is also what makes the strain read — the rope has nothing left to
 * give and the drone is still pulling.
 *
 * Two passes, dark then light, so the line has a lit edge. One flat colour at
 * this width vanishes against a night forest.
 */
function drawRope(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  drone: DronePhase,
  ropeLength: number,
  alpha: number,
): void {
  if (alpha <= 0.02) return;
  const ax = view.rawX(drone.eyeX);
  const ay = view.rawY(drone.eyeY);
  const bx = view.rawX(drone.x);
  const by = view.rawY(drone.y);
  const span = Math.hypot(drone.x - drone.eyeX, drone.y - drone.eyeY);
  const slack = Math.max(0, ropeLength - span);
  const sag = Math.min(slack * 0.55, ropeLength * 0.42) * view.zoom;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.lineCap = 'round';
  for (const [width, colour] of ROPE_STROKES) {
    ctx.lineWidth = Math.max(1, width * view.zoom);
    ctx.strokeStyle = colour;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.quadraticCurveTo((ax + bx) / 2, (ay + by) / 2 + sag, bx, by);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * The rope's two strokes: the body, then a thinner catch on top of it.
 *
 * Hardcoded rather than read off the palette because rope is a MATERIAL, the
 * same way `make_platform.py`'s `ROPE` ramp is — the theme decides what light
 * looks like in this game, not what hemp is made of. These are that ramp's
 * middle and top steps.
 */
const ROPE_STROKES: readonly (readonly [number, string])[] = [
  [1.6, '#33280f'],
  [0.7, '#6b5527'],
];

/**
 * One sprite, bottom-anchored, optionally scaled, tilted and faded.
 *
 * The rotation exists for exactly one thing — a skid leaning into the heading
 * it is flying off along — and it is kept SMALL (`tilt` never leaves a tenth
 * of a radian). Rotating pixel art is lossy at any angle; at this one the
 * sprite still reads as itself and the lean is what stops the departure
 * looking like a sticker being dragged up the screen.
 */
function drawSprite(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  image: CanvasImageSource,
  sx: number,
  frameWidth: number,
  frameHeight: number,
  worldX: number,
  worldY: number,
  scale: number,
  alpha: number,
  tilt: number,
  shadow: string | null,
  shadowWidth: number,
): void {
  if (alpha <= 0.02) return;
  const width = frameWidth * view.zoom * scale;
  const height = frameHeight * view.zoom * scale;
  const px = view.x(worldX);
  const py = view.y(worldY);

  if (shadow && shadowWidth > 0) {
    // The same contact shadow every other standing prop gets. Without it the
    // skid hovers: at this camera angle the dark ellipse where it meets the
    // floor is the only thing saying it is standing ON the ground.
    ctx.globalAlpha = RIFT_SHADOW_ALPHA;
    ctx.fillStyle = shadow;
    ctx.beginPath();
    ctx.ellipse(
      px,
      py - (RIFT_SHADOW_HEIGHT * view.zoom) / 2,
      (width * shadowWidth) / 2,
      (RIFT_SHADOW_HEIGHT * view.zoom) / 2,
      0, 0, Math.PI * 2,
    );
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  if (tilt === 0 && alpha >= 0.999) {
    ctx.drawImage(
      image, sx, 0, frameWidth, frameHeight,
      Math.round(px - width / 2), Math.round(py - height),
      Math.round(width), Math.round(height),
    );
    return;
  }
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(px, py);
  if (tilt !== 0) ctx.rotate(tilt);
  ctx.drawImage(
    image, sx, 0, frameWidth, frameHeight,
    Math.round(-width / 2), Math.round(-height),
    Math.round(width), Math.round(height),
  );
  ctx.restore();
}

/** Matches the scenery layer's contact shadow, so one pad has one language. */
const RIFT_SHADOW_ALPHA = 0.32;
const RIFT_SHADOW_WIDTH = 0.62;
const RIFT_SHADOW_HEIGHT = 4;

/**
 * The hole in the ground the skid was sitting in. Flat, centred, no silhouette.
 *
 * Drawn live with the boot prints rather than baked into the ground canvas,
 * for the same reason they are: it is one sprite in one place, and it does not
 * exist until the moment a platform comes free — rebuilding the ground bake on
 * that frame would hitch the one second of the night that must not hitch.
 *
 * TWO BLENDS. The pressed soil and the dents MULTIPLY, so the terrain's own
 * grain reads through what a tonne of iron did to it; the grit and the loose
 * bolts ADD, because two bright pixels are what a lantern finds when somebody
 * walks back across this later. Drawn `source-over` the whole mark would
 * replace the soil and read as a rectangle pasted onto the forest.
 */
export function drawRiftGround(
  ctx: CanvasRenderingContext2D,
  atlas: PlatformAtlas | null,
  rift: Rift,
  phase: RiftPhase,
  camera: Camera,
): void {
  const sheet = atlas?.imprint;
  if (!sheet || phase.imprint <= 0.01) return;
  const left = Math.round(rift.x - sheet.frameWidth / 2);
  const top = Math.round(rift.y - sheet.frameHeight / 2);
  if (
    left > camera.renderX + camera.viewWidth ||
    top > camera.renderY + camera.viewHeight ||
    left + sheet.frameWidth < camera.renderX ||
    top + sheet.frameHeight < camera.renderY
  ) {
    return;
  }
  ctx.save();
  ctx.globalAlpha = phase.imprint;
  ctx.globalCompositeOperation = 'multiply';
  ctx.drawImage(sheet.image, 0, 0, sheet.frameWidth, sheet.frameHeight,
    left, top, sheet.frameWidth, sheet.frameHeight);
  if (sheet.lit) {
    ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(sheet.lit, 0, 0, sheet.frameWidth, sheet.frameHeight,
      left, top, sheet.frameWidth, sheet.frameHeight);
  }
  ctx.restore();
}

/**
 * Everything about the rig that is LIGHT. World pixels, additive, drawn after
 * the darkness pass — a rotor disc catching a torch is light, not a thing
 * being lit.
 *
 * The order inside is the order of loudness: the wash on the ground first, the
 * burst over it, then the rotors and the nav lights, then the console's band.
 */
export function drawRiftGlow(
  ctx: CanvasRenderingContext2D,
  rift: Rift,
  phase: RiftPhase,
  riftAtlas: RiftAtlas | null,
  atlas: PlatformAtlas | null,
  beacon: string,
  tileSize: number,
  time: number,
): void {
  if (!atlas || phase.spent) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';

  // THE POWERED DECK IS A LIGHT SOURCE, and this halo is what makes it read as
  // one. The scene-light list reveals the pad, but it puts no light IN THE AIR
  // around the skid — so without this the platform reads as a lit object in
  // the dark rather than as the thing lighting the clearing. A whisper, never
  // a flood: gradient, never a filled arc, so the alpha is already zero before
  // the radius ends and the glow has no boundary anywhere.
  if (phase.powered && phase.alpha > 0 && !phase.airborne) {
    const beat = 0.92 + 0.08 * Math.sin(time * 1.6);
    const radius = rift.lightTiles * tileSize * beat;
    const [r, g, b] = palette().scene.beacon;
    const glow = ctx.createRadialGradient(rift.x, rift.y, 0, rift.x, rift.y, radius);
    glow.addColorStop(0, `rgb(${r} ${g} ${b} / 0.20)`);
    glow.addColorStop(0.24, `rgb(${r} ${g} ${b} / 0.09)`);
    glow.addColorStop(0.58, `rgb(${r} ${g} ${b} / 0.03)`);
    glow.addColorStop(1, `rgb(${r} ${g} ${b} / 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(rift.x - radius, rift.y - radius, radius * 2, radius * 2);
  }

  // Rotor wash. It exists whenever a rotor is turning over ground and it goes
  // to maximum through the strain, which is what says the machine is pulling
  // rather than idling. Gone the moment the skid is off the floor: dust needs
  // something to blow off, and there is nothing left under it but the hole.
  const wash = atlas.downwash;
  if (wash && !phase.airborne) {
    const running = phase.drones.reduce((sum, d) => sum + d.spool * d.rise, 0);
    const idle = Math.min(1, running / 4) * 0.30;
    ctx.globalAlpha = Math.min(0.95, idle + phase.strain * 0.70);
    blit(ctx, wash, rift.x, rift.y, time);
    ctx.globalAlpha = 1;
  }

  // The ground letting go. One event, on the frame it happens.
  const burst = atlas.burst;
  if (burst && phase.sinceBreak >= 0 && phase.sinceBreak < burst.frames / burst.fps) {
    blit(ctx, burst, rift.x, rift.y, phase.sinceBreak);
  }

  // Rotors and nav lights, per drone, EACH ON ITS OWN CLOCK. Four machines
  // playing the same frame on the same tick are four copies of one sprite,
  // which is exactly what they are and exactly what the eye must not notice —
  // so each is phased by its own age, which the stagger in `sync_drones`
  // already made different.
  const rotor = atlas.rotor;
  const strobe = atlas.strobe;
  const rotorY = atlas.layout.rotorY;
  for (const drone of phase.drones) {
    if (!drone.live) continue;
    if (rotor) {
      // A rotor that is still spooling turns SLOWER and is fainter. Playing
      // the loop at full rate from frame one is the single tell that would
      // give away that the wind-up is a fade rather than a machine starting.
      ctx.globalAlpha = phase.alpha * (0.25 + drone.spool * 0.75);
      blit(ctx, rotor, drone.x, drone.y - rotorY, drone.age * (0.35 + drone.spool * 0.65));
    }
    if (strobe && drone.spool >= 1) {
      ctx.globalAlpha = phase.alpha;
      blit(ctx, strobe, drone.x, drone.y, drone.age);
    }
  }
  ctx.globalAlpha = 1;

  // The paid console's band. On the CONSOLE, not on the platform: it is the
  // thing that changed, and it is the thing the player has to walk back to.
  // Wall time rather than the pad's clock, so every armed console in a party's
  // night turns at the same rate instead of at its own age.
  if (phase.ready && riftAtlas?.aura) {
    riftBlit(ctx, riftAtlas.aura, rift.consoleX, rift.consoleY, time, beacon);
  }
  ctx.restore();
}

/**
 * The torch marking every pad, burning. Additive, after the darkness.
 *
 * SAME SHEET THE EXIT USES, and that is the point rather than a saving: one
 * flame in this game means "a threshold somebody dressed", and the pad is the
 * other end of the same errand the exit corridor is. It burns in every state
 * including spent — the party has to be able to find their way back to a used
 * pad in the blackout, and by then it is the only thing left standing there.
 */
export function drawRiftFire(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  rifts: readonly Rift[],
  time: number,
): void {
  const sheet = atlas?.torchfire;
  if (!sheet || rifts.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  const period = sheet.frames / Math.max(sheet.fps, 1e-6);
  rifts.forEach((rift, index) => {
    const offset = (index / Math.max(rifts.length, 1)) * period;
    riftBlit(ctx, sheet, rift.torchX, rift.torchY, time + offset, '');
  });
  ctx.restore();
}

/**
 * Every torch at the exit, burning. Additive, after the darkness, world space.
 *
 * ON ITS OWN CLOCK AND ITS OWN PHASE. Four fires playing the same frame at the
 * same instant read as four copies of one sprite — so each is offset around
 * the loop by its index. Wall time, not a corridor clock: these burn for the
 * rest of the night and there is nothing for them to be in step with.
 */
export function drawEgressFire(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  egress: { torches: readonly { x: number; y: number }[] } | null,
  time: number,
): void {
  const sheet = atlas?.torchfire;
  if (!sheet || !egress || egress.torches.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  const period = sheet.frames / Math.max(sheet.fps, 1e-6);
  egress.torches.forEach((torch, index) => {
    const offset = (index / egress.torches.length) * period;
    riftBlit(ctx, sheet, torch.x, torch.y, time + offset, '');
  });
  ctx.restore();
}

/**
 * Paving on the ground at the exit.
 *
 * SCATTERED HERE, not shipped: which tile got which flagstone is decidable
 * from `(tx, ty, seed)`, so by the rule the whole world is split on it belongs
 * to the client. The server sends where the mouth is and nothing else.
 *
 * Drawn live with the boot prints rather than baked, because the corridor does
 * not exist when the ground canvas is built — it is carved into a map the
 * client already has, and rebuilding the bake for twenty tiles would hitch the
 * one moment of the run that must not hitch.
 */
export function drawEgressGround(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  world: TileMap,
  camera: Camera,
): void {
  const sheet = atlas?.egress;
  const egress = world.egress;
  if (!sheet || !egress) return;
  const tileSize = world.tileSize;
  const seed = world.seed;
  const mouthTx = Math.floor(egress.mouthX / tileSize);
  const mouthTy = Math.floor(egress.mouthY / tileSize);
  const reach = EGRESS_PAVE_TILES;

  for (let dy = -reach; dy <= reach; dy++) {
    for (let dx = -reach; dx <= reach; dx++) {
      // Round, and thinning out toward the rim: a square of paving would read
      // as a stamped rectangle, which is the one thing a laid floor must not.
      const falloff = Math.hypot(dx, dy) / reach;
      if (falloff > 1) continue;
      const tx = mouthTx + dx;
      const ty = mouthTy + dy;
      // GROUND ONLY. A flagstone painted over a trunk is a decal floating up
      // the tree, and the treeline is right there on three sides of a mouth.
      const kind = world.tiles[ty]?.[tx];
      if (kind !== FLOOR && kind !== VOID) continue;
      const roll = tileHash(tx, ty, seed);
      if (roll > 1 - falloff * falloff) continue;

      const left = tx * tileSize;
      const top = ty * tileSize;
      if (
        left > camera.renderX + camera.viewWidth ||
        top > camera.renderY + camera.viewHeight ||
        left + tileSize < camera.renderX ||
        top + tileSize < camera.renderY
      ) {
        continue;
      }
      const cut = Math.floor(tileHash(tx, ty, seed ^ 0x5157) * sheet.frames) % sheet.frames;
      const sx = cut * sheet.frameWidth;

      // The slabs MULTIPLY and the seams ADD, the same two-pass split every
      // ground decal in this atlas uses. Drawn `source-over` the stone would
      // replace the soil instead of staining it and the threshold would read
      // as a texture pasted onto the forest.
      ctx.globalCompositeOperation = 'multiply';
      ctx.drawImage(
        sheet.image, sx, 0, sheet.frameWidth, sheet.frameHeight,
        left, top, tileSize, tileSize,
      );
      if (sheet.lit) {
        ctx.globalCompositeOperation = 'lighter';
        ctx.drawImage(
          sheet.lit, sx, 0, sheet.frameWidth, sheet.frameHeight,
          left, top, tileSize, tileSize,
        );
      }
    }
  }
  ctx.globalCompositeOperation = 'source-over';
}

/** How far the paving reaches from the mouth, in tiles. */
const EGRESS_PAVE_TILES = 5;

/** Same mixer the terrain scatter uses, so the two agree about a tile. */
function tileHash(tx: number, ty: number, seed: number): number {
  let h = (tx * 374761393 + ty * 668265263 + seed * 2246822519) >>> 0;
  h ^= h >>> 13;
  h = Math.imul(h, 1274126177) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

/** One frame of a platform effect sheet, anchored on `anchorY`, world space. */
function blit(
  ctx: CanvasRenderingContext2D,
  sheet: PlatformEffectSheet,
  x: number,
  y: number,
  elapsed: number,
): void {
  const frame = platformFrame(sheet, elapsed);
  ctx.drawImage(
    sheet.image,
    frame * sheet.frameWidth,
    0,
    sheet.frameWidth,
    sheet.frameHeight,
    Math.round(x - sheet.frameWidth / 2),
    Math.round(y - sheet.anchorY),
    sheet.frameWidth,
    sheet.frameHeight,
  );
}

/** The same, for a sheet out of the rift atlas — the torch fire and the band. */
function riftBlit(
  ctx: CanvasRenderingContext2D,
  sheet: RiftEffectSheet | null,
  x: number,
  y: number,
  elapsed: number,
  beacon: string,
): void {
  if (!sheet) return;
  const frame = riftFrame(sheet, elapsed);
  ctx.drawImage(
    riftImage(sheet, beacon),
    frame * sheet.frameWidth,
    0,
    sheet.frameWidth,
    sheet.frameHeight,
    Math.round(x - sheet.frameWidth / 2),
    Math.round(y - sheet.anchorY),
    sheet.frameWidth,
    sheet.frameHeight,
  );
}
