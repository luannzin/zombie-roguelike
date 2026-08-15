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

import { clamp01 } from '../lib/math';
import type { Connection, ConnectionStatus, Unsubscribe } from '../net/connection';
import type {
  AttackEvent,
  EnemyTypeConfig,
  GameConfig,
  InputPacket,
  KillEvent,
  PickupEvent,
  PlayerMeta,
  ServerMessage,
  SnapshotMessage,
  WelcomeMessage,
  ZoneInfo,
} from '../net/protocol';
import { Camera } from '../render/camera';
import { projectionFor } from '../render/projection';
import { FovField, type LightSource, type VisionConfig, type Viewer } from '../render/fov';
import { Minimap, type MinimapPlayer } from '../render/minimap';
import { Renderer } from '../render/renderer';
import { SpriteBook } from '../render/sprites';
import { tileHash } from '../render/terrain';
import type { DrawableCoin, DrawableEntity } from '../render/types';
import { whenFontsReady } from '../theme/fonts';
import { palette } from '../theme/palette';
import { hitscan, type RayTarget } from './combat';
import { Effects } from './effects';
import { EntityVisuals } from './entity-visuals';
import { EMPTY_HUD, HUD_INTERVAL, type HudSnapshot, type HudStore } from './hud-store';
import { InputController } from './input';
import { Lantern } from './lantern';
import { SnapshotBuffer, type RenderedEnemy, type RenderedPlayer } from './interpolation';
import { LocalPlayer } from './prediction';
import { hearthMask, TileMap } from './world';
import {
  clearTooltipAnchors,
  dropTooltipAnchor,
  writeTooltipAnchor,
} from './tooltip-anchors';

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
/**
 * How far above the fire's base the ready tooltip sits, in tiles. The
 * campfire sprite is 1.75 tiles tall; this clears the flames by a bit.
 */
const FIRE_TOOLTIP_LIFT_TILES = 2.5;
/** Sprite sheet for players. Enemy sheets are named by the server's config. */
const PLAYER_SHEET = 'player';
/** Fallback if welcome.config.coinSprite is missing (older server). */
const COIN_SHEET = 'coin';
/**
 * Only used against a server too old to send vision numbers. A missing value
 * would otherwise put NaN through the light field and black out the screen.
 */
const VISION_FALLBACK: VisionConfig = {
  ambientTiles: 3.5,
  lanternTiles: 11,
  coneDegrees: 75,
};
/**
 * Below this much light an enemy is invisible; above the second it is solid.
 *
 * The floor is tiny because the fov lays a near-zero SIGHT wash over what the
 * player can see (see fov.ts — everything in line of sight with the lamp on,
 * the naked-eye cone with it off): a zombie standing in that wash and nothing
 * else lands around 25% alpha — a shape you notice moving and cannot identify —
 * and only resolves properly once the beam actually reaches it. A zombie
 * outside the wash gets no light at all and is not drawn.
 */
const ENEMY_HIDE_LIGHT = 0.012;
const ENEMY_SHOW_LIGHT = 0.3;

/**
 * Seconds after arriving in a zone before the player gets the controls back.
 *
 * The lobby has just pushed the camera onto their character; this is the beat
 * that follows, and it is doing real work rather than being a pause. The world
 * is on screen with NO HUD over it and the character standing still, facing the
 * camera — so what the player reads, in order, is: this is the same clearing I
 * was just looking at, that one is me, and it is called Preparação, Dia 1. Hand
 * back movement any earlier and half of them are walking before the title has
 * finished saying where they are.
 *
 * The title card (components/hud/ZoneTitle) is sized to clear just before this
 * ends, so the HUD arrives into an empty frame rather than under the type.
 */
const INTRO_TIME = 3;
/** Which way the character faces while the intro holds them. Down = at you. */
const INTRO_AIM_X = 0;
const INTRO_AIM_Y = 1;
/** Walk-out faces the black exit, which is always east of the fire. */
const DEPART_AIM_X = 1;
const DEPART_AIM_Y = 0;

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
  ready: boolean;
}

export interface GameOptions {
  canvas: HTMLCanvasElement;
  minimapCanvas: HTMLCanvasElement;
  hud: HudStore;
  /**
   * The room socket, opened and owned by the session (see
   * `hooks/useRoomSession`) — it was already carrying the lobby before this
   * game existed. `Game` subscribes to it and never closes it.
   */
  connection: Connection;
  /** The `welcome` that started this run; it arrived before `start()` ran. */
  welcome: WelcomeMessage;
  /**
   * Fired once, after the first frame that actually drew the world.
   *
   * The lobby is still on screen at that point, holding the frame its camera
   * landed on, and it is what the player is looking at until this says the
   * arena has something to show. Between mounting and this callback the game
   * canvas is a blank rectangle — the sheets are loading, the terrain is
   * baking — and cutting to it on mount is a black flash in the middle of the
   * transition. See `screens/RoomScreen`.
   */
  onFirstFrame?: () => void;
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
  /** The local player's lamp. Remotes use the `lantern` flag on their snapshot. */
  private readonly lantern = new Lantern();

  /** The welcome this game was built from, applied once `start()` is ready. */
  private readonly initialWelcome: WelcomeMessage;
  private readonly subscriptions: Unsubscribe[] = [];
  /** Cleared after it fires, so the handover can only happen once. */
  private onFirstFrame: (() => void) | null = null;

  private renderer: Renderer | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private rafId: number | null = null;
  private started = false;
  private disposed = false;

  private world: TileMap | null = null;
  private config: GameConfig | null = null;
  /** Where the run is and how it behaves. Rebuilt from every `welcome`. */
  private zone: ZoneInfo | null = null;
  /** The world's own lights — bonfires. Derived from the map, never a message. */
  private lights: LightSource[] = [];
  /** Team light + explored memory. Rebuilt per map, updated per frame. */
  private fov: FovField | null = null;
  private localId = '';
  private local: LocalPlayer | null = null;
  private localMeta: PlayerMeta | null = null;
  /**
   * Names, colours and score boards, keyed by player id. Snapshots carry only
   * what moves; this is refreshed from the roster they attach a few times a
   * second (see net/protocol).
   */
  private readonly roster = new Map<string, PlayerMeta>();
  /**
   * Local ready flag, flipped optimistically on keypress so the prompt answers
   * instantly, and overwritten by the server's own row on the next snapshot.
   */
  private localReady = false;

  private accumulator = 0;
  private lastFrame = 0;
  private localFireCooldown = 0;
  private hudTimer = 0;
  /** Seconds of the arrival hold still to run. 0 = the player has the controls. */
  private introLeft = 0;
  /** Camp walk-out: local prediction is off, camera follows the party. */
  private departing = false;
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
    this.connection = options.connection;
    this.initialWelcome = options.welcome;
    this.onFirstFrame = options.onFirstFrame ?? null;
    this.input = new InputController(options.canvas);
    // The lamp itself decides whether it may light — a zone that forbids it
    // still has to ANSWER the key, or pressing F in the camp is indistinguishable
    // from a broken keybind. See `Lantern.toggle`.
    this.input.onToggleLantern = () => this.lantern.toggle();
    this.input.onReady = () => this.sendReady();
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

    this.subscriptions.push(
      this.connection.onStatus((status) => this.onStatus(status)),
      this.connection.onMessage((msg) => this.onMessage(msg)),
    );
    // The socket has been open since the lobby, so `welcome` landed before this
    // object existed. Replaying it here is what builds the world — snapshots
    // arriving in the gap were dropped by `onSnapshot`'s own guard.
    this.onWelcome(this.initialWelcome);

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
    // Never leave the screen waiting on a game that is gone.
    this.onFirstFrame = null;

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;

    // Unsubscribe, never close: the session owns the socket and the player may
    // be dropping back to a lobby that is still live on it.
    for (const unsubscribe of this.subscriptions.splice(0)) unsubscribe();
    this.input.dispose();
    this.renderer?.dispose();
    this.renderer = null;
    this.minimap.setWorld(null);

    this.visuals.clear();
    this.effects.clear();
    this.snapshots.clear();
    this.lantern.reset();
    clearTooltipAnchors();
    this.world = null;
    this.fov = null;
    this.zone = null;
    this.departing = false;
    this.lights = [];
    this.local = null;
    this.localMeta = null;
    this.roster.clear();

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
      this.fov = null;
      this.minimap.setWorld(null);
      this.visuals.clear();
      this.effects.clear();
      this.snapshots.clear();
      this.lantern.reset();
      this.lights = [];
      this.roster.clear();
      this.patchHud({
        connection: status,
        status: 'disconnected — retrying…',
        inArena: false,
        vitals: null,
        lantern: null,
        arrival: null,
        introducing: false,
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
    this.zone = msg.zone;
    this.world = new TileMap(msg.map);
    // A new map is a new forest: nothing has been explored yet.
    this.fov = new FovField(this.world.width, this.world.height);
    this.localId = msg.playerId;
    this.localMeta = msg.player;
    // Seeds the cache: the first snapshot may land before the first roster.
    this.roster.clear();
    this.roster.set(msg.player.id, msg.player);
    this.localReady = msg.player.ready ?? false;
    // Keep numbering inputs above what the server already processed. The camp
    // walk-out alone can leave last_processed_seq in the hundreds; a fresh
    // LocalPlayer at 0 would have every later packet dropped as a replay, and
    // you spawn in the forest unable to leave the tile.
    const continued = this.local?.sequence ?? 0;
    const ack = msg.ack ?? 0;
    this.local = new LocalPlayer(msg.player, {
      sequence: Math.max(continued, ack),
      lastAck: ack,
    });

    // Bonfires are read off the tiles, not off a message: the fire that blocks
    // you, the fire you can see and the fire that lights you are one tile.
    this.lights = this.world.fires.map((fire, index) => ({
      id: index,
      x: fire.x,
      // Lifted off the contact row — the light comes from the flame, not from
      // the ashes — so the pool is centred on the fire rather than in front of it.
      y: fire.y - msg.config.tileSize * 0.5,
      radiusTiles: msg.config.campfireLightTiles,
    }));
    // Nothing grows in the hearth: a fern in front of a player hides the
    // character somebody is looking for. Cleared here rather than left over
    // from a previous zone, since a forest wants undergrowth everywhere.
    this.renderer?.setDecorationMask(
      hearthMask(
        this.world,
        msg.config.hearthTiles,
        msg.config.ringTilesX / msg.config.ringTilesY,
        tileHash,
      ),
    );

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
    // A new world hands you a fresh battery, switched off: the first thing the
    // player does in the dark is press F, which is how the mechanic teaches.
    // A zone that forbids the lamp is a zone where that press has to fail
    // audibly instead of silently.
    this.lantern.reset();
    this.lantern.allowed = msg.zone.lantern;
    this.time = 0;
    this.localFireCooldown = 0;
    this.accumulator = 0;
    this.smoothX = msg.player.x;
    this.smoothY = msg.player.y;
    this.departing = false;
    // Held still, facing the camera, while the zone names itself.
    this.introLeft = INTRO_TIME;
    this.aimX = INTRO_AIM_X;
    this.aimY = INTRO_AIM_Y;

    // Size the canvas NOW rather than on the first frame. The lobby has just
    // finished pushing in onto this exact player at this exact scale (see
    // `LobbyScene.beginLaunch`), and the first frame drawn here has to land on
    // top of the last frame drawn there — a canvas that is still zero-width
    // would frame it wrong and then correct itself in front of the player.
    if (this.renderer) {
      this.renderer.resize();
      this.resizeDirty = false;
    }
    this.camera.resize(this.canvas.width, this.canvas.height);
    this.camera.snapTo(msg.player.x, msg.player.y, this.world);
    this.minimap.setWorld(this.world);

    this.patchHud({
      inArena: true,
      status: msg.zone.hostile ? 'em campo' : 'no acampamento',
      zone: msg.zone,
      arrival: { key: msg.zone.key, zone: msg.zone },
      introducing: true,
      cinematic: false,
      ready: null,
      prompt: null,
    });
  }

  private onSnapshot(msg: SnapshotMessage): void {
    if (!this.world || !this.config || !this.local) return;
    if (msg.zoneKey && this.zone && msg.zoneKey !== this.zone.key) return;

    this.snapshots.push(msg, performance.now());
    const wasDeparting = this.departing;
    this.departing = Boolean(msg.departing) && this.zone?.kind === 'camp';
    if (this.departing && !wasDeparting) {
      this.patchHud({ cinematic: true, prompt: null, ready: null });
    }

    if (msg.roster) {
      for (const meta of msg.roster) this.roster.set(meta.id, meta);
      const mine = this.roster.get(this.localId);
      if (mine) this.localMeta = mine;
    }

    for (const state of msg.players) {
      if (state.id === this.localId) {
        this.localReady = state.ready ?? false;
        if (this.departing) {
          this.local.state.x = state.x;
          this.local.state.y = state.y;
          this.local.state.vx = state.vx;
          this.local.state.vy = state.vy;
          this.local.state.ax = state.ax;
          this.local.state.ay = state.ay;
          this.local.pending = [];
          this.local.lastAck = state.seq;
        } else {
          this.local.reconcile(state, state.seq, this.world, this.config);
        }
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
      const shooter = this.roster.get(shot.by);
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

    // The arrival hold. It runs on the render clock rather than the tick so it
    // ends on the same frame the HUD and the title card are cut to, whatever
    // the frame rate is doing — and the HUD is told the moment it does, not on
    // the next 5 Hz republish, because a fifth of a second is visible on a cut.
    if (this.introLeft > 0) {
      this.introLeft = Math.max(0, this.introLeft - dt);
      if (this.introLeft === 0) this.patchHud({ introducing: false });
    }

    if (this.world && this.config && this.local) {
      // Aim updates every frame, not every tick, so the crosshair never feels
      // capped at the simulation rate. Not while the intro holds them: the
      // character is facing the camera on purpose, and a cursor that had drifted
      // across the window would spin them the moment the frame opened.
      if (this.introLeft === 0 && !this.departing) this.updateAim();

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
      if (this.departing) {
        this.followDepartCamera(dt);
      } else {
        this.camera.follow(smooth.x, smooth.y, this.world, dt);
      }
    }

    this.effects.update(dt);
    this.visuals.update(dt);
    // Dying puts the lamp out: no drain while you are down, and you come back
    // holding a dark lantern.
    this.lantern.update(dt, this.local?.alive === true);
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
    if (!this.departing) {
      local.predict(packet, world, config);
    }
    this.connection.send(packet);

    if (this.departing) return;

    if (this.localFireCooldown > 0) {
      this.localFireCooldown = Math.max(0, this.localFireCooldown - dt);
    }
    if (packet.shoot && local.alive && this.localFireCooldown === 0) {
      this.localFireCooldown = config.fireCooldown;
      this.predictShot();
    }
  }

  /**
   * Current keys + aim as a packet. Sequence 0 means "scratch, never sent".
   *
   * Two masks, both applied HERE rather than at the input layer. `shoot` is
   * dropped in a safe zone because the server drops it too (see
   * `Room.handle_shooting`), and everything is dropped during the arrival hold
   * — the packet is what prediction replays, so a key filtered anywhere else
   * would still move the character locally and then be yanked back.
   */
  private liveInput(sequence = 0): InputPacket {
    if (this.introLeft > 0 || this.departing) {
      return {
        type: 'input',
        sequence,
        movement: { up: false, down: false, left: false, right: false },
        aim: this.departing
          ? { x: DEPART_AIM_X, y: DEPART_AIM_Y }
          : { x: INTRO_AIM_X, y: INTRO_AIM_Y },
        shoot: false,
        lantern: this.lantern.on,
      };
    }
    return {
      type: 'input',
      sequence,
      movement: { ...this.input.movement },
      aim: { x: this.aimX, y: this.aimY },
      shoot: this.input.shooting && this.zone?.hostile !== false,
      lantern: this.lantern.on,
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
    const sampled = this.snapshots.sample(
      now,
      this.departing ? undefined : this.localId,
      this.connection.rtt,
    );

    // The tick on a nameplate answers "who are we waiting on", which is only a
    // question at the camp. Everywhere else the flag is stale the moment the
    // party walks out, so it is dropped here rather than trusted downstream.
    const preparing = this.zone?.kind === 'camp' && !this.departing;

    for (const remote of sampled.players) {
      const meta = this.roster.get(remote.id);
      entities.push(
        this.toDrawablePlayer(
          {
            ...remote,
            // A player who joined in the last few ticks has no roster row yet;
            // they are drawn as a body without a label rather than skipped.
            name: meta?.name ?? '',
            color: meta?.color ?? palette().effects.fallbackShot,
            isLocal: remote.id === this.localId,
            ready: preparing && (remote.ready ?? false),
          },
          dt,
        ),
      );
    }

    if (!this.departing && this.local && this.localMeta) {
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
            // Your own tick comes from the optimistic flag, not the snapshot,
            // so pressing E marks your plate on the same frame it hides the
            // prompt instead of an RTT later.
            ready: preparing && this.localReady,
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

    this.updateVision(sampled.players, dt);
    this.applyVisibility(entities);
    this.syncTooltipAnchors();

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      entities,
      coins,
      effects: this.effects,
      fov: this.fov,
      danger: this.dangerLevel(),
      time: this.time,
      dt,
    });
    this.minimap.draw(toMinimap(entities), this.localId, this.fov);

    // There is now a world on this canvas. Whoever was covering for it can
    // stop. Fired here rather than from `start()` because the expensive part
    // is not loading, it is the first draw: the terrain layer bakes the whole
    // map into its cache on this call.
    const ready = this.onFirstFrame;
    if (ready) {
      this.onFirstFrame = null;
      ready();
    }
  }

  /**
   * Refresh the team's light. Every living PLAYER with the lamp on is a
   * viewer — remotes included, which is what makes vision shared. Their
   * switch arrives on the snapshot; only the local lamp has a battery.
   *
   * The world's own lights go in alongside them. In the camp they are the only
   * ones there are: lanterns are off by rule, and the bonfire is what lets the
   * party see each other.
   */
  private updateVision(remotes: RenderedPlayer[], dt: number): void {
    const fov = this.fov;
    const world = this.world;
    const config = this.config;
    if (!fov || !world || !config) return;

    const viewers: Viewer[] = [];
    if (this.local?.alive) {
      viewers.push({
        id: this.localId,
        x: this.smoothX,
        y: this.smoothY,
        ax: this.aimX,
        ay: this.aimY,
        lantern: this.lantern.output,
      });
    }
    for (const remote of remotes) {
      if (!remote.alive) continue;
      viewers.push({
        id: remote.id,
        x: remote.x,
        y: remote.y,
        ax: remote.ax,
        ay: remote.ay,
        lantern: remote.lantern ? 1 : 0,
      });
    }

    fov.update(
      world,
      viewers,
      this.lights,
      {
        ambientTiles: config.visionAmbientTiles ?? VISION_FALLBACK.ambientTiles,
        lanternTiles: config.visionLanternTiles ?? VISION_FALLBACK.lanternTiles,
        coneDegrees: config.visionConeDegrees ?? VISION_FALLBACK.coneDegrees,
      },
      this.time,
      dt,
    );
  }

  /**
   * Hide enemies the team has no light on.
   *
   * Runs after `updateVision` because it reads the light that pass just wrote.
   * The threshold has a soft band rather than a hard cut: a zombie crossing the
   * edge of the beam fades in over a few frames instead of blinking into
   * existence, which is the difference between "something stepped into my
   * light" and "a sprite was toggled".
   */
  private applyVisibility(entities: DrawableEntity[]): void {
    const fov = this.fov;
    const world = this.world;
    if (!fov || !world) return;
    const ts = world.tileSize;

    for (const entity of entities) {
      if (entity.kind === 'player') continue;
      const lit = fov.lightAt(Math.floor(entity.x / ts), Math.floor(entity.y / ts));
      entity.visibility = clamp01((lit - ENEMY_HIDE_LIGHT) / (ENEMY_SHOW_LIGHT - ENEMY_HIDE_LIGHT));
    }
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
      ready: source.ready,
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
      // Teammates are never hidden by the dark; only enemies are.
      visibility: 1,
      // Players notice nothing and see no cone — that is their own fov field.
      awareness: 0,
      viewRange: 0,
      viewDegrees: 0,
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
      ready: false,
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
      // Overwritten by applyVisibility once the light field is current.
      visibility: 0,
      // The detection meter and the wedge it colours. A server too old to send
      // either leaves the cone off rather than inventing one.
      awareness: enemy.aw ?? 0,
      viewRange: this.sightReach(type),
      viewDegrees: type.viewDegrees ?? 0,
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

  /**
   * How far this creature can see THE LOCAL PLAYER right now, in world px.
   *
   * Sight is symmetric and the dark is shared, so the answer depends on the
   * lamp: a shape gets `viewRange`, a shape holding a lantern gets
   * `viewRangeLit` (see server/app/config.py). Drawn from the local battery's
   * `output` rather than the switch, so the cones stretch out as the lamp comes
   * up and pull back in as it dies — the player watches the reach of every
   * enemy on screen answer their own key. The server switches on the boolean;
   * the few frames of fade where the two disagree cost nothing and read far
   * better than a snap.
   */
  private sightReach(type: EnemyTypeConfig): number {
    const dark = type.viewRange ?? 0;
    const lit = type.viewRangeLit ?? dark;
    return dark + (lit - dark) * clamp01(this.lantern.output);
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
      // Republished every HUD tick rather than once at the end of the hold: the
      // store is a snapshot, and a one-shot flip would be lost if a reconnect
      // rewrote the snapshot underneath it.
      introducing: this.introLeft > 0,
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
      lantern: local ? this.lantern.reading() : null,
      cinematic: this.departing,
      ready: this.readyCount(),
      prompt: this.readyPrompt(),
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

  private sendReady(): void {
    if (this.departing || this.introLeft > 0) return;
    if (this.zone?.kind !== 'camp') return;
    if (!this.nearFire()) return;
    this.connection.send({ type: 'ready' });
    this.localReady = !this.localReady;
  }

  private nearFire(): boolean {
    const world = this.world;
    const config = this.config;
    const local = this.local;
    if (!world || !config || !local) return false;
    const fire = world.fires[0];
    if (!fire) return false;
    const range = (config.readyRangeTiles ?? config.hearthTiles) * config.tileSize;
    const feetY = local.state.y + config.playerHalfHeight;
    return Math.hypot(local.state.x - fire.x, feetY - fire.y) <= range;
  }

  private readyCount(): { here: number; total: number } | null {
    if (this.zone?.kind !== 'camp' || this.departing) return null;
    const latest = this.snapshots.latest;
    if (!latest || latest.players.size === 0) return { here: 0, total: 1 };
    let here = 0;
    for (const player of latest.players.values()) {
      const ready = player.id === this.localId ? this.localReady : player.ready;
      if (ready) here += 1;
    }
    return { here, total: latest.players.size };
  }

  private readyPrompt(): 'ready' | null {
    if (this.zone?.kind !== 'camp' || this.departing || this.introLeft > 0) return null;
    if (this.localReady) return null;
    return this.nearFire() ? 'ready' : null;
  }

  /**
   * Pin world tooltips to the same camera the canvas just used.
   *
   * Show/hide is still `hud-store` (5 Hz). This only writes screen pixels so
   * the tooltip can sit on the fire without a React render.
   */
  private syncTooltipAnchors(): void {
    if (this.readyPrompt() !== 'ready' || !this.world || !this.config) {
      dropTooltipAnchor('ready');
      return;
    }
    const fire = this.world.fires[0];
    if (!fire) {
      dropTooltipAnchor('ready');
      return;
    }
    const view = projectionFor(this.camera);
    const lift = this.config.tileSize * FIRE_TOOLTIP_LIFT_TILES;
    writeTooltipAnchor('ready', view.x(fire.x), view.y(fire.y - lift));
  }

  /**
   * Frame the party walking east, looking a little ahead toward the mouth so
   * the exit is in the shot rather than sitting on the cut-off.
   */
  private followDepartCamera(dt: number): void {
    const world = this.world;
    if (!world) return;
    const latest = this.snapshots.latest;
    let cx = this.smoothX;
    let cy = this.smoothY;
    if (latest && latest.players.size > 0) {
      cx = 0;
      cy = 0;
      for (const player of latest.players.values()) {
        cx += player.x;
        cy += player.y;
      }
      cx /= latest.players.size;
      cy /= latest.players.size;
    }
    const mouth = world.exit;
    const look = world.tileSize * 4;
    const targetX = mouth ? cx * 0.55 + (mouth.x + look) * 0.45 : cx + look;
    this.camera.follow(targetX, cy, world, dt);
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
