/**
 * Canvas 2D renderer.
 *
 * Consumes a plain RenderState snapshot and draws it. It never touches the
 * network, never mutates game state, and holds no gameplay logic — swapping
 * renderers (or adding zombies to `players`) requires no changes elsewhere.
 */

import type { Effects } from '../game/effects';
import { WALL, type TileMap } from '../game/world';
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
  players: DrawablePlayer[];
  effects: Effects;
}

const FLOOR_COLORS = ['#23232c', '#262630', '#202029'];
const WALL_TOP = '#565673';
const WALL_BODY = '#3a3a4e';
const WALL_EDGE = '#1b1b24';

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly tints: TintCache;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly sheet: SpriteSheet,
  ) {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('2d context unavailable');
    this.ctx = ctx;
    this.tints = new TintCache(sheet);
  }

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

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#0a0a10';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const offsetX = Math.round(-camera.x * camera.zoom);
    const offsetY = Math.round(-camera.y * camera.zoom);
    ctx.setTransform(camera.zoom, 0, 0, camera.zoom, offsetX, offsetY);

    this.drawMap(state);
    this.drawShadows(state);

    const ordered = [...state.players].sort((a, b) => a.y - b.y);
    for (const player of ordered) this.drawPlayer(player);

    this.drawEffects(state);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.drawLabels(state, offsetX, offsetY);
  }

  // --- world ---------------------------------------------------------------
  private drawMap(state: RenderState): void {
    const { ctx } = this;
    const { world, camera } = state;
    const ts = world.tileSize;

    const x0 = Math.max(0, Math.floor(camera.x / ts));
    const y0 = Math.max(0, Math.floor(camera.y / ts));
    const x1 = Math.min(world.width - 1, Math.ceil((camera.x + camera.viewWidth) / ts));
    const y1 = Math.min(world.height - 1, Math.ceil((camera.y + camera.viewHeight) / ts));

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

  private drawShadows(state: RenderState): void {
    const { ctx } = this;
    ctx.fillStyle = 'rgba(0,0,0,0.32)';
    for (const player of state.players) {
      if (!player.alive) continue;
      ctx.beginPath();
      ctx.ellipse(Math.round(player.x), Math.round(player.y) + 6, 5, 2.5, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // --- entities ------------------------------------------------------------
  private drawPlayer(player: DrawablePlayer): void {
    if (!player.alive) return;
    const { ctx, sheet } = this;

    const row = sheet.rows[facingFromAim(player.ax, player.ay)] ?? 0;
    const col = frameIndex(sheet, player.animTime, player.moving);
    const image = this.tints.get(player.color);

    const w = sheet.frameWidth;
    const h = sheet.frameHeight;
    const dx = Math.round(player.x - w / 2);
    const dy = Math.round(player.y - h + 7); // feet roughly at the collision box bottom

    ctx.drawImage(image, col * w, row * h, w, h, dx, dy, w, h);

    // aim indicator
    ctx.strokeStyle = player.isLocal ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(player.x + player.ax * 6, player.y + player.ay * 6);
    ctx.lineTo(player.x + player.ax * 11, player.y + player.ay * 11);
    ctx.stroke();

    // health bar
    const barW = 14;
    const hpRatio = Math.max(0, Math.min(1, player.hp / player.maxHp));
    const barX = Math.round(player.x - barW / 2);
    const barY = Math.round(player.y - h + 1);
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(barX, barY, barW, 3);
    ctx.fillStyle = hpRatio > 0.5 ? '#7bd389' : hpRatio > 0.25 ? '#f2a541' : '#e6484f';
    ctx.fillRect(barX + 1, barY + 1, Math.round((barW - 2) * hpRatio), 1);
  }

  // --- effects -------------------------------------------------------------
  private drawEffects(state: RenderState): void {
    const { ctx } = this;
    const { effects } = state;

    for (const tracer of effects.tracers) {
      const fade = 1 - tracer.age / tracer.life;
      const ex = tracer.x + tracer.dx * tracer.dist;
      const ey = tracer.y + tracer.dy * tracer.dist;

      ctx.globalAlpha = 0.35 * fade;
      ctx.strokeStyle = tracer.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(tracer.x, tracer.y);
      ctx.lineTo(ex, ey);
      ctx.stroke();

      ctx.globalAlpha = fade;
      ctx.strokeStyle = '#fff6d5';
      ctx.lineWidth = 0.6;
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
      ctx.arc(flash.x + flash.dx * 2, flash.y + flash.dy * 2, 2.2 * fade + 0.8, 0, Math.PI * 2);
      ctx.fill();
    }

    for (const impact of effects.impacts) {
      const fade = 1 - impact.age / impact.life;
      ctx.globalAlpha = fade;
      ctx.fillStyle = impact.hit ? '#ff5a5a' : '#cfcfe0';
      const size = impact.hit ? 3 : 2;
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

    for (const player of state.players) {
      if (!player.alive) continue;
      const sx = Math.round(player.x * zoom + offsetX);
      const sy = Math.round((player.y - this.sheet.frameHeight + 6) * zoom + offsetY);
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.fillText(player.name, sx + 1, sy + 1);
      ctx.fillStyle = player.color;
      ctx.fillText(player.name, sx, sy);
    }
  }
}
