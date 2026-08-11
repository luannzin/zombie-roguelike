/**
 * Canvas 2D renderer.
 *
 * Consumes a plain RenderState snapshot and draws it. It never touches the
 * network, never mutates game state, and holds no gameplay logic — swapping
 * renderers (or adding zombies to `players`) requires no changes elsewhere.
 *
 * Two performance/quality decisions worth knowing:
 *   - the tile map is pre-rendered once into an offscreen canvas, so a frame
 *     costs one blit instead of ~1000 fillRect calls
 *   - entities are drawn in SCREEN space with integer rounding, so motion is
 *     quantized to 1 screen pixel instead of 1 world pixel (= `zoom` screen
 *     pixels). That is what makes 60 fps movement look smooth at zoom 3.
 */

import type { Effects } from '../game/effects';
import { WALL, type TileMap } from '../game/world';
import type { GameConfig } from '../net/protocol';
import type { Camera } from './camera';
import { facingFromAim, frameIndex, TintCache, type SpriteSheet } from './sprites';

export interface DrawablePlayer {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
  ax: number;
  ay: number;
  hp: number;
  maxHp: number;
  alive: boolean;
  moving: boolean;
  animTime: number;
  isLocal: boolean;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  players: DrawablePlayer[];
  effects: Effects;
}

const FLOOR_COLORS = ['#23232c', '#262630', '#202029'];
const WALL_TOP = '#565673';
const WALL_BODY = '#3a3a4e';
const WALL_EDGE = '#1b1b24';

/** Above this a map is drawn per-tile instead of cached (procedural maps later). */
const MAX_CACHED_MAP_PIXELS = 4096 * 4096;

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly tints: TintCache;

  private mapCanvas: HTMLCanvasElement | null = null;
  private mapCanvasFor: TileMap | null = null;
  /** set at the top of every draw(); all visual sizes are derived from it */
  private cfg!: GameConfig;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly sheet: SpriteSheet,
  ) {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('2d context unavailable');
    this.ctx = ctx;
    this.tints = new TintCache(sheet);
  }

  /** Call only when the canvas element actually changed size (see ResizeObserver). */
  resize(): void {
    const width = Math.max(1, Math.floor(this.canvas.clientWidth));
    const height = Math.max(1, Math.floor(this.canvas.clientHeight));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.ctx.imageSmoothingEnabled = false;
  }

  draw(state: RenderState): void {
    const { ctx } = this;
    const { camera } = state;
    this.cfg = state.config;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#0a0a10';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const offsetX = Math.round(-camera.x * camera.zoom);
    const offsetY = Math.round(-camera.y * camera.zoom);

    // world-space pass: map
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);
    this.drawMap(state);

    // screen-space pass: entities (pixel-exact placement)
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    const ordered = [...state.players].sort((a, b) => a.y - b.y);
    for (const player of ordered) this.drawShadow(player, camera, offsetX, offsetY);
    for (const player of ordered) this.drawPlayer(player, camera, offsetX, offsetY);

    // world-space pass: effects draw over entities
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);
    this.drawEffects(state);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.drawLabels(state, offsetX, offsetY);
  }

  // --- world ---------------------------------------------------------------
  private drawMap(state: RenderState): void {
    const { world, camera } = state;

    if (this.mapCanvasFor !== world) this.buildMapCache(world);

    if (this.mapCanvas) {
      const sx = Math.max(0, Math.floor(camera.x));
      const sy = Math.max(0, Math.floor(camera.y));
      const sw = Math.min(world.pixelWidth - sx, Math.ceil(camera.viewWidth) + 2);
      const sh = Math.min(world.pixelHeight - sy, Math.ceil(camera.viewHeight) + 2);
      if (sw > 0 && sh > 0) {
        this.ctx.drawImage(this.mapCanvas, sx, sy, sw, sh, sx, sy, sw, sh);
      }
      return;
    }

    const ts = world.tileSize;
    const x0 = Math.max(0, Math.floor(camera.x / ts));
    const y0 = Math.max(0, Math.floor(camera.y / ts));
    const x1 = Math.min(world.width - 1, Math.ceil((camera.x + camera.viewWidth) / ts));
    const y1 = Math.min(world.height - 1, Math.ceil((camera.y + camera.viewHeight) / ts));
    this.paintTiles(this.ctx, world, x0, y0, x1, y1);
  }

  private buildMapCache(world: TileMap): void {
    this.mapCanvasFor = world;
    if (world.pixelWidth * world.pixelHeight > MAX_CACHED_MAP_PIXELS) {
      this.mapCanvas = null;
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = world.pixelWidth;
    canvas.height = world.pixelHeight;
    const ctx = canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = false;
    this.paintTiles(ctx, world, 0, 0, world.width - 1, world.height - 1);
    this.mapCanvas = canvas;
  }

  private paintTiles(
    ctx: CanvasRenderingContext2D,
    world: TileMap,
    x0: number,
    y0: number,
    x1: number,
    y1: number,
  ): void {
    const ts = world.tileSize;
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const px = tx * ts;
        const py = ty * ts;
        if (world.tiles[ty][tx] === WALL) {
          ctx.fillStyle = WALL_BODY;
          ctx.fillRect(px, py, ts, ts);
          ctx.fillStyle = WALL_TOP;
          ctx.fillRect(px, py, ts, 3);
          ctx.fillStyle = WALL_EDGE;
          ctx.fillRect(px, py + ts - 2, ts, 2);
        } else {
          ctx.fillStyle = FLOOR_COLORS[(tx * 7 + ty * 13) % FLOOR_COLORS.length];
          ctx.fillRect(px, py, ts, ts);
          if ((tx + ty) % 9 === 0) {
            ctx.fillStyle = '#2c2c38';
            ctx.fillRect(px + 4, py + 6, 3, 1);
          }
        }
      }
    }
  }

  // --- entities ------------------------------------------------------------
  private drawShadow(
    player: DrawablePlayer,
    camera: Camera,
    offsetX: number,
    offsetY: number,
  ): void {
    if (!player.alive) return;
    const { ctx, cfg } = this;
    const zoom = camera.zoom;
    ctx.fillStyle = 'rgba(0,0,0,0.32)';
    ctx.beginPath();
    ctx.ellipse(
      Math.round(player.x * zoom + offsetX),
      Math.round((player.y + cfg.playerHalfHeight) * zoom + offsetY),
      cfg.playerHalfWidth * 1.15 * zoom,
      cfg.playerHalfHeight * 0.75 * zoom,
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }

  private drawPlayer(
    player: DrawablePlayer,
    camera: Camera,
    offsetX: number,
    offsetY: number,
  ): void {
    if (!player.alive) return;
    const { ctx, sheet, cfg } = this;
    const zoom = camera.zoom;
    const ts = cfg.tileSize;

    const row = sheet.rows[facingFromAim(player.ax, player.ay)] ?? 0;
    const col = frameIndex(sheet, player.animTime, player.moving);
    const image = this.tints.get(player.color);

    const w = sheet.frameWidth;
    const h = sheet.frameHeight;
    // The sprite's bottom edge sits on the bottom of the collision box, so a
    // 1x1.5-tile character stands correctly on a 0.6x0.45-tile footprint.
    const spriteTop = player.y + cfg.playerHalfHeight - h;
    const dx = Math.round((player.x - w / 2) * zoom + offsetX);
    const dy = Math.round(spriteTop * zoom + offsetY);
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, w * zoom, h * zoom);

    const cx = player.x * zoom + offsetX;
    const cy = player.y * zoom + offsetY;

    // aim indicator
    ctx.strokeStyle = player.isLocal ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.25)';
    ctx.lineWidth = Math.max(1, zoom * 0.7);
    ctx.beginPath();
    ctx.moveTo(cx + player.ax * ts * 0.4 * zoom, cy + player.ay * ts * 0.4 * zoom);
    ctx.lineTo(cx + player.ax * ts * 0.75 * zoom, cy + player.ay * ts * 0.75 * zoom);
    ctx.stroke();

    // health bar
    const unit = Math.max(1, Math.round(ts * 0.0625) * zoom); // 1 world px
    const barW = Math.round(ts * 0.875) * zoom;
    const barH = unit * 3;
    const hpRatio = Math.max(0, Math.min(1, player.hp / player.maxHp));
    const barX = Math.round(cx - barW / 2);
    const barY = Math.round((spriteTop - ts * 0.125) * zoom + offsetY);
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(barX, barY, barW, barH);
    ctx.fillStyle = hpRatio > 0.5 ? '#7bd389' : hpRatio > 0.25 ? '#f2a541' : '#e6484f';
    ctx.fillRect(barX + unit, barY + unit, Math.round((barW - 2 * unit) * hpRatio), unit);
  }

  // --- effects -------------------------------------------------------------
  private drawEffects(state: RenderState): void {
    const { ctx } = this;
    const { effects } = state;
    const ts = state.config.tileSize;

    for (const tracer of effects.tracers) {
      const fade = 1 - tracer.age / tracer.life;
      const ex = tracer.x + tracer.dx * tracer.dist;
      const ey = tracer.y + tracer.dy * tracer.dist;

      ctx.globalAlpha = 0.35 * fade;
      ctx.strokeStyle = tracer.color;
      ctx.lineWidth = ts * 0.125;
      ctx.beginPath();
      ctx.moveTo(tracer.x, tracer.y);
      ctx.lineTo(ex, ey);
      ctx.stroke();

      ctx.globalAlpha = fade;
      ctx.strokeStyle = '#fff6d5';
      ctx.lineWidth = ts * 0.0375;
      ctx.beginPath();
      ctx.moveTo(tracer.x, tracer.y);
      ctx.lineTo(ex, ey);
      ctx.stroke();
    }

    for (const flash of effects.flashes) {
      const fade = 1 - flash.age / flash.life;
      ctx.globalAlpha = fade;
      ctx.fillStyle = '#ffe9a8';
      ctx.beginPath();
      ctx.arc(
        flash.x + flash.dx * ts * 0.125,
        flash.y + flash.dy * ts * 0.125,
        ts * (0.14 * fade + 0.05),
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }

    for (const impact of effects.impacts) {
      const fade = 1 - impact.age / impact.life;
      ctx.globalAlpha = fade;
      ctx.fillStyle = impact.hit ? '#ff5a5a' : '#cfcfe0';
      const size = ts * (impact.hit ? 0.19 : 0.125);
      ctx.fillRect(impact.x - size / 2, impact.y - size / 2, size, size);
    }

    ctx.globalAlpha = 1;
  }

  // --- screen-space labels -------------------------------------------------
  private drawLabels(state: RenderState, offsetX: number, offsetY: number): void {
    const { ctx } = this;
    const zoom = state.camera.zoom;
    ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    const cfg = state.config;
    const nameOffset = this.sheet.frameHeight - cfg.playerHalfHeight + cfg.tileSize * 0.35;
    for (const player of state.players) {
      if (!player.alive) continue;
      const sx = Math.round(player.x * zoom + offsetX);
      const sy = Math.round((player.y - nameOffset) * zoom + offsetY);
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.fillText(player.name, sx + 1, sy + 1);
      ctx.fillStyle = player.color;
      ctx.fillText(player.name, sx, sy);
    }
  }
}
