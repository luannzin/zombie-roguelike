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

import { palette } from "../../theme/palette";
import { type Grade, type GradeLayer, NEUTRAL } from "./grade";

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
		exposure: 0.98,
		shoulder: 0.55,
		contrast: 1.12,
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
 * The camp before a run, and the title screen behind the menu.
 *
 * IT IS THE FOREST GRADE, EXACTLY. It used to be its own softer look — warmer,
 * a touch brighter, the frame opened up — on the argument that the camp is the
 * safe beat and should not wear the night the run does. What that actually did
 * was make the FIRST thing a player ever sees a different game to the one they
 * are about to play: the fire, the trees and the grass in the clearing are the
 * same art the forest is drawn from, and grading them warm made the handover
 * out of the lobby a visible cut in colour on the frame the camera push was
 * built to hide. The camp is a clearing in the same woods at the same hour;
 * it looks like it. What says "safe" here is the fire and the absence of
 * anything walking toward it, not a two-percent lift in exposure.
 *
 * The shop keeps its own look — that one is INDOORS and warm for a reason
 * (see `shopLook`), and the walk into it is meant to read as a change of
 * place.
 */
export function campLook(): Grade {
	return forestLook();
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
/**
 * THE LANDING, on a boss night. The forest grade with the temperature taken
 * off it and the contrast pushed.
 *
 * It is deliberately a SMALL move from `forestLook`, and the small move is the
 * whole point. The yard is the same woods at the same hour — the party walked
 * there down a corridor — so a look that announced itself would say "a
 * different game starts here", which is the thing a boss arena in a run like
 * this must not say. What changes is what the FIRES change: nine burning drums
 * is the most light this game has ever put in one place, so the cool cast the
 * forest wears comes off, the shoulder opens to let those fires actually
 * bloom, and the vignette closes a notch because the place is a RING and the
 * frame should feel like one.
 *
 * Saturation goes DOWN, not up. Everything about to happen in this room is
 * loud on its own; a grade that shouted with it would leave the enrage — the
 * one moment that is supposed to change how the room looks — with nowhere
 * left to go.
 */
export function arenaLook(): Grade {
	return base({
		exposure: 1.0,
		shoulder: 0.62,
		contrast: 1.2,
		saturation: 0.88,
		temperature: -0.04,
		tint: 0.03,
		lift: [-0.016, -0.008, 0.008],
		gamma: [1.0, 0.99, 0.97],
		gain: [1.06, 1.0, 0.93],
		bloom: 0.68,
		bloomThreshold: 0.66,
		shafts: 0.42,
		fog: 0.08,
		fogTint: palette().grade.fogForest,
		aberration: 0.55,
		blur: 0,
		focus: 0.75,
		vignette: 0.38,
		vignetteSoft: 0.58,
		vignetteTint: palette().grade.vignette,
		grain: 0.03,
	});
}

export function lookFor(zone: string | undefined): Grade {
	if (zone === "camp") return campLook();
	if (zone === "store") return shopLook();
	if (zone === "arena") return arenaLook();
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
 * It used to be the one look allowed to be loud, and loud meant bloom at 1.4
 * with the threshold dragged down to 0.5 — a grade that took anything already
 * bright and made it white. Over a pad that was ALSO drawing four additive
 * glare sheets and a halo, the three multiplied and the clearing came out as
 * one flat hole. The other two are gone (see `layers/rift.ts`); this one
 * keeps its job and loses its ceiling.
 *
 * WHAT IT STILL DOES is the part that was never the problem: the frame goes
 * colder and cleaner as the machines come in, because the thing arriving is a
 * machine and everything else on the map is a forest. Colour and contrast say
 * that. Exposure and bloom only ever said it LOUDER.
 */
export function extractionLook(intensity: number): GradeLayer {
	const t = Math.max(0, Math.min(1, intensity));
	return {
		exposure: 1.02 + 0.05 * t,
		shoulder: 0.55 + 0.25 * t,
		contrast: 1.1 + 0.06 * t,
		saturation: 0.92 + 0.14 * t,
		temperature: -0.16 - 0.14 * t,
		gain: [1.03 - 0.02 * t, 1.0 + 0.01 * t, 0.96 + 0.1 * t],
		bloom: 0.55 + 0.2 * t,
		bloomThreshold: 0.72 - 0.06 * t,
		shafts: 0.35 + 0.2 * t,
		fog: 0.05 + 0.1 * t,
		fogTint: palette().scene.beacon,
		aberration: 0.4 + 1.1 * t,
		vignette: 0.3 - 0.08 * t,
	};
}

/**
 * PAST HALF. He roars, and the room goes with him.
 *
 * A held layer for the rest of the fight rather than a flash, because it is
 * describing a STATE — the fight has changed and stays changed. Everything in
 * it moves one way: hotter, harder, tighter. It is the only look in the game
 * that pushes red gain past 1.1, and it can afford to because `arenaLook`
 * deliberately left room for it (see there).
 */
export function enrageLook(intensity: number): GradeLayer {
	const t = Math.max(0, Math.min(1, intensity));
	return {
		exposure: 1.0 + 0.03 * t,
		contrast: 1.2 + 0.1 * t,
		saturation: 0.88 + 0.16 * t,
		temperature: -0.04 + 0.2 * t,
		gain: [1.06 + 0.14 * t, 1.0 - 0.04 * t, 0.93 - 0.08 * t],
		bloom: 0.68 + 0.16 * t,
		bloomThreshold: 0.66 - 0.08 * t,
		aberration: 0.55 + 0.9 * t,
		vignette: 0.38 + 0.14 * t,
		grain: 0.03 + 0.02 * t,
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

/**
 * DOWN, and possibly for good.
 *
 * `deathLook` was written for a death that cost two seconds, and it is still
 * right for one — a body knifed at the merchant's counter is coming back. A
 * body down in a hostile zone is not on a timer: nothing stands it up but the
 * party reaching the next zone, and if nobody is left to get them there the
 * run is over. So this is the same photograph pushed a long way further down:
 * darker, flatter, almost no colour left, and the vignette closed to a hole.
 *
 * IT IS NOT BLACK, and the gap between this and `wipeLook` is the whole point.
 * A downed player in a party can still SEE — their teammate working the
 * clearing, the pack drifting off them, the pad two screens away — and that
 * view is the entire experience of being down. Taking the picture away would
 * turn the most tense minute in a co-op run into a loading screen.
 */
export function downedLook(): GradeLayer {
	return {
		exposure: 0.5,
		contrast: 1.34,
		saturation: 0.05,
		blur: 0.72,
		focus: 0.22,
		vignette: 0.82,
		vignetteSoft: 0.3,
		vignetteTint: palette().grade.vignette,
		grain: 0.1,
		bloom: 0.22,
	};
}

/**
 * THE RUN IS OVER. The world goes out from under the card.
 *
 * Everything on the floor: no exposure, no colour, no bloom to give a shape
 * back. What is left underneath the death card is a black frame with grain on
 * it, which is the point — the card is the only thing on screen, and it is not
 * competing with a forest still visible behind it.
 *
 * The grain stays deliberately. A perfectly flat black reads as the renderer
 * having stopped rather than as an ending, and the difference between "the
 * game crashed" and "you died" is worth one float.
 */
export function wipeLook(): GradeLayer {
	return {
		exposure: 0.0,
		contrast: 1.5,
		saturation: 0.0,
		blur: 1.0,
		focus: 0.0,
		vignette: 1.0,
		vignetteSoft: 0.16,
		vignetteTint: palette().grade.vignette,
		grain: 0.14,
		bloom: 0.0,
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
