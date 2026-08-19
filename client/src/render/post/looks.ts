/**
 * The looks: every grade this game ever wears, in one place.
 *
 * Two kinds live here and they are not interchangeable.
 *
 *   PLACE  a full `Grade`, handed to `GradeStack.setBase`. It answers "what
 *          does this map look like" and it crossfades when the party moves.
 *   EVENT  a `GradeLayer` — a partial — pushed on top for as long as the event
 *          lasts. It answers "what is happening to the picture right now" and
 *          it says nothing about the fields it does not name, so a hit taken in
 *          the shop still reads as the shop.
 *
 * They are FUNCTIONS, not constants, because every colour in them comes off
 * `index.css` through `palette()`, which resolves lazily on the first frame.
 * Freezing them at import time would bake in whatever the stylesheet had not
 * finished loading yet.
 *
 * THE NUMBERS ARE SMALL ON PURPOSE. Nothing in this file is meant to be
 * noticed on its own — the base looks sit within a few percent of neutral and
 * the events rarely go past a third of the way to their own extreme. A grade
 * the player can point at is a filter; a grade they cannot is a look.
 */

import { palette } from '../../theme/palette';
import { NEUTRAL, type Grade, type GradeLayer } from './grade';

function base(over: GradeLayer): Grade {
  return { ...NEUTRAL, ...over };
}

// --- places -----------------------------------------------------------------

/**
 * The hostile forest at night, and the default for anywhere unnamed.
 *
 * Cold, slightly crushed and desaturated, with the highlights left warm so the
 * only saturated things on screen are the things that are burning. That split
 * is the whole look: the night is teal and every light in it is orange, which
 * is what makes a distant campfire read as somewhere to go.
 */
export function forestLook(): Grade {
  return base({
    exposure: 1.02,
    shoulder: 0.55,
    contrast: 1.1,
    saturation: 0.92,
    temperature: -0.16,
    tint: 0.02,
    lift: [-0.012, -0.004, 0.014],
    gamma: [1.0, 1.0, 0.98],
    gain: [1.03, 1.0, 0.96],
    bloom: 0.55,
    bloomThreshold: 0.72,
    shafts: 0.35,
    fog: 0.05,
    fogTint: palette().grade.fogForest,
    aberration: 0.4,
    blur: 0,
    focus: 0.75,
    vignette: 0.3,
    vignetteSoft: 0.62,
    vignetteTint: palette().grade.vignette,
    grain: 0.028,
  });
}

/**
 * The camp before a run. The same forest with the threat taken out of it:
 * warmer, a touch brighter, and the frame opened up.
 */
export function campLook(): Grade {
  return base({
    exposure: 1.04,
    shoulder: 0.5,
    contrast: 1.06,
    saturation: 0.96,
    temperature: -0.06,
    lift: [0.006, 0.002, 0.01],
    gain: [1.02, 1.0, 0.99],
    bloom: 0.5,
    bloomThreshold: 0.74,
    shafts: 0.3,
    fog: 0.04,
    fogTint: palette().grade.fogCamp,
    aberration: 0.25,
    focus: 0.85,
    vignette: 0.2,
    vignetteSoft: 0.7,
    vignetteTint: palette().grade.vignette,
    grain: 0.024,
  });
}

/**
 * The merchant's clearing. The one warm place in the game, and the only look
 * that goes past neutral on saturation — money should feel good.
 */
export function shopLook(): Grade {
  return base({
    exposure: 1.06,
    shoulder: 0.6,
    contrast: 1.04,
    saturation: 1.06,
    temperature: 0.2,
    tint: 0.03,
    lift: [0.014, 0.006, -0.004],
    gamma: [1.0, 0.99, 0.97],
    gain: [1.05, 1.0, 0.93],
    bloom: 0.6,
    bloomThreshold: 0.68,
    shafts: 0.42,
    fog: 0.06,
    fogTint: palette().grade.fogShop,
    aberration: 0.2,
    focus: 0.8,
    vignette: 0.22,
    vignetteSoft: 0.72,
    vignetteTint: palette().grade.vignette,
    grain: 0.022,
  });
}

/** Which place a zone kind is. Anything unrecognised is the forest. */
export function lookFor(zone: string | undefined): Grade {
  if (zone === 'camp') return campLook();
  if (zone === 'store') return shopLook();
  return forestLook();
}

// --- events -----------------------------------------------------------------

/**
 * Low health, held while it lasts and scaled by how bad it is.
 *
 * The vignette closes, the colour drains, and the lens starts to come apart at
 * the edges. It replaces the old 2D danger vignette entirely: same read, but
 * it is now one layer in the same stack as everything else, so it composes
 * with an extraction instead of being painted over the top of one.
 */
export function dangerLook(level: number, pulse: number): GradeLayer {
  const heat = level * (0.72 + 0.28 * pulse);
  return {
    exposure: 1 - 0.06 * heat,
    contrast: 1.1 + 0.16 * heat,
    saturation: 0.92 - 0.34 * heat,
    temperature: -0.16 + 0.3 * heat,
    lift: [0.02 * heat, -0.01 * heat, -0.012 * heat],
    vignette: 0.3 + 0.42 * heat,
    vignetteSoft: 0.62 - 0.26 * heat,
    vignetteTint: palette().grade.washBlood,
    aberration: 0.4 + 2.0 * heat,
    grain: 0.028 + 0.03 * heat,
    fog: 0.05 + 0.05 * heat,
  };
}

/** A round landing on the player. Short, hard, and gone. */
export function hitLook(severity: number): GradeLayer {
  return {
    wash: 0.1 + 0.16 * severity,
    washTint: palette().grade.washBlood,
    exposure: 1 - 0.1 * severity,
    aberration: 1.6 + 3.4 * severity,
    saturation: 0.75,
    vignette: 0.42 + 0.2 * severity,
  };
}

/**
 * The extraction ceremony, driven 0..1 by the pad's own phase.
 *
 * This is the one look allowed to be loud. The exposure climbs, the bloom
 * opens, the shafts come up out of the rig's lights and cut through the trees,
 * and the whole frame goes a shade colder and cleaner — because the thing
 * arriving is a machine and everything else on the map is a forest.
 */
export function extractionLook(intensity: number): GradeLayer {
  const t = Math.max(0, Math.min(1, intensity));
  return {
    exposure: 1.02 + 0.2 * t,
    shoulder: 0.55 + 0.25 * t,
    contrast: 1.1 + 0.06 * t,
    saturation: 0.92 + 0.14 * t,
    temperature: -0.16 - 0.14 * t,
    gain: [1.03 - 0.02 * t, 1.0 + 0.01 * t, 0.96 + 0.1 * t],
    bloom: 0.55 + 0.85 * t,
    bloomThreshold: 0.72 - 0.22 * t,
    shafts: 0.35 + 1.05 * t,
    fog: 0.05 + 0.1 * t,
    fogTint: palette().scene.beacon,
    aberration: 0.4 + 1.1 * t,
    vignette: 0.3 - 0.08 * t,
  };
}

/** The payout: the night turning into money. Gold, warm, brief. */
export function payoutLook(intensity: number): GradeLayer {
  const t = Math.max(0, Math.min(1, intensity));
  return {
    exposure: 1.06 + 0.14 * t,
    saturation: 1.06 + 0.18 * t,
    temperature: 0.2 + 0.22 * t,
    bloom: 0.6 + 0.6 * t,
    bloomThreshold: 0.68 - 0.16 * t,
    shafts: 0.42 + 0.5 * t,
    vignette: 0.22 - 0.06 * t,
  };
}

/** Levelling, and anything else that is a good thing happening at a point. */
export function surgeLook(): GradeLayer {
  return {
    exposure: 1.16,
    bloom: 1.25,
    bloomThreshold: 0.55,
    saturation: 1.14,
    wash: 0.07,
    washTint: palette().grade.washFlash,
  };
}

/**
 * Down the scope. The ONE place depth of field is allowed to be obvious: the
 * frame narrows to what the gun is pointed at and the forest around it goes
 * soft. Held while the trigger is down, released the moment it is not.
 */
export function scopeLook(intensity: number): GradeLayer {
  const t = Math.max(0, Math.min(1, intensity));
  return {
    blur: 0.75 * t,
    focus: 0.75 - 0.5 * t,
    aberration: 0.4 + 0.8 * t,
    vignette: 0.3 + 0.26 * t,
    vignetteSoft: 0.62 - 0.2 * t,
    saturation: 0.92 - 0.08 * t,
  };
}

/** Dead. The picture stops being a place and becomes a photograph of one. */
export function deathLook(): GradeLayer {
  return {
    exposure: 0.78,
    contrast: 1.24,
    saturation: 0.12,
    blur: 0.5,
    focus: 0.3,
    vignette: 0.68,
    vignetteSoft: 0.4,
    vignetteTint: palette().grade.vignette,
    grain: 0.06,
    bloom: 0.3,
  };
}
