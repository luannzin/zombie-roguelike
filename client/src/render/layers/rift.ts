/**
 * The extraction point: an abandoned cargo skid with four corner lamps on it, a
 * console, and a torch that has been burning since the map was built.
 *
 * THIS FILE OWNS THE PAD'S TIMING and nothing else does. `riftPhase` turns two
 * numbers — seconds since the console was pressed, and the moment somebody
 * called the pickup — into where every piece of this scene is on this frame,
 * and the draw functions only read it. Splitting "what is happening" from
 * "what is drawn" is what keeps the aircraft on screen the aircraft the server
 * believes in: both sides run the same arithmetic off the same constants in
 * `server/app/rift.py`, shipped through `config.rift`.
 *
 * THE LAMPS ARE THE STATE, AND THERE ARE ONLY TWO THINGS THEY SAY. Green: this
 * pad is found, powered and taking cargo, and nothing out there has heard
 * anything. Red: somebody has called for a pickup, the corners are sweeping a
 * siren across a black forest, and the server has put every creature on the map
 * on hunt (`Room.sirening`). Everything else on this pad is detail; those two
 * colours are the whole decision the extraction offers.
 *
 * THE DRONES ARE NOT ON THIS MAP UNTIL THEY ARE CALLED. Nothing is parked at
 * the corners — the pad is a loading dock, not a complete machine — so there is
 * no drone geometry on the wire at all. Four aircraft come in over one treeline
 * on `rift.approach`, staggered, take a corner each, lower a line, and the
 * whole thing is one `closeAt` plus the constants. Four flight plans at 6 Hz to
 * describe something fully determined would be the largest message in the game
 * for no information.
 *
 * THE ROPES ARE DRAWN, NOT BAKED, and they are what makes the tie-on read as
 * something happening rather than something switching on. The art ships where
 * each line ends (`layout.eyes`) and how much of it there is (`layout.rope`);
 * this file pays it out of the drone's winch under gravity, lets the free end
 * swing, catches it on the eye, and only then lets the slack come out of it.
 *
 * The passes go in four different places in the frame, because they are four
 * different kinds of thing:
 *   `drawRiftGround`  with the boot prints, under everybody — the imprint the
 *                     skid uncovers when it finally comes free
 *   `riftStanding`    merged into the entity depth sort, so a player walks
 *                     behind the platform and disappears behind it
 *   `drawRiftAir`     after that sort and before the darkness: the ropes, the
 *                     aircraft, and a platform that is no longer on the ground.
 *                     Still dimmed by the night, which is what lets an inbound
 *                     drone resolve out of the dark instead of appearing
 *   `drawRiftGlow`    after the darkness pass, additive — corner lamps, rotor
 *                     discs, nav lights, rotor wash, the burst, and the red
 *                     wash the siren throws over the whole clearing
 */

import { FLOOR, VOID, type Rift, type TileMap } from '../../game/world';
import {
  CARGO_SCALE,
  padPile,
  padTosses,
  tossPose,
  type PadCargo,
} from '../../game/pad-cargo';
import type { LootAtlas } from '../loot';
import type { RiftTimingConfig } from '../../net/protocol';
import { palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import { groundShadow } from '../shadows';
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

/** Platform states. The index is the contract with `make_platform.py`. */
const COLD_FRAME = 0;
/** Powered and taking cargo: green corner lamps. */
const STANDBY_FRAME = 1;
/** The pickup has been called: red corner lamps, sirens sweeping. */
const ALARM_FRAME = 2;

/** Drone cuts. Level and holding, or pitched forward and travelling. */
const HOVER_FRAME = 0;
const CRUISE_FRAME = 1;

/** Console states, out of `make_rift.py`. */
const CONSOLE_IDLE = 0;
const CONSOLE_ARMED = 1;
/** Quota settled, plunger gold: pressing now CALLS THE PICKUP. */
const CONSOLE_READY = 2;
/** Driven home, every lamp on it dead. */
const CONSOLE_SPENT = 3;

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
/**
 * How far out an inbound drone starts, in tiles.
 *
 * Comfortably past the far edge of any viewport at arena zoom, so the aircraft
 * are NOT on screen when the siren starts. The whole point of the alarm beat is
 * that the party has called for something that is not here yet, and a drone
 * already visible at the treeline gives that away before the beat can land.
 */
const INBOUND_TILES = 38;
/**
 * How far apart the four hold in formation on the way in, in tiles.
 *
 * They arrive as a GROUP and split at the last moment — four machines crossing
 * a clearing on four separate bearings is four events, and this is one.
 */
const FORMATION_TILES = 1.7;

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

function easeOut(t: number): number {
  return 1 - (1 - t) ** 3;
}

function easeIn(t: number): number {
  return t * t;
}

/** One inbound aircraft, on this frame. */
export interface DronePhase {
  /** Corner index — into the atlas's eye list. */
  index: number;
  /** Seconds since it left the treeline. Phases its own rotors. */
  age: number;
  /** World position of its hull. */
  x: number;
  y: number;
  /** Still crossing the clearing: draw the pitched cut, not the level one. */
  cruising: boolean;
  /** The eye its line ends at, in world pixels. */
  eyeX: number;
  eyeY: number;
  /**
   * How much line is out, in world pixels. 0 before the drop starts, and the
   * full rope once the end has reached the eye.
   */
  rope: number;
  /** The end of the line has reached its eye and the corner is taking load. */
  tied: boolean;
  /** Where the free end of the line is while it is still falling. */
  endX: number;
  endY: number;
}

export interface RiftPhase {
  /** The deck is powered: corner lamps lit, strip on. */
  powered: boolean;
  /** The pickup has been called: lamps red, siren sweeping, aircraft coming. */
  alarm: boolean;
  /** The platform's own frame — cold, green standby, red alarm. */
  platformState: number;
  /** The console's own frame. */
  consoleState: number;
  /** Every aircraft currently in the air. Empty except during a pickup. */
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
  /** 0..1 through the strain — rotors at maximum, lines taut, stuck. */
  strain: number;
  /** Seconds since the ground let go, or -1 before it does. */
  sinceBreak: number;
  /** Opacity of the imprint. 0 while the skid is still covering it. */
  imprint: number;
  /** The quota is settled: gold console, band turning, E calls the pickup. */
  ready: boolean;
  /** The pad is finished with. */
  spent: boolean;
  /** Finished, and it finished by FLYING. A pad the night simply killed did not. */
  launched: boolean;
}

/** Nothing has happened here yet: a cold skid, and not an aircraft in sight. */
function restingPhase(rift: Rift): RiftPhase {
  return {
    powered: false,
    alarm: false,
    platformState: COLD_FRAME,
    consoleState: CONSOLE_IDLE,
    drones: [],
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
    ready: false,
    spent: false,
    launched: false,
  };
}

/**
 * What every piece is doing, from the clock the server and client share.
 *
 * `time` is wall time and is used for the two things that must NOT be in step
 * across a night: the shudder of a rig straining against the ground, and the
 * swing of a line still falling. Keyed off the pad's own elapsed seconds, two
 * pads mid-pickup would shake and swing identically.
 */
export function riftPhase(
  rift: Rift,
  timing: RiftTimingConfig,
  atlas: PlatformAtlas | null,
  time: number,
): RiftPhase {
  const layout = atlas?.layout;
  const ropeLength = layout?.ropeLength ?? 64;
  const eyes = layout?.eyes ?? [];

  if (rift.state === 'dormant') return restingPhase(rift);

  // SPENT is not a moment, it is a condition. A pad that flew before this
  // player even arrived has to look the same as one they watched leave ten
  // minutes ago: no skid, nothing in the air, a dead console, and the hole in
  // the ground. A pad the END OF THE NIGHT killed never flew at all — its
  // platform is still sitting there cold with its ground still under it.
  if (rift.state === 'spent') {
    const launched = rift.closeAt !== null || rift.elapsed > 0;
    return {
      ...restingPhase(rift),
      consoleState: CONSOLE_SPENT,
      imprint: launched ? 1 : 0,
      airborne: launched,
      alpha: 0,
      spent: true,
      launched,
    };
  }

  const elapsed = rift.elapsed;

  // --- the pickup ----------------------------------------------------------
  const since = rift.closeAt === null ? -1 : elapsed - rift.closeAt;
  const alarm = since >= 0;
  const sinceStrain = alarm ? since - timing.tiedAt : -1;
  const strain = sinceStrain < 0
    ? 0
    : clamp01(sinceStrain / Math.max(timing.liftStrain, 1e-6));
  const sinceBreak = alarm ? since - timing.breakAt : -1;
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
  const airborne = sinceBreak > 0;

  const drones = alarm
    ? inbound(rift, timing, eyes, ropeLength, since, deckX, deckY, strain, airborne, time)
    : [];

  const powered = elapsed >= timing.consoleLag;
  return {
    powered,
    alarm,
    platformState: alarm ? ALARM_FRAME : powered ? STANDBY_FRAME : COLD_FRAME,
    consoleState: alarm
      ? CONSOLE_READY
      : rift.ready ? CONSOLE_READY : powered ? CONSOLE_ARMED : CONSOLE_IDLE,
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
    // A pad already calling is not waiting on anybody, so the band stops the
    // instant the pickup is called.
    ready: rift.ready && !alarm,
    spent: false,
    launched: alarm,
  };
}

/**
 * The four aircraft, flown entirely off `since` and the constants.
 *
 * THEY ARRIVE AS A GROUP AND SPLIT AT THE LAST MOMENT. Each one starts well
 * off-screen on `rift.approach`, holds a formation slot on the way in, and
 * only peels to its own corner over the last third of the crossing — four
 * machines on four separate bearings across a clearing is four events, and
 * this has to be one. They leave the treeline `droneStagger` apart for the
 * opposite reason: arriving on the same frame is one sprite drawn four times.
 *
 * THE LINE IS PAID OUT, NOT SNAPPED ON. It falls out of the winch under its
 * own weight, swings while it falls, and the corner is only tied when the END
 * gets there — which is the difference between machinery doing a job and a
 * rope appearing.
 */
function inbound(
  rift: Rift,
  timing: RiftTimingConfig,
  eyes: readonly PlatformPoint[],
  ropeLength: number,
  since: number,
  deckX: number,
  deckY: number,
  strain: number,
  airborne: boolean,
  time: number,
): DronePhase[] {
  const out: DronePhase[] = [];
  const count = Math.max(1, Math.min(eyes.length || timing.drones, timing.drones));
  // Straight out along the approach, foreshortened like every ground distance.
  const farX = Math.cos(rift.approach) * INBOUND_TILES * TILE_PX;
  const farY = Math.sin(rift.approach) * INBOUND_TILES * TILE_PX * GROUND_SQUASH;
  // Across the approach, for the formation slots.
  const acrossX = -Math.sin(rift.approach) * FORMATION_TILES * TILE_PX;
  const acrossY = Math.cos(rift.approach) * FORMATION_TILES * TILE_PX * GROUND_SQUASH;

  for (let i = 0; i < count; i++) {
    const departs = timing.liftAlarm + i * timing.droneStagger;
    const local = since - departs;
    if (local < 0) continue;

    const eye = eyes[i] ?? { dx: 0, dy: -ropeLength * 0.5 };
    const eyeX = deckX + eye.dx;
    const eyeY = deckY + eye.dy;
    // Station: mostly straight above its own eye and a little outboard, at
    // exactly the line's length away, so a taut rope is a straight one.
    const spread = ropeLength * STATION_SPREAD * (eye.dx >= 0 ? 1 : -1);
    const lift = Math.sqrt(Math.max(0, ropeLength * ropeLength - spread * spread));
    // A straining drone steals height the line cannot give it. The platform has
    // not moved yet, so the only place that pull can go is upward — and seeing
    // the aircraft climb while the skid stays put is the picture.
    const pull = 1 + strain * STRAIN_PULL * (airborne ? 0 : 1);
    const stationX = eyeX + spread;
    const stationY = eyeY - lift * pull;

    // The crossing. Eased OUT: an aircraft arriving somewhere decelerates into
    // its hover, and easing in would have it accelerate into the platform.
    const cross = clamp01(local / Math.max(timing.droneInbound, 1e-6));
    const t = easeOut(cross);
    // The slot it holds on the way in, gone by the time it is on station. It
    // decays on the SAME `t` the approach does, and it has to: on any other
    // curve the formation offset outlives the approach, and the drone slides
    // past its own corner and drifts back out to it. One easing, one path.
    const slot = (i - (count - 1) / 2) * (1 - t);
    const x = stationX + farX * (1 - t) + acrossX * slot;
    const y = stationY + farY * (1 - t) + acrossY * slot;

    // The line. It starts falling the moment the aircraft is on station and
    // reaches the eye `droneDrop` later, under gravity rather than linearly —
    // rope that is being let out accelerates, and a constant-rate line looks
    // like a bar being extruded.
    const dropping = clamp01((local - timing.droneInbound) / Math.max(timing.droneDrop, 1e-6));
    const paid = easeIn(dropping) * ropeLength;
    const tied = dropping >= 1;
    // The free end swings under the winch while it falls, on its own slow beat.
    const swing = Math.sin(time * 3.1 + i * 1.9) * 0.30 * (1 - dropping);
    // AND IT HOMES ON THE EYE. A line dropped straight down would finish a
    // rope's length below the drone, which is NOT where its eye is — the
    // station is offset outboard — so a "tied" flag that snapped the end onto
    // the eye would jump it two tiles sideways on one frame. Blending the free
    // hang into the eye's position on the same curve the rope pays out is what
    // makes the last moment of the drop read as somebody catching the hook.
    const settle = easeIn(dropping);
    out.push({
      index: i,
      age: local,
      x,
      y,
      cruising: cross < 1,
      eyeX,
      eyeY,
      rope: tied ? ropeLength : paid,
      tied,
      endX: (x + Math.sin(swing) * paid) * (1 - settle) + eyeX * settle,
      endY: (y + Math.cos(swing) * paid) * (1 - settle) + eyeY * settle,
    });
  }
  return out;
}

export interface RiftStanding {
  sheet: 'console' | 'torch' | 'platform';
  x: number;
  y: number;
  shape: number;
  state: number;
  /**
   * Which pad this is, on the platform piece only. The deck carries a LOAD —
   * everything the party has poured into it — and the pile is drawn with the
   * box in the same depth slot, so the piece has to know whose it is.
   */
  rift?: string;
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
 * and neither leaves with the platform. The skid drops out the moment it is in
 * the air — `drawRiftAir` takes it, because something twenty tiles up has no
 * business being sorted against the feet of people standing on the ground.
 *
 * NO DRONES, EVER. Nothing about the aircraft touches the floor: they arrive
 * flying, they leave flying, and the whole of their existence is the air pass.
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
      state: phase.platformState,
      rift: rift.id,
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
 * purpose — one torch, one meaning: a threshold), the skid is
 * `make_platform.py`'s.
 */
export function drawRiftProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  rift: RiftAtlas | null,
  platform: PlatformAtlas | null,
  piece: RiftStanding,
  shadow: string,
  loot: LootAtlas | null = null,
): void {
  if (piece.sheet === 'platform') {
    const sheet = platform?.platform;
    if (!sheet) return;
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, piece.state) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      piece.x, piece.y, 1, 1, 0, shadow, 0.74,
    );
    // The load, in the box's own depth slot. It is drawn AFTER the skid and
    // never sorted against the party: cargo is part of the platform now, and a
    // player walking behind the box has to be hidden by what is inside it the
    // same way they are hidden by the box.
    if (piece.rift) {
      drawCargoPile(ctx, view, loot, padPile(piece.rift), piece.x, piece.y, 1, 1);
    }
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
 * Everything that is OFF THE GROUND: the lines, the aircraft, and a skid that
 * has broken free.
 *
 * Screen space, run right after the entity depth sort and BEFORE the darkness.
 * Both halves of that matter. After the sort, because nothing standing on the
 * floor can plausibly be in front of a machine hanging over it. Before the
 * darkness, because a drone is a lit object and not a light — which is what
 * lets one resolve OUT OF THE DARK as it crosses into the pad's own glow
 * instead of popping into existence at full brightness, and what lets the
 * loaded platform dissolve into the night as it climbs away.
 */
export function drawRiftAir(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  phase: RiftPhase,
  atlas: PlatformAtlas | null,
  shadow: string,
  riftId: string | null = null,
  loot: LootAtlas | null = null,
): void {
  // No state guard beyond the atlas. Outside a pickup the drone list is empty
  // and `airborne` is false, so every block below skips itself on its own.
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
    drawRope(ctx, view, drone, phase.alpha);
  }

  if (phase.airborne && atlas.platform) {
    const sheet = atlas.platform;
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, ALARM_FRAME) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      phase.deckX, phase.deckY, phase.scale, phase.alpha, phase.tilt, null, 0,
    );
    // THE LOAD LEAVES WITH THE SKID. Same offsets, same scale, same fade —
    // this is the one frame the night is actually for, and a platform that
    // climbed away empty would throw it away.
    if (riftId) {
      drawCargoPile(
        ctx, view, loot, padPile(riftId),
        phase.deckX, phase.deckY, phase.scale, phase.alpha,
      );
    }
  }

  // Everything still in the air out of somebody's backpack. In THIS pass and
  // not the standing sort, because the body doing the pouring stands in front
  // of the deck: sorted by feet, every item would fly behind the person
  // throwing it.
  if (riftId) drawCargoTosses(ctx, view, loot, riftId, shadow);

  const sheet = atlas.drone;
  if (!sheet) return;
  for (const drone of phase.drones) {
    drawSprite(
      ctx, view, sheet.image,
      platformPropFrame(sheet, drone.cruising ? CRUISE_FRAME : HOVER_FRAME) * sheet.frameWidth,
      sheet.frameWidth, sheet.frameHeight,
      drone.x, drone.y, phase.airborne ? phase.scale : 1, phase.alpha, 0, null, 0,
    );
  }
}

/**
 * A deck's load, back to front, in the platform's own frame of reference.
 *
 * Offsets are from the CONTACT point and are scaled by whatever the skid is
 * scaled by, which is the whole trick: one number moves the box and its cargo
 * together, so a pile stacked on the ground is still stacked when the thing it
 * is stacked on is forty tiles up and half the size.
 *
 * Bottom-anchored like everything else that stands on something, rotated about
 * its own base so a leaning crate leans on the floor rather than hovering off
 * it. No shadows: twenty ellipses under twenty items on an iron deck is a
 * texture, not a contact.
 */
function drawCargoPile(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  loot: LootAtlas | null,
  pile: readonly PadCargo[],
  deckX: number,
  deckY: number,
  scale: number,
  alpha: number,
): void {
  if (!loot || pile.length === 0 || alpha <= 0.02) return;
  const { image, frameWidth, frameHeight } = loot;
  ctx.globalAlpha = alpha;
  for (const item of pile) {
    const w = frameWidth * CARGO_SCALE * item.scale * scale;
    const h = frameHeight * CARGO_SCALE * item.scale * scale;
    const px = view.x(deckX + item.dx * scale);
    const py = view.y(deckY + (item.dy - item.z) * scale);
    const dw = view.size(w);
    const dh = view.size(h);
    if (item.rot === 0) {
      ctx.drawImage(image, item.frame * frameWidth, 0, frameWidth, frameHeight,
        Math.round(px - dw / 2), Math.round(py - dh), Math.round(dw), Math.round(dh));
      continue;
    }
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(item.rot);
    ctx.drawImage(image, item.frame * frameWidth, 0, frameWidth, frameHeight,
      Math.round(-dw / 2), Math.round(-dh), Math.round(dw), Math.round(dh));
    ctx.restore();
  }
  ctx.globalAlpha = 1;
}

/**
 * What is between the bag and the deck on this frame.
 *
 * THE SHADOW IS WHAT SELLS IT. At this camera angle a sprite moving up the
 * screen and a sprite moving away are the same pixels; a dark ellipse pinned
 * to the spot it is going to land on, growing as it falls, is the only thing
 * that says which. It is drawn at the RESTING place, not under the sprite,
 * because that is where the thing is heading and watching the shadow arrive
 * first is what makes the landing feel aimed.
 */
function drawCargoTosses(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  loot: LootAtlas | null,
  riftId: string,
  shadow: string,
): void {
  if (!loot) return;
  const { image, frameWidth, frameHeight } = loot;
  for (const toss of padTosses()) {
    if (toss.rift !== riftId) continue;
    const pose = tossPose(toss);
    const w = frameWidth * CARGO_SCALE * pose.scale;
    const h = frameHeight * CARGO_SCALE * pose.scale;
    const groundX = toss.deckX + toss.rest.dx;
    const groundY = toss.deckY + toss.rest.dy - toss.rest.z;
    const drop = Math.max(0, groundY - pose.y);
    const near = 1 - Math.min(1, drop / Math.max(toss.rise, 1));

    ctx.globalAlpha = 0.16 + 0.24 * near;
    ctx.fillStyle = shadow;
    ctx.beginPath();
    ctx.ellipse(
      view.x(groundX), view.y(groundY),
      view.size(w * (0.34 + 0.16 * near)),
      view.size(h * (0.16 + 0.08 * near)),
      0, 0, Math.PI * 2,
    );
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.save();
    ctx.translate(view.x(pose.x), view.y(pose.y));
    ctx.rotate(pose.rot);
    ctx.drawImage(
      image, pose.frame * frameWidth, 0, frameWidth, frameHeight,
      Math.round(-view.size(w) / 2), Math.round(-view.size(h)),
      Math.round(view.size(w)), Math.round(view.size(h)),
    );
    ctx.restore();
  }
  ctx.globalAlpha = 1;
}

/**
 * One line, winch to whatever its free end has reached. PLOTTED AS PIXEL ART.
 *
 * TWO DIFFERENT PICTURES OUT OF ONE ROUTINE, and the difference is where the
 * far end is. While the line is falling the end is hanging in the air below the
 * drone, swinging, and only as much rope as has been paid out is drawn — so what
 * the player watches is a cable coming down, not a cable that exists. Once it is
 * tied the end IS the eye, and from that frame on the curve is governed by
 * SLACK: how much more rope there is than there is distance to cover. That
 * single number does the rest of the job — a fresh tie still has plenty of line
 * in it and pools, and by the time the rig is straining there is none left and
 * it is dead straight, which is what says the machine is pulling.
 *
 * WHY IT IS NOT A STROKE ANY MORE. This used to be two `quadraticCurveTo`
 * strokes at 1.6 and 0.7 screen pixels wide. Canvas anti-aliases a stroke, and
 * a fractional-width one at that: the rope came out as a soft grey smear with
 * partial alpha down both sides, hanging between a pixel-art aircraft and a
 * pixel-art deck. PIXEL-ART-DIRECTION.md S4 is explicit — strict 1:1 pixel grid,
 * zero anti-aliasing, zero sub-pixel work — and the one part of the extraction
 * that the player watches for a full four seconds was the one part of it drawn
 * with a pen.
 *
 * So the curve is SAMPLED into WORLD pixels, deduplicated, and each surviving
 * pixel is filled as a `zoom`-sized block. Two passes, because a rope needs a
 * lit edge to exist at all against a night forest and S8 says where that edge
 * is: the crest goes one world pixel UP from the core, which is the 135deg key,
 * and the core is drawn over it so the highlight never eats the line's body.
 */
function drawRope(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  drone: DronePhase,
  alpha: number,
): void {
  if (alpha <= 0.02 || drone.rope <= 0.5) return;
  const span = Math.hypot(drone.x - drone.endX, drone.y - drone.endY);
  const slack = Math.max(0, drone.rope - span);
  // All of this stays in WORLD pixels — the sag used to be scaled by zoom on
  // the way in, which made a rope hang further at higher magnification.
  const sag = Math.min(slack * 0.55, drone.rope * 0.42);
  const midX = (drone.endX + drone.x) / 2;
  const midY = (drone.endY + drone.y) / 2 + sag;

  // One sample per half world pixel of arc: enough that the curve never gaps,
  // few enough that a four-rope rig is a few hundred cheap rounds a frame.
  const steps = Math.max(4, Math.ceil((span + sag) * 2));
  const core = new Map<number, [number, number]>();
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    const wx = Math.round(u * u * drone.endX + 2 * u * t * midX + t * t * drone.x);
    const wy = Math.round(u * u * drone.endY + 2 * u * t * midY + t * t * drone.y);
    core.set(ropeKey(wx, wy), [wx, wy]);
  }

  const block = Math.max(1, Math.ceil(view.zoom));
  ctx.save();
  ctx.globalAlpha = alpha;
  // The crest first and the core over it: a 2px band with its lit edge on top,
  // which is the same section every cylinder in `make_objects` is banded into.
  ctx.fillStyle = ROPE_CREST;
  for (const [wx, wy] of core.values()) {
    if (core.has(ropeKey(wx, wy - 1))) continue;
    ctx.fillRect(view.x(wx), view.y(wy - 1), block, block);
  }
  ctx.fillStyle = ROPE_CORE;
  for (const [wx, wy] of core.values()) {
    ctx.fillRect(view.x(wx), view.y(wy), block, block);
  }
  // The hook on the end while it is still falling. Three world pixels, and they
  // are what the eye tracks down the screen — a line with nothing on its end
  // reads as a crack in the image rather than as something being lowered.
  if (!drone.tied) {
    const hx = Math.round(drone.endX);
    const hy = Math.round(drone.endY);
    ctx.fillStyle = ROPE_HOOK;
    ctx.fillRect(view.x(hx - 1), view.y(hy), block * 3, block);
    ctx.fillRect(view.x(hx), view.y(hy + 1), block, block);
  }
  ctx.restore();
}

/** One world pixel as a number, for the dedupe map. Offset so negatives pack. */
function ropeKey(x: number, y: number): number {
  return (x + 4096) * 16384 + (y + 4096);
}

/**
 * The rope's three tones, and they are `make_platform.py`'s `ROPE` ramp.
 *
 * Hardcoded rather than read off the palette because rope is a MATERIAL, the
 * same way that ramp is — the theme decides what light looks like in this game,
 * not what hemp is made of. These are steps 1, 3 and 5 of it: the underside, the
 * body and the crest the key catches. Move the ramp and move these with it.
 */
const ROPE_CORE = '#624425';
const ROPE_CREST = '#9e8544';
const ROPE_HOOK = '#836534';

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
    groundShadow(
      ctx,
      view,
      worldX,
      worldY - RIFT_SHADOW_HEIGHT / 2,
      (frameWidth * scale * shadowWidth) / 2,
      RIFT_SHADOW_HEIGHT / 2,
      frameHeight * scale,
      RIFT_SHADOW_ALPHA * alpha,
    );
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
 * The order inside is the order of loudness: the light the pad puts on its own
 * clearing, the corner lamps, the wash on the ground, the burst over it, the
 * aircraft, and the console's band.
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

  // THE PAD PUTS LIGHT IN THE AIR, and this halo is what makes it read as the
  // source rather than as a lit object in somebody else's light. Green while it
  // is loading; once the pickup is called it goes RED AND BREATHES ON THE
  // SIREN'S OWN BEAT, so the whole clearing pulses with the corners and the
  // party is standing inside the alarm rather than beside it. A gradient, never
  // a filled arc — the alpha is already zero before the radius ends, so the
  // glow has no boundary anywhere.
  if (phase.powered && phase.alpha > 0 && !phase.airborne) {
    const siren = atlas.siren;
    const beat = phase.alarm
      ? 0.72 + 0.55 * Math.abs(Math.sin(time * Math.PI * sirenRate(siren)))
      : 0.92 + 0.08 * Math.sin(time * 1.6);
    const radius = rift.lightTiles * tileSize * (phase.alarm ? 1.35 : 1.0);
    const [r, g, b] = phase.alarm ? ALARM_TONE : palette().scene.beacon;
    // THE HALO IS THE AIR, NOT THE LAMP. The corner lamps are baked into the
    // sheet and their glare is its own additive sheet on top; this gradient
    // sits UNDER both and only has to say the clearing has a source in it. At
    // 0.30/0.20 it was doing all three jobs at once — a wash the width of the
    // pad's whole light radius that flattened the skid's own banding into a
    // silhouette and blew the deck out to one value. Halved: the lamps stay
    // the brightest thing on the structure, which is what they are for.
    // HALVED ONCE, AND CUT AGAIN: the halo, the four lamps and the wash are one
    // stack, and every pass that tuned them apart put the sum back. This is the
    // layer with the least to say — it is the AIR having a source in it — so it
    // gives first, and the lamps stay the brightest thing on the structure.
    const peak = phase.alarm ? 0.095 : 0.06;
    const glow = ctx.createRadialGradient(rift.x, rift.y, 0, rift.x, rift.y, radius);
    glow.addColorStop(0, `rgb(${r} ${g} ${b} / ${(peak * beat).toFixed(3)})`);
    glow.addColorStop(0.24, `rgb(${r} ${g} ${b} / ${(peak * 0.45 * beat).toFixed(3)})`);
    glow.addColorStop(0.58, `rgb(${r} ${g} ${b} / ${(peak * 0.15 * beat).toFixed(3)})`);
    glow.addColorStop(1, `rgb(${r} ${g} ${b} / 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(rift.x - radius, rift.y - radius, radius * 2, radius * 2);
  }

  // THE FOUR CORNER LAMPS, each turning on its own phase. This is the pad's
  // whole vocabulary: a slow green breath while it is taking cargo, and four
  // red beams sweeping out of step once the pickup is called. Out of step is
  // load-bearing — four beams in lockstep read as one flashing rectangle,
  // four running at their own offsets read as four machines on a structure.
  const lamp = phase.alarm ? atlas.siren : atlas.standby;
  if (lamp && !phase.airborne && phase.powered) {
    const period = lamp.frames / Math.max(lamp.fps, 1e-6);
    // FOUR OF THESE OVERLAP. Each lamp sheet bakes its own glare, and drawn at
    // full strength onto `lighter` the four corners summed into one white
    // rectangle the size of the deck — the pad reading as a lightbox rather
    // than as four lamps on a structure. They are one budget with the halo
    // above and the flames in the shop; judged apart, the sum creeps back.
    // Four of these sum, and they sum on top of the halo above and whatever the
    // party is carrying. A lamp reads as a lamp well below full: what says
    // "beacon" is the BEAT and the four phases, not the peak value.
    ctx.globalAlpha = phase.alarm ? 0.68 : 0.55;
    atlas.layout.lamps.forEach((point, i) => {
      const offset = (i / Math.max(atlas.layout.lamps.length, 1)) * period;
      blit(ctx, lamp, phase.deckX + point.dx, phase.deckY + point.dy, time + offset);
    });
    ctx.globalAlpha = 1;
  }

  // Rotor wash. Only once something is actually holding station over the pad,
  // and it goes to maximum through the strain, which is what says the machines
  // are pulling rather than hovering. Gone the moment the skid is off the
  // floor: dust needs something to blow off, and there is nothing left under it
  // but the hole.
  const wash = atlas.downwash;
  if (wash && !phase.airborne && phase.drones.length > 0) {
    const holding = phase.drones.reduce((sum, d) => sum + (d.cruising ? 0 : 1), 0);
    const idle = (holding / Math.max(timing_drones(atlas), 1)) * 0.30;
    // Dust in a rotor wash is DUST — lit air over a dark floor, never a white
    // sheet. At 0.95 the strain wash covered the imprint, the hazard paint and
    // the front third of the deck with one flat glare on the frame the player
    // is meant to be watching the skid come free.
    ctx.globalAlpha = Math.min(0.5, idle + phase.strain * 0.38);
    blit(ctx, wash, rift.x, rift.y, time);
    ctx.globalAlpha = 1;
  }

  // The ground letting go. One event, on the frame it happens.
  const burst = atlas.burst;
  if (burst && phase.sinceBreak >= 0 && phase.sinceBreak < burst.frames / burst.fps) {
    blit(ctx, burst, rift.x, rift.y, phase.sinceBreak);
  }

  // Rotors and nav lights, per aircraft, EACH ON ITS OWN CLOCK. Four machines
  // playing the same frame on the same tick are four copies of one sprite,
  // which is exactly what they are and exactly what the eye must not notice —
  // so each is phased by its own age, which the departure stagger already made
  // different.
  const rotor = atlas.rotor;
  const strobe = atlas.strobe;
  const rotorY = atlas.layout.rotorY;
  for (const drone of phase.drones) {
    if (rotor) {
      // A machine crossing a clearing has its rotors HARDER over than one
      // holding station — that is what forward flight costs — so an inbound
      // drone's discs are brighter and turning faster than a hovering one's.
      ctx.globalAlpha = phase.alpha * (drone.cruising ? 1 : 0.78);
      blit(ctx, rotor, drone.x, drone.y - rotorY, drone.age * (drone.cruising ? 1.25 : 1));
    }
    if (strobe) {
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
 * The colour the clearing goes once the pickup is called.
 *
 * Hardcoded rather than pulled off the palette, and for once that is right:
 * every other light in this game belongs to the theme, but this one has to be
 * the SAME RED as `RED_GLARE` in `make_platform.py`, because the corner lamps
 * and the wash they throw on the ground are one light source. A themed red
 * would drift away from the baked one the first time the palette moved.
 */
const ALARM_TONE: readonly [number, number, number] = [232, 60, 48];

/** Turns of the siren per second — the beat the whole clearing pulses on. */
function sirenRate(siren: PlatformEffectSheet | null): number {
  if (!siren) return 1.3;
  return siren.fps / Math.max(siren.frames, 1);
}

/** How many lamps the rig has, which is how many aircraft it takes. */
function timing_drones(atlas: PlatformAtlas): number {
  return Math.max(1, atlas.layout.lamps.length);
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
