/**
 * The extraction point: a sigil on the floor, four stones, a console, and the
 * thing they open.
 *
 * THIS FILE OWNS THE CEREMONY'S TIMING and nothing else does. `riftPhase`
 * turns one number — seconds since the console was pressed — into what every
 * piece of the structure is doing on this frame, and the three draw functions
 * only read it. Splitting "what is happening" from "what is drawn" is what
 * keeps the stone that lights on screen the stone the server thinks lit: both
 * sides run the same arithmetic off the same constants in
 * `server/app/rift.py`, shipped through `config.rift`.
 *
 * THE STAGGER IS THE WHOLE EFFECT. The stones do not come on together. Each
 * one starts `pillarStagger` after the one before it, so the light visibly
 * RUNS AROUND THE RING and the structure reads as waking up rather than as a
 * switch being thrown. The order is the order the server placed them: back
 * left, back right, front left, front right — around, not across, so the run
 * never jumps the diagonal.
 *
 * The three passes go in three different places in the frame, because they are
 * three different kinds of thing:
 *   `drawRiftScar`   with the boot prints, on the floor, under everybody
 *   `riftStanding`   merged into the entity depth sort, so a player walks
 *                    behind a pillar and disappears behind it
 *   `drawRiftGlow`   after the darkness pass, additive — light, not lit
 */

import { FLOOR, VOID, type Rift, type TileMap } from '../../game/world';
import type { RiftTimingConfig } from '../../net/protocol';
import { palette } from '../../theme/palette';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import {
  riftFrame,
  riftImage,
  riftLevelImage,
  riftPropFrame,
  type RiftAtlas,
  type RiftEffectSheet,
} from '../rift';

/**
 * Additive strength of the hovering sphere. The stones keep full strength —
 * 1 here stacked with the halo and blew the lattice out to a white disc.
 */
const ANOMALY_GLOW = 0.72;

/** Prop states. The index is the contract with `make_rift.py`. */
const DORMANT_FRAME = 0;
const AWAKE_FRAME = 1;
/** Console only: quota paid, plunger gold, pressing now SHUTS the rift. */
const READY_FRAME = 2;
/** Console only: driven home, every lamp on it dead. */
const SPENT_FRAME = 3;

/**
 * Tile size, for turning `boomTiles` into world pixels.
 *
 * The config gives the blast's reach in TILES because that is how every
 * distance in this game is authored; the marks live in world pixels.
 */
const TILE_PX = 16;

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

function easeOut(t: number): number {
  return 1 - (1 - t) ** 3;
}

/** A stone that has not started waking yet. */
const NOT_STARTED = -1;

/**
 * The ceremony, if the server did not send one.
 *
 * Mirrors `server/app/rift.py`. It exists so a client talking to an older
 * server draws a plausible sequence instead of dividing by undefined — the
 * server's numbers win whenever they arrive, and they always do in practice.
 */
export const RIFT_FALLBACK: RiftTimingConfig = {
  consoleLag: 0.35,
  pillarStagger: 0.45,
  chargeTime: 1.0,
  settle: 0.3,
  emergeAt: 1.65,
  emergeTime: 1.25,
  openAt: 2.9,
  lightTiles: 4.5,
  boomAt: 2.15,
  boomTime: 3.4,
  boomTiles: 34,
  openTime: null,
  collapseAt: null,
  collapseTime: 28 / 16,
  spentAt: null,
};

export interface RiftPhase {
  /**
   * Seconds into each stone's `charge` timeline, or `NOT_STARTED` before it
   * begins. Past `chargeTime` the stone is crowned and this stops being read.
   */
  pillarCharge: number[];
  /** Whether each stone's PROP has flipped to its awake frame. */
  pillarAwake: boolean[];
  /** Whether each stone is holding its `crown` loop. */
  pillarCrowned: boolean[];
  consoleArmed: boolean;
  /**
   * Seconds each stone has been holding its `crown` loop.
   *
   * ANCHORED ON THE HANDOVER, not on wall time. `charge` ends on exactly
   * `crown` frame 0, so the loop has to START at frame 0 or the handover jumps
   * to an arbitrary point in the cycle and undoes the whole reason the seam was
   * built to be byte-identical. It also gets the stagger for free: each stone
   * crowns at its own moment, so no two are in phase.
   */
  crownTime: number[];
  /** Seconds into `emerge`, or `NOT_STARTED` before the tear begins. */
  emerging: number;
  /**
   * 0..1 how far through `emerge` we are. The halo grows with this so the
   * tear lights the pad as it opens rather than snapping on at `openAt`.
   */
  emergeProgress: number;
  /** Seconds the anomaly has been on its resting loop. Same rule as `crownTime`. */
  anomalyTime: number;
  /** The anomaly is on its resting loop. */
  open: boolean;
  /**
   * How far the blast has travelled, in world px. Marks inside this have been
   * laid; everything past it has not happened yet. 0 before the burst and
   * `Infinity` once the wave is long finished — which is what makes a rift
   * that was already spent when you arrived simply HAVE residue, with no
   * replay of an explosion nobody was there for.
   */
  waveRadius: number;
  /** Seconds since the burst, for the per-mark flash as the wave passes. */
  sinceBoom: number;
  /**
   * 1 while the rift holds, falling to 0 across the collapse.
   *
   * THE HALO'S ONLY, now. It used to fade the anomaly's sprite as well, which
   * was the right answer when the vanish was a fade — but `collapse.png` IS
   * the vanish, and multiplying an alpha over a sheet that already ends on an
   * empty frame would dim the implosion flash out of existence.
   */
  fade: number;
  /** Seconds into `collapse`, or NOT_STARTED while it is still holding. */
  collapsing: number;
  /** Overfeed tier, 0..3. Picks which colour bank the anomaly draws from. */
  level: number;
  /** Quota paid and still holding: gold console, rainbow band. */
  ready: boolean;
  /** Nothing left but the marks. */
  spent: boolean;
}

/**
 * Nothing has happened yet.
 *
 * Sized from the rift's OWN stone count rather than a fixed four. How many
 * stones a structure has is data now (`server/app/rift.py` derives the whole
 * ceremony's length from it), so a hardcoded four would hand back `undefined`
 * for the fifth the day somebody places one.
 */
function dormantPhase(stones: number): RiftPhase {
  return {
    pillarCharge: new Array<number>(stones).fill(NOT_STARTED),
    pillarAwake: new Array<boolean>(stones).fill(false),
    pillarCrowned: new Array<boolean>(stones).fill(false),
    crownTime: new Array<number>(stones).fill(0),
    consoleArmed: false,
    emerging: NOT_STARTED,
    emergeProgress: 0,
    anomalyTime: 0,
    open: false,
    waveRadius: 0,
    sinceBoom: 0,
    fade: 1,
    collapsing: NOT_STARTED,
    level: 0,
    ready: false,
    spent: false,
  };
}

/**
 * What every piece is doing, from the one clock the server and client share.
 *
 * `handoffAt` is the fraction of `charge` at which the sheet whites the
 * capstone out, and it is where the PROP swaps from its dormant cut to its
 * awake one — the flash is what hides the swap. Flipping a frame early or late
 * is a visible cut to a different stone, which is why the number comes off the
 * sheet's own manifest rather than being chosen here.
 */
export function riftPhase(
  rift: Rift,
  timing: RiftTimingConfig,
  chargeHandoff: number,
): RiftPhase {
  if (rift.state === 'dormant') return dormantPhase(rift.pillars.length);

  // SPENT is not a moment, it is a condition. A rift that went off before this
  // player even arrived has to look the same as one they watched go off ten
  // minutes ago: structure dark, ground marked, nothing playing. So the wave is
  // already everywhere and the fade is already zero, with no timeline behind it.
  if (rift.state === 'spent') {
    const stones = rift.pillars.length;
    const neverTore = rift.elapsed <= 0 && rift.closeAt === null;
    return {
      ...dormantPhase(stones),
      pillarAwake: new Array<boolean>(stones).fill(false),
      consoleArmed: true,
      waveRadius: neverTore ? 0 : Infinity,
      sinceBoom: neverTore ? 0 : Infinity,
      fade: 0,
      level: rift.level,
      spent: true,
    };
  }

  const elapsed = rift.elapsed;
  const pillarCharge: number[] = [];
  const pillarAwake: boolean[] = [];
  const pillarCrowned: boolean[] = [];
  const crownTime: number[] = [];
  for (let i = 0; i < rift.pillars.length; i++) {
    const local = elapsed - (timing.consoleLag + i * timing.pillarStagger);
    const crowned = local >= timing.chargeTime;
    pillarCharge.push(local >= 0 && !crowned ? local : NOT_STARTED);
    pillarAwake.push(local >= timing.chargeTime * chargeHandoff);
    pillarCrowned.push(crowned);
    crownTime.push(Math.max(0, local - timing.chargeTime));
  }

  const sinceTear = elapsed - timing.emergeAt;
  // The vanish runs on the same one clock everything else does, measured from
  // the tick the server said a player shut the pad.
  const sinceClose = rift.closeAt === null ? NOT_STARTED : elapsed - rift.closeAt;
  // The blast, easing out: it leaves fast and slows as it spreads, which is
  // what a shock front does and what stops the marks appearing at a constant
  // rate like a progress bar filling.
  const sinceBoom = elapsed - timing.boomAt;
  const boomT = clamp01(sinceBoom / Math.max(timing.boomTime, 1e-6));
  const reach = timing.boomTiles * TILE_PX;
  return {
    pillarCharge,
    pillarAwake,
    pillarCrowned,
    crownTime,
    anomalyTime: Math.max(0, elapsed - timing.openAt),
    waveRadius: sinceBoom <= 0 ? 0 : (boomT >= 1 ? Infinity : easeOut(boomT) * reach),
    sinceBoom: Math.max(0, sinceBoom),
    // Holds at 1 until the window is nearly out, then draws in over the
    // collapse. Never negative — the anomaly is simply gone at `spentAt`.
    // No deadline means it never dims. `collapseAt` is null while the rift is
    // open-ended, and dividing by a missing number would fade it out instantly.
    fade: timing.collapseAt === null && rift.closeAt === null
      ? 1
      : 1 - clamp01(
        (elapsed - (rift.closeAt ?? timing.collapseAt ?? elapsed))
        / Math.max(timing.collapseTime, 1e-6),
      ),
    collapsing: sinceClose >= 0 ? sinceClose : NOT_STARTED,
    level: rift.level,
    // A pad that is already closing is not waiting on anybody, so the gold
    // console and the band both stop the instant it is shut.
    ready: rift.ready && rift.closeAt === null,
    spent: false,
    // The console answers the instant it is pressed. It is the one piece that
    // must not wait for anything: a button that visibly does nothing for a
    // third of a second reads as a button that did not take the press.
    consoleArmed: elapsed >= 0,
    emerging: sinceTear >= 0 && elapsed < timing.openAt ? sinceTear : NOT_STARTED,
    emergeProgress: sinceTear < 0
      ? 0
      : clamp01(sinceTear / Math.max(timing.emergeTime, 1e-6)),
    open: elapsed >= timing.openAt,
  };
}

/** How far into `charge` the sheet flashes. Falls back to the authored 0.55. */
export function chargeHandoff(atlas: RiftAtlas | null): number {
  return atlas?.charge?.handoffAt ?? 0.55;
}

export interface RiftStanding {
  sheet: 'pillar' | 'console' | 'torch';
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
 * The structure's standing pieces, ascending in `y`.
 *
 * Handed to the renderer to merge into the entity depth sort. Already sorted,
 * because that merge walks two ascending lists and re-sorting a fixed set of
 * five pieces every frame would be pure waste — the stones do not move.
 */
export function riftStanding(rift: Rift, phase: RiftPhase): RiftStanding[] {
  const pieces: RiftStanding[] = rift.pillars.map((pillar, index) => ({
    sheet: 'pillar' as const,
    x: pillar.x,
    y: pillar.y,
    shape: pillar.shape,
    state: phase.pillarAwake[index] ? AWAKE_FRAME : DORMANT_FRAME,
  }));
  pieces.push({
    sheet: 'console',
    x: rift.consoleX,
    y: rift.consoleY,
    shape: 0,
    state: phase.spent
      ? SPENT_FRAME
      : phase.ready
        ? READY_FRAME
        : phase.consoleArmed ? AWAKE_FRAME : DORMANT_FRAME,
  });
  pieces.sort((a, b) => a.y - b.y);
  return pieces;
}

/**
 * One standing piece, bottom-anchored on its contact point.
 *
 * SCREEN SPACE, through the projection — this runs inside the entity depth
 * sort, which is a screen-space pass, and every sprite in it is placed with
 * `view.x/y` and scaled by `view.zoom`. Drawing world pixels here instead
 * pins the structure near the screen origin and it rides the camera like a
 * HUD element, which is exactly what it looks like.
 */
export function drawRiftProp(
  ctx: CanvasRenderingContext2D,
  view: Projection,
  atlas: RiftAtlas,
  piece: RiftStanding,
  shadow: string,
): void {
  const sheet = piece.sheet === 'pillar'
    ? atlas.pillar
    : piece.sheet === 'torch' ? atlas.torch : atlas.console;
  if (!sheet) return;
  const frame = riftPropFrame(sheet, piece.shape, piece.state);
  const width = sheet.frameWidth * view.zoom;
  const height = sheet.frameHeight * view.zoom;
  const px = view.x(piece.x);
  const py = view.y(piece.y);

  // The same contact shadow every other standing prop gets. Without it a three
  // metre stone hovers: at this camera angle the dark ellipse where it meets
  // the floor is the only thing saying it is standing ON the ground.
  ctx.globalAlpha = RIFT_SHADOW_ALPHA;
  ctx.fillStyle = shadow;
  ctx.beginPath();
  ctx.ellipse(
    px,
    py - (RIFT_SHADOW_HEIGHT * view.zoom) / 2,
    (width * RIFT_SHADOW_WIDTH) / 2,
    (RIFT_SHADOW_HEIGHT * view.zoom) / 2,
    0, 0, Math.PI * 2,
  );
  ctx.fill();
  ctx.globalAlpha = 1;

  ctx.drawImage(
    sheet.image,
    frame * sheet.frameWidth,
    0,
    sheet.frameWidth,
    sheet.frameHeight,
    Math.round(px - width / 2),
    Math.round(py - height),
    Math.round(width),
    Math.round(height),
  );
}

/**
 * Every torch at the exit, burning. Additive, after the darkness, world space.
 *
 * ON ITS OWN CLOCK AND ITS OWN PHASE. Four fires playing the same frame at the
 * same instant read as four copies of one sprite, which is exactly what they
 * are and exactly what the eye must not notice — so each is offset around the
 * loop by its index. Wall time, not a corridor clock: these burn for the rest
 * of the night and there is nothing for them to be in step with.
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
    blit(ctx, sheet, torch.x, torch.y, time + offset, '');
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

/** Matches the scenery layer's contact shadow, so one pad has one language. */
const RIFT_SHADOW_ALPHA = 0.32;
const RIFT_SHADOW_WIDTH = 0.62;
const RIFT_SHADOW_HEIGHT = 4;

/**
 * The sigil cut into the floor. Flat, centred, no silhouette.
 *
 * Drawn live with the boot prints rather than baked into the ground canvas,
 * for the same reason they are: it is one sprite in one place, and baking it
 * would mean rebuilding the ground bake if the map is ever re-dressed.
 */
export function drawRiftScar(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  rift: Rift | null,
  camera: Camera,
): void {
  const sheet = atlas?.scar;
  if (!sheet || !rift) return;
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
  ctx.drawImage(sheet.image, 0, 0, sheet.frameWidth, sheet.frameHeight,
    left, top, sheet.frameWidth, sheet.frameHeight);
}

/**
 * Everything about the structure that is LIGHT. World pixels, additive, drawn
 * after the darkness pass — a beacon is a light source, not a thing being lit.
 *
 * `beacon` tints the greyscale pillar sheets. The anomaly's two sheets bake
 * their own iridescence and `riftImage` refuses the tint for them, so passing
 * a colour here is safe and passing none is not a bug.
 */
export function drawRiftGlow(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  rift: Rift | null,
  phase: RiftPhase,
  beacon: string,
  tileSize: number,
  time: number,
): void {
  if (!atlas || !rift || rift.state === 'dormant') return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';

  // THE ANOMALY IS A LIGHT SOURCE, and the halo is what makes it read as one.
  //
  // The sheet and the scene-light list reveal the pad — but neither puts light
  // IN THE AIR around the sphere, so without this it reads as a lit object
  // sitting in the dark rather than as the thing lighting it. A whisper, never
  // a flood: stacking a hard core on the additive sheet ate the lattice and
  // turned the rift into a white disc.
  //
  // Gradient, never a filled arc. It has no boundary anywhere — the alpha is
  // already zero before the radius ends — which is the whole difference
  // between a glow and the hard disc this used to draw.
  const halo = phase.open ? phase.fade : phase.emergeProgress;
  if (halo > 0) {
    // Breathes on the same beat the shell does, a full turn of the loop, so
    // the light and the thing throwing it are visibly one object.
    const beat = 0.92 + 0.08 * Math.sin(time * 1.1);
    const radius = rift.lightTiles * tileSize * beat;
    const gx = rift.anomalyX;
    const gy = rift.anomalyY;
    // The light in the air follows the SPHERE'S tier. Leaving it mint while
    // the anomaly went gold put a cold halo around a hot object, which reads
    // as two light sources instead of one thing lighting a clearing.
    const [br, bg, bb] = haloTone(phase.level);
    const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, radius);
    glow.addColorStop(0, `rgb(${br} ${bg} ${bb} / ${(0.26 * halo).toFixed(3)})`);
    glow.addColorStop(0.22, `rgb(${br} ${bg} ${bb} / ${(0.11 * halo).toFixed(3)})`);
    glow.addColorStop(0.55, `rgb(${br} ${bg} ${bb} / ${(0.04 * halo).toFixed(3)})`);
    glow.addColorStop(1, `rgb(${br} ${bg} ${bb} / 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(gx - radius, gy - radius, radius * 2, radius * 2);
  }

  for (let i = 0; i < rift.pillars.length; i++) {
    const pillar = rift.pillars[i];
    if (phase.pillarCrowned[i]) {
      blit(ctx, atlas.crown, pillar.x, pillar.y, phase.crownTime[i], beacon);
    } else if (phase.pillarCharge[i] >= 0) {
      blit(ctx, atlas.charge, pillar.x, pillar.y, phase.pillarCharge[i], beacon);
    }
  }

  // THE VANISH IS A SHEET, NOT A FADE, and it takes priority over the resting
  // loop the moment a player shuts the pad. It is drawn at FULL alpha on
  // purpose: `collapse.png` ends on an empty frame, so it disappears itself,
  // and multiplying `fade` over it would dim the implosion — the one frame the
  // whole timeline is built to arrive at — down to nothing.
  if (phase.collapsing >= 0) {
    ctx.globalAlpha = ANOMALY_GLOW;
    blitLevel(
      ctx, atlas.collapse, rift.anomalyX, rift.anomalyY, phase.collapsing, phase.level,
    );
    ctx.globalAlpha = 1;
  } else if (phase.open) {
    ctx.globalAlpha = ANOMALY_GLOW;
    blitLevel(
      ctx, atlas.rift, rift.anomalyX, rift.anomalyY, phase.anomalyTime, phase.level,
    );
    ctx.globalAlpha = 1;
  } else if (phase.emerging >= 0) {
    ctx.globalAlpha = ANOMALY_GLOW;
    blit(ctx, atlas.emerge, rift.anomalyX, rift.anomalyY, phase.emerging, beacon);
    ctx.globalAlpha = 1;
  }

  // The paid console's band. On the CONSOLE, not on the anomaly: it is the
  // thing that changed, and it is the thing the player has to walk back to.
  // Wall time rather than the pad's clock, so every armed console in a party's
  // night turns at the same rate instead of at its own age.
  if (phase.ready) {
    blit(ctx, atlas.aura, rift.consoleX, rift.consoleY, time, beacon);
  }
  ctx.restore();
}

/**
 * The colour of the light an anomaly of this tier puts in the air.
 *
 * Mint at rest and amber when it is gorged, mixed rather than switched so a
 * pad crossing a tier does not snap the whole clearing to a new colour.
 */
function haloTone(level: number): readonly [number, number, number] {
  const tone = palette().scene;
  const t = Math.max(0, Math.min(1, level / 3));
  const [cr, cg, cb] = tone.beacon;
  const [hr, hg, hb] = tone.ember;
  return [
    Math.round(cr + (hr - cr) * t),
    Math.round(cg + (hg - cg) * t),
    Math.round(cb + (hb - cb) * t),
  ];
}

/** Same blit, reading the overfeed tier's own bitmap instead of the tint. */
function blitLevel(
  ctx: CanvasRenderingContext2D,
  sheet: RiftEffectSheet | null,
  x: number,
  y: number,
  elapsed: number,
  level: number,
): void {
  if (!sheet) return;
  const frame = riftFrame(sheet, elapsed);
  ctx.drawImage(
    riftLevelImage(sheet, level),
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

function blit(
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
