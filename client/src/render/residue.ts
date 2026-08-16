/**
 * What the anomaly threw across the ground, and where.
 *
 * NOT ON THE WIRE. The blast lays hundreds of marks, and sending hundreds of
 * positions for something nobody can interact with would be the largest
 * message in the game for the least gameplay. Instead both the WHERE and the
 * WHICH are derived from `world.seed` hashed with the rift's own tile — the
 * same trick the forest already uses for grass, prop variants and soil, and
 * for the same reason: one number on the wire, an identical field everywhere.
 *
 * The server only ever says the rift went off. Every client agrees on the
 * result because they all agree on the seed.
 *
 * THE MARKS ARE ORDERED BY DISTANCE from the centre, which is what lets the
 * shockwave reveal them: the wave is a radius growing with time, and the marks
 * inside it are simply the ones already laid. A binary search would be
 * overkill for a few hundred — the draw loop stops at the first one the wave
 * has not reached yet.
 */

import type { Rift } from '../game/world';

export interface ResidueMark {
  x: number;
  y: number;
  /** Frame on the residue sheet. Chosen by distance — see `variantFor`. */
  variant: number;
  /** Distance from the blast centre in world px; the wave reveals in this order. */
  dist: number;
  /** 0..1 of the blast's reach. Drives how faint the mark settles. */
  falloff: number;
}

/**
 * Marks per tile of area. LOW, and it has to be.
 *
 * These are litter, not a texture. At 1.35 the ground vanished under them and
 * the field read as decoration somebody placed — the marks were legible as
 * individual stickers, which is exactly what they must not be. The thing that
 * changes the GROUND is `layers/corruption.ts`; this is the debris on top of
 * it, and debris is sparse or it stops being debris.
 */
const DENSITY = 0.16;

/**
 * Nothing lands within this of the centre, in world px.
 *
 * The structure's own sigil is already there, and it is the busiest art on the
 * map. Piling the densest residue on top of it buried the one piece that says
 * what this place IS — so the blast leaves the pad alone and starts marking
 * outside it. It also matches how a shock front behaves: the middle is where
 * the thing still is, not where its debris settles.
 */
const CLEAR_RADIUS = 56;

/** Deterministic 0..1 from integers. Mirrors `hash01` in make_textures.py. */
function hash01(a: number, b: number, c: number): number {
  let h = 2166136261 >>> 0;
  for (const value of [a | 0, b | 0, c | 0]) {
    h = (h ^ (value & 0xffff)) >>> 0;
    h = Math.imul(h, 16777619) >>> 0;
    h = (h ^ (value >>> 16)) >>> 0;
    h = Math.imul(h, 16777619) >>> 0;
  }
  h = (h ^ (h >>> 15)) >>> 0;
  h = Math.imul(h, 2246822507) >>> 0;
  h = (h ^ (h >>> 13)) >>> 0;
  return (h >>> 8) / 16777216;
}

/**
 * Which cut belongs at this distance. Mirrors `residue_variant` in
 * `server/tools/make_rift.py`, where the art's own falloff is authored: dense
 * knots in the middle, bare dust at the rim, so a field of these reads as one
 * event fading outward instead of as confetti.
 */
function variantFor(falloff: number): number {
  if (falloff < 0.22) return 4;
  if (falloff < 0.42) return 1;
  if (falloff < 0.6) return 3;
  if (falloff < 0.78) return 2;
  if (falloff < 0.92) return 0;
  return 5;
}

/**
 * Every mark the blast lays, nearest first.
 *
 * Rejection-sampled on a disc rather than laid on a grid: a grid shows through
 * as rows the moment the density drops, and the whole illusion is that
 * something was thrown rather than placed.
 */
export function riftResidue(seed: number, rift: Rift, reach: number): ResidueMark[] {
  const marks: ResidueMark[] = [];
  const area = Math.PI * reach * reach;
  const tile = 16;
  const target = Math.round((area / (tile * tile)) * DENSITY);
  const salt = (seed ^ ((rift.x | 0) * 73856093) ^ ((rift.y | 0) * 19349663)) | 0;

  for (let i = 0; i < target; i++) {
    // sqrt keeps the sample uniform over AREA; without it everything piles
    // into the middle and the rim is bare.
    const radius = Math.sqrt(hash01(i, 1, salt)) * reach;
    const angle = hash01(i, 2, salt) * Math.PI * 2;
    if (radius < CLEAR_RADIUS) continue;
    const falloff = radius / reach;
    // Thin with distance ON TOP of the uniform sample, so the near ground is
    // the busiest and the edge trails off instead of stopping.
    if (hash01(i, 3, salt) > 1.0 - falloff * 0.72) continue;
    marks.push({
      x: rift.x + Math.cos(angle) * radius,
      y: rift.y + Math.sin(angle) * radius,
      variant: variantFor(falloff),
      dist: radius,
      falloff,
    });
  }
  marks.sort((a, b) => a.dist - b.dist);
  return marks;
}
