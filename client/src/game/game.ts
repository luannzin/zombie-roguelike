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

import {
  playSfx,
  playSfxAt,
  primeAudio,
  resetSfxState,
  setAudioListener,
  setBedRate,
  setBeds,
  stopBeds,
  throttled,
} from '../audio';
import { clamp01, expDamp } from '../lib/math';
import type { Connection, ConnectionStatus, Unsubscribe } from '../net/connection';
import type {
  AttackEvent,
  EnemyTypeConfig,
  GameConfig,
  InputPacket,
  KillEvent,
  CrateBreakEvent,
  CrateState,
  CorpseState,
  LootPickupEvent,
  LootRarity,
  LootState,
  MeleeConfig,
  PickupEvent,
  PlayerMeta,
  RiftStateRow,
  ServerMessage,
  SnapshotMessage,
  SwingEvent,
  WelcomeMessage,
  WeaponConfig,
  ZoneInfo,
} from '../net/protocol';
import { Camera } from '../render/camera';
import { ARENA_ZOOM } from '../render/framing';
import { gunMuzzle, loadGuns, type GunAtlas } from '../render/guns';
import { projectionFor } from '../render/projection';
import { riftResidue, type ResidueMark } from '../render/residue';
import { FovField, type LightSource, type VisionConfig, type Viewer } from '../render/fov';
import { DEATH_TIME, POOL_GROW, poolRadius, poolWetness } from '../render/layers/corpses';
import { soilAt } from '../render/layers/terrain';
import { setClimate } from '../render/wind';
import { Minimap, type MinimapPlayer } from '../render/minimap';
import { Renderer } from '../render/renderer';
import { SpriteBook } from '../render/sprites';
import { NOTICE_AT } from '../render/layers/vision';
import { tileHash } from '../render/terrain';
import type { DrawableCoin, DrawableCorpse, DrawableEntity, DrawableLoot } from '../render/types';
import { whenFontsReady } from '../theme/fonts';
import { palette } from '../theme/palette';
import { crateAlongRay, hitscan, type RayTarget } from './combat';
import { Effects, type ShotFeel } from './effects';
import { EntityVisuals, hitPower, type BloodStain } from './entity-visuals';
import {
  EMPTY_HUD,
  HUD_INTERVAL,
  type HudHotbar,
  type HudInventory,
  type HudLootPrompt,
  type HudSnapshot,
  type HudStore,
} from './hud-store';
import { InputController } from './input';
import { bindInventoryDrop } from './inventory-actions';
import { readInventoryAnchor, clearInventoryAnchors } from './inventory-anchors';
import { Lantern } from './lantern';
import { SnapshotBuffer, type RenderedEnemy, type RenderedPlayer } from './interpolation';
import { clearLootFlies, listLootFlies, spawnLootFly, stepLootFlies } from './loot-flies';
import { warpHudPoint } from '../lib/lens';
import { LocalPlayer } from './prediction';
import { carryBurden } from './simulation';
import { crateFootprint, FLOOR, hearthMask, TileMap } from './world';
import {
  clearTooltipAnchors,
  dropTooltipAnchor,
  writeTooltipAnchor,
} from './tooltip-anchors';

const MAX_TICKS_PER_FRAME = 5;
/** Extra camera punch when local shot lands on a target. */
const HIT_TRAUMA = 0.12;
/** Camera punch when local player loses HP. */
const HURT_TRAUMA = 0.55;
/** Tiny bump when a coin lands in the pocket. */
const PICKUP_TRAUMA = 0.06;
/** Camera punch when an enemy drops. */
const DEATH_TRAUMA = 0.32;
/** How much blood a print loses each stride after leaving a pool. */
const BLOOD_STEP_KEEP = 0.72;
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
/** How far above a drop the collect tooltip sits, in tiles. */
const LOOT_TOOLTIP_LIFT_TILES = 1.1;
/** How far above a crate's contact the smash tooltip sits, in tiles. */
const CRATE_TOOLTIP_LIFT_TILES = 1.4;
/** Smash sheet duration. Matches `make_scenery.py` crate break (8 frames @ 12 fps). */
const CRATE_BREAK_LIFE = 8 / 12;
/** Empty-crate gust. Matches `make_vfx.py` wind (8 frames @ 14 fps). */
const WIND_LIFE = 8 / 14;
/** How far above the console the activate tooltip sits, in tiles. */
const RIFT_TOOLTIP_LIFT_TILES = 1.9;
/**
 * Where inside its own charge the stone actually flashes — `crownAt` in
 * `assets/processed/rift/manifest.json`. The beat fired here has to sit on the
 * frame the sprite whites out, or the shove arrives beside the flash instead
 * of with it. The anomaly's equivalent is `config.rift.boomAt`, which the
 * server computes from the same number.
 */
const RIFT_CROWN_FRACTION = 0.55;
/** Sphere height above its anchor, in world px — where burst debris starts. */
const RIFT_BURST_LIFT = 34;
/** Distance between boot prints, in tiles. One stride, not one frame. */
const FOOTPRINT_STRIDE = 0.9;
/**
 * Seconds a print survives. Long, and deliberately so: on an extraction run
 * the trail you laid walking out is how you find your way back, so it has to
 * outlive the trip that made it.
 */
const FOOTPRINT_LIFE = 75;
/**
 * How lit a body has to be before it marks the ground. Above zero so a
 * creature at the very edge of the beam does not leave a dotted line pointing
 * at itself out in the dark.
 */
const FOOTPRINT_MIN_VISIBILITY = 0.25;
/**
 * Seconds between ambient zombie growls, before jitter.
 *
 * The growl is the game's main horror channel and it is spent carefully. Too
 * often and a pack becomes a drone you stop hearing; this is roughly one every
 * few seconds when creatures are near and nothing at all when they are not.
 * Unlike the sprite, it is NOT gated on visibility — a thing you can hear and
 * cannot see is the entire point, and the lantern is what converts one into
 * the other.
 */
const GROWL_INTERVAL = 3.4;
/** How far a growl can still reach the ear, in tiles. Past the lantern's throw. */
const GROWL_TILES = 17;
/** Minimum seconds between two growls anywhere. Stops a pack stacking. */
const GROWL_SPACING = 0.9;
/**
 * Seconds between the forest's false alarms, before jitter.
 *
 * A branch going somewhere you are not looking, attached to nothing. It works
 * because it is a lie: the player turns, and nothing is there. Rare enough
 * that it never becomes a metronome.
 */
const DREAD_INTERVAL = 38;
/** HP ratio at which the heartbeat bed is at full and running fastest. */
const HEART_FLOOR = 0.15;
/** Playback rate of the heartbeat at `HEART_FLOOR`. 1 = as recorded. */
const HEART_MAX_RATE = 1.55;
/**
 * How well each soil takes a print, indexed the way the terrain atlas orders
 * its grounds: loam, turf, mud, litter. Mud holds one, leaf litter shrugs it
 * off — the same ground the player can see themselves standing on.
 */
const SOIL_PRINT_DEPTH = [0.55, 0.3, 0.85, 0.16];
/** Index of leaf litter in that same order. The one soil that is loud underfoot. */
const LITTER_SOIL = 3;
/**
 * Rarity -> chime variant in the `rarity` sound.
 *
 * The generator renders five tiers of the same instrument, each one more of
 * itself than the last. Ordering it here rather than deriving it from the
 * palette keeps the sound independent of what the colours happen to be.
 */
const RARITY_CHIME: Record<LootRarity, number> = {
  common: 0,
  uncommon: 1,
  rare: 2,
  epic: 3,
  legendary: 4,
};

/** Sprite sheet for players. Enemy sheets are named by the server's config. */
const PLAYER_SHEET = 'player';
/** Fallback if welcome.config.coinSprite is missing (older server). */
const COIN_SHEET = 'coin';
/** Fallback if welcome.config.backpackSprite is missing (older server). */
const BACKPACK_SHEET = 'backpack';
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
  held?: number;
  ads?: boolean;
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
  private guns: GunAtlas | null = null;
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
  /**
   * The world's own lights: bonfires read off the tiles, plus whatever the
   * map's placed scenes are burning. Derived from the map, never a message.
   */
  private lights: LightSource[] = [];
  /** Where each body last put a foot down — see `trackFootsteps`. */
  private readonly strides = new Map<string, { x: number; y: number }>();
  /**
   * Enemies this client has seen while they were already alerting. The hunt
   * diamond may follow them into the dark only then — see `latchAlertMarks`.
   */
  private readonly alertSeen = new Set<string>();
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
  /**
   * What the extraction blast threw on the ground, generated ONCE.
   *
   * Deterministic from the map seed, so every client lays the same field
   * without a byte of it crossing the wire (`render/residue.ts`). Held here
   * rather than on `TileMap` because it is presentation: nothing collides with
   * it, nothing queries it, and the renderer is its only reader.
   */
  private residue: readonly ResidueMark[] = [];
  /** Remaining world drops. Replaced on welcome and on a dirty snapshot. */
  private readonly loot = new Map<string, LootState>();
  /** Dead bodies on this map. Replaced on welcome; upserted from kills. */
  private readonly corpses = new Map<string, LiveCorpse>();
  /** 0..1 blood on each walker's boots, decaying per stride. */
  private readonly bloodWet = new Map<string, number>();
  /** TAB. Client-local — the bag itself is authoritative, the drawer is not. */
  private inventoryOpen = false;
  /** Flies that have landed. HUD reads the count so a bump cannot collapse. */
  private bagCatches = 0;
  /** E on a full bag. Same counter contract as a refused lantern. */
  private bagRefusals = 0;

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
  /** Hotbar slot in hand. -1 is holstered. Client-authored, like the lamp. */
  private heldSlot = 0;
  /** Seconds the trigger has been down. AWP spends this before it fires. */
  private adsHold = 0;
  /**
   * Which beat of the melee chain the next swing is, and how long is left to
   * keep it. A local mirror of `Player.combo_step` / `combo_left` on the
   * server, run off the same numbers in `weapons[k].melee` — the two agree
   * because they are the same arithmetic on the same constants, exactly the
   * way movement prediction does. The wire never carries the counter; the
   * swing event carries the step it WAS, which is what remotes draw.
   */
  private comboStep = 0;
  private comboLeft = 0;
  /** Selection punches. Same counter contract as lantern refusals. */
  private hotbarPicks = 0;
  /** local player position interpolated between fixed ticks (see prediction.ts) */
  private smoothX = 0;
  private smoothY = 0;
  private resizeDirty = true;
  private fps = 0;
  /** Elapsed seconds for vignette heartbeat. */
  private time = 0;
  /** The zone's own ambience, without the heartbeat laid over it. */
  private beds: Record<string, number> = {};
  /** Last published heartbeat level, quantized. -1 forces a republish. */
  private heartLevel = -1;
  /** Countdown to the next ambient growl — see `GROWL_INTERVAL`. */
  private growlLeft = GROWL_INTERVAL;
  /** Countdown to the next false alarm — see `DREAD_INTERVAL`. */
  private dreadLeft = DREAD_INTERVAL;
  /** Enemies already heard alerting, so one hunt makes one snarl. */
  private alertHeard = new Set<string>();

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
    // The lamp decides what happened; the sound reports it. Three outcomes and
    // they must not share a sound: it lit, it went out, or the zone said no.
    // The refusal counter is how the third one is detectable at all.
    this.input.onToggleLantern = () => {
      const before = this.lantern.reading();
      this.lantern.toggle();
      const after = this.lantern.reading();
      if (after.on !== before.on) playSfx(after.on ? 'lantern-on' : 'lantern-off');
      else if (after.refusals !== before.refusals) playSfx('ui-error');
    };
    this.input.onInteract = () => this.sendInteract();
    this.input.onToggleInventory = () => this.toggleInventory();
    this.input.onHotbar = (slot) => this.selectHotbar(slot);
    bindInventoryDrop((slot) => this.requestDrop(slot));
    this.minimap = new Minimap(options.minimapCanvas);
  }

  async start(): Promise<void> {
    if (this.started || this.disposed) return;
    this.started = true;

    // Wait for the webfont too, so the first frame's labels are not drawn in
    // the fallback face and then visibly swapped. Enemy sheets are NOT loaded
    // here: which ones exist is the server's answer, and it arrives with
    // `welcome` — long before the first zombie does.
    await Promise.all([
      this.sprites.load([PLAYER_SHEET, BACKPACK_SHEET]),
      whenFontsReady(),
      loadGuns().then((atlas) => {
        this.guns = atlas;
      }),
    ]);
    // dispose() can land while these are loading.
    if (this.disposed) return;

    // Audio is NOT awaited. A slow decode must never hold the first frame, and
    // the alternative to a sound arriving a moment late is the whole arena
    // arriving a moment late. The list is what must not be silent the first
    // time it happens — the rest decodes on first use.
    void primeAudio([
      'shot',
      'step-soft',
      'step-litter',
      'hurt',
      'zombie-idle',
      'zombie-alert',
      'zombie-attack',
      'zombie-hit',
      'zombie-death',
      'wind',
      'night',
      'rain',
      'fire',
      'heartbeat',
      'arrive',
      'loot',
      'rarity',
      'coin',
      'crate-break',
    ]);

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
    this.corpses.clear();
    this.bloodWet.clear();
    this.snapshots.clear();
    this.alertSeen.clear();
    this.alertHeard.clear();
    // The beds are the one part of the audio graph that outlives a single
    // sound, so they are the one part with a release here. One-shots already
    // in the air are left to finish; cutting them would click.
    stopBeds();
    resetSfxState();
    setClimate('clear');
    this.lantern.reset();
    clearTooltipAnchors();
    clearInventoryAnchors();
    clearLootFlies();
    bindInventoryDrop(null);
    this.inventoryOpen = false;
    this.bagCatches = 0;
    this.bagRefusals = 0;
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
      this.corpses.clear();
      this.bloodWet.clear();
      this.snapshots.clear();
      this.alertSeen.clear();
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
    // A new map is a new forest: nothing has been explored yet, and it has its
    // own rift — so the old map's marks must not survive into it.
    this.fov = new FovField(this.world.width, this.world.height);
    this.residue = [];
    this.ensureResidue();
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
    this.local.carryWeight = msg.player.inv?.w ?? 0;
    this.heldSlot = msg.player.guns?.held ?? 0;
    this.adsHold = 0;
    this.comboStep = 0;
    this.comboLeft = 0;

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
    // Whatever the map's own scenes are still burning, on the same list. The
    // lighting has no concept of "a camp light" versus "a light out in the
    // woods" and must not grow one: a lamp at a dead homestead throws real
    // light, casts real shadows through the trees around it, and is the reason
    // a player crosses half a map to find out what is under it. Ids continue
    // past the fires so a flicker never walks when the list changes length.
    for (const [index, light] of this.world.scenery.lights.entries()) {
      this.lights.push({
        id: this.world.fires.length + index,
        x: light.x,
        y: light.y,
        radiusTiles: light.radiusTiles,
      });
    }
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
    const names = Object.values(msg.config.enemyTypes).flatMap((t) => [
      t.sprite,
      ...(t.variants ?? []),
      ...(t.hats ?? []),
      ...(t.clothes ?? []),
    ]);
    const sheets = [
      ...names,
      ...names.map((name) => `${name}-death`),
      msg.config.coinSprite || COIN_SHEET,
      msg.config.backpackSprite || BACKPACK_SHEET,
    ];
    void this.sprites.load(sheets);

    this.visuals.clear();
    this.effects.clear();
    this.corpses.clear();
    this.bloodWet.clear();
    this.snapshots.clear();
    this.alertSeen.clear();
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
    this.alertHeard.clear();
    this.growlLeft = GROWL_INTERVAL;
    this.dreadLeft = DREAD_INTERVAL;
    // The zone decides what the place sounds like, exactly the way it already
    // decides the title card, whether guns fire and whether the lamp works.
    // Nothing here reads the map to find out where it is.
    this.applyZoneAmbience(msg.zone);
    // The hit the title card lands on. Delayed to sit under the type rather
    // than under the cut: `ZoneTitle` draws its rules first and the word after,
    // and a sting on the first frame would be answering the screen change
    // instead of the name.
    playSfx('arrive', { delay: 0.18, jitter: 0 });
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
      lootPrompt: null,
      inventory: this.inventoryHud(),
      hotbar: this.hotbarHud(),
    });
    this.replaceLoot(msg.loot ?? []);
    this.replaceCorpses(msg.corpses ?? [], true);
  }

  private onSnapshot(msg: SnapshotMessage): void {
    if (!this.world || !this.config || !this.local) return;
    if (msg.zoneKey && this.zone && msg.zoneKey !== this.zone.key) return;

    this.snapshots.push(msg, performance.now());
    const wasDeparting = this.departing;
    this.departing = Boolean(msg.departing) && this.zone?.kind === 'camp';
    if (this.departing && !wasDeparting) {
      this.patchHud({ cinematic: true, prompt: null, ready: null, cratePrompt: false });
      // The walk-out, in one gesture: the bonfire is pulled down to a memory
      // of itself while the corridor's drone comes up under the march. The
      // point of leaving the camp is that the warmth stops, so the fire has to
      // audibly go — but not to nothing, because it is still behind you and
      // the forest `welcome` a few seconds later is what finally cuts it.
      this.beds = { fire: 0.18, wind: 0.5 };
      this.pushBeds();
      playSfx('void', { jitter: 0 });
    }

    if (msg.roster) {
      for (const meta of msg.roster) this.roster.set(meta.id, meta);
      const mine = this.roster.get(this.localId);
      if (mine) {
        this.localMeta = mine;
        if (this.local && mine.inv) this.local.carryWeight = mine.inv.w;
      }
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
        playSfx('hurt');
      }
    }

    // Same rule for enemies: whoever hurt them, they flash.
    for (const enemy of msg.enemies) this.visuals.noteHp(enemy.id, enemy.hp);

    // Own shots were already drawn locally at fire time.
    for (const shot of msg.shots) {
      if (shot.by === this.localId) continue;
      const shooter = this.roster.get(shot.by);
      const hit = shot.hit !== null;
      const weapon = shot.k ? this.config.weapons?.[shot.k] : undefined;
      const body = msg.players.find((p) => p.id === shot.by);
      const origin = this.shotOrigin(
        shot.by,
        shot.k,
        body?.x ?? shot.x,
        body?.y ?? shot.y,
        shot.dx,
        shot.dy,
      );
      const tracer = aimTracer(origin.x, origin.y, shot.x, shot.y, shot.dx, shot.dy, shot.dist);
      this.effects.spawnShot(
        tracer.x,
        tracer.y,
        tracer.dx,
        tracer.dy,
        tracer.dist,
        shooter?.color ?? palette().effects.fallbackShot,
        hit,
        hit ? (shot.dmg ?? weapon?.damage ?? this.config.shotDamage) : undefined,
        hit,
        weapon ? shotFeel(weapon) : undefined,
      );
      this.visuals.kickRecoil(shot.by, shot.dx, shot.dy, weapon?.kick);
      if (weapon) this.visuals.kickGun(shot.by, weapon.gunKick, weapon.gunPump);
      if (shot.hit) {
        const dmg = shot.dmg ?? weapon?.damage ?? this.config.shotDamage;
        this.feelVictim(shot.hit, shot.dx, shot.dy, dmg);
      }
      // A teammate's gun is heard from where they are standing. Same sample as
      // your own; the distance falloff is the whole difference, and it is
      // enough to tell "beside me" from "somewhere over there".
      playSfxAt('shot', shot.x, shot.y, { gain: 0.85 });
      if (hit) playSfxAt('zombie-hit', shot.x + shot.dx * shot.dist, shot.y + shot.dy * shot.dist);
    }

    for (const swing of msg.swings ?? []) this.onSwing(swing, msg);
    for (const attack of msg.attacks) this.onAttack(attack);
    for (const kill of msg.kills) this.onKill(kill);
    for (const pickup of msg.pickups ?? []) this.onPickup(pickup);
    if (msg.loot) this.replaceLoot(msg.loot);
    for (const ev of msg.lootPickups ?? []) this.onLootPickup(ev);
    if (msg.crates) this.replaceCrates(msg.crates);
    for (const ev of msg.crateBreaks ?? []) this.onCrateBreak(ev);
    if (msg.rift) this.onRiftState(msg.rift);
    if (msg.corpses) this.mergeCorpses(msg.corpses);
  }

  /**
   * A player's blade landing. Only connections arrive — the server drops whiffs.
   *
   * Split down the middle by who threw it. The ARC belongs to the swinger and
   * is only drawn for remotes, because the local player has been looking at
   * their own since the frame they clicked and a second one on top is a
   * double image. The BODIES belong to everybody: the local player's
   * prediction deliberately resolved no victims, so the blood, the numbers
   * and the wounds all come from here whoever swung.
   */
  private onSwing(swing: SwingEvent, msg: SnapshotMessage): void {
    const step = this.config?.weapons?.[swing.k]?.melee?.steps?.[swing.step];
    if (!step) return;

    if (swing.by !== this.localId) {
      // Off the live body rather than off the event: the row is up to a tick
      // old and an arc anchored behind a walking teammate reads as lag.
      const body = msg.players.find((p) => p.id === swing.by);
      this.effects.spawnSwing(
        body?.x ?? swing.x,
        body?.y ?? swing.y,
        swing.dx,
        swing.dy,
        step.reach,
        step.arcDegrees,
        step.sweep,
        step.kind === 'cut',
        true,
      );
      this.visuals.kickRecoil(swing.by, -swing.dx, -swing.dy, step.lunge);
      this.visuals.kickGun(swing.by, step.swing, 0);
      playSfxAt('knife-swing', swing.x, swing.y, {
        gain: 0.85,
        variant: Math.min(swing.step, 2),
      });
    }

    for (const hit of swing.hits) {
      // On the BODY, not projected down the aim: the finisher opens up to
      // three of them and a single spray at arm's length would put all the
      // blood in one place regardless of who it came out of.
      const body =
        msg.enemies.find((e) => e.id === hit.id) ?? msg.players.find((p) => p.id === hit.id);
      const hx = body?.x ?? swing.x + swing.dx * step.reach * 0.6;
      const hy = body?.y ?? swing.y + swing.dy * step.reach * 0.6;
      this.feelVictim(hit.id, swing.dx, swing.dy, hit.dmg);
      // A blade opens rather than passes through, so the spray is smaller
      // than a round of the same damage — and the cut still throws more than
      // a slash, off the same ladder every other hit in the game reads.
      this.effects.spawnBlood(hx, hy, swing.dx, swing.dy, 0.4 + hitPower(hit.dmg) * 0.5);
      this.effects.spawnDamage(hx, hy, hit.dmg);
      playSfxAt('knife-hit', hx, hy);
    }
    if (swing.hits.length > 0 && swing.by === this.localId) {
      this.camera.addTrauma(HIT_TRAUMA);
    }
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
    playSfxAt('zombie-attack', attack.x, attack.y, { gain: attack.blocked ? 0.55 : 1 });

    this.effects.spawnMelee(attack.x, attack.y, attack.dx, attack.dy, attack.dmg, attack.blocked);
    // A swing the i-frames ate drew nothing but a deflect arc, and it must not
    // leave a wound either.
    if (!attack.blocked) this.visuals.splatter(attack.target, attack.dx, attack.dy);
  }

  private onKill(kill: KillEvent): void {
    if (kill.kind !== 'enemy') return;
    const dx = kill.dx ?? 0;
    const dy = kill.dy ?? 0;
    this.effects.spawnDeath(kill.x, kill.y, dx, dy);
    this.effects.spawnDeathBurst(kill.x, kill.y + 2, DEATH_TIME);
    playSfxAt('zombie-death', kill.x, kill.y);
    this.camera.addTrauma(DEATH_TRAUMA);
    this.upsertCorpse(kill, this.visuals.stainsOf(kill.victim).map(cloneStain), 0);
    // It stops growling the moment it dies, and re-arms if the id ever returns.
    this.alertHeard.delete(kill.victim);
    if (kill.killer === this.localId && kill.xp > 0) {
      this.effects.spawnReward(kill.x, kill.y, `+${kill.xp} xp`);
    }
  }

  private onPickup(pickup: PickupEvent): void {
    if (pickup.by !== this.localId) return;
    this.effects.spawnGoldPickup(pickup.x, pickup.y, pickup.gold);
    this.camera.addTrauma(PICKUP_TRAUMA);
    playSfx('coin', { gain: 0.9 });
  }

  private replaceLoot(rows: LootState[]): void {
    this.loot.clear();
    for (const row of rows) this.loot.set(row.id, row);
  }

  private replaceCorpses(rows: CorpseState[], landed: boolean): void {
    this.corpses.clear();
    this.bloodWet.clear();
    const age = landed ? POOL_GROW : 0;
    for (const row of rows) this.upsertFromState(row, age);
  }

  private mergeCorpses(rows: CorpseState[]): void {
    for (const row of rows) {
      if (!this.corpses.has(row.id)) this.upsertFromState(row, POOL_GROW);
    }
  }

  private upsertCorpse(kill: KillEvent, stains: BloodStain[], age: number): void {
    if (!kill.t) return;
    this.upsertFromState(
      {
        id: kill.victim,
        x: kill.x,
        y: kill.y,
        t: kill.t,
        v: kill.v ?? 0,
        hat: kill.hat,
        cloth: kill.cloth,
        ax: kill.ax ?? 0,
        ay: kill.ay ?? 1,
        dx: kill.dx ?? 0,
        dy: kill.dy ?? 1,
      },
      age,
      stains,
    );
  }

  private upsertFromState(row: CorpseState, age: number, stains?: BloodStain[]): void {
    const existing = this.corpses.get(row.id);
    if (existing) {
      if (stains && stains.length > 0) existing.stains = stains;
      return;
    }
    const type = this.enemyType(row.t);
    this.corpses.set(row.id, {
      id: row.id,
      x: row.x,
      y: row.y,
      t: row.t,
      v: row.v,
      hat: row.hat,
      cloth: row.cloth,
      ax: row.ax,
      ay: row.ay,
      dx: row.dx,
      dy: row.dy,
      stains: stains ?? [],
      age,
      halfHeight: type?.halfHeight ?? 4,
    });
  }

  /**
   * Dip the boots if this stride landed in a pool, then spend some of that
   * blood on the print. Decays per step, so a trail of red dries out behind
   * you instead of painting the rest of the map.
   */
  private stepBlood(id: string, x: number, footY: number): number {
    let wet = this.bloodWet.get(id) ?? 0;
    for (const body of this.corpses.values()) {
      const px = body.x;
      const py = body.y + body.halfHeight;
      const radius = poolRadius(body.age);
      const dx = x - px;
      const dy = footY - py;
      if (dx * dx + dy * dy > radius * radius) continue;
      wet = Math.max(wet, poolWetness(body.age));
    }
    const print = wet;
    wet *= BLOOD_STEP_KEEP;
    if (wet < 0.04) this.bloodWet.delete(id);
    else this.bloodWet.set(id, wet);
    return print;
  }

  private drawableCorpses(dt: number): DrawableCorpse[] {
    const fov = this.fov;
    const ts = this.config?.tileSize ?? 16;
    const out: DrawableCorpse[] = [];
    for (const body of this.corpses.values()) {
      body.age += dt;
      const type = this.enemyType(body.t);
      if (!type) continue;
      const lit = fov
        ? fov.lightAt(Math.floor(body.x / ts), Math.floor(body.y / ts))
        : 1;
      const visibility = clamp01(
        (lit - ENEMY_HIDE_LIGHT) / (ENEMY_SHOW_LIGHT - ENEMY_HIDE_LIGHT),
      );
      out.push({
        id: body.id,
        x: body.x,
        y: body.y,
        sheet: type.variants?.[body.v] ?? type.sprite,
        gear: corpseGear(type, body.cloth, body.hat),
        ax: body.ax,
        ay: body.ay,
        dx: body.dx,
        dy: body.dy,
        stains: body.stains,
        age: body.age,
        visibility,
        halfHeight: body.halfHeight,
      });
    }
    return out;
  }

  private onLootPickup(ev: LootPickupEvent): void {
    this.loot.delete(ev.id);
    if (ev.by !== this.localId) {
      // Somebody else got it. Heard, not celebrated: the thunk carries across
      // the clearing so the party knows a drop was taken, and the chime that
      // says WHAT it was belongs to whoever is holding it.
      playSfxAt('loot', ev.x, ev.y, { gain: 0.5 });
      return;
    }
    const def = this.config?.loot?.[ev.k];
    if (def) {
      // Two sounds, and the order is the point: the physical one lands on the
      // frame the item leaves the ground, and the chime that names its rarity
      // comes a beat later, on the fly. The player learns the five tiers in
      // one session and after that knows what they picked up before the
      // tooltip has drawn.
      playSfx('loot');
      playSfx('rarity', { variant: RARITY_CHIME[def.rarity], jitter: 0, delay: 0.07 });
      const dest = ev.dest === 'hotbar' ? 'hotbar' : 'bag';
      if (dest === 'bag') this.inventoryOpen = true;
      else if (this.heldSlot < 0) this.heldSlot = ev.slot;
      spawnLootFly({
        id: ev.id,
        key: ev.k,
        frame: def.frame,
        rarity: def.rarity,
        slot: ev.slot,
        dest,
      });
      const inventory = this.inventoryHud();
      const hotbar = this.hotbarHud();
      this.patchHud({
        inventory: inventory ?? undefined,
        hotbar: hotbar ?? undefined,
      });
    }
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
      this.stepScope(dt);

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

    this.stepCollectFlies(dt);
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
    // The chain closes on its own clock, not on the button — which is what
    // lets a player break contact after two slashes and come back to a fresh
    // one instead of an accidental finisher. Mirrors `Room.step_players`.
    if (this.comboLeft > 0) {
      this.comboLeft = Math.max(0, this.comboLeft - dt);
      if (this.comboLeft === 0) this.comboStep = 0;
    }

    const weapon = this.heldWeapon();
    if (weapon?.melee) {
      this.adsHold = 0;
      if (packet.shoot && local.alive && this.localFireCooldown === 0) {
        this.predictSwing(weapon.melee);
      }
      return;
    }
    // Holstering the blade mid-chain abandons it, same as the server.
    this.comboStep = 0;
    this.comboLeft = 0;
    if (packet.shoot && local.alive && weapon) {
      this.adsHold += dt;
      if (this.localFireCooldown === 0 && this.adsHold >= weapon.aimDelay) {
        this.localFireCooldown = weapon.fireCooldown;
        this.predictShot(weapon);
      }
    } else {
      this.adsHold = 0;
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
        held: this.heldSlot,
      };
    }
    return {
      type: 'input',
      sequence,
      movement: { ...this.input.movement },
      aim: { x: this.aimX, y: this.aimY },
      shoot: this.input.shooting && this.zone?.hostile !== false,
      lantern: this.lantern.on,
      held: this.heldSlot,
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
  private predictShot(weapon: WeaponConfig): void {
    const world = this.world!;
    const config = this.config!;
    const recoil = this.visuals.recoilOf(this.localId);
    const gun = this.visuals.gunFeelOf(this.localId);
    const origin = gunMuzzle({
      x: this.smoothX + recoil.x,
      y: this.smoothY + recoil.y,
      ax: this.aimX,
      ay: this.aimY,
      weapon: this.weaponKeyOf(this.localId, this.heldSlot),
      guns: this.guns,
      pump: gun.pump,
      kick: gun.kick,
    });
    const ox = origin.x;
    const oy = origin.y;
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
      weapon.range,
      targets,
      this.localId,
    );
    const crateDist = crateAlongRay(
      world.crates,
      ox,
      oy,
      this.aimX,
      this.aimY,
      result.distance,
      (config.crateHitWTiles ?? 1) * config.tileSize,
      (config.crateHitHTiles ?? 2) * config.tileSize,
    );
    const crateHit = crateDist !== null;
    const distance = crateHit ? crateDist : result.distance;
    const hit = result.target !== null && !crateHit;
    this.effects.spawnShot(
      ox,
      oy,
      this.aimX,
      this.aimY,
      distance,
      this.localMeta?.color ?? palette().effects.fallbackShot,
      hit || crateHit,
      hit ? weapon.damage : undefined,
      hit,
      shotFeel(weapon),
    );
    this.camera.addTrauma(weapon.trauma + (hit || crateHit ? HIT_TRAUMA : 0));
    this.visuals.kickRecoil(this.localId, this.aimX, this.aimY, weapon.kick);
    this.visuals.kickGun(this.localId, weapon.gunKick, weapon.gunPump);
    playSfx('shot');
    if (hit && result.target) {
      this.feelVictim(result.target.id, this.aimX, this.aimY, weapon.damage);
      playSfxAt('zombie-hit', ox + this.aimX * distance, oy + this.aimY * distance);
    }
  }

  /**
   * One beat of the melee chain, thrown locally the frame the button went down.
   *
   * The same three things happen here that happen in `predictShot`, and for
   * the same reason: the arc, the punch and the sound are what the player is
   * buying with the click, and a round trip in front of them is the whole
   * difference between a weapon and a request. The server still decides
   * damage — nothing below reduces anybody's HP.
   *
   * What is NOT predicted is who got opened. `predictShot` runs a local
   * hitscan because it has to know where to stop the tracer; a swing has no
   * length to resolve, so it draws its own reach and lets the authoritative
   * `swings` row bring back the blood and the numbers. Predicting victims
   * would mean drawing a wound on a zombie the server says was out of the
   * arc, and the wound is the one effect here that lasts long enough to be
   * a lie.
   */
  private predictSwing(melee: MeleeConfig): void {
    const steps = melee.steps;
    if (steps.length === 0) return;
    const index = this.comboStep % steps.length;
    const step = steps[index];

    this.localFireCooldown = step.cooldown;
    if (step.window > 0) {
      this.comboStep = index + 1;
      this.comboLeft = step.cooldown + step.window;
    } else {
      this.comboStep = 0;
      this.comboLeft = 0;
    }

    // Thrown from the BODY, not the barrel. The arc is centred on the same
    // point the server sweeps from, so what is drawn is the reach that was
    // actually tested rather than a shape hanging off the sprite.
    this.effects.spawnSwing(
      this.smoothX,
      this.smoothY,
      this.aimX,
      this.aimY,
      step.reach,
      step.arcDegrees,
      step.sweep,
      step.kind === 'cut',
      // A local swing does not know yet. Drawn as a whiff and left alone:
      // the landed version arrives with the blood, a fifth of a second later,
      // and thickening a stroke after the fact is a flicker.
      false,
    );
    this.camera.addTrauma(step.trauma);
    // Forward, not back: a swing carries you into it. `kickRecoil` takes the
    // direction it should push AGAINST, so the aim is negated to lunge along it.
    this.visuals.kickRecoil(this.localId, -this.aimX, -this.aimY, step.lunge);
    this.visuals.kickGun(this.localId, step.swing, 0);
    playSfx('knife-swing', { variant: Math.min(index, 2) });
  }

  // --- sound ---------------------------------------------------------------
  //
  // Two kinds of sound and they are driven from two different places. EVENTS
  // (a shot, a hit, a crate) are played by the handler that already knows the
  // event happened, right next to the visual effect it belongs with — one
  // thing occurred, so it is fired once, in one place. STATE (which ambience
  // is playing, how fast the heart is going, whether anything is growling out
  // there) is reconciled every frame from what is on screen, because it is a
  // continuous property of the world rather than a thing that happened.
  //
  // Nothing here reads the map to decide where it is: the zone says.

  /**
   * One footfall, coloured by what is under it and how loaded the walker is.
   *
   * Called from `trackFootsteps`, which means it inherits that loop's
   * visibility gate: a body the light does not reach makes no sound. For
   * prints that rule exists so a trail cannot appear out of the dark; here it
   * means the unlit half of the forest speaks through GROWLS instead of
   * footsteps, which keeps the two channels saying different things. Moving
   * the call outside the gate is the one-line version of the other choice.
   */
  private playStep(entity: DrawableEntity, tx: number, ty: number, burden: number): void {
    const world = this.world;
    if (!world) return;
    const inside = tx >= 0 && ty >= 0 && tx < world.width && ty < world.height;
    const soil = inside ? soilAt(tx, ty, world.seed) : 0;
    const load = Math.min(1, burden);
    playSfxAt(
      soil === LITTER_SOIL ? 'step-litter' : 'step-soft',
      entity.x,
      entity.y + entity.halfHeight,
      {
        // Enemies tread quieter than the party: the growl is their channel,
        // and a pack of six all crunching leaves buries everything else.
        gain: (entity.kind === 'enemy' ? 0.5 : 0.95) * (1 + load * 0.3),
        // A full pack lands lower and slower.
        rate: 1 - load * 0.12,
      },
    );
  }

  /** What this place sounds like. Restated on every arrival, and only there. */
  private applyZoneAmbience(zone: ZoneInfo): void {
    const weather = zone.weather ?? 'clear';
    setClimate(weather);
    this.beds =
      zone.kind === 'camp'
        ? // The bonfire is the camp's whole bed. It is not positional — the
          // clearing is small enough that being "away from the fire" is not a
          // place you can stand, and a panning hearth would swing every time
          // the camera drifted.
          { fire: 1, wind: 0.22 }
        : weather === 'rain'
          ? { wind: 0.55, night: 0.35, rain: 1 }
          : weather === 'fog'
            ? { wind: 0.4, night: 1 }
            : { wind: 1, night: 0.85 };
    this.heartLevel = -1;
    this.pushBeds();
  }

  /** Send the current bed mix. The heartbeat rides on top of the zone's own. */
  private pushBeds(): void {
    setBeds(this.heartLevel > 0 ? { ...this.beds, heartbeat: this.heartLevel } : this.beds);
  }

  /**
   * Per-frame audio state. Called from `render` with the entities it just
   * built, so awareness and visibility are already resolved on them.
   */
  private updateAudio(dt: number, entities: DrawableEntity[]): void {
    const world = this.world;
    if (!world) return;

    // Everything spatial is measured from the ear, and the ear is the player.
    // Not the camera: during the walk-out the camera looks ahead at the VOID
    // mouth, and a party marching away from a fire that got LOUDER would be
    // the wrong story told very precisely.
    setAudioListener(this.smoothX, this.smoothY, world.tileSize);

    this.updateHeartbeat();
    if (this.zone?.hostile !== true || this.introLeft > 0) return;

    this.updateGrowls(dt, entities);

    this.dreadLeft -= dt;
    if (this.dreadLeft <= 0) {
      this.dreadLeft = DREAD_INTERVAL * (0.6 + Math.random() * 0.8);
      // Placed off to one side at a plausible distance rather than at a real
      // point in the world, because there is nothing there. It only has to
      // arrive from a direction.
      const angle = Math.random() * Math.PI * 2;
      const reach = world.tileSize * (9 + Math.random() * 7);
      playSfxAt(
        'dread',
        this.smoothX + Math.cos(angle) * reach,
        this.smoothY + Math.sin(angle) * reach,
      );
    }
  }

  /**
   * The heart, as one looping buffer played faster and louder as HP falls.
   *
   * It shares its threshold with the danger vignette on purpose: the screen
   * closing in and the pulse coming up are one effect delivered on two
   * channels, and a player who has the sound off still gets the whole message.
   */
  private updateHeartbeat(): void {
    const local = this.local;
    const config = this.config;
    let level = 0;
    let rate = 1;
    if (local?.alive && config) {
      const ratio = clamp01(local.hp / config.maxHp);
      if (ratio < DANGER_START) {
        const t = clamp01((DANGER_START - ratio) / (DANGER_START - HEART_FLOOR));
        level = t;
        rate = 1 + (HEART_MAX_RATE - 1) * t;
      }
    }
    // Quantized so a hp bar drifting by a point does not re-ramp every frame.
    const stepped = Math.round(level * 8) / 8;
    if (stepped !== this.heartLevel) {
      this.heartLevel = stepped;
      this.pushBeds();
    }
    if (stepped > 0) setBedRate('heartbeat', rate);
  }

  /**
   * The growls, and the snarl when something commits.
   *
   * The ambient growl is picked from creatures near the ear WITHOUT checking
   * whether they can be seen — the sound is what tells you a thing is there,
   * and pointing the lantern at it is what tells you where. Gating it on
   * visibility would mean you only ever hear what you are already looking at,
   * which is the one arrangement that makes it useless.
   *
   * The alert snarl is the opposite: it fires ONCE per hunt, latched by id, so
   * a creature that has committed announces it and then shuts up rather than
   * re-snarling every frame it stays angry.
   */
  private updateGrowls(dt: number, entities: DrawableEntity[]): void {
    const world = this.world;
    if (!world) return;
    const reach = GROWL_TILES * world.tileSize;
    const near: DrawableEntity[] = [];
    const live = new Set<string>();

    for (const entity of entities) {
      if (entity.kind !== 'enemy' || !entity.alive) continue;
      if (Math.hypot(entity.x - this.smoothX, entity.y - this.smoothY) > reach) continue;
      near.push(entity);

      if (entity.awareness >= NOTICE_AT) {
        live.add(entity.id);
        if (!this.alertHeard.has(entity.id)) {
          this.alertHeard.add(entity.id);
          playSfxAt('zombie-alert', entity.x, entity.y);
        }
      }
    }
    // Calming down re-arms the snarl, the same way it drops the hunt diamond.
    for (const id of this.alertHeard) {
      if (!live.has(id)) this.alertHeard.delete(id);
    }

    if (near.length === 0) {
      this.growlLeft = GROWL_INTERVAL;
      return;
    }

    // A crowd talks more often, but sublinearly — six of them are not six
    // times as many growls, they are roughly twice as many.
    this.growlLeft -= dt * (1 + Math.sqrt(near.length - 1) * 0.6);
    if (this.growlLeft > 0) return;
    this.growlLeft = GROWL_INTERVAL * (0.55 + Math.random() * 0.9);

    if (!throttled('growl', GROWL_SPACING, this.time)) return;
    const speaker = near[(Math.random() * near.length) | 0];
    playSfxAt('zombie-idle', speaker.x, speaker.y, { gain: 0.9 });
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

    const loot = this.drawableLoot(dt);
    const corpses = this.drawableCorpses(dt);

    // Everyone in this frame was touched above; anyone who left — a player who
    // disconnected, an enemy that died — is now unreferenced and gets dropped.
    this.visuals.prune();

    this.updateVision(sampled.players, dt);
    this.applyVisibility(entities);
    this.latchAlertMarks(entities);
    // After `applyVisibility`, so a body the team cannot see leaves no prints.
    // A trail appearing out of the dark would be a free tracker. The hunt
    // diamond is the one exception, and only for enemies this client already
    // saw while they were alerting — see `latchAlertMarks`.
    this.trackFootsteps(entities);
    // After visibility and the alert latch, so it reads the same resolved
    // state the renderer is about to draw.
    this.updateAudio(dt, entities);
    // The ceremony runs on the render clock, not the tick: it is four seconds
    // of pure presentation between two snapshots, and stepping it at 30 Hz
    // would make the light walk around the ring in visible increments.
    this.stepRift(dt);
    this.syncTooltipAnchors();

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      entities,
      coins,
      loot,
      corpses,
      residue: this.residue,
      weather: this.zone?.weather ?? 'clear',
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
  /**
   * Lay boot prints for everything walking on visible ground.
   *
   * Purely a client-side reading of positions the server already broadcast —
   * nothing here is authoritative and nothing is sent. A print goes down every
   * `FOOTPRINT_STRIDE` tiles travelled, so the spacing is a stride rather than
   * a frame rate, and the ground decides how well it takes: mud holds a print,
   * leaf litter barely does (`soilAt`).
   *
   * Enemies leave them too, and that is the interesting half. Fresh prints
   * crossing yours that you did not make are the cheapest piece of information
   * an extraction run can hand a player, and it costs nothing to produce
   * because the tracks are already being drawn for the map's own trails.
   */
  private trackFootsteps(entities: DrawableEntity[]): void {
    const world = this.world;
    if (!world) return;
    const baseStride = world.tileSize * FOOTPRINT_STRIDE;

    for (const entity of entities) {
      if (!entity.alive || entity.visibility <= FOOTPRINT_MIN_VISIBILITY) {
        this.strides.delete(entity.id);
        continue;
      }
      const footY = entity.y + entity.halfHeight;
      const last = this.strides.get(entity.id);
      if (!last) {
        // First sighting lays nothing: with no previous point there is no
        // heading, and a print pointing the wrong way is worse than a gap.
        this.strides.set(entity.id, { x: entity.x, y: footY });
        continue;
      }

      const burden = entity.kind === 'player' ? this.carryBurdenOf(entity.id) : 0;
      const stride = baseStride * (1 - 0.38 * Math.min(1, burden));
      const dx = entity.x - last.x;
      const dy = footY - last.y;
      if (dx * dx + dy * dy < stride * stride) continue;

      const tx = Math.floor(entity.x / world.tileSize);
      const ty = Math.floor(footY / world.tileSize);
      const depth =
        tx >= 0 && ty >= 0 && tx < world.width && ty < world.height
          ? SOIL_PRINT_DEPTH[soilAt(tx, ty, world.seed)] ?? SOIL_PRINT_DEPTH[0]
          : SOIL_PRINT_DEPTH[0];
      const printDepth = depth * (1 + 0.75 * Math.min(1.2, burden));
      const blood = this.stepBlood(entity.id, entity.x, footY);
      this.effects.spawnFootprint(entity.x, footY, dx, dy, printDepth, FOOTPRINT_LIFE, blood);
      // The step is played HERE because this loop is already the one place
      // that fires exactly once per stride, for every body, with the soil in
      // hand. A second timer keyed off velocity would drift out of sync with
      // the print and you would see a boot mark land a beat after you heard it.
      // Loose litter reads dry and loud; everything else is a soft thud.
      this.playStep(entity, tx, ty, burden);
      last.x = entity.x;
      last.y = footY;
    }

    // Anything that stopped being drawn stops being tracked, or the map keeps
    // one stride marker per entity that has ever walked past.
    if (this.strides.size > entities.length) {
      const live = new Set(entities.map((entity) => entity.id));
      for (const id of this.strides.keys()) {
        if (!live.has(id)) this.strides.delete(id);
      }
    }
  }

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

  /**
   * The hunt diamond may sit on the night only if this client has already
   * seen the body while it was alerting. A hunter that committed in the
   * dark, never seen, wears nothing — that would be a free tracker.
   *
   * Latch when the body is visible and `aw` is past NOTICE_AT; drop it when
   * the creature calms down or leaves the snapshot.
   */
  private latchAlertMarks(entities: DrawableEntity[]): void {
    const live = new Set<string>();
    for (const entity of entities) {
      if (entity.kind !== 'enemy') continue;
      const alerting = entity.awareness >= NOTICE_AT;
      if (!alerting) {
        this.alertSeen.delete(entity.id);
        entity.alertKnown = false;
        continue;
      }
      live.add(entity.id);
      if (entity.visibility > 0.01) this.alertSeen.add(entity.id);
      entity.alertKnown = this.alertSeen.has(entity.id);
    }
    for (const id of this.alertSeen) {
      if (!live.has(id)) this.alertSeen.delete(id);
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
      this.carryBurdenOf(id),
    );
    const recoil = this.visuals.recoilOf(id);
    const gun = this.visuals.gunFeelOf(id);
    const weaponKey = this.weaponKeyOf(id, source.isLocal ? this.heldSlot : source.held);

    return {
      id,
      kind: 'player',
      sheet: PLAYER_SHEET,
      tint: source.color,
      // Always on for now — the overlay is what "equipped" means, and every
      // player walks out of camp wearing one.
      gear: [this.config?.backpackSprite || BACKPACK_SHEET],
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
      visibility: 1,
      awareness: 0,
      alertKnown: false,
      viewRange: 0,
      viewDegrees: 0,
      hitFlash: this.visuals.hitFlashAmount(id),
      stains: this.visuals.stainsOf(id),
      recoilX: recoil.x,
      recoilY: recoil.y,
      halfWidth: config.playerHalfWidth,
      halfHeight: config.playerHalfHeight,
      weapon: weaponKey,
      gunKick: gun.kick,
      gunPump: gun.pump,
      hitSpin: 0,
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
    const planted = this.visuals.planted(id);
    this.visuals.emitFootsteps(
      id,
      x,
      y,
      vx,
      vy,
      moving && !planted,
      this.effects,
      type.halfHeight,
      this.config!.moveSpeed,
    );
    const recoil = this.visuals.recoilOf(id);

    return {
      id,
      kind: 'enemy',
      sheet: type.variants?.[enemy.v ?? 0] ?? type.sprite,
      // The art carries its own palette; tinting it would flatten the pixels.
      tint: null,
      gear: enemyGear(type, enemy),
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
      moving: moving && !planted,
      animTime: this.visuals.advanceAnim(id, moving && !planted, dt),
      isLocal: false,
      // Overwritten by applyVisibility once the light field is current.
      visibility: 0,
      // The detection meter that fills the hunt diamond. A server too old
      // to send it leaves the mark off rather than inventing one.
      awareness: enemy.aw ?? 0,
      // Overwritten by latchAlertMarks once visibility is current.
      alertKnown: false,
      viewRange: this.sightReach(type),
      viewDegrees: type.viewDegrees ?? 0,
      hitFlash: this.visuals.hitFlashAmount(id),
      stains: this.visuals.stainsOf(id),
      recoilX: recoil.x,
      recoilY: recoil.y,
      halfWidth: type.halfWidth,
      halfHeight: type.halfHeight,
      weapon: null,
      gunKick: 0,
      gunPump: 0,
      hitSpin: this.visuals.hitSpinOf(id),
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
   * `output` rather than the switch, so the reach answers the lamp as it
   * comes up and as it dies. The server switches on the boolean; the few
   * frames of fade where the two disagree cost nothing and read far better
   * than a snap. Hunt uses the same pair — killing the lamp shortens a
   * hunter too, which is how you slip it.
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
      lootPrompt: this.lootPromptInfo(),
      cratePrompt: this.cratePromptInfo(),
      riftPrompt: this.riftPrompt(),
      inventory: this.inventoryHud(),
      hotbar: this.hotbarHud(),
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

  private sendInteract(): void {
    if (this.departing || this.introLeft > 0) return;
    const nearLoot = this.nearLoot();
    if (nearLoot) {
      if (!this.canStow(nearLoot.k)) {
        this.bagRefusals += 1;
        // A refused key has to answer, for the same reason the panel kicks:
        // a control that silently does nothing reads as a broken keybind
        // rather than as a rule.
        playSfx('ui-error');
        const inventory = this.inventoryHud();
        if (inventory) this.patchHud({ inventory });
        return;
      }
      this.connection.send({ type: 'collect', id: nearLoot.id });
      return;
    }
    // Before the crate, and before the fire. If you are standing at the
    // console with a box at your elbow, you did not walk here for the box.
    if (this.riftPrompt()) {
      this.connection.send({ type: 'activate' });
      return;
    }
    const nearCrate = this.nearCrate();
    if (nearCrate) {
      this.connection.send({ type: 'break', id: nearCrate.id });
      return;
    }
    if (this.readyPrompt() === 'ready') {
      this.connection.send({ type: 'ready' });
      this.localReady = !this.localReady;
      // Optimistic, like the nameplate tick: the server decides whether it
      // counted, but the key has to answer on the frame it was pressed.
      playSfx(this.localReady ? 'ready' : 'unready');
    }
  }

  private toggleInventory(): void {
    if (this.departing || this.introLeft > 0) return;
    this.inventoryOpen = !this.inventoryOpen;
    playSfx(this.inventoryOpen ? 'bag-open' : 'bag-close');
    const inventory = this.inventoryHud();
    if (inventory) this.patchHud({ inventory });
  }

  private selectHotbar(slot: number): void {
    if (this.departing || this.introLeft > 0) return;
    const guns = this.localMeta?.guns;
    if (!guns || slot < 0 || slot >= guns.slots.length) return;
    if (!guns.slots[slot]) {
      playSfx('ui-error');
      return;
    }
    this.heldSlot = this.heldSlot === slot ? -1 : slot;
    this.hotbarPicks += 1;
    this.adsHold = 0;
    // Swapping weapons abandons the chain, the same way the server does it.
    this.comboStep = 0;
    this.comboLeft = 0;
    const hotbar = this.hotbarHud();
    if (hotbar) this.patchHud({ hotbar });
  }

  private requestDrop(slot: number): void {
    if (this.departing || this.introLeft > 0) return;
    if (this.zone?.kind === 'camp') return;
    const meta = this.localMeta;
    if (!meta?.inv) return;
    const row = meta.inv.bag[slot];
    if (!row) return;
    playSfx('drop');
    this.connection.send({ type: 'drop', slot });
    meta.inv.bag[slot] = null;
    const catalog = this.config?.loot ?? {};
    let weight = 0;
    for (const cell of meta.inv.bag) {
      if (!cell) continue;
      const def = catalog[cell.k];
      if (def) weight += def.weight * cell.n;
    }
    meta.inv.w = Math.round(weight * 100) / 100;
    if (this.local) this.local.carryWeight = meta.inv.w;
    const inventory = this.inventoryHud();
    if (inventory) this.patchHud({ inventory });
  }

  private canStow(key: string): boolean {
    const catalog = this.config?.loot ?? {};
    const def = catalog[key];
    if (def?.pocket === 'hotbar') {
      const guns = this.localMeta?.guns;
      if (!guns) return true;
      return guns.slots.some((cell) => cell === null);
    }
    const inv = this.localMeta?.inv;
    if (!inv) return true;
    for (let i = 0; i < inv.cap; i++) {
      const slot = inv.bag[i];
      if (!slot || slot.k === key) return true;
    }
    return false;
  }

  private inventoryHud(): HudInventory | null {
    const config = this.config;
    if (!config) return null;
    const catalog = config.loot ?? {};
    const cap = this.localMeta?.inv?.cap ?? config.inventorySlots ?? 3;
    const bag = this.localMeta?.inv?.bag ?? [];
    const slots = Array.from({ length: cap }, (_, index) => {
      const row = bag[index];
      if (!row) return null;
      const def = catalog[row.k];
      if (!def) return null;
      return {
        key: row.k,
        qty: row.n,
        name: def.name,
        rarity: def.rarity,
        frame: def.frame,
        value: def.value,
        weight: def.weight,
      };
    });
    let frames = 0;
    for (const def of Object.values(catalog)) {
      if (def.frame + 1 > frames) frames = def.frame + 1;
    }
    let weight = this.local?.carryWeight ?? this.localMeta?.inv?.w ?? 0;
    let gold = 0;
    for (const slot of slots) {
      if (slot) gold += slot.value * slot.qty;
    }
    for (const fly of listLootFlies()) {
      const def = catalog[fly.key];
      if (!def) continue;
      weight -= def.weight;
      if ((fly.dest ?? 'bag') === 'bag') gold -= def.value;
    }
    if (weight < 0) weight = 0;
    if (gold < 0) gold = 0;

    return {
      open: this.inventoryOpen,
      cap,
      slots,
      weight: Math.round(weight * 100) / 100,
      maxWeight: config.carryMaxWeight ?? 10,
      gold,
      lootFrames: Math.max(1, frames),
      catches: this.bagCatches,
      refusals: this.bagRefusals,
    };
  }

  private hotbarHud(): HudHotbar | null {
    const config = this.config;
    if (!config) return null;
    const catalog = config.loot ?? {};
    const cap = this.localMeta?.guns?.cap ?? config.hotbarSlots ?? 3;
    const cells = this.localMeta?.guns?.slots ?? [];
    const slots = Array.from({ length: cap }, (_, index) => {
      const key = cells[index];
      if (!key) return null;
      const def = catalog[key];
      if (!def) return null;
      return {
        key,
        name: def.name,
        rarity: def.rarity,
        frame: def.frame,
        weight: def.weight,
      };
    });
    let frames = 0;
    for (const def of Object.values(catalog)) {
      if (def.frame + 1 > frames) frames = def.frame + 1;
    }
    return {
      slots,
      held: this.heldSlot,
      lootFrames: Math.max(1, frames),
      picks: this.hotbarPicks,
    };
  }

  private stepCollectFlies(dt: number): void {
    const config = this.config;
    if (!config) return;
    const view = projectionFor(this.camera);
    const headX = view.x(this.smoothX);
    const headY = view.y(
      this.smoothY + config.playerHalfHeight - config.spriteHeight - config.tileSize * 0.35,
    );
    const landed = stepLootFlies(dt, (fly) => {
      const dest = fly.dest === 'hotbar' ? `hotbar-${fly.slot}` : `slot-${fly.slot}`;
      const slot = readInventoryAnchor(dest);
      const from = { x: headX, y: headY };
      if (!slot) return { from, to: from, ready: false };
      const to = warpHudPoint(slot.x, slot.y, window.innerWidth, window.innerHeight);
      return { from, to, ready: true };
    });
    if (landed > 0) {
      this.bagCatches += landed;
      const inventory = this.inventoryHud();
      const hotbar = this.hotbarHud();
      this.patchHud({
        inventory: inventory ?? undefined,
        hotbar: hotbar ?? undefined,
      });
    }
  }

  private heldWeapon(): WeaponConfig | null {
    const key = this.weaponKeyOf(this.localId, this.heldSlot);
    if (!key) return null;
    return this.config?.weapons?.[key] ?? null;
  }

  private weaponKeyOf(id: string, held?: number): string | null {
    const guns = this.roster.get(id)?.guns;
    const index = held ?? guns?.held ?? -1;
    if (index < 0 || !guns) return null;
    return guns.slots[index] ?? null;
  }

  /**
   * Body that just ate a round. Enemies take the knockback/tilt/freeze;
   * a player only flashes and stains — shoving a teammate would fight
   * their prediction.
   */
  private feelVictim(id: string, dx: number, dy: number, damage: number): void {
    if (id === this.localId || this.roster.has(id)) {
      this.visuals.pulseHitFlash(id);
      this.visuals.splatter(id, dx, dy);
      return;
    }
    const power = hitPower(damage);
    this.visuals.takeHit(id, dx, dy, power);
    if (power > 1.6) this.camera.addTrauma(0.06 + (power - 1.6) * 0.05);
  }

  /** Visual barrel tip. Hitscan still uses the server origin; the tracer does not. */
  private shotOrigin(
    id: string,
    weapon: string | undefined,
    x: number,
    y: number,
    ax: number,
    ay: number,
  ): { x: number; y: number } {
    const recoil = this.visuals.recoilOf(id);
    const gun = this.visuals.gunFeelOf(id);
    return gunMuzzle({
      x: x + recoil.x,
      y: y + recoil.y,
      ax,
      ay,
      weapon,
      guns: this.guns,
      pump: gun.pump,
      kick: gun.kick,
    });
  }

  private stepScope(dt: number): void {
    const weapon = this.heldWeapon();
    const ads =
      !!weapon &&
      weapon.scopeZoom > 0 &&
      this.input.shooting &&
      this.zone?.hostile !== false &&
      this.introLeft === 0 &&
      !this.departing;
    const want = ads && weapon ? weapon.scopeZoom : ARENA_ZOOM;
    const k = 1 - expDamp(9, dt);
    this.camera.zoom += (want - this.camera.zoom) * k;
    if (Math.abs(this.camera.zoom - want) < 0.02) this.camera.zoom = want;
    this.camera.resize(this.canvas.width, this.canvas.height);
  }

  private carryBurdenOf(id: string): number {
    if (!this.config) return 0;
    const weight =
      id === this.localId
        ? (this.local?.carryWeight ?? 0)
        : (this.roster.get(id)?.inv?.w ?? 0);
    return carryBurden(weight, this.config);
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
    if (this.nearCrate()) return null;
    return this.nearFire() ? 'ready' : null;
  }

  private cratePromptInfo(): boolean {
    if (this.departing || this.introLeft > 0) return false;
    if (this.nearLoot()) return false;
    if (this.riftPrompt()) return false;
    return this.nearCrate() !== null;
  }

  /**
   * Whether E is offering the extraction console right now.
   *
   * Only while it is DORMANT. Once the sequence starts there is nothing left
   * to press, and leaving a prompt on a structure that is already answering
   * would read as the first press not having registered.
   *
   * Measured feet-to-console, mirroring `Room.activate_rift`, so the prompt on
   * screen and the check on the server agree about what "close enough" means.
   */
  private riftPrompt(): boolean {
    if (this.departing || this.introLeft > 0) return false;
    const config = this.config;
    const local = this.local;
    const rift = this.world?.rift;
    if (!config || !local || !rift || rift.state !== 'dormant') return false;
    const range = (config.riftActivateTiles ?? 2.75) * config.tileSize;
    const dx = rift.consoleX - local.state.x;
    const dy = rift.consoleY - (local.state.y + config.playerHalfHeight);
    return dx * dx + dy * dy <= range * range;
  }

  /**
   * The server changed the rift's state. Adopt its clock and answer with juice.
   *
   * The visuals are all client-side and deliberately so: the server says WHAT
   * happened, this decides what that feels like. `elapsed` is taken from the
   * server rather than zeroed, so a player who joins mid-sequence picks it up
   * in progress instead of watching it replay.
   */
  private onRiftState(row: RiftStateRow): void {
    const world = this.world;
    if (!world?.rift) return;
    const was = world.rift.state;
    world.setRiftState(row.state, row.t);
    this.ensureResidue();
    if (was === row.state) return;
    if (row.state === 'charging') {
      // A switch being thrown. The console answering on the frame it was
      // pressed is what makes the button feel connected to the structure.
      playSfx('lantern-on');
    }
  }

  /**
   * Lay the blast's marks, once.
   *
   * Called on every state change and on arrival, because the field has to
   * exist for a rift that is ALREADY open or spent when this client turns up —
   * they walk into a clearing that is covered in it and no wave ever plays
   * (`riftPhase` hands back an infinite `waveRadius` for those). Generating on
   * the burst alone would leave late arrivals looking at clean ground.
   */
  private ensureResidue(): void {
    const rift = this.world?.rift;
    if (!rift || this.residue.length > 0) return;
    if (rift.state === 'dormant') return;
    const timing = this.config?.rift ?? null;
    if (!timing || !this.world) return;
    this.residue = riftResidue(
      this.world.seed, rift, timing.boomTiles * this.world.tileSize,
    );
  }

  /**
   * Run the ceremony's clock and fire the beats that need an effect.
   *
   * The four seconds between the server's two snapshots are entirely local, so
   * this is where the light and the shove come from.
   *
   * Each beat fires on the frame `elapsed` CROSSES it — the `before < at &&
   * after >= at` window is what makes it happen exactly once even if a frame
   * runs long enough to step over two stones, and what stops a late joiner
   * (who starts at the server's `t`) replaying the beats it already missed.
   */
  private stepRift(dt: number): void {
    const rift = this.world?.rift;
    if (!rift) return;
    const before = rift.elapsed;
    // Unconditionally, and BEFORE the charging guard: the clock keeps running
    // once the rift is open because that is what phases the resting loop. Stop
    // it here and the anomaly freezes on frame 0 forever.
    this.world?.stepRift(dt);
    if (rift.state !== 'charging' || !this.config) return;
    const after = rift.elapsed;
    const timing = this.config.rift ?? null;
    if (!timing) return;
    const fx = palette().effects;
    const beacon = palette().scene.beacon;
    const beaconCss = `rgb(${beacon[0]} ${beacon[1]} ${beacon[2]})`;

    // A stone catching. A small shove and a note each, so the four of them
    // walking around the ring are four separate events rather than one long
    // brightening — the punctuation is what sells the stagger.
    //
    // NO POINT LIGHT. `Effects.spawnLight` is a `ctx.arc` radial gradient in
    // WORLD pixels, and the world is drawn at `ARENA_ZOOM` — so a radius that
    // reads as modest in this file arrives on screen multiplied by the zoom and
    // covers half the viewport as a hard-edged disc. Every existing caller gets
    // away with it by being over in about a tenth of a second; a beat you are
    // meant to WATCH cannot hide behind that. The glow belongs to the sheets,
    // which are pixel art and lit like everything else — see `crown` and
    // `emerge` in `make_rift.py`.
    for (let i = 0; i < rift.pillars.length; i++) {
      const at = timing.consoleLag + i * timing.pillarStagger
        + timing.chargeTime * RIFT_CROWN_FRACTION;
      if (before < at && after >= at) {
        this.camera.addTrauma(0.08);
        // Four of these in a row is a rising figure, which is the whole reason
        // the stones are staggered. Borrowed from the loot-reveal chime for
        // now — the rift has no voice of its own in `make_audio.py` yet.
        playSfx('rarity');
      }
    }

    // The tear. The largest thing that happens on this map, and the only one
    // that earns a real shove.
    if (before < timing.emergeAt && after >= timing.emergeAt) {
      playSfx('summon');
    }
    // The window closing, if it ever does. `collapseAt` is null while the rift
    // is open-ended — a comparison against it would be false forever anyway,
    // but saying so here is what stops the next person wiring a timer to it.
    if (timing.collapseAt !== null
      && before < timing.collapseAt && after >= timing.collapseAt) {
      playSfx('lantern-off');
      this.camera.addTrauma(0.12);
    }
    // THE FRONT REACHING YOU. Not the explosion going off across the clearing —
    // the moment it arrives where this player is standing, which is a different
    // instant for everybody in the party and is the whole reason the wave is
    // slow and wide. Someone at the far edge feels it three seconds after the
    // person who pressed the button.
    const reach = timing.boomTiles * (this.world?.tileSize ?? 16);
    const local = this.local;
    if (local && rift) {
      const away = Math.hypot(rift.x - local.state.x, rift.y - local.state.y);
      if (away <= reach) {
        const front = (t: number) => {
          const u = Math.max(0, Math.min(1, (t - timing.boomAt) / timing.boomTime));
          return (1 - (1 - u) ** 3) * reach;
        };
        if (front(before) < away && front(after) >= away) {
          // Hardest up close and still felt at the rim, so the shove reports
          // how much of the blast you actually took.
          this.camera.addTrauma(0.55 * (1 - (away / reach) * 0.65));
          playSfx('crate-break');
        }
      }
    }

    const burst = timing.boomAt;
    if (before < burst && after >= burst) {
      // Same reason: the sheet already whites the whole frame out on this
      // exact frame. A gradient disc on top of it only adds the one thing the
      // sheet does not have — a hard circular edge.
      this.camera.addTrauma(0.42);
      playSfx('kindle');
      for (let i = 0; i < 30; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 40 + Math.random() * 90;
        this.effects.particles.push({
          x: rift.anomalyX,
          y: rift.anomalyY - RIFT_BURST_LIFT,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed * 0.7,
          size: 1 + Math.random() * 2,
          color: i % 3 === 0 ? fx.goldCore : beaconCss,
          age: 0,
          life: 0.35 + Math.random() * 0.4,
          gy: 30,
        });
      }
    }
  }

  private nearCrate() {
    const config = this.config;
    const local = this.local;
    const world = this.world;
    if (!config || !local || !world) return null;
    const range = (config.crateBreakTiles ?? 2.25) * config.tileSize;
    const feetY = local.state.y + config.playerHalfHeight;
    let best = null;
    let bestD2 = range * range;
    for (const crate of world.crates) {
      const dx = crate.x - local.state.x;
      const dy = crate.y - feetY;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        bestD2 = d2;
        best = crate;
      }
    }
    return best;
  }

  private replaceCrates(rows: CrateState[]): void {
    if (!this.world) return;
    this.world.replaceCrates(
      rows.map((row) => ({
        id: row.id,
        x: row.x,
        y: row.y,
        variant: row.v,
        flip: row.flip !== 0,
      })),
    );
  }

  private onCrateBreak(ev: CrateBreakEvent): void {
    if (!this.world) return;
    this.world.removeCrate(ev.id);
    const { tx, ty } = crateFootprint(ev.x, ev.y, this.world.tileSize);
    this.world.setTile(tx, ty, FLOOR);
    const empty = ev.drop === 'empty';
    this.effects.spawnCrateSmash(ev.x, ev.y, ev.v, ev.flip !== 0, empty, CRATE_BREAK_LIFE);
    playSfxAt('crate-break', ev.x, ev.y);
    if (empty) this.effects.spawnWind(ev.x, ev.y, WIND_LIFE);
  }

  private lootPromptInfo(): HudLootPrompt | null {
    if (this.zone?.kind === 'camp' || this.departing || this.introLeft > 0) return null;
    const near = this.nearLoot();
    if (!near || !this.config) return null;
    const def = this.config.loot?.[near.k];
    if (!def) return null;
    return {
      id: near.id,
      name: def.name,
      rarity: def.rarity,
      full: !this.canStow(near.k),
    };
  }

  private nearLoot(): LootState | null {
    const config = this.config;
    const local = this.local;
    if (!config || !local) return null;
    const range = (config.lootCollectTiles ?? 2.25) * config.tileSize;
    const feetY = local.state.y + config.playerHalfHeight;
    let best: LootState | null = null;
    let bestD2 = range * range;
    for (const drop of this.loot.values()) {
      const dx = drop.x - local.state.x;
      const dy = drop.y - feetY;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        bestD2 = d2;
        best = drop;
      }
    }
    return best;
  }

  private drawableLoot(dt: number): DrawableLoot[] {
    const config = this.config;
    const fov = this.fov;
    const ts = config?.tileSize ?? 16;
    const catalog = config?.loot ?? {};
    const out: DrawableLoot[] = [];
    for (const drop of this.loot.values()) {
      const def = catalog[drop.k];
      if (!def) continue;
      const lit = fov
        ? fov.lightAt(Math.floor(drop.x / ts), Math.floor(drop.y / ts))
        : 1;
      const visibility = clamp01((lit - ENEMY_HIDE_LIGHT) / (ENEMY_SHOW_LIGHT - ENEMY_HIDE_LIGHT));
      out.push({
        id: drop.id,
        key: drop.k,
        x: drop.x,
        y: drop.y,
        frame: def.frame,
        rarity: def.rarity,
        beam: def.rarity === 'epic' || def.rarity === 'legendary',
        visibility,
        animTime: this.visuals.advanceAnim(drop.id, true, dt),
        phase: hashLootId(drop.id),
      });
    }
    return out;
  }

  /**
   * Pin world tooltips to the same camera the canvas just used.
   *
   * Show/hide is still `hud-store` (5 Hz). This only writes screen pixels so
   * the tooltip can sit on the fire without a React render.
   */
  private syncTooltipAnchors(): void {
    const view = projectionFor(this.camera);
    if (this.readyPrompt() === 'ready' && this.world && this.config) {
      const fire = this.world.fires[0];
      if (fire) {
        const lift = this.config.tileSize * FIRE_TOOLTIP_LIFT_TILES;
        writeTooltipAnchor('ready', view.x(fire.x), view.y(fire.y - lift));
      } else {
        dropTooltipAnchor('ready');
      }
    } else {
      dropTooltipAnchor('ready');
    }

    const near = this.lootPromptInfo();
    if (near && this.config) {
      const drop = this.loot.get(near.id);
      if (drop) {
        const lift = this.config.tileSize * LOOT_TOOLTIP_LIFT_TILES;
        writeTooltipAnchor('loot', view.x(drop.x), view.y(drop.y - lift));
      } else {
        dropTooltipAnchor('loot');
      }
    } else {
      dropTooltipAnchor('loot');
    }

    const rift = this.world?.rift;
    if (rift && this.riftPrompt() && this.config) {
      const lift = this.config.tileSize * RIFT_TOOLTIP_LIFT_TILES;
      writeTooltipAnchor('rift', view.x(rift.consoleX), view.y(rift.consoleY - lift));
    } else {
      dropTooltipAnchor('rift');
    }

    const crate = this.cratePromptInfo() ? this.nearCrate() : null;
    if (crate && this.config) {
      const lift = this.config.tileSize * CRATE_TOOLTIP_LIFT_TILES;
      writeTooltipAnchor('crate', view.x(crate.x), view.y(crate.y - lift));
    } else {
      dropTooltipAnchor('crate');
    }
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

/** Clothes first so a hat draws on top. Missing or out-of-range indices skip. */
function enemyGear(type: EnemyTypeConfig, enemy: RenderedEnemy): string[] {
  return corpseGear(type, enemy.cloth, enemy.hat);
}

function corpseGear(type: EnemyTypeConfig, cloth?: number, hat?: number): string[] {
  const gear: string[] = [];
  if (cloth != null && cloth >= 0 && type.clothes?.[cloth]) {
    gear.push(type.clothes[cloth]);
  }
  if (hat != null && hat >= 0 && type.hats?.[hat]) {
    gear.push(type.hats[hat]);
  }
  return gear;
}

interface LiveCorpse {
  id: string;
  x: number;
  y: number;
  t: string;
  v: number;
  hat?: number;
  cloth?: number;
  ax: number;
  ay: number;
  dx: number;
  dy: number;
  stains: BloodStain[];
  age: number;
  halfHeight: number;
}

function cloneStain(stain: BloodStain): BloodStain {
  return { ...stain };
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

function hashLootId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return ((h & 0xffff) / 0xffff) * Math.PI * 2;
}

function shotFeel(weapon: WeaponConfig): ShotFeel {
  return {
    tracerLife: weapon.tracerLife,
    tracerWidth: weapon.tracerWidth,
    flash: weapon.flash,
    casings: weapon.casings,
    lightRadius: weapon.lightRadius,
    lightLife: weapon.lightLife,
  };
}

/** Keep the impact where the server put it; start the streak at the barrel. */
function aimTracer(
  muzzleX: number,
  muzzleY: number,
  originX: number,
  originY: number,
  dx: number,
  dy: number,
  dist: number,
): { x: number; y: number; dx: number; dy: number; dist: number } {
  const hitX = originX + dx * dist;
  const hitY = originY + dy * dist;
  const vx = hitX - muzzleX;
  const vy = hitY - muzzleY;
  const len = Math.hypot(vx, vy);
  if (len < 1e-3) {
    return { x: muzzleX, y: muzzleY, dx, dy, dist };
  }
  return { x: muzzleX, y: muzzleY, dx: vx / len, dy: vy / len, dist: len };
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
