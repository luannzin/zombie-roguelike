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
 * exactly as `tracks.png` is chosen by a compass heading. Every mark leans away
 * from the centre, which is why it reads as an explosion having passed rather
 * than as an area having been painted.
 *
 * IT IS BAKED, AND IT HAS TO BE.
 * The first version drew every visible corrupted tile every frame: at a normal
 * viewport that is ~500 tiles, doubled for the two blend modes, plus a second
 * full tile scan for the motes and a third pass over the residue — about 1300
 * canvas draw calls and two array allocations, sixty to a hundred and fifty
 * times a second. It cost about half the frame rate the moment the rift went
 * off, which is exactly what happened.
 *
 * But NONE OF IT MOVES. Once the front has passed a tile, that tile never
 * changes again. So the field is painted ONCE into a pair of offscreen
 * canvases — one per blend mode — and every later frame is two `drawImage`
 * calls of the visible sub-rectangle. The same trick `TerrainLayer` already
 * uses for the floor, for the same reason.
 *
 * While the wave is still travelling the bake is INCREMENTAL: the paint list is
 * sorted by distance from the blast, so each frame advances a cursor and paints
 * only the ring that was uncovered since the last one.
 */

import { createSurface } from '../../lib/canvas';
import type { TileMap } from '../../game/world';
import type { ResidueMark } from '../residue';
import type { Camera } from '../camera';
import type { RiftAtlas } from '../rift';

/**
 * How hard the damage half bites, at its strongest.
 *
 * Under `multiply` this is not coverage but DEPTH: at 1 the darkest fissure
 * pixels take the ground to near black, which is right for a crack and too
 * much for the blotches around it.
 */
const PEAK = 0.78;

/** And how hard the light half adds. Low: these are glints, not lamps. */
const LIT = 0.62;

/**
 * New tiles painted into the bake per frame while the wave is travelling.
 *
 * The list is distance-sorted, so a live boom only needs a handful per frame.
 * A join onto a spent rift would otherwise stamp every tile in one go (~3000
 * drawImage calls) and hitch. Spreading that over a few frames costs a brief
 * fill-in and keeps the frame that discovered the field cheap.
 */
const PAINT_BUDGET = 96;

/** Deterministic 0..1 per tile. Mirrors `hash01` in make_textures.py. */
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
 * same answer the floor did.
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
  // The per-tile roll makes the boundary a ragged fringe rather than an arc —
  // but it may only bite NEAR THE RIM. Applied evenly it speckles the middle
  // too, and rolled per tile that speckle is a visible checkerboard.
  const roll = hash01(tx, ty, seed | 0);
  return Math.max(0, shape * shape - roll * 0.75 * t * t);
}

/** One thing to paint into the bake, in world pixels. */
interface Paint {
  /** Distance from the blast centre. The list is sorted on this. */
  dist: number;
  frame: number;
  x: number;
  y: number;
  size: number;
  alpha: number;
  /** Residue is litter and sits ON the corrupted ground, so it paints later. */
  residue: boolean;
}

/** A speck of light over the field. Placed once, animated for free. */
interface Mote {
  x: number;
  y: number;
  dist: number;
  phase: number;
  drift: number;
  strength: number;
  color: string;
}

/** The prism, at mote size. Pale — these are specks of light, not gems. */
const MOTE_COLORS = ['#9ee4f8', '#96ffd4', '#d4bcff', '#ffc8dd', '#ffdf9c'];

/**
 * The blast's mark on the world, baked.
 *
 * Owned by the renderer, reset when the map changes. Holds two canvases the
 * size of the blast — at 34 tiles that is about 1088px square each, roughly
 * 9 MB for the pair, which is the price of not redrawing it a hundred and
 * fifty times a second.
 */
export class CorruptionField {
  private dark: HTMLCanvasElement | null = null;
  private lit: HTMLCanvasElement | null = null;
  private darkCtx: CanvasRenderingContext2D | null = null;
  private litCtx: CanvasRenderingContext2D | null = null;
  /** World pixel the canvases' top-left corner sits on. */
  private originX = 0;
  private originY = 0;
  private paints: Paint[] = [];
  private motes: Mote[] = [];
  /** How far down `paints` the bake has got. */
  private cursor = 0;
  private key = '';

  /** Throw the bake away. Call when the map changes. */
  reset(): void {
    if (!this.dark && this.key === '') return;
    this.dark = this.lit = null;
    this.darkCtx = this.litCtx = null;
    this.paints = [];
    this.motes = [];
    this.cursor = 0;
    this.key = '';
  }

  /**
   * Bring the bake up to `front`, then hand back whether there is anything
   * to draw. Cheap on every frame after the wave finishes: the cursor is at
   * the end of the list and this does nothing at all.
   */
  advance(
    atlas: RiftAtlas | null,
    world: TileMap,
    centre: { x: number; y: number },
    reach: number,
    front: number,
    marks: readonly ResidueMark[],
  ): boolean {
    const sheet = atlas?.corrupt;
    if (!sheet || reach <= 0 || front <= 0) return false;
    this.ensure(sheet, world, centre, reach, marks, atlas.residue?.frameWidth ?? 0);
    if (!this.darkCtx || !this.litCtx) return false;

    const residueSheet = atlas.residue;
    let painted = 0;
    while (
      this.cursor < this.paints.length
      && this.paints[this.cursor].dist <= front
      && painted < PAINT_BUDGET
    ) {
      const paint = this.paints[this.cursor++];
      painted++;
      const from = paint.residue ? residueSheet : sheet;
      if (!from) continue;
      const sx = paint.frame * from.frameWidth;
      const dx = paint.x - this.originX;
      const dy = paint.y - this.originY;
      // Painted `source-over` INTO the layer; the blend that matters is the one
      // the layer is blitted with. Compositing here and blending once at the
      // end is what makes the whole field two draw calls instead of two
      // thousand — overlapping marks compose a hair differently than they
      // would blended individually, which at these alphas is invisible.
      this.darkCtx.globalAlpha = paint.alpha;
      this.darkCtx.drawImage(
        from.image, sx, 0, from.frameWidth, from.frameHeight,
        dx, dy, paint.size, paint.size,
      );
      if (from.lit) {
        this.litCtx.globalAlpha = paint.alpha;
        this.litCtx.drawImage(
          from.lit, sx, 0, from.frameWidth, from.frameHeight,
          dx, dy, paint.size, paint.size,
        );
      }
    }
    return true;
  }

  /** Two blits of the visible sub-rectangle. World space, over the floor. */
  draw(ctx: CanvasRenderingContext2D, camera: Camera): void {
    if (!this.dark || !this.lit || this.cursor === 0) return;
    const left = Math.max(this.originX, Math.floor(camera.renderX));
    const top = Math.max(this.originY, Math.floor(camera.renderY));
    const right = Math.min(
      this.originX + this.dark.width, Math.ceil(camera.renderX + camera.viewWidth),
    );
    const bottom = Math.min(
      this.originY + this.dark.height, Math.ceil(camera.renderY + camera.viewHeight),
    );
    const w = right - left;
    const h = bottom - top;
    if (w <= 0 || h <= 0) return;

    const sx = left - this.originX;
    const sy = top - this.originY;
    ctx.save();
    ctx.globalCompositeOperation = 'multiply';
    ctx.globalAlpha = PEAK;
    ctx.drawImage(this.dark, sx, sy, w, h, left, top, w, h);
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = LIT;
    ctx.drawImage(this.lit, sx, sy, w, h, left, top, w, h);
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  /**
   * Motes over the field. Additive, after the darkness pass.
   *
   * The one part that cannot be baked, because it moves — so it is a flat list
   * placed once and culled to the camera, rather than the tile scan it used to
   * be. A few hundred cheap bounds checks instead of a full viewport sweep.
   */
  drawMotes(
    ctx: CanvasRenderingContext2D,
    tileSize: number,
    front: number,
    time: number,
    camera: Camera,
  ): void {
    if (this.motes.length === 0) return;
    const left = camera.renderX - tileSize;
    const top = camera.renderY - tileSize * 2;
    const right = camera.renderX + camera.viewWidth + tileSize;
    const bottom = camera.renderY + camera.viewHeight + tileSize;
    if (
      this.originX > right
      || this.originY > bottom
      || this.originX + (this.dark?.width ?? 0) < left
      || this.originY + (this.dark?.height ?? 0) < top
    ) {
      return;
    }

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    let color = '';
    for (const mote of this.motes) {
      if (mote.dist > front) continue;
      if (mote.x < left || mote.x > right || mote.y < top || mote.y > bottom) continue;
      // Rises, wraps, rises again: a sawtooth in height with a sine across, so
      // it wanders upward instead of bobbing on the spot.
      const climb = (time * 0.22 + mote.drift) % 1;
      const mx = mote.x + Math.sin(mote.phase + time * 0.8) * tileSize * 0.3;
      const my = mote.y - climb * tileSize * 1.6;
      // Brightest mid-climb: it fades in off the ground and out into the air.
      if (mote.color !== color) {
        color = mote.color;
        ctx.fillStyle = color;
      }
      ctx.globalAlpha = Math.sin(climb * Math.PI) * 0.5 * mote.strength;
      ctx.fillRect(Math.round(mx), Math.round(my), 1, 1);
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  /**
   * Allocate the canvases and work out every paint, once.
   *
   * The list is sorted by distance so the wave can be painted as a widening
   * cursor. Residue sorts a hair behind the tile it lands on (`+0.5`) so litter
   * always lands ON the corrupted ground rather than under it.
   */
  private ensure(
    sheet: NonNullable<RiftAtlas['corrupt']>,
    world: TileMap,
    centre: { x: number; y: number },
    reach: number,
    marks: readonly ResidueMark[],
    residue: number,
  ): void {
    const key = `${world.seed}:${centre.x}:${centre.y}:${reach}:${marks.length}:${residue}`;
    if (this.key === key) return;
    this.key = key;
    this.cursor = 0;

    const tile = world.tileSize;
    this.originX = Math.floor((centre.x - reach) / tile) * tile;
    this.originY = Math.floor((centre.y - reach) / tile) * tile;
    const span = Math.ceil((reach * 2) / tile) * tile + tile;

    const dark = createSurface(span, span, 'corruption/dark');
    const lit = createSurface(span, span, 'corruption/lit');
    this.dark = dark.canvas;
    this.lit = lit.canvas;
    this.darkCtx = dark.ctx;
    this.litCtx = lit.ctx;

    const paints: Paint[] = [];
    const motes: Mote[] = [];
    const minTx = Math.floor(this.originX / tile);
    const minTy = Math.floor(this.originY / tile);
    const tiles = Math.ceil(span / tile);
    for (let iy = 0; iy < tiles; iy++) {
      for (let ix = 0; ix < tiles; ix++) {
        const tx = minTx + ix;
        const ty = minTy + iy;
        if (tx < 0 || ty < 0 || tx >= world.width || ty >= world.height) continue;
        const strength = corruptionAt(world.seed, centre.x, centre.y, reach, tx, ty, tile);
        if (strength <= 0.04) continue;
        const dx = (tx + 0.5) * tile - centre.x;
        const dy = (ty + 0.5) * tile - centre.y;
        const dist = Math.hypot(dx, dy);
        if (dist > reach) continue;

        // Same heading convention as `tracks.png`: angle 0 is +y (down the
        // screen), so a direction of (dx, dy) is `atan2(dx, dy)`. Backwards
        // here points every mark at the crater instead of away from it.
        const dir =
          ((Math.round((Math.atan2(dx, dy) / (Math.PI * 2)) * sheet.directions) %
            sheet.directions) + sheet.directions) % sheet.directions;
        const level = strength > 0.66 ? 0 : strength > 0.33 ? 1 : 2;
        const roll = Math.floor(hash01(tx, ty, 31) * sheet.rolls) % sheet.rolls;
        paints.push({
          dist,
          frame: ((dir * sheet.levels + level) * sheet.rolls + roll) % sheet.frames,
          x: tx * tile,
          y: ty * tile,
          size: tile,
          alpha: Math.min(1, 0.45 + strength * 0.55),
          residue: false,
        });

        // Roughly one tile in twelve carries a mote. Any denser and the field
        // sparkles like snow, which is charming and completely wrong — and the
        // leftover fillRects start to show up in the frame.
        if (hash01(tx, ty, 517) <= 0.08 && strength > 0.15) {
          motes.push({
            x: (tx + 0.5) * tile,
            y: (ty + 1) * tile,
            dist,
            phase: hash01(tx, ty, 733) * Math.PI * 2,
            drift: hash01(tx, ty, 191),
            strength,
            color: MOTE_COLORS[Math.floor(hash01(tx, ty, 61) * MOTE_COLORS.length)
              % MOTE_COLORS.length],
          });
        }
      }
    }

    for (const mark of marks) {
      if (residue <= 0) break;
      paints.push({
        dist: mark.dist + 0.5,
        frame: mark.variant,
        x: Math.round(mark.x - residue / 2),
        y: Math.round(mark.y - residue / 2),
        size: residue,
        alpha: 0.42 - mark.falloff * 0.24,
        residue: true,
      });
    }
    paints.sort((a, b) => a.dist - b.dist);
    // Same colour consecutive so the draw loop changes fillStyle a handful of
    // times instead of once per speck.
    motes.sort((a, b) => (a.color < b.color ? -1 : a.color > b.color ? 1 : 0));
    this.paints = paints;
    this.motes = motes;
  }
}
