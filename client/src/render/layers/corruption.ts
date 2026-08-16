/**
 * What the blast did to the GROUND, and the air over it.
 *
 * The residue decals are litter — things the anomaly threw. This is the other
 * half and the bigger one: the soil itself is replaced where the front went
 * through, so the clearing does not merely acquire debris, it becomes
 * somewhere else.
 *
 * IT IS A DRAWN TEXTURE, NOT A TINT. This started as a per-tile colour fill and
 * it was wrong twice over — a flat fill has no detail, so at any zoom it is a
 * coloured rectangle, and rolling the hue per tile made the field a patchwork
 * of unrelated colours. The sheet (`make_corrupt` in make_rift.py) draws
 * cracks, drained blotches, grit and a little crystal on ground that has been
 * DRAINED rather than dyed; the prism only survives in the crystal and along
 * one lip of each crack.
 *
 * AND IT IS AIMED. The blast came out of one point and dragged everything
 * outward, so the frame is chosen by the tile's DIRECTION from that point,
 * exactly as `tracks.png` is chosen by a compass heading. Every mark on the
 * field leans away from the centre, which is the whole reason it reads as an
 * explosion having passed rather than as an area having been painted.
 *
 * WHY A WASH PASS AND NOT A RE-BAKE
 * `TerrainLayer` bakes the ground once. Re-baking on the burst would be truest
 * and would also mean rebuilding the whole map's floor mid-frame, on a machine
 * already drawing an explosion. This is one `drawImage` per visible corrupted
 * tile, culled to the camera — the cost is the screen, not the map.
 */

import type { TileMap } from '../../game/world';
import type { Camera } from '../camera';
import type { RiftAtlas } from '../rift';

/** Strongest coverage at the centre. The soil underneath still reads through. */
const PEAK = 0.92;

/** Deterministic 0..1 per tile. Mirrors the residue field's hash. */
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
 * How contaminated a tile is, 0..1, for a blast of `reach` world px.
 *
 * Exported because anything else that wants to answer "was this ground got
 * at?" — the trees standing on it, a future ambience trigger — has to get the
 * same answer as the floor did.
 */
export function corruptionAt(
  seed: number,
  cx: number,
  cy: number,
  reach: number,
  tx: number,
  ty: number,
  tileSize: number,
): number {
  const dx = (tx + 0.5) * tileSize - cx;
  const dy = (ty + 0.5) * tileSize - cy;
  const dist = Math.hypot(dx, dy);
  if (dist >= reach) return 0;
  // Flat through the middle, then a long shoulder to nothing. A linear falloff
  // is a visible cone; this holds the near ground fully changed and spends the
  // outer half disappearing.
  const t = dist / reach;
  const shape = t < 0.45 ? 1 : 1 - (t - 0.45) / 0.55;
  // The per-tile roll makes the boundary a ragged fringe of stained tiles
  // rather than an arc — but it may only bite NEAR THE RIM. Applied evenly it
  // speckles the middle too, and rolled per tile that speckle is a visible
  // checkerboard: the one artifact that gives away a grid of fills.
  const roll = hash01(tx, ty, seed | 0);
  return Math.max(0, shape * shape - roll * 0.75 * t * t);
}

/**
 * Lay the corrupted ground. World space, over the baked floor, under
 * everything that stands on it.
 *
 * `waveRadius` is how far the front has travelled, so the ground changes WITH
 * the wave: tiles ahead of it are still clean forest. Once the boom is over it
 * is `Infinity` and the whole field is simply there.
 */
export function drawCorruption(
  ctx: CanvasRenderingContext2D,
  atlas: RiftAtlas | null,
  world: TileMap,
  centre: { x: number; y: number },
  reach: number,
  waveRadius: number,
  camera: Camera,
): void {
  const sheet = atlas?.corrupt;
  if (!sheet || waveRadius <= 0 || reach <= 0) return;
  const tile = world.tileSize;
  const front = Math.min(waveRadius, reach);

  // Only the tiles that are BOTH on screen and inside the front.
  const left = Math.max(0, Math.floor(Math.max(camera.renderX, centre.x - front) / tile));
  const top = Math.max(0, Math.floor(Math.max(camera.renderY, centre.y - front) / tile));
  const right = Math.min(
    world.width - 1,
    Math.ceil(Math.min(camera.renderX + camera.viewWidth, centre.x + front) / tile),
  );
  const bottom = Math.min(
    world.height - 1,
    Math.ceil(Math.min(camera.renderY + camera.viewHeight, centre.y + front) / tile),
  );

  for (let ty = top; ty <= bottom; ty++) {
    for (let tx = left; tx <= right; tx++) {
      const strength = corruptionAt(world.seed, centre.x, centre.y, reach, tx, ty, tile);
      if (strength <= 0.04) continue;
      const dx = (tx + 0.5) * tile - centre.x;
      const dy = (ty + 0.5) * tile - centre.y;
      if (Math.hypot(dx, dy) > front) continue;

      // Same heading convention as `tracks.png`: angle 0 is +y (down the
      // screen), so a direction of (dx, dy) is `atan2(dx, dy)`. Getting this
      // backwards points every mark at the crater instead of away from it.
      const dir =
        ((Math.round((Math.atan2(dx, dy) / (Math.PI * 2)) * sheet.directions) %
          sheet.directions) + sheet.directions) % sheet.directions;
      const level = strength > 0.66 ? 0 : strength > 0.33 ? 1 : 2;
      const roll = Math.floor(hash01(tx, ty, 31) * sheet.rolls) % sheet.rolls;
      const frame = ((dir * sheet.levels + level) * sheet.rolls + roll) % sheet.frames;

      ctx.globalAlpha = Math.min(1, 0.45 + strength * 0.55) * PEAK;
      ctx.drawImage(
        sheet.image,
        frame * sheet.frameWidth,
        0,
        sheet.frameWidth,
        sheet.frameHeight,
        tx * tile,
        ty * tile,
        tile,
        tile,
      );
    }
  }
  ctx.globalAlpha = 1;
}

/**
 * Motes hanging over the corrupted ground. Additive, after the darkness pass.
 *
 * The last piece of the illusion, and the cheapest: a few dozen specks that
 * drift and wink, placed and animated entirely from the tile hash so nothing is
 * stored and nothing is simulated. Still ground that has been changed is a
 * picture; ground with something coming off it is a place that is still wrong.
 *
 * Only ever drawn for tiles ON SCREEN, so the count is the viewport's, not the
 * blast's.
 */
export function drawCorruptionMotes(
  ctx: CanvasRenderingContext2D,
  world: TileMap,
  centre: { x: number; y: number },
  reach: number,
  waveRadius: number,
  time: number,
  camera: Camera,
): void {
  if (waveRadius <= 0 || reach <= 0) return;
  const tile = world.tileSize;
  const front = Math.min(waveRadius, reach);
  const left = Math.max(0, Math.floor(Math.max(camera.renderX, centre.x - front) / tile));
  const top = Math.max(0, Math.floor(Math.max(camera.renderY, centre.y - front) / tile));
  const right = Math.min(
    world.width - 1,
    Math.ceil(Math.min(camera.renderX + camera.viewWidth, centre.x + front) / tile),
  );
  const bottom = Math.min(
    world.height - 1,
    Math.ceil(Math.min(camera.renderY + camera.viewHeight, centre.y + front) / tile),
  );

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let ty = top; ty <= bottom; ty++) {
    for (let tx = left; tx <= right; tx++) {
      // Roughly one tile in seven carries a mote. Any denser and the field
      // sparkles like snow, which is charming and completely wrong.
      const pick = hash01(tx, ty, 517);
      const strength = corruptionAt(world.seed, centre.x, centre.y, reach, tx, ty, tile);
      if (pick > 0.14 || strength <= 0.15) continue;
      const dx = (tx + 0.5) * tile - centre.x;
      const dy = (ty + 0.5) * tile - centre.y;
      if (Math.hypot(dx, dy) > front) continue;

      const phase = hash01(tx, ty, 733) * Math.PI * 2;
      // Rises, wraps, rises again — a sawtooth in height and a sine across, so
      // it wanders up rather than bobbing on the spot.
      const climb = ((time * 0.22 + hash01(tx, ty, 191)) % 1);
      const mx = (tx + 0.5) * tile + Math.sin(phase + time * 0.8) * tile * 0.3;
      const my = (ty + 1) * tile - climb * tile * 1.6;
      // Brightest mid-climb: it fades in off the ground and out into the air.
      const life = Math.sin(climb * Math.PI);
      ctx.globalAlpha = life * 0.5 * strength;
      ctx.fillStyle = MOTE[Math.floor(hash01(tx, ty, 61) * MOTE.length) % MOTE.length];
      ctx.fillRect(Math.round(mx), Math.round(my), 1, 1);
    }
  }
  ctx.restore();
}

/** The prism, at mote size. Pale — these are specks of light, not gems. */
const MOTE = ['#9ee4f8', '#96ffd4', '#d4bcff', '#ffc8dd', '#ffdf9c'];
