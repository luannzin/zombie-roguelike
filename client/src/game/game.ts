/**
 * Game orchestrator: owns the network connection, the predicted local player,
 * the interpolated remote players and the render loop.
 *
 * Two clocks:
 *   - fixed 30 Hz tick  -> sample input, predict, send (matches server tick)
 *   - requestAnimationFrame -> interpolate, smooth, render
 */

import { Connection, type ConnectionStatus } from '../net/connection';
import type {
  GameConfig,
  InputPacket,
  PlayerState,
  ServerMessage,
  SnapshotMessage,
  WelcomeMessage,
} from '../net/protocol';
import { Camera } from '../render/camera';
import { Minimap } from '../render/minimap';
import { Renderer, type DrawablePlayer } from '../render/renderer';
import { loadCharacterSheet, type SpriteSheet } from '../render/sprites';
import { hitscan, type RayTarget } from './combat';
import { Effects } from './effects';
import { InputController } from './input';
import { SnapshotBuffer } from './interpolation';
import { LocalPlayer } from './prediction';
import { TileMap } from './world';

const MAX_TICKS_PER_FRAME = 5;

export interface Hud {
  status: HTMLElement;
  you: HTMLElement;
  net: HTMLElement;
  minimap: HTMLCanvasElement;
}

export class Game {
  private readonly connection = new Connection();
  private readonly input: InputController;
  private readonly camera = new Camera();
  private readonly effects = new Effects();
  private readonly snapshots = new SnapshotBuffer();
  private readonly minimap: Minimap;
  private renderer: Renderer | null = null;
  private sheet: SpriteSheet | null = null;

  private world: TileMap | null = null;
  private config: GameConfig | null = null;
  private localId = '';
  private local: LocalPlayer | null = null;
  private localMeta: PlayerState | null = null;

  private accumulator = 0;
  private lastFrame = 0;
  private localFireCooldown = 0;
  private animTimes = new Map<string, number>();
  private hudTimer = 0;
  private aimX = 1;
  private aimY = 0;
  private lastPacket: InputPacket | null = null;
  /** local player position interpolated between fixed ticks (see prediction.ts) */
  private smoothX = 0;
  private smoothY = 0;
  private resizeDirty = true;
  private fps = 0;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly hud: Hud,
  ) {
    this.input = new InputController(canvas);
    this.minimap = new Minimap(hud.minimap);
  }

  async start(): Promise<void> {
    this.sheet = await loadCharacterSheet('player');
    this.renderer = new Renderer(this.canvas, this.sheet);

    // Reading clientWidth every frame forces a layout; only resize on change.
    new ResizeObserver(() => {
      this.resizeDirty = true;
    }).observe(this.canvas);

    this.connection.onStatus = (status) => this.onStatus(status);
    this.connection.onMessage = (msg) => this.onMessage(msg);
    this.connection.connect();

    this.lastFrame = performance.now();
    requestAnimationFrame(this.frame);
  }

  // --- networking ----------------------------------------------------------
  private onStatus(status: ConnectionStatus): void {
    if (status === 'connecting') this.hud.status.textContent = 'connecting…';
    if (status === 'closed') {
      this.hud.status.textContent = 'disconnected — retrying…';
      this.local = null;
      this.world = null;
      this.minimap.setWorld(null);
    }
  }

  private onMessage(msg: ServerMessage): void {
    if (msg.type === 'welcome') this.onWelcome(msg);
    else if (msg.type === 'snapshot') this.onSnapshot(msg);
  }

  private onWelcome(msg: WelcomeMessage): void {
    this.config = msg.config;
    this.world = new TileMap(msg.map);
    this.localId = msg.playerId;
    this.localMeta = msg.player;
    this.local = new LocalPlayer(msg.player);
    this.animTimes.clear();
    this.localFireCooldown = 0;
    this.accumulator = 0;
    this.lastPacket = null;
    this.smoothX = msg.player.x;
    this.smoothY = msg.player.y;

    this.camera.resize(this.canvas.width, this.canvas.height);
    this.camera.snapTo(msg.player.x, msg.player.y, this.world);
    this.minimap.setWorld(this.world);

    this.hud.status.textContent = 'in arena';
  }

  private onSnapshot(msg: SnapshotMessage): void {
    if (!this.world || !this.config || !this.local) return;

    this.snapshots.push(msg, performance.now());

    for (const state of msg.players) {
      if (state.id === this.localId) {
        this.localMeta = state;
        this.local.reconcile(state, msg.ack, this.world, this.config);
      }
    }

    // Own shots were already drawn locally at fire time.
    for (const shot of msg.shots) {
      if (shot.by === this.localId) continue;
      const shooter = msg.players.find((p) => p.id === shot.by);
      this.effects.spawnShot(
        shot.x,
        shot.y,
        shot.dx,
        shot.dy,
        shot.dist,
        shooter?.color ?? '#ffd166',
        shot.hit !== null,
      );
    }
  }

  // --- loop ----------------------------------------------------------------
  private frame = (now: number): void => {
    const dt = Math.min(0.25, (now - this.lastFrame) / 1000);
    this.lastFrame = now;
    if (dt > 0) this.fps += (1 / dt - this.fps) * 0.05;

    if (this.resizeDirty && this.renderer) {
      this.renderer.resize();
      this.camera.resize(this.canvas.width, this.canvas.height);
      this.resizeDirty = false;
    }

    if (this.world && this.config && this.local) {
      // Aim updates every frame, not every tick, so the crosshair never feels
      // capped at the simulation rate.
      this.updateAim();

      this.accumulator += dt;
      const step = this.config.dt;
      let ticks = 0;
      while (this.accumulator >= step && ticks < MAX_TICKS_PER_FRAME) {
        this.accumulator -= step;
        this.tick(step);
        ticks++;
      }
      if (ticks === MAX_TICKS_PER_FRAME) this.accumulator = 0;

      this.local.decayError(dt);
      const smooth = this.local.subTickPosition(
        this.lastPacket,
        this.world,
        this.config,
        this.accumulator,
      );
      this.smoothX = smooth.x;
      this.smoothY = smooth.y;
      this.camera.follow(smooth.x, smooth.y, this.world, dt);
    }

    this.effects.update(dt);
    this.render(dt);
    this.updateHud(dt);

    requestAnimationFrame(this.frame);
  };

  /** One fixed simulation step: sample input, predict, send. */
  private tick(dt: number): void {
    const world = this.world!;
    const config = this.config!;
    const local = this.local!;

    const packet: InputPacket = {
      type: 'input',
      sequence: local.nextSequence(),
      movement: { ...this.input.movement },
      aim: { x: this.aimX, y: this.aimY },
      shoot: this.input.shooting,
    };

    local.predict(packet, world, config);
    this.connection.send(packet);
    this.lastPacket = packet;

    if (this.localFireCooldown > 0) {
      this.localFireCooldown = Math.max(0, this.localFireCooldown - dt);
    }
    if (packet.shoot && local.alive && this.localFireCooldown === 0) {
      this.localFireCooldown = config.fireCooldown;
      this.predictShot();
    }
  }

  private updateAim(): void {
    const local = this.local;
    if (!local) return;
    const point = this.camera.screenToWorld(this.input.mouseX, this.input.mouseY);
    let dx = point.x - this.smoothX;
    let dy = point.y - this.smoothY;
    const len = Math.hypot(dx, dy);
    if (len > 1e-3) {
      dx /= len;
      dy /= len;
      this.aimX = Number(dx.toFixed(3));
      this.aimY = Number(dy.toFixed(3));
    }
  }

  /** Immediate local tracer so shooting feels instant; server still decides damage. */
  private predictShot(): void {
    const world = this.world!;
    const config = this.config!;

    const ox = this.smoothX + this.aimX * config.muzzleOffset;
    const oy = this.smoothY + this.aimY * config.muzzleOffset;
    const targets: RayTarget[] = this.snapshots
      .sample(performance.now(), this.localId, this.connection.rtt)
      .map((p) => ({
        id: p.id,
        x: p.x,
        y: p.y,
        radius: config.playerHitRadius,
        alive: p.alive,
      }));

    const result = hitscan(
      world,
      ox,
      oy,
      this.aimX,
      this.aimY,
      config.shotRange,
      targets,
      this.localId,
    );
    this.effects.spawnShot(
      ox,
      oy,
      this.aimX,
      this.aimY,
      result.distance,
      this.localMeta?.color ?? '#ffd166',
      result.target !== null,
    );
  }

  // --- rendering -----------------------------------------------------------
  private render(dt: number): void {
    if (!this.renderer || !this.world || !this.config) return;

    const drawables: DrawablePlayer[] = [];
    const now = performance.now();

    for (const remote of this.snapshots.sample(now, this.localId, this.connection.rtt)) {
      drawables.push({
        id: remote.id,
        name: remote.name,
        color: remote.color,
        x: remote.x,
        y: remote.y,
        ax: remote.ax,
        ay: remote.ay,
        hp: remote.hp,
        maxHp: this.config.maxHp,
        alive: remote.alive,
        moving: remote.moving,
        animTime: this.advanceAnim(remote.id, remote.moving, dt),
        isLocal: false,
      });
    }

    if (this.local && this.localMeta) {
      const moving = Math.hypot(this.local.state.vx, this.local.state.vy) > 1;
      drawables.push({
        id: this.localId,
        name: this.localMeta.name,
        color: this.localMeta.color,
        x: this.smoothX,
        y: this.smoothY,
        ax: this.aimX,
        ay: this.aimY,
        hp: this.local.hp,
        maxHp: this.config.maxHp,
        alive: this.local.alive,
        moving,
        animTime: this.advanceAnim(this.localId, moving, dt),
        isLocal: true,
      });
    }

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      players: drawables,
      effects: this.effects,
    });
    this.minimap.draw(drawables, this.localId);
  }

  private advanceAnim(id: string, moving: boolean, dt: number): number {
    const current = this.animTimes.get(id) ?? 0;
    const next = moving ? current + dt : 0;
    this.animTimes.set(id, next);
    return next;
  }

  // --- hud -----------------------------------------------------------------
  private updateHud(dt: number): void {
    this.hudTimer += dt;
    if (this.hudTimer < 0.2) return;
    this.hudTimer = 0;

    if (this.localMeta && this.local) {
      const meta = this.localMeta;
      this.hud.you.innerHTML =
        `<span style="color:${meta.color}">${meta.name}</span> ` +
        `· hp ${this.local.hp} · k/d ${meta.kills}/${meta.deaths}` +
        (this.local.alive ? '' : ' · <span style="color:#e6484f">respawning…</span>');
    }

    const latest = this.snapshots.latest;
    const count = latest ? latest.players.size : 0;
    this.hud.net.textContent =
      `players ${count} · rtt ${this.connection.rtt}ms · ` +
      `interp ${Math.round(this.snapshots.effectiveDelay(this.connection.rtt))}ms · ` +
      `pending ${this.local ? this.local.pending.length : 0} · ` +
      `${Math.round(this.fps)} fps`;
  }
}
