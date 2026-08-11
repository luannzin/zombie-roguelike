/**
 * Game orchestrator: owns the network connection, the predicted local player,
 * the interpolated remote players and the render loop.
 *
 * Two clocks:
 *   - fixed 30 Hz tick  -> sample input, predict, send (matches server tick)
 *   - requestAnimationFrame -> interpolate, smooth, render
 *
 * The UI boundary is a single `HudStore`: this class publishes a snapshot at
 * HUD_INTERVAL and never touches the DOM beyond its two canvases. React reads
 * that store and is never part of the frame loop.
 *
 * Lifecycle is explicit — `start()` / `dispose()`. Every timer, listener,
 * observer and socket created here is released by `dispose()`, so remounting
 * (StrictMode, HMR, switching rooms) cannot leave a second loop running.
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
import { Renderer } from '../render/renderer';
import { loadCharacterSheet, type SpriteSheet } from '../render/sprites';
import type { DrawablePlayer } from '../render/types';
import { palette } from '../theme/palette';
import { hitscan, type RayTarget } from './combat';
import { Effects } from './effects';
import { EMPTY_HUD, HUD_INTERVAL, type HudSnapshot, type HudStore } from './hud-store';
import { InputController } from './input';
import { SnapshotBuffer } from './interpolation';
import { PlayerVisuals } from './player-visuals';
import { LocalPlayer } from './prediction';
import { TileMap } from './world';

const MAX_TICKS_PER_FRAME = 5;
/** Camera punch on local fire (miss or hit). */
const FIRE_TRAUMA = 0.16;
/** Extra camera punch when local shot lands on a target. */
const HIT_TRAUMA = 0.12;
/** Camera punch when local player loses HP. */
const HURT_TRAUMA = 0.55;
/** HP ratio where vignette starts (above = none). */
const DANGER_START = 0.45;
/** HP ratio where vignette hits full crush. */
const DANGER_CRITICAL = 0.2;
/** Speed (world px/s) above which the local player reads as walking. */
const MOVING_SPEED = 1;

/**
 * Everything `toDrawable` needs, in the shape both a snapshot-interpolated
 * remote and the locally predicted player can supply.
 */
interface DrawableSource {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  ax: number;
  ay: number;
  hp: number;
  alive: boolean;
  moving: boolean;
  isLocal: boolean;
}

export interface GameOptions {
  canvas: HTMLCanvasElement;
  minimapCanvas: HTMLCanvasElement;
  hud: HudStore;
  /** Override the default server URL (room-scoped URLs land here later). */
  serverUrl?: string;
}

export class Game {
  private readonly canvas: HTMLCanvasElement;
  private readonly hud: HudStore;
  private readonly connection: Connection;
  private readonly input: InputController;
  private readonly minimap: Minimap;
  private readonly camera = new Camera();
  private readonly effects = new Effects();
  private readonly snapshots = new SnapshotBuffer();
  private readonly visuals = new PlayerVisuals();

  private renderer: Renderer | null = null;
  private sheet: SpriteSheet | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private rafId: number | null = null;
  private started = false;
  private disposed = false;

  private world: TileMap | null = null;
  private config: GameConfig | null = null;
  private localId = '';
  private local: LocalPlayer | null = null;
  private localMeta: PlayerState | null = null;

  private accumulator = 0;
  private lastFrame = 0;
  private localFireCooldown = 0;
  private hudTimer = 0;
  private aimX = 1;
  private aimY = 0;
  /** local player position interpolated between fixed ticks (see prediction.ts) */
  private smoothX = 0;
  private smoothY = 0;
  private resizeDirty = true;
  private fps = 0;
  /** Elapsed seconds for vignette heartbeat. */
  private time = 0;

  constructor(options: GameOptions) {
    this.canvas = options.canvas;
    this.hud = options.hud;
    this.connection = new Connection(options.serverUrl);
    this.input = new InputController(options.canvas);
    this.minimap = new Minimap(options.minimapCanvas);
  }

  async start(): Promise<void> {
    if (this.started || this.disposed) return;
    this.started = true;

    this.sheet = await loadCharacterSheet('player');
    // dispose() can land while the sheet is loading.
    if (this.disposed) return;

    this.renderer = new Renderer(this.canvas, this.sheet);

    // Reading clientWidth every frame forces a layout; only resize on change.
    this.resizeObserver = new ResizeObserver(() => {
      this.resizeDirty = true;
    });
    this.resizeObserver.observe(this.canvas);

    this.connection.onStatus = (status) => this.onStatus(status);
    this.connection.onMessage = (msg) => this.onMessage(msg);
    this.connection.connect();

    this.lastFrame = performance.now();
    this.rafId = requestAnimationFrame(this.frame);
  }

  /**
   * Stop everything and release every resource. Idempotent, and safe to call
   * while `start()` is still awaiting the sprite sheet.
   */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;

    this.connection.close();
    this.input.dispose();
    this.renderer?.dispose();
    this.renderer = null;
    this.minimap.setWorld(null);

    this.visuals.clear();
    this.effects.clear();
    this.world = null;
    this.local = null;
    this.localMeta = null;

    this.hud.set(EMPTY_HUD);
  }

  // --- networking ----------------------------------------------------------
  private onStatus(status: ConnectionStatus): void {
    if (status === 'connecting') {
      this.patchHud({ connection: status, status: 'connecting…' });
      return;
    }
    if (status === 'closed') {
      this.local = null;
      this.world = null;
      this.minimap.setWorld(null);
      this.visuals.clear();
      this.effects.clear();
      this.patchHud({
        connection: status,
        status: 'disconnected — retrying…',
        inArena: false,
        vitals: null,
      });
      return;
    }
    this.patchHud({ connection: status });
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

    this.visuals.clear();
    this.effects.clear();
    this.time = 0;
    this.localFireCooldown = 0;
    this.accumulator = 0;
    this.smoothX = msg.player.x;
    this.smoothY = msg.player.y;

    this.camera.resize(this.canvas.width, this.canvas.height);
    this.camera.snapTo(msg.player.x, msg.player.y, this.world);
    this.minimap.setWorld(this.world);

    this.patchHud({ inArena: true, status: 'in arena' });
  }

  private onSnapshot(msg: SnapshotMessage): void {
    if (!this.world || !this.config || !this.local) return;

    this.snapshots.push(msg, performance.now());

    for (const state of msg.players) {
      if (state.id === this.localId) {
        this.localMeta = state;
        this.local.reconcile(state, msg.ack, this.world, this.config);
      }
      // Damage detection is authoritative: HP dropping between snapshots is
      // the only signal that works for local and remote players alike.
      if (this.visuals.noteHp(state.id, state.hp) && state.id === this.localId) {
        this.camera.addTrauma(HURT_TRAUMA);
      }
    }

    // Own shots were already drawn locally at fire time.
    for (const shot of msg.shots) {
      if (shot.by === this.localId) continue;
      const shooter = msg.players.find((p) => p.id === shot.by);
      const hit = shot.hit !== null;
      this.effects.spawnShot(
        shot.x,
        shot.y,
        shot.dx,
        shot.dy,
        shot.dist,
        shooter?.color ?? palette().effects.fallbackShot,
        hit,
        hit ? this.config.shotDamage : undefined,
      );
      this.visuals.kickRecoil(shot.by, shot.dx, shot.dy);
      if (shot.hit) this.visuals.pulseHitFlash(shot.hit);
    }
  }

  // --- loop ----------------------------------------------------------------
  private frame = (now: number): void => {
    if (this.disposed) return;

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
      // Live movement/aim for the render remainder so a mid-tick keypress
      // starts motion this frame — not after the next 30 Hz sample. Tick
      // still samples + sends at 30 Hz; this scratch never commits.
      const smooth = this.local.subTickPosition(
        this.liveInput(),
        this.world,
        this.config,
        this.accumulator,
      );
      this.smoothX = smooth.x;
      this.smoothY = smooth.y;
      this.camera.follow(smooth.x, smooth.y, this.world, dt);
    }

    this.effects.update(dt);
    this.visuals.update(dt);
    this.time += dt;
    this.render(dt);
    this.publishHud(dt);

    this.rafId = requestAnimationFrame(this.frame);
  };

  /** One fixed simulation step: sample input, predict, send. */
  private tick(dt: number): void {
    const world = this.world!;
    const config = this.config!;
    const local = this.local!;

    const packet = this.liveInput(local.nextSequence());
    local.predict(packet, world, config);
    this.connection.send(packet);

    if (this.localFireCooldown > 0) {
      this.localFireCooldown = Math.max(0, this.localFireCooldown - dt);
    }
    if (packet.shoot && local.alive && this.localFireCooldown === 0) {
      this.localFireCooldown = config.fireCooldown;
      this.predictShot();
    }
  }

  /** Current keys + aim as a packet. Sequence 0 means "scratch, never sent". */
  private liveInput(sequence = 0): InputPacket {
    return {
      type: 'input',
      sequence,
      movement: { ...this.input.movement },
      aim: { x: this.aimX, y: this.aimY },
      shoot: this.input.shooting,
    };
  }

  private updateAim(): void {
    if (!this.local) return;
    const point = this.camera.screenToWorld(this.input.mouseX, this.input.mouseY);
    const dx = point.x - this.smoothX;
    const dy = point.y - this.smoothY;
    const len = Math.hypot(dx, dy);
    if (len > 1e-3) {
      this.aimX = Number((dx / len).toFixed(3));
      this.aimY = Number((dy / len).toFixed(3));
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
    const hit = result.target !== null;
    this.effects.spawnShot(
      ox,
      oy,
      this.aimX,
      this.aimY,
      result.distance,
      this.localMeta?.color ?? palette().effects.fallbackShot,
      hit,
      hit ? config.shotDamage : undefined,
    );
    this.camera.addTrauma(FIRE_TRAUMA + (hit ? HIT_TRAUMA : 0));
    this.visuals.kickRecoil(this.localId, this.aimX, this.aimY);
    if (result.target) this.visuals.pulseHitFlash(result.target.id);
  }

  // --- rendering -----------------------------------------------------------
  private render(dt: number): void {
    if (!this.renderer || !this.world || !this.config) return;

    const drawables: DrawablePlayer[] = [];
    const now = performance.now();

    for (const remote of this.snapshots.sample(now, this.localId, this.connection.rtt)) {
      drawables.push(this.toDrawable({ ...remote, isLocal: false }, dt));
    }

    if (this.local && this.localMeta) {
      const { vx, vy } = this.local.state;
      drawables.push(
        this.toDrawable(
          {
            id: this.localId,
            name: this.localMeta.name,
            color: this.localMeta.color,
            x: this.smoothX,
            y: this.smoothY,
            vx,
            vy,
            ax: this.aimX,
            ay: this.aimY,
            hp: this.local.hp,
            alive: this.local.alive,
            moving: Math.hypot(vx, vy) > MOVING_SPEED,
            isLocal: true,
          },
          dt,
        ),
      );
    }

    // Everyone in this frame was touched by toDrawable; anyone who left is now
    // unreferenced and gets dropped.
    this.visuals.prune();

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      players: drawables,
      effects: this.effects,
      danger: this.dangerLevel(),
      time: this.time,
    });
    this.minimap.draw(drawables, this.localId);
  }

  /** Build one renderable entity and advance its per-player visual state. */
  private toDrawable(source: DrawableSource, dt: number): DrawablePlayer {
    const config = this.config!;
    const { id, x, y, vx, vy, moving, alive } = source;

    this.visuals.emitFootsteps(id, x, y, vx, vy, moving && alive, this.effects, config);
    const recoil = this.visuals.recoilOf(id);

    return {
      id,
      name: source.name,
      color: source.color,
      x,
      y,
      ax: source.ax,
      ay: source.ay,
      hp: source.hp,
      maxHp: config.maxHp,
      alive,
      moving,
      animTime: this.visuals.advanceAnim(id, moving, dt),
      isLocal: source.isLocal,
      hitFlash: this.visuals.hitFlashAmount(id),
      recoilX: recoil.x,
      recoilY: recoil.y,
    };
  }

  /** 0..1 screen danger from local HP. Dead = no vignette (respawn clean). */
  private dangerLevel(): number {
    const local = this.local;
    const config = this.config;
    if (!local || !config || !local.alive) return 0;
    const ratio = local.hp / config.maxHp;
    if (ratio >= DANGER_START) return 0;
    if (ratio <= DANGER_CRITICAL) {
      return 0.72 + (1 - ratio / DANGER_CRITICAL) * 0.28;
    }
    return ((DANGER_START - ratio) / (DANGER_START - DANGER_CRITICAL)) * 0.72;
  }

  // --- hud -----------------------------------------------------------------
  private patchHud(patch: Partial<HudSnapshot>): void {
    this.hud.update((previous) => ({ ...previous, ...patch }));
  }

  /** Republish HUD state at HUD_INTERVAL — text does not need 60 Hz. */
  private publishHud(dt: number): void {
    this.hudTimer += dt;
    if (this.hudTimer < HUD_INTERVAL) return;
    this.hudTimer = 0;

    const meta = this.localMeta;
    const local = this.local;
    const config = this.config;

    this.patchHud({
      vitals:
        meta && local && config
          ? {
              name: meta.name,
              color: meta.color,
              kills: meta.kills,
              deaths: meta.deaths,
              hp: local.hp,
              maxHp: config.maxHp,
              alive: local.alive,
            }
          : null,
      net: {
        players: this.snapshots.latest?.players.size ?? 0,
        rttMs: this.connection.rtt,
        interpMs: Math.round(this.snapshots.effectiveDelay(this.connection.rtt)),
        pending: local?.pending.length ?? 0,
        fps: Math.round(this.fps),
      },
    });
  }
}
