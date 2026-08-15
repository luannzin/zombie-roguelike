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

import type { Rift } from '../../game/world';
import type { RiftTimingConfig } from '../../net/protocol';
import type { Camera } from '../camera';
import type { Projection } from '../projection';
import {
  riftFrame,
  riftImage,
  riftPropFrame,
  type RiftAtlas,
  type RiftEffectSheet,
} from '../rift';

/** Prop states. The index is the contract with `make_rift.py`. */
const DORMANT_FRAME = 0;
const AWAKE_FRAME = 1;

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
  emergeAt: 3.0,
  emergeTime: 1.25,
  openAt: 4.25,
  lightTiles: 3.5,
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
  /** Seconds into `emerge`, or `NOT_STARTED` before the tear begins. */
  emerging: number;
  /** The anomaly is on its resting loop. */
  open: boolean;
}

const DORMANT_PHASE: RiftPhase = {
  pillarCharge: [NOT_STARTED, NOT_STARTED, NOT_STARTED, NOT_STARTED],
  pillarAwake: [false, false, false, false],
  pillarCrowned: [false, false, false, false],
  consoleArmed: false,
  emerging: NOT_STARTED,
  open: false,
};

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
  if (rift.state === 'dormant') return DORMANT_PHASE;
  if (rift.state === 'open') {
    return {
      pillarCharge: [NOT_STARTED, NOT_STARTED, NOT_STARTED, NOT_STARTED],
      pillarAwake: [true, true, true, true],
      pillarCrowned: [true, true, true, true],
      consoleArmed: true,
      emerging: NOT_STARTED,
      open: true,
    };
  }

  const elapsed = rift.elapsed;
  const pillarCharge: number[] = [];
  const pillarAwake: boolean[] = [];
  const pillarCrowned: boolean[] = [];
  for (let i = 0; i < rift.pillars.length; i++) {
    const local = elapsed - (timing.consoleLag + i * timing.pillarStagger);
    const crowned = local >= timing.chargeTime;
    pillarCharge.push(local >= 0 && !crowned ? local : NOT_STARTED);
    pillarAwake.push(local >= timing.chargeTime * chargeHandoff);
    pillarCrowned.push(crowned);
  }

  const sinceTear = elapsed - timing.emergeAt;
  return {
    pillarCharge,
    pillarAwake,
    pillarCrowned,
    // The console answers the instant it is pressed. It is the one piece that
    // must not wait for anything: a button that visibly does nothing for a
    // third of a second reads as a button that did not take the press.
    consoleArmed: elapsed >= 0,
    emerging: sinceTear >= 0 && elapsed < timing.openAt ? sinceTear : NOT_STARTED,
    open: elapsed >= timing.openAt,
  };
}

/** How far into `charge` the sheet flashes. Falls back to the authored 0.55. */
export function chargeHandoff(atlas: RiftAtlas | null): number {
  return atlas?.charge?.handoffAt ?? 0.55;
}

export interface RiftStanding {
  sheet: 'pillar' | 'console';
  x: number;
  y: number;
  shape: number;
  state: number;
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
    state: phase.consoleArmed ? AWAKE_FRAME : DORMANT_FRAME,
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
  const sheet = piece.sheet === 'pillar' ? atlas.pillar : atlas.console;
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
  time: number,
  beacon: string,
): void {
  if (!atlas || !rift || rift.state === 'dormant') return;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';

  for (let i = 0; i < rift.pillars.length; i++) {
    const pillar = rift.pillars[i];
    if (phase.pillarCrowned[i]) {
      // The loop is driven by wall time, not by the sequence clock, so four
      // crowned stones breathe out of step with each other instead of pulsing
      // as one object.
      blit(ctx, atlas.crown, pillar.x, pillar.y, time + i * 0.37, beacon);
    } else if (phase.pillarCharge[i] >= 0) {
      blit(ctx, atlas.charge, pillar.x, pillar.y, phase.pillarCharge[i], beacon);
    }
  }

  if (phase.open) {
    blit(ctx, atlas.rift, rift.anomalyX, rift.anomalyY, time, beacon);
  } else if (phase.emerging >= 0) {
    blit(ctx, atlas.emerge, rift.anomalyX, rift.anomalyY, phase.emerging, beacon);
  }
  ctx.restore();
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
