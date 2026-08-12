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
  AttackEvent,
  EnemyTypeConfig,
  GameConfig,
  InputPacket,
  KillEvent,
  PickupEvent,
  PlayerState,
  ServerMessage,
  SnapshotMessage,
  WelcomeMessage,
} from '../net/protocol';
import { Camera } from '../render/camera';
import { Minimap, type MinimapPlayer } from '../render/minimap';
import { Renderer } from '../render/renderer';
import { SpriteBook } from '../render/sprites';
import type { DrawableCoin, DrawableEntity } from '../render/types';
import { whenFontsReady } from '../theme/fonts';
import { palette } from '../theme/palette';
import { hitscan, type RayTarget } from './combat';
import { Effects } from './effects';
import { EntityVisuals } from './entity-visuals';
import { EMPTY_HUD, HUD_INTERVAL, type HudSnapshot, type HudStore } from './hud-store';
import { InputController } from './input';
import { SnapshotBuffer, type RenderedEnemy } from './interpolation';
import { LocalPlayer } from './prediction';
import { TileMap } from './world';

const MAX_TICKS_PER_FRAME = 5;
/** Camera punch on local fire (miss or hit). */
const FIRE_TRAUMA = 0.16;
/** Extra camera punch when local shot lands on a target. */
const HIT_TRAUMA = 0.12;
/** Camera punch when local player loses HP. */
const HURT_TRAUMA = 0.55;
/** Tiny bump when a coin lands in the pocket. */
const PICKUP_TRAUMA = 0.06;
/** HP ratio where vignette starts (above = none). */
const DANGER_START = 0.45;
/** HP ratio where vignette hits full crush. */
const DANGER_CRITICAL = 0.2;
/** Speed (world px/s) above which the local player reads as walking. */
const MOVING_SPEED = 1;
/** Sprite sheet for players. Enemy sheets are named by the server's config. */
const PLAYER_SHEET = 'player';
/** Fallback if welcome.config.coinSprite is missing (older server). */
const COIN_SHEET = 'coin';

/**
 * Everything `toDrawablePlayer` needs, in the shape both a snapshot-interpolated
 * remote and the locally predicted player can supply.
 */
interface PlayerSource {
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
  private readonly visuals = new EntityVisuals();
  private readonly sprites = new SpriteBook();

  private renderer: Renderer | null = null;
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

    // Wait for the webfont too, so the first frame's labels are not drawn in
    // the fallback face and then visibly swapped. Enemy sheets are NOT loaded
    // here: which ones exist is the server's answer, and it arrives with
    // `welcome` — long before the first zombie does.
    await Promise.all([this.sprites.load([PLAYER_SHEET]), whenFontsReady()]);
    // dispose() can land while these are loading.
    if (this.disposed) return;

    this.renderer = new Renderer(this.canvas, this.sprites);

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
    this.snapshots.clear();
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
      this.snapshots.clear();
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

    // Enemy + coin art are named by the server's config, so a new creature or
    // pickup ships without a client change. Loading is fire-and-forget: the
    // renderer skips any entity whose sheet is not in yet.
    const sheets = [
      ...Object.values(msg.config.enemyTypes).map((t) => t.sprite),
      msg.config.coinSprite || COIN_SHEET,
    ];
    void this.sprites.load(sheets);

    this.visuals.clear();
    this.effects.clear();
    this.snapshots.clear();
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

    // Same rule for enemies: whoever hurt them, they flash.
    for (const enemy of msg.enemies) this.visuals.noteHp(enemy.id, enemy.hp);

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

    for (const attack of msg.attacks) this.onAttack(attack);
    for (const kill of msg.kills) this.onKill(kill);
    for (const pickup of msg.pickups ?? []) this.onPickup(pickup);
  }

  /**
   * An enemy swing. The camera punch for the local player is NOT triggered
   * here — HP loss already does that above, and a blocked swing must not shake
   * the screen for damage it did not deal.
   */
  private onAttack(attack: AttackEvent): void {
    this.visuals.lunge(attack.by, attack.dx, attack.dy);

    // A pack in contact throws several absorbed swings a second; drawing all
    // of them turns the victim into a strobe.
    if (attack.blocked && !this.visuals.allowBlockedVfx(attack.target)) return;

    this.effects.spawnMelee(attack.x, attack.y, attack.dx, attack.dy, attack.dmg, attack.blocked);
  }

  private onKill(kill: KillEvent): void {
    if (kill.kind !== 'enemy') return;
    this.effects.spawnDeath(kill.x, kill.y);
    if (kill.killer === this.localId && kill.xp > 0) {
      this.effects.spawnReward(kill.x, kill.y, `+${kill.xp} xp`);
    }
  }

  private onPickup(pickup: PickupEvent): void {
    if (pickup.by !== this.localId) return;
    this.effects.spawnGoldPickup(pickup.x, pickup.y, pickup.gold);
    this.camera.addTrauma(PICKUP_TRAUMA);
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
    const world_ = this.snapshots.sample(performance.now(), this.localId, this.connection.rtt);

    const hitR = config.playerHitRadius;
    const targets: RayTarget[] = world_.players.map((p) =>
      capsule(p.id, p.x, p.y, config.playerHalfHeight, config.spriteHeight, hitR, p.alive),
    );
    // Enemies are shootable, so the predicted tracer has to stop on them too —
    // otherwise the local shot draws through a zombie the server says it hit.
    for (const enemy of world_.enemies) {
      const type = this.enemyType(enemy.t);
      if (!type) continue;
      targets.push(
        capsule(enemy.id, enemy.x, enemy.y, type.halfHeight, type.spriteHeight, type.hitRadius, true),
      );
    }

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

    const entities: DrawableEntity[] = [];
    const now = performance.now();
    const sampled = this.snapshots.sample(now, this.localId, this.connection.rtt);

    for (const remote of sampled.players) {
      entities.push(this.toDrawablePlayer({ ...remote, isLocal: false }, dt));
    }

    if (this.local && this.localMeta) {
      const { vx, vy } = this.local.state;
      entities.push(
        this.toDrawablePlayer(
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

    for (const enemy of sampled.enemies) {
      const drawable = this.toDrawableEnemy(enemy, dt);
      if (drawable) entities.push(drawable);
    }

    const coins: DrawableCoin[] = sampled.coins.map((coin) => ({
      id: coin.id,
      x: coin.x,
      y: coin.y,
      animTime: this.visuals.advanceAnim(coin.id, true, dt),
    }));

    // Everyone in this frame was touched above; anyone who left — a player who
    // disconnected, an enemy that died — is now unreferenced and gets dropped.
    this.visuals.prune();

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      entities,
      coins,
      effects: this.effects,
      danger: this.dangerLevel(),
      time: this.time,
    });
    this.minimap.draw(toMinimap(entities), this.localId);
  }

  /** Build one renderable player and advance its per-entity visual state. */
  private toDrawablePlayer(source: PlayerSource, dt: number): DrawableEntity {
    const config = this.config!;
    const { id, x, y, vx, vy, moving, alive } = source;

    this.visuals.emitFootsteps(
      id,
      x,
      y,
      vx,
      vy,
      moving && alive,
      this.effects,
      config.playerHalfHeight,
      config.moveSpeed,
    );
    const recoil = this.visuals.recoilOf(id);

    return {
      id,
      kind: 'player',
      sheet: PLAYER_SHEET,
      tint: source.color,
      color: source.color,
      name: source.name,
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
      halfWidth: config.playerHalfWidth,
      halfHeight: config.playerHalfHeight,
    };
  }

  /**
   * Build one renderable enemy. Every number comes from its stat block, so a
   * bigger, tougher creature needs nothing here. Untyped enemies (a server
   * newer than this client) are skipped rather than guessed at.
   */
  private toDrawableEnemy(enemy: RenderedEnemy, dt: number): DrawableEntity | null {
    const type = this.enemyType(enemy.t);
    if (!type) return null;

    const { id, x, y, vx, vy, moving } = enemy;
    this.visuals.emitFootsteps(
      id,
      x,
      y,
      vx,
      vy,
      moving,
      this.effects,
      type.halfHeight,
      this.config!.moveSpeed,
    );
    const recoil = this.visuals.recoilOf(id);

    return {
      id,
      kind: 'enemy',
      sheet: type.sprite,
      // The art carries its own palette; tinting it would flatten the pixels.
      tint: null,
      color: palette().minimap.enemy,
      name: '',
      x,
      y,
      ax: enemy.ax,
      ay: enemy.ay,
      hp: enemy.hp,
      maxHp: type.maxHp,
      alive: true,
      moving,
      animTime: this.visuals.advanceAnim(id, moving, dt),
      isLocal: false,
      hitFlash: this.visuals.hitFlashAmount(id),
      recoilX: recoil.x,
      recoilY: recoil.y,
      halfWidth: type.halfWidth,
      halfHeight: type.halfHeight,
    };
  }

  private enemyType(key: string): EnemyTypeConfig | undefined {
    return this.config?.enemyTypes[key];
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
              level: meta.level,
              xpInLevel: meta.xpInLevel,
              xpToLevel: meta.xpToLevel,
              gold: meta.gold,
            }
          : null,
      net: {
        players: this.snapshots.latest?.players.size ?? 0,
        enemies: this.snapshots.latest?.enemies.size ?? 0,
        rttMs: this.connection.rtt,
        interpMs: Math.round(this.snapshots.effectiveDelay(this.connection.rtt)),
        pending: local?.pending.length ?? 0,
        fps: Math.round(this.fps),
      },
    });
  }
}

/** A vertical full-body hit capsule, the shape server/app/combat.py expects. */
function capsule(
  id: string,
  x: number,
  y: number,
  halfHeight: number,
  spriteHeight: number,
  radius: number,
  alive: boolean,
): RayTarget {
  const feet = y + halfHeight;
  return {
    id,
    x,
    capsuleY0: feet - radius,
    capsuleY1: feet - spriteHeight + radius,
    radius,
    alive,
  };
}

/** Dots for the minimap: same entities, only the fields it needs. */
function toMinimap(entities: DrawableEntity[]): MinimapPlayer[] {
  return entities.map((e) => ({
    id: e.id,
    x: e.x,
    y: e.y,
    color: e.color,
    alive: e.alive,
    kind: e.kind,
  }));
}
