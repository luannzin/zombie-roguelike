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
  /** 0..1 white flash intensity after taking a hit. */
  hitFlash: number;
  /** Visual kick opposite aim (world px). Does not affect simulation. */
  recoilX: number;
  recoilY: number;
}

export interface RenderState {
  world: TileMap;
  camera: Camera;
  config: GameConfig;
  players: DrawablePlayer[];
  effects: Effects;
  /** 0..1 local low-HP danger for screen vignette (0 = healthy). */
  danger: number;
  /** Elapsed seconds — drives heartbeat pulse. */
  time: number;
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

    const offsetX = Math.round(-camera.renderX * camera.zoom);
    const offsetY = Math.round(-camera.renderY * camera.zoom);

    // world-space pass: map
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);
    this.drawMap(state);

    // world-space: dust under feet (before entities)
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);
    this.drawDust(state);

    // screen-space pass: entities (pixel-exact placement)
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    const ordered = [...state.players].sort((a, b) => a.y - b.y);
    for (const player of ordered) this.drawShadow(player, camera, offsetX, offsetY);
    for (const player of ordered) this.drawPlayer(player, camera, offsetX, offsetY);

    // world-space pass: combat effects draw over entities
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);
    this.drawEffects(state);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.drawLabels(state, offsetX, offsetY);
    this.drawVignette(state);
  }

  // --- world ---------------------------------------------------------------
  private drawMap(state: RenderState): void {
    const { world, camera } = state;

    if (this.mapCanvasFor !== world) this.buildMapCache(world);

    if (this.mapCanvas) {
      const sx = Math.max(0, Math.floor(camera.renderX));
      const sy = Math.max(0, Math.floor(camera.renderY));
      const sw = Math.min(world.pixelWidth - sx, Math.ceil(camera.viewWidth) + 2);
      const sh = Math.min(world.pixelHeight - sy, Math.ceil(camera.viewHeight) + 2);
      if (sw > 0 && sh > 0) {
        this.ctx.drawImage(this.mapCanvas, sx, sy, sw, sh, sx, sy, sw, sh);
      }
      return;
    }

    const ts = world.tileSize;
    const x0 = Math.max(0, Math.floor(camera.renderX / ts));
    const y0 = Math.max(0, Math.floor(camera.renderY / ts));
    const x1 = Math.min(world.width - 1, Math.ceil((camera.renderX + camera.viewWidth) / ts));
    const y1 = Math.min(world.height - 1, Math.ceil((camera.renderY + camera.viewHeight) / ts));
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
      Math.round((player.x + player.recoilX) * zoom + offsetX),
      Math.round((player.y + player.recoilY + cfg.playerHalfHeight) * zoom + offsetY),
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
    const px = player.x + player.recoilX;
    const py = player.y + player.recoilY;
    const spriteTop = py + cfg.playerHalfHeight - h;
    const dx = Math.round((px - w / 2) * zoom + offsetX);
    const dy = Math.round(spriteTop * zoom + offsetY);
    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, w * zoom, h * zoom);

    if (player.hitFlash > 0) {
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = Math.min(1, player.hitFlash * 0.95);
      ctx.drawImage(image, col * w, row * h, w, h, dx, dy, w * zoom, h * zoom);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
    }

    const cx = px * zoom + offsetX;
    const cy = py * zoom + offsetY;

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
  private drawDust(state: RenderState): void {
    const { ctx } = this;
    for (const p of state.effects.dust) {
      const t = p.age / p.life;
      const fade = (1 - t) * (1 - t);
      // Bloom early, shrink late — reads as a puff, not a spark.
      const grow = t < 0.25 ? 0.6 + t * 2.2 : 1.15 - (t - 0.25) * 0.7;
      ctx.globalAlpha = 0.55 * fade;
      ctx.fillStyle = p.color;
      const s = p.size * Math.max(0.35, grow);
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
    }
    ctx.globalAlpha = 1;
  }

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

    for (const p of effects.particles) {
      const fade = 1 - p.age / p.life;
      ctx.globalAlpha = fade;
      ctx.fillStyle = p.color;
      const s = p.size * (0.55 + 0.45 * fade);
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
    }

    ctx.globalAlpha = 1;
  }

  /** Radial red/black crush — intensity from danger, heartbeat from time. */
  private drawVignette(state: RenderState): void {
    const danger = state.danger;
    if (danger <= 0.001) return;

    const { ctx } = this;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const cx = w * 0.5;
    const cy = h * 0.5;
    const radius = Math.hypot(cx, cy);

    // Heartbeat: stronger + faster as danger climbs.
    const bpm = 1.1 + danger * 2.4;
    const beat = Math.sin(state.time * Math.PI * 2 * bpm);
    // Soft asymmetric pulse (lub-dub-ish): sharp attack, slow release.
    const pulse = Math.pow(0.5 + 0.5 * beat, 1.6);
    const intensity = danger * (0.62 + 0.38 * pulse);

    const grad = ctx.createRadialGradient(cx, cy, radius * 0.22, cx, cy, radius * 0.98);
    grad.addColorStop(0, 'rgba(0,0,0,0)');
    grad.addColorStop(0.45, `rgba(40,0,8,${0.08 * intensity})`);
    grad.addColorStop(0.75, `rgba(90,4,14,${0.42 * intensity})`);
    grad.addColorStop(1, `rgba(140,6,18,${0.82 * intensity})`);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Critical: full-screen blood wash on the beat peak.
    if (danger > 0.65) {
      const wash = (danger - 0.65) / 0.35;
      ctx.fillStyle = `rgba(160, 12, 28, ${0.1 * wash * pulse})`;
      ctx.fillRect(0, 0, w, h);
    }

    // Edge bars for a harder crush on the frame (pixel-art readable).
    const edge = Math.max(10, Math.round(Math.min(w, h) * 0.04 * (0.5 + intensity)));
    ctx.fillStyle = `rgba(0,0,0,${0.35 * intensity})`;
    ctx.fillRect(0, 0, w, edge);
    ctx.fillRect(0, h - edge, w, edge);
    ctx.fillRect(0, 0, edge, h);
    ctx.fillRect(w - edge, 0, edge, h);
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
      const sx = Math.round((player.x + player.recoilX) * zoom + offsetX);
      const sy = Math.round((player.y + player.recoilY - nameOffset) * zoom + offsetY);
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.fillText(player.name, sx + 1, sy + 1);
      ctx.fillStyle = player.color;
      ctx.fillText(player.name, sx, sy);
    }

    this.drawDamageFloats(state, offsetX, offsetY);
  }

  private drawDamageFloats(state: RenderState, offsetX: number, offsetY: number): void {
    const { ctx } = this;
    const zoom = state.camera.zoom;
    ctx.font = `bold ${Math.max(11, Math.round(10 * zoom * 0.45))}px ui-monospace, Menlo, Consolas, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (const d of state.effects.damageFloats) {
      const t = d.age / d.life;
      const fade = 1 - t;
      const sx = Math.round(d.x * zoom + offsetX);
      const sy = Math.round(d.y * zoom + offsetY);
      ctx.globalAlpha = fade;
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillText(String(d.value), sx + 1, sy + 1);
      ctx.fillStyle = '#ffe8e8';
      ctx.fillText(String(d.value), sx, sy);
    }
    ctx.globalAlpha = 1;
  }
}
