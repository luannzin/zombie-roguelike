/**
 * HUD minimap: cached tile bitmap, fog overlay, live dots.
 *
 * Colours come from `theme/palette`, the same source the main renderer uses, so
 * the two views can never drift apart.
 *
 * The minimap obeys the same vision the world does. Ground nobody has walked
 * into is covered; ground the team has seen but cannot see now is dimmed to a
 * memory; and an enemy dot only appears where somebody currently has light on
 * it. Teammates are always shown — they are your team, you know where they are,
 * and the whole point of shared vision is that their light is your light.
 *
 * EXTRACTION POINTS ARE ON IT, and they obey a different rule from an enemy for
 * the same reason a teammate does: what the party KNOWS is not what the party
 * can currently see. A dormant pad has to be found, so it appears once somebody
 * has explored its ground and then stays. A pad that is awake appears whatever
 * the fog says — it is a beacon burning in a dark forest and there is nobody on
 * the map it is a secret from. A spent one keeps a dead mark, because the whole
 * point of a spent pad is that the map remembers.
 *
 * Visibility of the canvas itself is NOT managed here — the React HUD decides
 * whether to mount it. This class only owns pixels.
 */

import { FLOOR, TILEFLOOR, TREE, VOID, type Rift, type TileMap } from '../game/world';
import { createSurface, get2d } from '../lib/canvas';
import { floorColor, palette } from '../theme/palette';
import type { FovField } from './fov';

const MAX_SIDE = 160;
/**
 * Minimum ms between repaints. The whole widget is at most 160px across and a
 * dot on it moves a fraction of a pixel per frame, so redrawing it on the
 * render clock spends a full-map fog pass and two blits to change nothing.
 */
const REPAINT_INTERVAL = 100;
const DOT_R = 2.5;
/** Enemies read as a smaller swarm so players stay the thing you look for. */
const ENEMY_DOT_R = 1.6;
const LOCAL_RING_R = 4;
/** Light at or above this counts as "the team can see that". */
const SEEN_LIGHT = 0.12;

/**
 * The extraction mark: a DIAMOND, and it is the only diamond on this widget.
 *
 * Players are round and enemies are round, so a rotated square is the shape
 * with the most silhouette left over — readable at four pixels, on a fogged
 * ground, next to two sizes of dot, with nothing else to confuse it with.
 */
const RIFT_R = 4;
/** The dead mark a used pad leaves. Smaller, because it is history. */
const RIFT_SPENT_R = 2.5;
/** Full turn of the awake pad's pulse, in ms. */
const RIFT_PULSE_MS = 1400;
/**
 * And of a pad that has called for a pickup. It is the corner sirens' own
 * period (12 frames at 16 fps out of `siren.png`), so the dot on the map and
 * the lamps in the clearing are the same alarm rather than two.
 */
const RIFT_ALARM_MS = 750;
/**
 * The red a called pad takes. Hardcoded to match `RED_GLARE` in
 * `make_platform.py` for the same reason the world's alarm wash is: the lamp,
 * the glare it throws and this dot are ONE light, and a themed red would drift
 * from the baked one the first time the palette moved.
 */
const RIFT_ALARM_TONE: readonly [number, number, number] = [232, 60, 48];

export interface MinimapPlayer {
  id: string;
  x: number;
  y: number;
  color: string;
  alive: boolean;
  kind?: 'player' | 'enemy';
}

export class Minimap {
  private readonly ctx: CanvasRenderingContext2D;
  private world: TileMap | null = null;
  private cache: HTMLCanvasElement | null = null;
  private fog: HTMLCanvasElement | null = null;
  private fogCtx: CanvasRenderingContext2D | null = null;
  private fogData: ImageData | null = null;
  private lastPaint = 0;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.ctx = get2d(canvas, 'minimap');
  }

  setWorld(world: TileMap | null): void {
    this.world = world;
    this.cache = null;
    this.fog = null;
    this.fogCtx = null;
    this.fogData = null;
    if (!world) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      return;
    }
    this.cache = buildTileCache(world);
    const fog = createSurface(world.width, world.height, 'minimap/fog');
    this.fog = fog.canvas;
    this.fogCtx = fog.ctx;
    this.fogData = fog.ctx.createImageData(world.width, world.height);
    this.fitCanvas(world);
    this.lastPaint = 0;
    this.paint([], '', null);
  }

  /** Tile kinds changed. Rebuild the ground cache; fog stays. */
  rebuildTiles(): void {
    if (!this.world) return;
    this.cache = buildTileCache(this.world);
    this.lastPaint = 0;
  }

  /** Safe to call every frame — it repaints at its own cadence. */
  draw(players: MinimapPlayer[], localId: string, fov: FovField | null): void {
    if (!this.world || !this.cache) return;
    const now = performance.now();
    if (now - this.lastPaint < REPAINT_INTERVAL) return;
    this.lastPaint = now;
    this.paint(players, localId, fov);
  }

  /** Backing store is 1px per tile, scaled up to at most MAX_SIDE on screen. */
  private fitCanvas(world: TileMap): void {
    const scale = Math.min(MAX_SIDE / world.width, MAX_SIDE / world.height);
    const w = Math.max(1, Math.round(world.width * scale));
    const h = Math.max(1, Math.round(world.height * scale));
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.ctx.imageSmoothingEnabled = false;
  }

  private paint(players: MinimapPlayer[], localId: string, fov: FovField | null): void {
    const { world, cache, ctx } = this;
    if (!world || !cache) return;
    const { width, height } = this.canvas;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(cache, 0, 0, width, height);
    if (fov) this.paintFog(fov, width, height);

    const sx = width / world.pixelWidth;
    const sy = height / world.pixelHeight;
    const ts = world.tileSize;

    // Under the bodies. A pad is a place, and a place does not cover a person
    // standing on it.
    for (const rift of world.rifts) this.paintRift(rift, sx, sy, ts, fov);

    for (const player of players) {
      // An enemy the team has no light on is not on the map. A teammate always
      // is, whether or not anyone can currently see them.
      if (player.kind === 'enemy' && fov) {
        const lit = fov.lightAt(Math.floor(player.x / ts), Math.floor(player.y / ts));
        if (lit < SEEN_LIGHT) continue;
      }

      const px = player.x * sx;
      const py = player.y * sy;

      ctx.globalAlpha = player.alive ? 1 : 0.35;

      if (player.kind === 'enemy') {
        ctx.beginPath();
        ctx.arc(px, py, ENEMY_DOT_R, 0, Math.PI * 2);
        ctx.fillStyle = player.color;
        ctx.fill();
        continue;
      }

      if (player.id === localId) {
        ctx.beginPath();
        ctx.arc(px, py, LOCAL_RING_R, 0, Math.PI * 2);
        ctx.strokeStyle = palette().minimap.localRing;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(px, py, DOT_R, 0, Math.PI * 2);
      ctx.fillStyle = player.color;
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }

  /**
   * One extraction pad, as a diamond on the ground it stands on.
   *
   * The colour is the pad's own story and matches what the clearing looks
   * like: mint while it is dormant or loading, GOLD once its quota is settled
   * and the console is waiting to be pressed again — the same gold the console
   * itself takes — RED for the thirteen seconds a pickup is running, and a flat
   * dead grey once the platform has flown. A live pad breathes; nothing else on
   * this widget does, so movement alone says "that one is doing something", and
   * a pad under alarm breathes FAST for the same reason the clearing does.
   */
  private paintRift(
    rift: Rift,
    sx: number,
    sy: number,
    ts: number,
    fov: FovField | null,
  ): void {
    const { ctx } = this;
    const awake = rift.state === 'charging' || rift.state === 'open';
    const alarm = awake && rift.closeAt !== null;
    if (!awake && fov) {
      // Dormant or spent: it is knowledge, not light. Show it once the team
      // has been there.
      const tx = Math.floor(rift.x / ts);
      const ty = Math.floor(rift.y / ts);
      if (!fov.isExplored(tx, ty) && fov.lightAt(tx, ty) < SEEN_LIGHT) return;
    }

    const tone = palette().scene;
    const [r, g, b] = alarm
      ? RIFT_ALARM_TONE
      : rift.ready ? tone.ember : tone.beacon;
    const px = rift.x * sx;
    const py = rift.y * sy;

    if (rift.state === 'spent') {
      ctx.globalAlpha = 0.5;
      diamond(ctx, px, py, RIFT_SPENT_R);
      ctx.strokeStyle = palette().minimap.fog;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.globalAlpha = 1;
      return;
    }

    const period = alarm ? RIFT_ALARM_MS : RIFT_PULSE_MS;
    const beat = awake
      ? (alarm ? 0.62 : 0.8)
        + (alarm ? 0.38 : 0.2) * Math.sin((performance.now() / period) * Math.PI * 2)
      : 1;
    const radius = RIFT_R * (awake ? beat : 0.8);

    if (awake) {
      // A halo, so a live pad is findable in one glance at a fogged map.
      ctx.globalAlpha = 0.28 * beat;
      diamond(ctx, px, py, radius * 2.1);
      ctx.fillStyle = `rgb(${r} ${g} ${b})`;
      ctx.fill();
    }

    ctx.globalAlpha = awake ? 1 : 0.7;
    diamond(ctx, px, py, radius);
    // Hollow while dormant, filled once it is answering: the same "found it /
    // switched it on" split the console sprite draws.
    if (awake) {
      ctx.fillStyle = `rgb(${r} ${g} ${b})`;
      ctx.fill();
    } else {
      ctx.strokeStyle = `rgb(${r} ${g} ${b})`;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  /**
   * One pixel per tile, written straight into ImageData and blitted. A rect per
   * tile would be thousands of fill calls a frame for the same picture.
   */
  private paintFog(fov: FovField, width: number, height: number): void {
    const { fog, fogCtx, fogData } = this;
    if (!fog || !fogCtx || !fogData) return;

    const [r, g, b] = palette().night.shadow;
    const pixels = fogData.data;
    for (let i = 0; i < fov.light.length; i++) {
      const offset = i * 4;
      pixels[offset] = r;
      pixels[offset + 1] = g;
      pixels[offset + 2] = b;
      if (fov.light[i] >= SEEN_LIGHT) pixels[offset + 3] = 0;
      else pixels[offset + 3] = fov.explored[i] === 1 ? 158 : 235;
    }
    fogCtx.putImageData(fogData, 0, 0);
    this.ctx.drawImage(fog, 0, 0, width, height);
  }
}

/** Path a square standing on one corner. Caller fills or strokes it. */
function diamond(ctx: CanvasRenderingContext2D, x: number, y: number, r: number): void {
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + r, y);
  ctx.lineTo(x, y + r);
  ctx.lineTo(x - r, y);
  ctx.closePath();
}

/** One pixel per tile; scaling to the display size happens at draw time. */
function buildTileCache(world: TileMap): HTMLCanvasElement {
  const { canvas, ctx } = createSurface(world.width, world.height, 'minimap/cache');
  const tiles = palette().tiles;

  for (let ty = 0; ty < world.height; ty++) {
    for (let tx = 0; tx < world.width; tx++) {
      const tile = world.tiles[ty][tx];
      // The shop's laid floor is ground like any other here: a minimap is a
      // map of where you can WALK, and a room drawn as a solid block because
      // its floor is brick would read as the one place you cannot go.
      if (tile === FLOOR || tile === VOID || tile === TILEFLOOR) {
        ctx.fillStyle = floorColor(tx, ty);
      } else {
        // Cheap top-edge hint so blockers read the same way as the main view.
        const above = ty === 0 ? FLOOR : world.tiles[ty - 1][tx];
        const exposed = above === FLOOR || above === VOID || above === TILEFLOOR;
        if (tile === TREE) ctx.fillStyle = exposed ? tiles.treeTop : tiles.tree;
        else ctx.fillStyle = exposed ? tiles.wallTop : tiles.wallBody;
      }
      ctx.fillRect(tx, ty, 1, 1);
    }
  }
  return canvas;
}
