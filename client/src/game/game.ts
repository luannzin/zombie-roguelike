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
  BuyEvent,
  EnemyTypeConfig,
  GameConfig,
  HotbarState,
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
  PourEvent,
  RiftStateRow,
  RiftTimingConfig,
  QuestState,
  ServerMessage,
  SnapshotMessage,
  SkillConfig,
  SpinEvent,
  SwingEvent,
  WelcomeMessage,
  WeaponConfig,
  ZoneInfo,
} from '../net/protocol';
import { Camera } from '../render/camera';
import { ARENA_ZOOM } from '../render/framing';
import { gunMuzzle, loadGuns, type GunAtlas } from '../render/guns';
import { projectionFor } from '../render/projection';
import { FovField, type LightSource, type VisionConfig, type Viewer } from '../render/fov';
import {
  loadMerchant,
  newMerchantPose,
  stepMerchant,
  type MerchantAtlas,
  type MerchantPose,
} from '../render/merchant';
import type { StoreScene } from '../render/layers/store';
import { DEATH_TIME, POOL_GROW, poolRadius, poolWetness } from '../render/layers/corpses';
import { soilAt } from '../render/layers/terrain';
import { setClimate } from '../render/wind';
import { Minimap, type MinimapPlayer } from '../render/minimap';
import { Renderer } from '../render/renderer';
import { SpriteBook } from '../render/sprites';
import { NOTICE_AT } from '../render/layers/vision';
import { tileHash } from '../render/terrain';
import type {
  DrawableCoin,
  DrawableCorpse,
  DrawableEntity,
  DrawableLoot,
  PourPose,
} from '../render/types';
import { whenFontsReady } from '../theme/fonts';
import { palette } from '../theme/palette';
import { crateAlongRay, hitscan, type RayTarget } from './combat';
import { Effects, type ShotFeel } from './effects';
import { EntityVisuals, hitPower, type BloodStain } from './entity-visuals';
import {
  EMPTY_HUD,
  HUD_INTERVAL,
  type HudBuyPrompt,
  type HudHotbar,
  type HudInventory,
  type HudLootPrompt,
  type HudMachinePrompt,
  type HudRiftPrompt,
  type HudSkill,
  type HudSnapshot,
  type HudStore,
} from './hud-store';
import { InputController } from './input';
import { bindInventoryDrop } from './inventory-actions';
import { readInventoryAnchor, clearInventoryAnchors } from './inventory-anchors';
import { Lantern } from './lantern';
import { SnapshotBuffer, type RenderedEnemy, type RenderedPlayer } from './interpolation';
import { clearLootFlies, listLootFlies, spawnLootFly, stepLootFlies } from './loot-flies';
import {
  POUR_DUMP,
  POUR_LIFT,
  POUR_WALK,
  POUR_LIFT_TIME,
  POUR_STOW_TIME,
  clearPadCargo,
  stepPadCargo,
  tipPadItem,
} from './pad-cargo';
import { warpHudPoint } from '../lib/lens';
import { LocalPlayer } from './prediction';
import { carryBurden } from './simulation';
import {
  crateCells, FLOOR, VOID, hearthMask, makeCrate, TileMap,
  type Rift, type Stand,
} from './world';
import {
  crateOpenSound, objectHitBox, objectLabel, objectSheet, objectTilesW,
  objectVerb, setObjectCatalog,
} from './objects';
import {
  clearTooltipAnchors,
  dropTooltipAnchor,
  writeTooltipAnchor,
} from './tooltip-anchors';
import { dropExitGuide, guidePoint, writeExitGuide } from './exit-guide';
import {
  beginPull,
  pullFinished,
  stepPull,
  type MachineBeat,
  type MachinePull,
} from './machine';
import {
  beginPayout,
  payoutFinished,
  stepPayout,
  type Payout,
} from './payout';

const MAX_TICKS_PER_FRAME = 5;
/** Extra camera punch when local shot lands on a target. */
const HIT_TRAUMA = 0.12;
/** Camera punch when local player loses HP. */
const HURT_TRAUMA = 0.55;
/** Tiny bump when a coin lands in the pocket. */
const PICKUP_TRAUMA = 0.06;
/**
 * The kick each item gives when it hits the deck. A twentieth of a pickup:
 * a pour is twenty of these in a row, and at pickup strength emptying a full
 * bag would shake the camera off the map.
 */
const POUR_LAND_TRAUMA = 0.012;
/**
 * Camera shove when a returning platform hits the shop's apron.
 *
 * An order of magnitude above a crate landing on a deck and still well under a
 * gunshot's, because several tonnes of iron touching down twenty tiles away is
 * a big event happening at a distance — a shake sized like the thing rather
 * than like the room would make the safest zone in the game the loudest.
 */
const PAYOUT_LAND_TRAUMA = 0.09;

/**
 * How long the exit chevron stays at full strength, and how long it takes to
 * leave, in seconds.
 *
 * IT LEAVES. The arrow used to be permanent, which made every other channel
 * the exit has — a column of light over the treeline, four torches burning on
 * a map with nothing else alight, a ping from the mouth — decoration nobody
 * had a reason to read. The hold is long enough to point somebody the right
 * way out of the clearing they are standing in; after that the world says it.
 */
const EXIT_GUIDE_HOLD = 7;
const EXIT_GUIDE_FADE = 3.5;
/** Seconds between the exit's distant signal pings. See `stepBeacon`. */
const BEACON_PING_INTERVAL = 3.4;
/**
 * Shortest gap between two snarls, in seconds. See `drainAlertQueue`.
 *
 * Tuned against the startle wave on the server (`ai.STARTLE_SPREAD_TILES`), so
 * the noises arrive at roughly the rate the bodies actually start moving —
 * a queue that drained faster than the pack turned would be a soundtrack
 * playing over the event rather than the event.
 */
const ALERT_SNARL_GAP = 0.18;
/** Where the held bag's mouth is, in world px out along aim and up from the feet. */
const POUR_MOUTH_OUT = 5.5;
const POUR_MOUTH_UP = 15;
/** The skid's own size in tiles. Mirrors make_platform.py. */
const PLATFORM_TILES_W = 5;
const PLATFORM_TILES_H = 4;
/** Camera punch when an enemy drops. */
const DEATH_TRAUMA = 0.32;
/** The woods swallowing the way in — one beat per rank of trees. */
const SEAL_TRAUMA = 0.18;
const SEAL_TRAUMA_START = 0.42;
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
/** How far above an object's contact the use tooltip sits, in tiles. */
const CRATE_TOOLTIP_LIFT_TILES = 1.4;
/**
 * How long a used object keeps playing before it stops being drawn.
 *
 * ONE NUMBER FOR BOTH VERBS, and it is a ceiling rather than a duration: the
 * sheet's own `animFrames`/`fps` decide when the last frame lands, and this is
 * how long the sprite lingers after that. A break sheet ends near-empty so the
 * extra beat costs nothing; an OPEN sheet ends on a held pose of a lid
 * standing up, and that beat is the whole difference between a container being
 * emptied and a container vanishing.
 */
const CRATE_BREAK_LIFE = 0.85;
/**
 * How long the item jumping out of an opened container is in the air.
 *
 * Slow enough to read the rarity colour at the top of the arc, short enough
 * that it is over before the player has finished deciding to walk to it.
 */
const LOOT_POP_LIFE = 0.62;
/** Empty-crate gust. Matches `make_vfx.py` wind (8 frames @ 14 fps). */
const WIND_LIFE = 8 / 14;
/**
 * How far above a shop table the buy tooltip sits, in tiles.
 *
 * Higher than the others because this stall already has a price tag hanging
 * over it: the tooltip has to clear the tag, or the two stack into one block
 * of numbers nobody reads.
 */
const BUY_TOOLTIP_LIFT_TILES = 2.6;

/**
 * How far above the machine's contact the lever tooltip sits, in tiles.
 *
 * The tallest lift in the game, because the cabinet is the tallest object a
 * player stands at: anything lower lands over the tray, which is exactly the
 * part of it they are watching while the canister comes out.
 */
const MACHINE_TOOLTIP_LIFT_TILES = 3.4;

/** How far above the console the activate tooltip sits, in tiles. */
const RIFT_TOOLTIP_LIFT_TILES = 1.9;
/**
 * How far the ground-break throws dirt, in world px per second.
 *
 * Read against `make_platform.py`'s `burst` sheet rather than chosen: the
 * sprite's own debris crosses about half its 128px frame in the first third of
 * a 0.67s timeline, and particles that outrun the sheet they are supposed to
 * be part of read as a second, unrelated effect going off underneath it.
 */
const RIFT_BURST_SPEED = 110;
/**
 * Seconds per turn of the corner sirens, and therefore per audible tick.
 *
 * Read off the art rather than chosen: `siren.png` is 12 frames at 16 fps, so
 * the lamp comes back round every 0.75s. A tick that did not land on the sweep
 * would be a second, unrelated alarm playing underneath the one on screen.
 */
const SIREN_SWEEP = 12 / 16;
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
  /** Which beat of a pour this body is on, if any. Absent for the local one. */
  pour?: number;
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
  /**
   * The party's money. Whole-group rather than per-player — see the note on
   * `SnapshotMessage.balance`. Held here rather than on the roster because
   * both the price tags (canvas) and the purse (React) read it, and there is
   * only ever one of it.
   */
  private balance = 0;
  /**
   * The lever pull running in the glade, or null. ONE at a time, because the
   * server refuses a second — so this is a field rather than a list, and a
   * spin event arriving over a live pull replaces it rather than queueing,
   * which can only happen after a reconnect.
   */
  private pull: MachinePull | null = null;
  /** Pulls the local player has banked. Read off the roster. */
  private spins = 0;
  /** This player's skills, keyed by catalog key. Read off the roster. */
  private skillStacks: Record<string, number> = {};
  /** The skill that just landed, held for a beat so the tray can play it in. */
  private reward: HudSkill | null = null;
  /**
   * The night's platforms being set down in the shop, or null.
   *
   * Pure presentation: the balance was already credited when the party crossed
   * the corridor, and nothing here can move it. What this owns is the two
   * seconds between the number being true and the player believing it.
   */
  private payout: Payout | null = null;
  /**
   * What the HUD is allowed to SAY the balance is.
   *
   * It trails `this.balance` while the gold is in the air and equals it every
   * other frame. A shop that opened with the full number already printed would
   * spend its whole ceremony animating coins toward a total that had visibly
   * been there since before they left the deck.
   */
  private balanceShown = 0;
  /** Render-clock time the extraction exit opened. Drives the beacon's flare. */
  private egressAt = 0;
  /** Seconds until the next spatial ping from the exit's mouth. */
  private beaconLeft = 0;
  /**
   * The merchant's clip player, and the sheets it drives. He is not an entity
   * and the server has never had an opinion about which frame he is on, so
   * this lives entirely client-side — see `render/merchant.ts`.
   */
  private merchantAtlas: MerchantAtlas | null = null;
  private merchantPose: MerchantPose = newMerchantPose(null);
  private localId = '';
  private local: LocalPlayer | null = null;
  private localMeta: PlayerMeta | null = null;
  /**
   * THIS PLAYER'S ROUNDS, BY CALIBRE, PREDICTED.
   *
   * The same contract as position: the server owns it, the client spends it
   * locally on the frame it predicts a shot, and every roster overwrites it.
   * A counter that only moved on the 5 Hz roster would fall in visible steps
   * behind rounds the player is watching leave the barrel, and — worse — the
   * last shot of a magazine would fire locally after the reserve was already
   * empty server-side.
   */
  private ammo: Record<string, number> = {};
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
   * Which beat of a POUR the local body is on, or null. Read off its own
   * snapshot row rather than the interpolated list, because the local player
   * is the one body the interpolator deliberately does not carry.
   */
  private localPour: number | null = null;
  /**
   * How far each body's backpack is off its shoulders, keyed by player.
   *
   * The BEAT is the server's and the POSE is this client's: one integer on the
   * wire says which part of the ceremony a body is in, and the ease between a
   * pack that is worn and a pack that is held upside down runs here, on the
   * render clock, where 30 Hz would show as steps.
   */
  private pourPoses = new Map<string, { phase: number; raw: number; age: number }>();
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
  /** Forest emerge: same lock, walking out of the VOID corridor. */
  private arriving = false;
  /** Run objectives. Cached; snapshots only attach the list when it changes. */
  private quests: QuestState[] = [];
  private get locked(): boolean {
    return this.departing || this.arriving;
  }
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
  /** Snarls waiting to be heard, nearest first. See `drainAlertQueue`. */
  private alertQueue: Array<{ x: number; y: number }> = [];
  /** Seconds until the next queued snarl may play. */
  private alertGap = 0;

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
    // Fire-and-forget, like every other atlas: until it lands the merchant is
    // simply not drawn, which is better than holding up the corridor for him.
    void loadMerchant().then((atlas) => {
      this.merchantAtlas = atlas;
      this.merchantPose = newMerchantPose(atlas);
    });
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
      'object-open',
      'object-heavy',
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
    this.alertQueue.length = 0;
    // The beds are the one part of the audio graph that outlives a single
    // sound, so they are the one part with a release here. One-shots already
    // in the air are left to finish; cutting them would click.
    stopBeds();
    resetSfxState();
    setClimate('clear');
    this.lantern.reset();
    clearTooltipAnchors();
    dropExitGuide();
    clearInventoryAnchors();
    clearLootFlies();
    clearPadCargo();
    bindInventoryDrop(null);
    this.inventoryOpen = false;
    this.bagCatches = 0;
    this.bagRefusals = 0;
    this.world = null;
    this.fov = null;
    this.zone = null;
    this.departing = false;
    this.arriving = false;
    this.quests = [];
    this.lights = [];
    this.local = null;
    this.localMeta = null;
    this.ammo = {};
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
    // BEFORE the map, and that order is load-bearing: `TileMap` resolves each
    // object row's atlas sheet as it unpacks it, and it can only do that once
    // the catalog the server just sent is in place.
    setObjectCatalog(msg.config.objects);
    this.world = new TileMap(msg.map);
    // A new map is a new set of decks. Piles are keyed by pad id and pad ids
    // repeat across nights, so carrying them would stack tonight's haul on top
    // of last night's on a platform that has never been touched.
    clearPadCargo();
    this.pourPoses.clear();
    this.localPour = null;
    // A new map is a new forest: nothing has been explored yet.
    this.fov = new FovField(this.world.width, this.world.height);
    this.localId = msg.playerId;
    this.localMeta = msg.player;
    this.ammo = { ...(msg.player.ammo ?? {}) };
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
    this.heldSlot = msg.player.guns?.held ?? 0;
    this.local.carryWeight =
      (msg.player.inv?.w ?? 0) + this.heldWeaponWeight(msg.player.guns, this.heldSlot);
    this.adsHold = 0;
    this.comboStep = 0;
    this.comboLeft = 0;

    this.rebuildLights();
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
    // Both corridor zones arrive the same way — puppeted out of a VOID path
    // that then seals behind them. The camp is the only one you simply appear
    // in, because you were already standing there.
    this.arriving =
      (msg.zone.kind === 'forest' || msg.zone.kind === 'store') &&
      msg.map.entrance?.state === 'open';
    this.balance = msg.balance ?? 0;
    // THE NIGHT'S PLATFORMS COME HOME. Started here rather than on a snapshot
    // because it belongs to the ARRIVAL: the skids are already in the air when
    // the corridor opens, so the first thing the party sees in this glade is
    // the thing they spent the night earning.
    this.payout = beginPayout(this.world.store?.payout ?? []);
    // The HUD is told a balance that has not been paid yet, so the count-up
    // has somewhere to climb from. With no ceremony running it is simply the
    // real number — see `balanceShown`.
    this.balanceShown = this.balance - (this.payout?.total ?? 0);
    // A fresh performance for a fresh arrival: he should not be caught halfway
    // through opening his coat on the frame the party walks in.
    this.merchantPose = newMerchantPose(this.merchantAtlas);
    this.quests = msg.quests ?? [];
    if (msg.blackout) this.lantern.kill();
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
    // Forest arrival is a walk out of the corridor, not a posed hold. The
    // title still names the night; the body keeps moving.
    if (this.arriving && this.world.entrance) {
      this.introLeft = 0;
      this.aimX = this.world.entrance.dirX;
      this.aimY = this.world.entrance.dirY;
      playSfx('void', { jitter: 0 });
    } else {
      this.introLeft = INTRO_TIME;
      this.aimX = INTRO_AIM_X;
      this.aimY = INTRO_AIM_Y;
    }

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
      introducing: !this.arriving,
      cinematic: this.arriving,
      ready: null,
      prompt: null,
      lootPrompt: null,
      quests: this.quests,
      balance: this.balance,
      buyPrompt: null,
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
      this.patchHud({ cinematic: true, prompt: null, ready: null, cratePrompt: null });
      // The walk-out, in one gesture: the bonfire is pulled down to a memory
      // of itself while the corridor's drone comes up under the march. The
      // point of leaving the camp is that the warmth stops, so the fire has to
      // audibly go — but not to nothing, because it is still behind you and
      // the forest `welcome` a few seconds later is what finally cuts it.
      this.beds = { fire: 0.18, wind: 0.5 };
      this.pushBeds();
      playSfx('void', { jitter: 0 });
    }

    const wasArriving = this.arriving;
    this.arriving =
      Boolean(msg.arriving) &&
      (this.zone?.kind === 'forest' || this.zone?.kind === 'store');
    if (this.arriving && !wasArriving) {
      this.patchHud({ cinematic: true, prompt: null, cratePrompt: null });
    }
    if (!this.arriving && wasArriving) {
      this.patchHud({ cinematic: false });
    }

    if (msg.entrance && this.world.entrance) {
      const was = this.world.entrance.state;
      this.world.setEntranceState(msg.entrance.state, msg.entrance.t);
      if (was !== 'sealing' && msg.entrance.state === 'sealing') {
        this.camera.addTrauma(SEAL_TRAUMA_START);
        playSfx('void', { jitter: 0 });
      }
    }
    // Egress before the patches: VOID is walkable only once the exit exists,
    // and the same snapshot carves those tiles.
    if (msg.egress && this.world) {
      const opening = this.world.egress === null;
      this.world.setEgress({
        side: msg.egress.side,
        mouthX: msg.egress.mouth[0],
        mouthY: msg.egress.mouth[1],
        backX: msg.egress.back[0],
        backY: msg.egress.back[1],
        dirX: msg.egress.dir[0],
        dirY: msg.egress.dir[1],
        state: msg.egress.state,
        elapsed: msg.egress.t,
        torches: (msg.egress.torches ?? []).map(([x, y]) => ({ x, y })),
      });
      // `setEgress` puts the torches on `scenery.lights`, and FOV reads
      // `Game.lights` — a snapshot of that list. Without this the way out is
      // marked by four fires that light nothing, on the one night the party
      // has no lantern and nothing else on the map is burning.
      this.rebuildLights();
      if (opening) this.onExitOpened();
    }
    if (msg.tilePatches && msg.tilePatches.length > 0) {
      this.applyTilePatches(msg.tilePatches);
    }
    if (msg.quests) {
      this.quests = msg.quests;
    }

    if (msg.roster) {
      for (const meta of msg.roster) this.roster.set(meta.id, meta);
      const mine = this.roster.get(this.localId);
      if (mine) {
        this.localMeta = mine;
        // Authoritative resync. Replaces rather than merges: a calibre the
        // server has dropped to zero has to come back as zero, not survive
        // as whatever the prediction last left behind.
        if (mine.ammo) this.ammo = { ...mine.ammo };
        this.adoptMods(mine);
        if (this.local && mine.inv) this.local.carryWeight = this.moveWeight();
      }
    }

    for (const state of msg.players) {
      if (state.id === this.localId) {
        this.localReady = state.ready ?? false;
        this.localPour = state.pour ?? null;
        if (this.locked) {
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
    for (const ev of msg.pours ?? []) this.onPour(ev);
    if (msg.crates) this.replaceCrates(msg.crates);
    for (const ev of msg.crateBreaks ?? []) this.onCrateBreak(ev);
    if (msg.rifts) {
      for (const row of msg.rifts) this.onRiftState(row);
    }
    if (msg.stands) this.world.setStands(msg.stands);
    if (msg.balance !== undefined) {
      const delta = msg.balance - this.balance;
      this.balance = msg.balance;
      // A purchase (or any other change) while gold is still in the air moves
      // the shown number with it, so the count-up keeps climbing toward a
      // total that already has the spend taken off it.
      this.balanceShown += delta;
    }
    for (const ev of msg.buys ?? []) this.onBuy(ev);
    for (const ev of msg.spins ?? []) this.onSpin(ev);
    if (msg.blackout) this.lantern.kill();
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
    this.effects.spawnDarkGoldPickup(pickup.x, pickup.y, pickup.gold);
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
      // AMMUNITION FLIES ONTO THE GUN IT FEEDS. The server sent the hotbar
      // cell holding the weapon of that calibre, so the sprite lands on the
      // thing it just topped up rather than on a bag that never held it —
      // and it must not open the pack, because nothing went in there.
      const dest = ev.dest === 'bag' || ev.dest === undefined ? 'bag' : 'hotbar';
      if (dest === 'bag') this.inventoryOpen = true;
      else if (ev.dest === 'hotbar' && this.heldSlot < 0) this.heldSlot = ev.slot;
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

  /**
   * One item out of somebody's backpack and onto a platform's deck.
   *
   * The server tips the pocket one unit at a time and sends one of these per
   * item, so this is the only place that knows what a pour looks like: the
   * thing leaves the bag's mouth, arcs over the skid's front lip and lands in
   * the square the pad's own pile index put it in. Everything after that
   * belongs to `pad-cargo.ts` — it is furniture now.
   *
   * NOTHING ABOUT THE INVENTORY HAPPENS HERE. The bag emptying is the roster's
   * job and it arrives on its own cadence; the point of pacing the server's
   * spend is that the two already agree without this having to force it.
   */
  private onPour(ev: PourEvent): void {
    const pad = this.world?.rifts.find((row) => row.id === ev.r);
    const def = this.config?.loot?.[ev.k];
    if (!pad || !def || !this.config) return;
    const tile = this.config.tileSize;

    // Out of the mouth of a bag that is being held out toward the deck. The
    // pose in `layers/entities.ts` puts the pack there; this has to agree with
    // it or the items fall out of the character's chest.
    let nx = pad.deckX - ev.x;
    let ny = pad.deckY - ev.y;
    const span = Math.hypot(nx, ny) || 1;
    nx /= span;
    ny /= span;

    tipPadItem({
      rift: ev.r,
      frame: def.frame,
      n: ev.n,
      scale: ev.s ?? 1,
      fromX: ev.x + nx * POUR_MOUTH_OUT,
      fromY: ev.y + ny * POUR_MOUTH_OUT * 0.45 - POUR_MOUTH_UP,
      deckX: pad.deckX,
      deckY: pad.deckY,
      // The skid is authored 5x4 TILES (make_platform.py). Derived rather than
      // hardcoded at 80x64 so a re-rendered atlas still stacks inside the box.
      frameW: tile * PLATFORM_TILES_W,
      frameH: tile * PLATFORM_TILES_H,
    });
  }

  /**
   * Somebody bought a weapon off a table.
   *
   * Deliberately the same performance a world pickup gets — the thunk, the
   * rarity chime, the sprite flying onto the belt cell — because it IS the
   * same event from the player's side: a gun they did not have is now in their
   * hands. What is different is the coin sound underneath it, which is the
   * only part that says this one cost the party something.
   *
   * The table emptying is not done here. That arrives on `msg.stands` and is
   * the server's word; drawing it off the event would leave a table looking
   * sold to one client if the packet carrying the real state were dropped.
   */
  private onBuy(ev: BuyEvent): void {
    if (ev.by !== this.localId) {
      // Heard across the corridor, not celebrated. The party should know
      // somebody just spent the group's money.
      playSfxAt('coin', ev.x, ev.y, { gain: 0.6 });
      return;
    }
    playSfx('coin');
    const def = this.config?.loot?.[ev.k];
    if (def) {
      playSfx('loot', { delay: 0.05 });
      playSfx('rarity', { variant: RARITY_CHIME[def.rarity], jitter: 0, delay: 0.12 });
      if (this.heldSlot < 0) this.heldSlot = ev.slot;
      spawnLootFly({
        id: `buy-${ev.id}`,
        key: ev.k,
        frame: def.frame,
        rarity: def.rarity,
        slot: ev.slot,
        dest: 'hotbar',
      });
      const hotbar = this.hotbarHud();
      this.patchHud({ hotbar: hotbar ?? undefined, balance: this.balance });
    }
    this.camera.addTrauma(PICKUP_TRAUMA);
  }

  /**
   * Take the skills, the spins and the movement mods off a roster row.
   *
   * The MODS are the load-bearing half: the server multiplies move speed and
   * carry capacity by them, so prediction has to hold the same numbers or the
   * local body drifts from the authoritative one for the rest of the run. The
   * stacks and the spin count are HUD state and could have waited; they are
   * read in the same place because they arrive on the same row and splitting
   * them would mean two things to remember.
   */
  private adoptMods(meta: PlayerMeta): void {
    const stacks: Record<string, number> = {};
    for (const row of meta.skills ?? []) stacks[row.k] = row.n;
    this.skillStacks = stacks;
    this.spins = meta.spins ?? 0;
    if (this.local) {
      this.local.mods = meta.mods ? { speed: meta.mods.speed, carry: meta.mods.carry } : null;
    }
    this.lantern.setEndurance(meta.mods?.lamp ?? 1);
  }

  /**
   * A lever came down. Start the ceremony; the roll is already resolved.
   *
   * EVERY CLIENT IN THE GLADE RUNS THIS, not just the puller's, because a slot
   * machine going off is the loudest thing in the shop and a party should be
   * able to look over at somebody else's legendary. What is local-only is the
   * CLAIM — the canister flying into a HUD tray — which is why that beat
   * checks `by` and the rest do not.
   */
  private onSpin(ev: SpinEvent): void {
    this.pull = beginPull(ev, this.config?.machine);
    if (ev.by === this.localId) {
      this.spins = ev.left;
      this.skillStacks = { ...this.skillStacks, [ev.k]: ev.n };
      this.patchHud({ spins: this.spins, machinePrompt: this.machinePrompt() });
    }
  }

  /**
   * Run the pull a frame further and play the beats it crossed.
   *
   * THE SOUND IS THE ANTICIPATION. The reels stop left to right, each with its
   * own click, and the gap before the third is where the whole thing lives —
   * so the third click is pitched up with the rarity and the payout chime
   * behind it is the same five-step ladder loot already uses. A player learns
   * that ladder in the woods and gets to use it here.
   */
  private stepMachine(dt: number): void {
    const pull = this.pull;
    if (!pull) return;
    const world = this.world;
    const spot = world?.store;
    const x = spot?.machineX ?? this.smoothX;
    const y = spot?.machineY ?? this.smoothY;
    for (const beat of stepPull(pull, dt)) this.playMachineBeat(beat, pull, x, y);
    if (pullFinished(pull)) {
      this.pull = null;
      // The reward card is a beat, not a state: the tile it flew into is the
      // permanent record, and leaving the banner up would make a HUD region
      // that only ever grows.
      this.reward = null;
    }
  }

  private playMachineBeat(
    beat: MachineBeat,
    pull: MachinePull,
    x: number,
    y: number,
  ): void {
    const tier = RARITY_CHIME[pull.rarity] ?? 0;
    switch (beat) {
      case 'arm':
        // The cabinet's own lever, not a container's lid. See the machine
        // block in `server/tools/make_audio.py` — borrowing `object-heavy`
        // here made a slot machine sound like a car boot.
        playSfxAt('lever', x, y, { gain: 0.95 });
        break;
      case 'reel0':
        playSfxAt('reel', x, y, { variant: 0, jitter: 0 });
        break;
      case 'reel1':
        playSfxAt('reel', x, y, { variant: 1, jitter: 0 });
        break;
      case 'reel2':
        // The one that matters. Pitched with the tier, and the rarity chime
        // rides right behind it — by the third shop the pitch alone has
        // already told the player what they got.
        playSfxAt('reel', x, y, { variant: 2, jitter: 0, rate: 1 + tier * 0.13 });
        playSfxAt('rarity', x, y, { variant: tier, jitter: 0, delay: 0.06 });
        // The flourish is EPIC AND UP only. A celebration on every pull is a
        // celebration on none of them, and this is the audio half of the same
        // ladder `pullGain` draws.
        if (tier >= 3) playSfxAt('jackpot', x, y, { gain: 0.9, delay: 0.1 });
        this.camera.addTrauma(PICKUP_TRAUMA * (1 + tier * 0.8));
        break;
      case 'eject':
        playSfxAt('lever', x, y, { gain: 0.4, rate: 1.6 });
        break;
      case 'settle':
        // Metal in a steel tray. Deliberately not `drop`, which is loot
        // landing on soil.
        playSfxAt('can', x, y, { gain: 0.85 });
        break;
      case 'claim':
        if (pull.by !== this.localId) break;
        // It goes into the tray the way a collect goes into the bag, because
        // it is the same statement: this is mine now.
        playSfx('bag-open', { gain: 0.7 });
        this.reward = this.skillRow(pull.key, pull.copies);
        this.patchHud({
          skills: this.skillList(),
          reward: this.reward,
          spins: this.spins,
          machinePrompt: this.machinePrompt(),
        });
        break;
    }
  }

  /**
   * Run the payout a frame further and play the beats it crossed.
   *
   * THE SOUND IS THE SEQUENCE. A siren would be wrong — nothing is coming for
   * them here — so it is rotors settling, a heavy landing per skid, the lines
   * letting go, and then a stream of coin ticks as the gold arrives. The last
   * of those is deliberately the same `coin` sound a dark-gold pickup makes:
   * a party has been hearing that noise mean "money" all night, and this is
   * the payoff for it.
   */
  private stepPayout(dt: number): void {
    const payout = this.payout;
    if (!payout) return;
    for (const { pad, beat } of stepPayout(payout, dt)) {
      switch (beat) {
        case 'touch':
          // The one beat that earns a real camera shove: several tonnes of
          // iron arriving on soil, close enough to feel.
          playSfxAt('object-heavy', pad.x, pad.y, { gain: 1 });
          this.camera.addTrauma(PAYOUT_LAND_TRAUMA);
          this.effects.spawnImpact(pad.x, pad.y, 0, -1, false, 1.4);
          break;
        case 'release':
          playSfxAt('drop', pad.x, pad.y, { gain: 0.7, rate: 0.8 });
          break;
        case 'cash':
          // Not spatial: the gold is going to a number on the glass, not to a
          // place in the world, so a coin stream that panned with the deck
          // would be arriving somewhere the player is not looking.
          playSfx('coin', { gain: 0.9 });
          playSfx('rarity', { variant: 4, jitter: 0, delay: 0.12 });
          break;
        case 'done':
          playSfx('coin', { gain: 0.6, rate: 1.25 });
          break;
      }
    }
    // The shown balance is driven off the ceremony's own clock rather than off
    // however many coin sprites happened to be spawned: the number has to be
    // exactly right when it stops, and a counter tied to the draw would land a
    // few gold short on a slow frame.
    this.balanceShown = this.balance - payout.total + payout.paid;
    if (payoutFinished(payout)) {
      this.payout = null;
      this.balanceShown = this.balance;
    }
  }

  /**
   * THE EXIT OPENED. Three channels, and the split is the whole point.
   *
   * WORLD    a column of light straight up over the treeline
   *          (`drawEgressBeacon`), plus the four torches at the threshold. It
   *          is drawn in world space, so it is only on screen when the camera
   *          is pointed at it — which is what turns finding the way out into
   *          looking for something rather than following a marker.
   * HUD      the quest row announces itself at top-centre and flies into the
   *          card, exactly as every other objective does, and the chevron
   *          burns for a few seconds and then FADES OUT. It is a statement,
   *          not a compass; see `guideStrength`.
   * AUDIO    a launch, and then a slow spatial ping FROM the mouth. That is
   *          the channel that actually carries navigation, because it works
   *          while the player is looking the other way — which is exactly the
   *          moment they need it.
   */
  private onExitOpened(): void {
    this.egressAt = this.time;
    playSfx('siren', { jitter: 0, rate: 0.72, gain: 0.55 });
    playSfx('void', { jitter: 0, delay: 0.25 });
    this.beaconLeft = BEACON_PING_INTERVAL;
  }

  /**
   * The distant signal, repeating, FROM the mouth.
   *
   * Spatial, so it pans and thins with distance — which makes it navigation
   * rather than an alarm: a player who has lost the column behind a stand of
   * trees can still hear which way it is. It is slow on purpose. A ping every
   * couple of seconds is a landmark; a ping every half second is a countdown,
   * and the pack hunting them is already doing that job.
   */
  private stepBeacon(dt: number): void {
    const egress = this.world?.egress;
    if (!egress) return;
    this.beaconLeft -= dt;
    if (this.beaconLeft > 0) return;
    this.beaconLeft = BEACON_PING_INTERVAL;
    playSfxAt('void', egress.mouthX, egress.mouthY, { gain: 0.5, rate: 1.4 });
  }

  /**
   * How strongly to draw the exit chevron, 0..1.
   *
   * IT FADES, and that is the change. A permanent arrow answers "where is the
   * exit" forever, which means the world never has to — the column over the
   * trees, the torches at the threshold and the ping from the mouth all become
   * decoration the moment a chevron is doing their job. So it burns while the
   * news is news and then leaves, and everything after that is the map.
   */
  private guideStrength(): number {
    if (!this.world?.egress) return 0;
    const since = this.time - this.egressAt;
    if (since <= EXIT_GUIDE_HOLD) return 1;
    const fade = 1 - (since - EXIT_GUIDE_HOLD) / EXIT_GUIDE_FADE;
    return fade > 0 ? fade : 0;
  }

  /**
   * Let one queued snarl through per `ALERT_SNARL_GAP`, nearest first.
   *
   * The queue is sorted every drain rather than on push because it is nearly
   * always empty or one deep — the only thing that ever fills it is a pickup
   * being called, and on that frame the sort is over a handful of entries and
   * buys the wave its direction: the ones on top of you answer first and the
   * ones out in the trees a beat later.
   */
  private drainAlertQueue(dt: number): void {
    if (this.alertQueue.length === 0) {
      this.alertGap = 0;
      return;
    }
    this.alertGap -= dt;
    if (this.alertGap > 0) return;
    this.alertQueue.sort(
      (a, b) =>
        Math.hypot(a.x - this.smoothX, a.y - this.smoothY) -
        Math.hypot(b.x - this.smoothX, b.y - this.smoothY),
    );
    const next = this.alertQueue.shift();
    if (next) playSfxAt('zombie-alert', next.x, next.y);
    this.alertGap = ALERT_SNARL_GAP;
  }

  /** One tray tile, built from the catalog. Null for a key nobody shipped. */
  private skillRow(key: string, qty: number): HudSkill | null {
    const def: SkillConfig | undefined = this.config?.skills?.[key];
    if (!def) return null;
    return {
      key,
      name: def.name,
      blurb: def.blurb,
      rarity: def.rarity,
      frame: def.frame,
      qty,
      cap: def.cap,
    };
  }

  /** The whole tray, in catalog order. Empty until the first pull. */
  private skillList(): HudSkill[] {
    const out: HudSkill[] = [];
    for (const [key, qty] of Object.entries(this.skillStacks)) {
      const row = this.skillRow(key, qty);
      if (row) out.push(row);
    }
    out.sort((a, b) => a.frame - b.frame);
    return out;
  }

  /**
   * Whether the local body is standing at the cabinet, and what E would do.
   *
   * Measured feet to contact against `storeSpinTiles`, mirroring `Room.spin`,
   * so the prompt on screen and the check on the server agree. It answers even
   * with nothing to spend — a machine that only spoke to somebody who could
   * already afford it would never teach anybody what it was.
   */
  private machinePrompt(): HudMachinePrompt | null {
    if (this.locked || this.introLeft > 0) return null;
    if (this.zone?.kind !== 'store') return null;
    const config = this.config;
    const local = this.local;
    const fixtures = this.world?.store;
    if (!config || !local || !fixtures) return null;
    const { machineX, machineY } = fixtures;
    if (machineX === null || machineY === null) return null;
    const range = (config.storeSpinTiles ?? 2.2) * config.tileSize;
    const dx = machineX - local.state.x;
    const dy = machineY - (local.state.y + config.playerHalfHeight);
    if (dx * dx + dy * dy > range * range) return null;
    const mode = this.pull !== null ? 'busy' : this.spins > 0 ? 'ready' : 'empty';
    return { mode, spins: this.spins };
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
      if (this.introLeft === 0 && !this.locked) this.updateAim();
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
      } else if (this.arriving) {
        this.followArriveCamera(dt);
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
    if (!this.locked) {
      local.predict(packet, world, config);
    }
    this.connection.send(packet);

    if (this.locked) return;

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
        const key = this.weaponKeyOf(this.localId, this.heldSlot);
        // A DRY TRIGGER STILL EATS THE COOLDOWN, exactly as it does on the
        // server. Both halves matter: without the spend the tracer would
        // outlive the reserve, and without the cooldown an empty gun would
        // click thirty times a second for as long as the button was down.
        this.localFireCooldown = weapon.fireCooldown;
        if (this.hasRound(key)) {
          this.spendRound(key);
          this.predictShot(weapon);
        } else {
          playSfx('ui-error');
        }
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
    if (this.introLeft > 0 || this.locked) {
      return {
        type: 'input',
        sequence,
        movement: { up: false, down: false, left: false, right: false },
        aim: this.departing
          ? { x: DEPART_AIM_X, y: DEPART_AIM_Y }
          : this.arriving && this.world?.entrance
            ? { x: this.world.entrance.dirX, y: this.world.entrance.dirY }
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
      shoot: this.input.shooting && this.canAttack(),
      lantern: this.lantern.on,
      held: this.heldSlot,
    };
  }

  /**
   * Whether the trigger means anything where we are standing.
   *
   * `zone.hostile` gates the GUN, not the swing — the rule is "weapons fire
   * here", and a knife does not fire. So the blade works at the campfire and
   * a gun does not, and the mask has to agree with `Room.handle_attack` or
   * prediction throws an arc the server never resolved.
   */
  private canAttack(): boolean {
    // Both hands are on a backpack. The server ignores the trigger for the
    // length of a pour, so predicting a swing here would draw an arc that
    // never happened.
    if (this.localPour !== null) return false;
    if (this.zone?.hostile !== false) return true;
    return !!this.heldWeapon()?.melee;
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
      (kind) => objectVerb(kind) === 'break',
      (kind) =>
        objectHitBox(
          kind,
          (config.crateHitWTiles ?? 1) * config.tileSize,
          (config.crateHitHTiles ?? 2) * config.tileSize,
        ),
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
          // QUEUED, NOT PLAYED. One creature noticing you is one snarl; the
          // extraction alarm commits everything within earshot on the SAME
          // frame, and eight of these stacked on one tick is a wall of noise
          // that says nothing about how many there are or where. Draining the
          // queue nearest-first at a fixed gap turns the same event into heads
          // turning one after another around you — which is the beat, and it
          // is the sound of the pack noticing rather than of a switch flipping.
          this.alertQueue.push({ x: entity.x, y: entity.y });
        }
      }
    }
    this.drainAlertQueue(dt);
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
      this.locked ? undefined : this.localId,
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

    if (!this.locked && this.local && this.localMeta) {
      const { vx, vy } = this.local.state;
      const pourAim = this.pourAim();
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
            // A pour turns the body toward the deck and keeps it there. The
            // local sprite normally faces the MOUSE, so without this the
            // player alone would watch themselves tip a bag out sideways
            // while everybody else in the room saw it done properly.
            ax: pourAim?.x ?? this.aimX,
            ay: pourAim?.y ?? this.aimY,
            hp: this.local.hp,
            alive: this.local.alive,
            // The walk up to the mark is the server's, so locally there is no
            // predicted velocity to read it off — the legs have to be told.
            moving:
              Math.hypot(vx, vy) > MOVING_SPEED || this.localPour === POUR_WALK,
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
    // What is falling out of a backpack, on the same clock and for the same
    // reason. The thud is fired from HERE and not from the event, because the
    // moment a pour is actually about is the item hitting the deck.
    stepPadCargo(dt, (px, py) => {
      playSfxAt('drop', px, py, { gain: 0.7, rate: 0.9 + Math.random() * 0.3 });
      // Grit off the plate, not a footfall puff: dust is drawn under the
      // standing sort and the skid would sit on top of it, so the scatter that
      // sells the landing has to be one that draws over the night.
      this.effects.spawnImpact(px, py, 0, -1, false, 0.55);
      this.camera.addTrauma(POUR_LAND_TRAUMA);
    });
    // The merchant's performance runs on the render clock for the same reason
    // the rift's ceremony does: it is pure presentation between snapshots, and
    // nothing about which frame he is on has ever been on the wire.
    stepMerchant(this.merchantPose, this.merchantAtlas, dt);
    // The lever pull, on the same render clock and for the same reason: four
    // seconds of pure presentation between two snapshots, and the reels would
    // visibly step if they were resolved at 30 Hz.
    this.stepMachine(dt);
    // The night's platforms landing, and the gold coming off them.
    this.stepPayout(dt);
    // The exit's distant signal, once it exists.
    this.stepBeacon(dt);
    this.syncTooltipAnchors();

    this.renderer.draw({
      world: this.world,
      camera: this.camera,
      config: this.config,
      entities,
      coins,
      loot,
      corpses,
      weather: this.zone?.weather ?? 'clear',
      // How much light this PLACE has of its own. Zero everywhere but the
      // shop; see `server/app/zones.py`.
      ambient: this.zone?.ambient ?? 0,
      store: this.storeScene(),
      payout: this.payout,
      egressAge: this.world?.egress ? this.time - this.egressAt : 0,
      balance: this.balance,
      effects: this.effects,
      // The merchant's camp runs the darkness like every other forest map: it
      // IS a forest map, and his torches are ordinary scene lights. The pitch
      // being a pool of warmth in a dark glade is the whole picture — an
      // evenly lit clearing would read as somewhere with no night in it.
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
    const pack = this.config?.backpackSprite || BACKPACK_SHEET;
    const pour = this.pourPose(
      id,
      source.isLocal ? this.localPour : source.pour ?? null,
      pack,
      x,
      y,
      dt,
    );

    return {
      id,
      kind: 'player',
      sheet: PLAYER_SHEET,
      tint: source.color,
      // Always on for now — the overlay is what "equipped" means, and every
      // player walks out of camp wearing one. A body mid-POUR is the one
      // exception: its pack has come off, so it stops being gear and is drawn
      // as something held instead (see `pour` below).
      gear: pour ? [] : [pack],
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
      pour,
    };
  }

  /**
   * Ease one body's backpack between worn and held-out-upside-down.
   *
   * TWO CLOCKS, AND THAT SPLIT IS THE POINT. The server owns the BEAT — walk,
   * lift, dump, stow — because it owns when the pocket actually empties. This
   * owns the pose, on the render clock, because a pack that changed position
   * thirty times a second reads as a stutter and this is a four-second shot
   * the player is looking directly at.
   *
   * A pour that simply STOPS (cancelled by a step, or by something hitting the
   * player) is not a special case: the beat goes away, the grip eases back to
   * zero from wherever it had got to, and the pack is on the shoulders again
   * by the time the body has taken two paces.
   */
  private pourPose(
    id: string,
    phase: number | null,
    pack: string,
    x: number,
    y: number,
    dt: number,
  ): PourPose | null {
    let pose = this.pourPoses.get(id);
    if (pose === undefined) {
      if (phase === null) return null;
      pose = { phase, raw: 0, age: 0 };
      this.pourPoses.set(id, pose);
    }
    if (phase !== null && phase !== pose.phase) {
      // The two sounds of a pour, and they are the pack's, not the pad's: one
      // as it comes off the shoulders and one as it goes back on. Everything
      // between them is things hitting iron.
      if (phase === POUR_LIFT) playSfxAt('bag-open', x, y);
      else if (phase > POUR_DUMP) playSfxAt('bag-close', x, y);
    }
    if (phase !== null) pose.phase = phase;
    pose.age += dt;

    // Held for the two beats that need a hand on it; on the back for the walk
    // up, the walk away, and everything after the ceremony ends.
    const held = phase === POUR_LIFT || phase === POUR_DUMP;
    const rate = dt / (held ? POUR_LIFT_TIME : POUR_STOW_TIME);
    pose.raw = held
      ? Math.min(1, pose.raw + rate)
      : Math.max(0, pose.raw - rate);
    if (phase === null && pose.raw <= 0.0001) {
      this.pourPoses.delete(id);
      return null;
    }
    return {
      phase: pose.phase,
      // Smoothstep: the pack accelerates off the back and settles into the
      // hold instead of sliding there at a constant rate.
      grip: pose.raw * pose.raw * (3 - 2 * pose.raw),
      age: pose.age,
      sheet: pack,
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
      // Only a player carries a bag, and only a player ever pours one out.
      pour: null,
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
    const ratio = local.hp / (this.localMeta?.mods?.maxHp ?? config.maxHp);
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
              // THIS BODY'S ceiling, not the run's opening one — a skill moves
              // it, and a bar drawn against the constant would read as full
              // while the player was thirty points down.
              maxHp: meta.mods?.maxHp ?? config.maxHp,
              alive: local.alive,
              level: meta.level,
              xpInLevel: meta.xpInLevel,
              xpToLevel: meta.xpToLevel,
              gold: meta.gold,
            }
          : null,
      lantern: local ? this.lantern.reading() : null,
      cinematic: this.locked,
      quests: this.quests,
      ready: this.readyCount(),
      prompt: this.readyPrompt(),
      lootPrompt: this.lootPromptInfo(),
      cratePrompt: this.cratePromptInfo(),
      riftPrompt: this.riftPrompt(),
      buyPrompt: this.buyPrompt(),
      machinePrompt: this.machinePrompt(),
      skills: this.skillList(),
      spins: this.spins,
      reward: this.reward,
      // What the HUD may SAY. It trails the real number only while a payout is
      // running; see `balanceShown`.
      balance: this.payout ? this.balanceShown : this.balance,
      exitGuide: this.guidePose() !== null ? this.guideStrength() : 0,
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
    if (this.locked || this.introLeft > 0) return;
    const nearLoot = this.nearLoot();
    if (nearLoot) {
      // A full belt with a gun in hand is a TRADE, not a refusal, and it
      // goes through the same `collect` message — the server decides
      // whether the swap was legal (`Room.swap_weapon`), exactly as it
      // decides whether you were close enough.
      const trades =
        this.config?.loot?.[nearLoot.k]?.pocket === 'hotbar' &&
        this.swapTargetFor() !== null;
      if (!trades && !this.canStow(nearLoot.k)) {
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
    const rift = this.riftPrompt();
    if (rift) {
      // Two dead presses, and both get the buzz rather than a packet the
      // server would drop on the floor: an empty bag at a pad still under its
      // quota, and a second console while another platform is already running.
      if ((rift.mode === 'feed' && rift.empty) || rift.mode === 'busy') {
        playSfx('ui-error');
        return;
      }
      this.connection.send({ type: 'activate', id: rift.id });
      return;
    }
    // The shop's table. Before the crate and the fire for the same reason the
    // console is: there is nothing else in this corridor E could have meant.
    const buy = this.buyPrompt();
    if (buy) {
      // Both dead presses buzz rather than sending a packet the server would
      // drop on the floor: a price the party cannot cover, and a belt with no
      // free cell and no gun in hand to trade.
      if (!buy.afford || buy.full) {
        playSfx('ui-error');
        return;
      }
      this.connection.send({ type: 'buy', id: buy.id });
      return;
    }
    // The lever. After the tables because the cabinet stands past the last of
    // them, so the two reaches never overlap and the order is only a rule for
    // the frame somebody is standing exactly between them.
    const lever = this.machinePrompt();
    if (lever) {
      // Both dead presses buzz rather than sending a packet the server would
      // drop: no level owed, and somebody else's pull still running.
      if (lever.mode !== 'ready') {
        playSfx('ui-error');
        return;
      }
      this.connection.send({ type: 'spin' });
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
    if (this.locked || this.introLeft > 0) return;
    this.inventoryOpen = !this.inventoryOpen;
    playSfx(this.inventoryOpen ? 'bag-open' : 'bag-close');
    const inventory = this.inventoryHud();
    if (inventory) this.patchHud({ inventory });
  }

  private selectHotbar(slot: number): void {
    if (this.locked || this.introLeft > 0) return;
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
    // Only the weapon in hand is carried, so a swap changes the walk on the
    // frame it happens. Waiting for the next roster would make the speed
    // change arrive a fifth of a second after the keypress that caused it.
    if (this.local) this.local.carryWeight = this.moveWeight();
    const hotbar = this.hotbarHud();
    if (hotbar) this.patchHud({ hotbar });
  }

  private requestDrop(slot: number): void {
    if (this.locked || this.introLeft > 0) return;
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
      if (def) weight += (cell.w ?? def.weight) * cell.n;
    }
    meta.inv.w = Math.round(weight * 100) / 100;
    if (this.local) this.local.carryWeight = this.moveWeight();
    const inventory = this.inventoryHud();
    if (inventory) this.patchHud({ inventory });
  }

  private canStow(key: string): boolean {
    const catalog = this.config?.loot ?? {};
    const def = catalog[key];
    if (def?.pocket === 'ammo') {
      // AMMUNITION ANSWERS TO YOUR OWN BELT, and to nothing else. Mirrors
      // `Room.collect_loot`: a calibre you are not carrying is refused (the
      // rifle rounds belong to whoever brought the rifle) and a reserve
      // already at its cap is refused too — the box stays on the ground and
      // is still there on the way back, which is exactly what a player wants
      // from ammunition they cannot use yet.
      const calibre = def.ammo;
      if (!calibre) return false;
      const guns = this.localMeta?.guns;
      const owns = (guns?.slots ?? []).some(
        (cell) => cell !== null && this.config?.weapons?.[cell]?.ammo === calibre,
      );
      if (!owns) return false;
      const cap = this.config?.ammo?.max?.[calibre];
      return cap === undefined || (this.ammo[calibre] ?? 0) < cap;
    }
    if (def?.pocket === 'hotbar') {
      const guns = this.localMeta?.guns;
      if (!guns) return true;
      return guns.slots.some((cell) => cell === null);
    }
    const inv = this.localMeta?.inv;
    if (!inv) return true;
    for (let i = 0; i < inv.cap; i++) {
      const slot = inv.bag[i];
      // A slot carrying its own numbers is not a stack anything can join —
      // two cores worth 40 and 300 are not two of a thing. Mirrors
      // `Inventory.can_stow` on the server.
      if (!slot || (slot.k === key && slot.v === undefined && slot.w === undefined)) {
        return true;
      }
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
        // The SLOT's numbers win over the catalog's. Everything the world
        // scatters leaves these unset and reads its row; a condensed core out
        // of an overfed rift carries what it is actually worth.
        value: row.v ?? def.value,
        weight: row.w ?? def.weight,
      };
    });
    let frames = 0;
    for (const def of Object.values(catalog)) {
      if (def.frame + 1 > frames) frames = def.frame + 1;
    }
    // The BAG's own weight, not the walk's. This bar answers "how much loot
    // can I still carry out", so a rifle on the belt must not eat into it —
    // guns are not what extraction is for. What actually slows the body is
    // `moveWeight`, which is a different number and lives on prediction.
    let weight = this.localMeta?.inv?.w ?? 0;
    let gold = 0;
    for (const slot of slots) {
      if (slot) gold += slot.value * slot.qty;
    }
    for (const fly of listLootFlies()) {
      const def = catalog[fly.key];
      if (!def) continue;
      // Only a bag-bound fly is missing from this total; a gun in the air
      // was never counted in it.
      if ((fly.dest ?? 'bag') !== 'bag') continue;
      weight -= def.weight;
      gold -= def.value;
    }
    if (weight < 0) weight = 0;
    if (gold < 0) gold = 0;

    return {
      open: this.inventoryOpen,
      cap,
      slots,
      weight: Math.round(weight * 100) / 100,
      // The pocket's own ceiling, which a skill moves. `config.carryMaxWeight`
      // is only where a run opens, exactly as `maxHp` is.
      maxWeight: this.localMeta?.mods?.carry ?? config.carryMaxWeight ?? 10,
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
        ammo: this.roundsFor(key),
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

  /**
   * Rounds this player has for `key`'s calibre, or null if it eats none.
   *
   * Read off the LOCAL mirror rather than off the roster, because the roster
   * is 5 Hz and the trigger is 60: a counter that only fell five times a
   * second while you were holding down a Glock would tick in visible steps
   * behind the shots you were watching leave the barrel. `this.ammo` is spent
   * on the frame the shot is predicted and overwritten by every roster that
   * lands, exactly like position reconciliation.
   */
  private roundsFor(key: string | null | undefined): number | null {
    if (!key) return null;
    const calibre = this.config?.weapons?.[key]?.ammo;
    if (!calibre || calibre === 'none') return null;
    return this.ammo[calibre] ?? 0;
  }

  /** Take one round for `key`'s calibre off the local mirror. */
  private spendRound(key: string | null | undefined): void {
    if (!key) return;
    const calibre = this.config?.weapons?.[key]?.ammo;
    if (!calibre || calibre === 'none') return;
    const have = this.ammo[calibre] ?? 0;
    if (have <= 0) return;
    this.ammo[calibre] = have - 1;
    const hotbar = this.hotbarHud();
    if (hotbar) this.patchHud({ hotbar });
  }

  /** Whether the weapon in hand can fire. A knife always can. */
  private hasRound(key: string | null | undefined): boolean {
    const rounds = this.roundsFor(key);
    return rounds === null || rounds > 0;
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
      !this.locked;
    const want = ads && weapon ? weapon.scopeZoom : ARENA_ZOOM;
    const k = 1 - expDamp(9, dt);
    this.camera.zoom += (want - this.camera.zoom) * k;
    if (Math.abs(this.camera.zoom - want) < 0.02) this.camera.zoom = want;
    this.camera.resize(this.canvas.width, this.canvas.height);
  }

  /**
   * Kilos of the weapon in `guns` at `held`. Zero for an empty hand.
   *
   * The catalog is the one place a weapon's kg is written, so a gun on the
   * ground, a gun on the belt and a gun in the hand are the same number —
   * see `ItemDef.weight` in `server/app/loot.py`.
   */
  private heldWeaponWeight(guns: HotbarState | undefined, held: number): number {
    if (!guns || held < 0) return 0;
    const key = guns.slots[held];
    if (!key) return 0;
    return this.config?.loot?.[key]?.weight ?? 0;
  }

  /**
   * What the WALK carries for one player: the bag, plus only the weapon in
   * hand. A line-for-line mirror of `Player.carry_weight` on the server.
   *
   * It is rebuilt here rather than sent as a field precisely because the
   * hotbar selection is client-authored: `heldSlot` changes on the frame the
   * key is pressed and the server learns about it a packet later, so a
   * number computed there would be stale for exactly the frames the player
   * is watching their own speed change. Both sides run the same sum over the
   * same catalog instead, the way `simulation.ts` mirrors movement.
   *
   * Omit `id` for the local player, whose held slot is the predicted one.
   */
  private moveWeight(id?: string): number {
    if (id === undefined || id === this.localId) {
      const meta = this.localMeta;
      return (meta?.inv?.w ?? 0) + this.heldWeaponWeight(meta?.guns, this.heldSlot);
    }
    const meta = this.roster.get(id);
    return (meta?.inv?.w ?? 0) + this.heldWeaponWeight(meta?.guns, meta?.guns?.held ?? -1);
  }

  private carryBurdenOf(id: string): number {
    if (!this.config) return 0;
    const weight = id === this.localId ? (this.local?.carryWeight ?? 0) : this.moveWeight(id);
    // THAT BODY'S ceiling, off THAT body's roster row. Reading the local
    // player's would make everybody else's footsteps read as heavy the moment
    // this client pulled a carry skill.
    return carryBurden(weight, this.config, this.roster.get(id)?.mods?.carry);
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

  /**
   * The line E is offering on the object in front of you, or null.
   *
   * A STRING RATHER THAN A FLAG, because the objects no longer share a verb:
   * a barrel says destroy, a boot says search, a chest says open. The wording
   * is authored server-side next to the object's drop table
   * (`crates.ObjectType.label`) so the promise and the prompt cannot drift.
   */
  private cratePromptInfo(): string | null {
    if (this.locked || this.introLeft > 0) return null;
    if (this.nearLoot()) return null;
    if (this.riftPrompt()) return null;
    const near = this.nearCrate();
    return near ? objectLabel(near.kind) : null;
  }

  /**
   * Whether E is offering an extraction pad right now, and for what.
   *
   * Every branch is measured feet-to-console, mirroring `Room.activate_rift`,
   * so the prompt on screen and the check on the server agree about what
   * "close enough" means. The MODES mirror it too — including `busy`, which is
   * the client's copy of the one-pad-at-a-time rule: without it, walking up to
   * a second console offers a press the server will silently ignore.
   */
  private riftPrompt(): HudRiftPrompt | null {
    if (this.locked || this.introLeft > 0) return null;
    // Mid-pour there is nothing to offer: the server refuses a second press
    // for the length of one, and a key prompt that does nothing when pressed
    // is worse than no prompt at all.
    if (this.localPour !== null) return null;
    const rift = this.nearRift();
    if (!rift) return null;
    const empty = (this.inventoryHud()?.gold ?? 0) <= 0;
    if (rift.state === 'dormant') {
      const busy = this.world?.rifts.some(
        (row) => row.id !== rift.id && (row.state === 'charging' || row.state === 'open'),
      ) ?? false;
      return {
        id: rift.id,
        mode: busy ? 'busy' : 'open',
        have: 0,
        need: 0,
        empty: false,
      };
    }
    // A pad that is already calling takes no more presses. `closeAt` is the
    // server's word for that, and it is what stops a second E from being
    // offered on a pad whose aircraft are already in the air.
    if (rift.state !== 'open' || rift.closeAt !== null) return null;
    // Same split `Room.activate_rift` makes, off the same facts: whether the
    // quota is paid and whether the pocket still has anything. Saturating is
    // offered on EVERY pad, last one included — the payout at the end of the
    // night is what was fed, so value loaded past the quota is banked whether
    // or not there is another console left to carry a core to.
    const mode = !rift.ready ? 'feed' : empty ? 'close' : 'over';
    return {
      id: rift.id,
      mode,
      have: rift.fed,
      need: rift.need,
      empty,
    };
  }

  /**
   * What the renderer needs to draw the shop, or null anywhere else.
   *
   * `nearId` is resolved here rather than in the layer because it is a
   * GAMEPLAY fact — it is the same test `Room.buy` runs, feet to table — and
   * the lift, the pool and the prompt all have to agree with it. A layer that
   * worked it out for itself would be a second opinion about what "close
   * enough" means.
   */
  private storeScene(): StoreScene | null {
    const fixtures = this.world?.store;
    if (!fixtures) return null;
    const skills = this.config?.skills;
    return {
      fixtures,
      pose: this.merchantPose,
      nearId: this.nearStand()?.id ?? null,
      pull: this.pull,
      // The cabinet burns harder for somebody holding an unspent level. It is
      // the only piece of teaching in this zone that happens at a distance,
      // and it costs one float.
      invite: this.spins > 0 ? 1 : 0,
      iconOf: (key: string) => skills?.[key]?.frame ?? 0,
    };
  }

  /**
   * The stall the local player could buy from, or null.
   *
   * Measured from the FEET to the table's contact, mirroring
   * `Room._stand_in_reach`, so the prompt on screen and the check on the
   * server agree. Sold tables are skipped: an empty table is not something to
   * be standing at.
   */
  private nearStand(): Stand | null {
    const config = this.config;
    const local = this.local;
    const fixtures = this.world?.store;
    if (!config || !local || !fixtures) return null;
    const range = (config.storeBuyTiles ?? 1.9) * config.tileSize;
    const feetY = local.state.y + config.playerHalfHeight;
    let best: Stand | null = null;
    let bestD2 = range * range;
    for (const stand of fixtures.stands) {
      if (stand.sold) continue;
      const dx = stand.x - local.state.x;
      const dy = stand.y - feetY;
      const d2 = dx * dx + dy * dy;
      if (d2 <= bestD2) {
        bestD2 = d2;
        best = stand;
      }
    }
    return best;
  }

  /**
   * Whether E is offering a weapon right now, and whether it can be taken.
   *
   * Every refusal is NAMED rather than hidden, which is the opposite of the
   * rule the loot prompt follows for a full bag. A price you cannot meet is
   * the whole point of a shop — the party is supposed to look at the AWP and
   * decide to come back for it — so the tooltip says what it costs and turns
   * red, and the key buzzes instead of sending a packet the server would drop.
   */
  private buyPrompt(): HudBuyPrompt | null {
    if (this.locked || this.introLeft > 0) return null;
    if (this.zone?.kind !== 'store') return null;
    const stand = this.nearStand();
    if (!stand) return null;
    const item = this.config?.loot?.[stand.key];
    // A full belt is a TRADE here exactly as it is on a world drop, and the
    // tooltip has to say whose gun is being given up — otherwise E silently
    // costs the player the weapon in their hands.
    const room = this.canStow(stand.key);
    const swap = room ? null : this.swapTargetFor();
    return {
      id: stand.id,
      name: item?.name ?? stand.key,
      rarity: item?.rarity ?? 'common',
      price: stand.price,
      afford: stand.price <= this.balance,
      full: !room && swap === null,
      swap: swap ?? undefined,
    };
  }

  /**
   * Which way the local body is turned while it is pouring, or null.
   *
   * Taken off the AWAKE pad rather than off anything the pour event carries:
   * only one platform on a map may be awake at a time (`Room._awake_rift`), so
   * the pad somebody is emptying a bag into is never ambiguous.
   */
  private pourAim(): { x: number; y: number } | null {
    if (this.localPour === null || !this.world) return null;
    const pad = this.world.rifts.find((row) => row.state === 'open');
    if (!pad) return null;
    const dx = pad.deckX - this.smoothX;
    const dy = pad.deckY - this.smoothY;
    const len = Math.hypot(dx, dy) || 1;
    return { x: dx / len, y: dy / len };
  }

  private nearRift(): Rift | null {
    const config = this.config;
    const local = this.local;
    const world = this.world;
    if (!config || !local || !world) return null;
    const range = (config.riftActivateTiles ?? 2.75) * config.tileSize;
    const feetY = local.state.y + config.playerHalfHeight;
    let best: Rift | null = null;
    let bestD2 = range * range;
    for (const rift of world.rifts) {
      const dx = rift.consoleX - local.state.x;
      const dy = rift.consoleY - feetY;
      const d2 = dx * dx + dy * dy;
      if (d2 <= bestD2) {
        bestD2 = d2;
        best = rift;
      }
    }
    return best;
  }

  /**
   * Point the local player at the extraction exit while that quest is live.
   *
   * The HUD arrow reads this pose; it is not drawn in the forest.
   */
  private guidePose(): { fromX: number; fromY: number; toX: number; toY: number } | null {
    const exit = this.quests.find((quest) => quest.id === 'exit');
    const egress = this.world?.egress;
    const local = this.local;
    if (!exit || exit.done || !egress || !local) return null;
    // Anchored on the UPPER HALF of the body, not its centre and not its feet.
    // The arrow sits halfway out along this ray, and a ray leaving the feet
    // puts it over the ground the player is about to walk onto; leaving the
    // head it rides above the action, which is where a marker belongs.
    const lift = (this.config?.playerHalfHeight ?? 0) * 0.5;
    return {
      fromX: local.state.x,
      fromY: local.state.y - lift,
      toX: egress.backX,
      toY: egress.backY,
    };
  }

  /**
   * The server changed a pad's state. Adopt its clock and answer with juice.
   *
   * The visuals are all client-side and deliberately so: the server says WHAT
   * happened, this decides what that feels like. `elapsed` is taken from the
   * server rather than zeroed, so a player who joins mid-sequence picks it up
   * in progress instead of watching it replay.
   */
  private onRiftState(row: RiftStateRow): void {
    const world = this.world;
    if (!world) return;
    const before = world.rifts.find((item) => item.id === row.id);
    const was = before?.state;
    const wasReady = before?.ready ?? false;
    const closing = row.closeAt != null && was === 'open';
    world.setRiftState(row.id, row.state, row.t, row.closeAt ?? null, {
      fed: row.fed ?? 0,
      need: row.need ?? 0,
      ready: row.ready ?? false,
    });
    // The quota landing is an EVENT the state string does not name: the console
    // goes gold, the band starts, and the button stops meaning "load" and
    // starts meaning "call it in". It has to be as loud as the press was or
    // nobody notices the pad is waiting on them.
    if ((row.ready ?? false) && !wasReady) playSfx('rarity', { variant: 4 });
    if (was === row.state && !closing) return;
    // The beacon joins and leaves `scenery.lights` here. FOV reads `Game.lights`,
    // which is a snapshot of that list — without a rebuild the pad stays dark
    // even though the glow pass can already see the new row.
    this.rebuildLights();
    if (row.state === 'charging') {
      // A switch being thrown. The console answering on the frame it was
      // pressed is what makes the button feel connected to the structure.
      playSfx('lantern-on');
    }
  }

  /**
   * Rebuild the FOV light list from the map as it is right now.
   *
   * Bonfires come off the tiles; everything else comes off `scenery.lights`.
   * That second list is live — a powered platform pushes a light onto it, a
   * flown one takes it off — so this has to run again whenever that membership
   * changes, not only on welcome. A snapshot taken once at embark leaves the
   * pad dark after the tear, which is how a 7-tile beacon produced no light.
   */
  private rebuildLights(): void {
    const world = this.world;
    const config = this.config;
    if (!world || !config) {
      this.lights = [];
      return;
    }
    // Bonfires are read off the tiles, not off a message: the fire that blocks
    // you, the fire you can see and the fire that lights you are one tile.
    this.lights = world.fires.map((fire, index) => ({
      id: index,
      x: fire.x,
      // Lifted off the contact row — the light comes from the flame, not from
      // the ashes — so the pool is centred on the fire rather than in front of it.
      y: fire.y - config.tileSize * 0.5,
      radiusTiles: config.campfireLightTiles,
    }));
    // Whatever the map's own scenes are still burning, on the same list. The
    // lighting has no concept of "a camp light" versus "a light out in the
    // woods" and must not grow one: a lamp at a dead homestead throws real
    // light, casts real shadows through the trees around it, and is the reason
    // a player crosses half a map to find out what is under it. Ids continue
    // past the fires so a flicker never walks when the list changes length.
    for (const [index, light] of world.scenery.lights.entries()) {
      this.lights.push({
        id: world.fires.length + index,
        x: light.x,
        y: light.y,
        radiusTiles: light.radiusTiles,
      });
    }
  }

  /**
   * Run the rig's clock and fire the beats that need an effect.
   *
   * The seconds between the server's snapshots are entirely local, so this is
   * where the shove and the noise come from.
   *
   * Each beat fires on the frame `elapsed` CROSSES it — the `before < at &&
   * after >= at` window is what makes it happen exactly once even if a frame
   * runs long enough to step over two drones, and what stops a late joiner
   * (who starts at the server's `t`) replaying the beats it already missed.
   */
  private stepRift(dt: number): void {
    const world = this.world;
    if (!world || world.rifts.length === 0) return;
    const befores = world.rifts.map((row) => row.elapsed);
    // Unconditionally, and BEFORE the state guard: the clock keeps running
    // once a platform is awake because that is what flies the inbound aircraft
    // and phases the siren. Stop it here and a pickup freezes mid-crossing.
    world.stepRift(dt);
    if (!this.config) return;
    const timing = this.config.rift ?? null;
    if (!timing) return;
    for (let i = 0; i < world.rifts.length; i++) {
      const rift = world.rifts[i];
      if (rift.state !== 'charging' && rift.state !== 'open') continue;
      this.stepRiftBeats(rift, befores[i] ?? 0, rift.elapsed, timing);
    }
  }

  private stepRiftBeats(
    rift: Rift,
    before: number,
    after: number,
    timing: RiftTimingConfig,
  ): void {
    const fx = palette().effects;

    // Everything here is the PICKUP, and none of it exists until somebody has
    // called for one. `closeAt` is that press.
    //
    // NO POINT LIGHT anywhere in it. `Effects.spawnLight` is a `ctx.arc` radial
    // gradient in WORLD pixels and the world is drawn at `ARENA_ZOOM`, so a
    // radius that reads as modest here arrives on screen multiplied by the
    // zoom and covers half the viewport as a hard-edged disc. Every existing
    // caller gets away with it by being over in a tenth of a second; a beat
    // you are meant to WATCH for thirteen seconds cannot hide behind that. The
    // light belongs to the sheets, which are pixel art and lit like everything
    // else — see `siren.png`.
    const launch = rift.closeAt;
    if (launch === null) return;

    // THE CALL. The single most expensive press in the game, so it gets the
    // hardest single hit: the lamps go red on this frame and the server has
    // already put every creature on the map on hunt.
    if (before < launch && after >= launch) {
      this.camera.addTrauma(0.30);
      playSfx('kindle');
    }

    // THE SIREN, once per sweep, for as long as the aircraft are working. A
    // repeating tick under a scene nobody can leave is the whole tension of
    // the beat — it is a countdown the party can hear but cannot read, and it
    // keeps not stopping while things walk in out of the dark.
    const sweep = SIREN_SWEEP;
    const first = Math.ceil((before - launch) / sweep);
    const last = Math.floor((after - launch) / sweep);
    for (let n = Math.max(0, first); n <= last; n++) {
      if ((launch + n * sweep) <= before) continue;
      playSfx('siren');
      this.camera.addTrauma(0.04);
    }

    // EACH AIRCRAFT ARRIVING, and then its line reaching the eye. Two beats
    // per drone because they are two different pieces of information: one more
    // machine is here, and one more corner is taking load.
    for (let i = 0; i < timing.drones; i++) {
      const arrives = launch + timing.liftAlarm + i * timing.droneStagger + timing.droneInbound;
      if (before < arrives && after >= arrives) {
        this.camera.addTrauma(0.07);
        playSfx('lantern-on');
      }
      const tied = arrives + timing.droneDrop;
      if (before < tied && after >= tied) {
        this.camera.addTrauma(0.10);
        // Each corner a step higher than the last, so four of them tying on is
        // a rising figure. Borrowed from the loot-reveal chime for now — the
        // rig has no voice of its own in `make_audio.py` yet.
        playSfx('rarity', { variant: Math.min(4, i + 1) });
      }
    }

    // THE STRAIN. Rotors to maximum against ground that will not let go: a
    // shove that GROWS rather than a single hit, because what the beat has to
    // communicate is effort, and effort is the one thing a one-frame impulse
    // cannot say.
    const strainFrom = launch + timing.tiedAt;
    const strainTo = launch + timing.breakAt;
    if (before < strainFrom && after >= strainFrom) playSfx('kindle');
    if (after > strainFrom && after < strainTo) {
      const climb = (after - strainFrom) / Math.max(timing.liftStrain, 1e-6);
      this.camera.addTrauma(0.035 + climb * 0.06);
    }

    // THE GROUND LETTING GO. The largest thing that happens on this map and
    // the only beat here that earns a real shove.
    const broke = launch + timing.breakAt;
    if (before < broke && after >= broke) {
      this.camera.addTrauma(0.55);
      playSfx('crate-break');
      // Dirt out of the hole, low and flat: this is soil being thrown sideways
      // by a slab coming off it, not an explosion. `gy` pulls it back down
      // inside the sheet's own timeline so the two settle together.
      for (let i = 0; i < 34; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = RIFT_BURST_SPEED * (0.35 + Math.random() * 0.9);
        this.effects.particles.push({
          x: rift.x,
          y: rift.y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed * 0.5,
          size: 1 + Math.random() * 2,
          color: i % 4 === 0 ? fx.goldCore : fx.dust[i % fx.dust.length],
          age: 0,
          life: 0.30 + Math.random() * 0.45,
          gy: 40,
        });
      }
    }

    // Out of sight. Quiet on purpose — the party has already watched it go,
    // and a flourish here would ask them to look up again at nothing.
    const gone = launch + timing.collapseTime;
    if (before < gone && after >= gone) playSfx('lantern-off');
  }

  /**
   * The object E is offering, or null.
   *
   * Distance runs feet to the nearest point of the FOOTPRINT, mirroring
   * `crates.nearest`. A bus is four tiles long: measured centre to centre,
   * standing at its rear doors is standing two tiles away from the object,
   * and the prompt would refuse on the exact spot the art is pointing at.
   */
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
      if (crate.opened) continue;
      const half = objectTilesW(crate.kind) * config.tileSize * 0.5;
      const dx = Math.max(0, Math.abs(crate.x - local.state.x) - half);
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
    // Through the same unpacker the map payload uses, so a snapshot row and a
    // map row can never resolve to different sheets for the same object.
    this.world.replaceCrates(rows.map((row) => makeCrate(row)));
  }

  private onCrateBreak(ev: CrateBreakEvent): void {
    if (!this.world) return;
    // IT STAYS. The object flips to its opened state and keeps standing where
    // it stood — the sheet plays off the object itself from here, dated now,
    // which is why the one-shot below is spawned WITHOUT a sheet: it is the
    // dust and the splinters only, and drawing the animation twice would
    // double every frame of it.
    const live = this.world.openCrate(ev.id, this.time);
    const verb = objectVerb(ev.t);
    // Only a BREAK hands its ground back. An opened car is still solid — see
    // `Room.smash_crate`, which makes the same split — and freeing its tiles
    // would let a body walk through the bodywork. EVERY tile it stood on: a
    // vehicle claims four, and freeing only the contact tile would leave
    // three invisible walls where the car used to be.
    if (verb === 'break') {
      for (const cell of crateCells(
        ev.x,
        ev.y,
        this.world.tileSize,
        objectTilesW(ev.t),
      )) {
        this.world.setTile(cell.tx, cell.ty, FLOOR);
      }
    }
    const empty = ev.drop === 'empty';
    this.effects.spawnCrateSmash(
      // Only when the object is somehow not in the live list — a break event
      // for a row this client never had — does the one-shot draw the sheet
      // itself, so the press is never silent.
      live ? '' : objectSheet(ev.t),
      ev.x,
      ev.y,
      ev.v,
      ev.flip !== 0,
      empty,
      CRATE_BREAK_LIFE,
      verb,
    );
    // THREE SOUNDS FOR THREE WEIGHTS OF HINGE. A break shatters; a lid creaks
    // and knocks; a car panel or a stone slab has to be forced. Opening used
    // to play `bag-open` — the inventory panel's own UI tick — so a lorry, a
    // chest and the backpack were indistinguishable with the eyes shut, which
    // threw away the object vocabulary on the one channel that reaches a
    // player who is looking somewhere else.
    playSfxAt(crateOpenSound(ev.t, verb), ev.x, ev.y);
    // NOTHING IN HERE, and it is said out loud on EVERY verb.
    //
    // It used to be a gust on a break and silence on an open, on the reasoning
    // that a lid coming up on an empty boot had already said it. It had not:
    // an opened chest that pays nothing looks and sounds exactly like a press
    // the server dropped, so the player cannot tell "I found nothing" from
    // "the game ignored me" — and those are opposite feelings. The dry knock
    // and the puff of air out of the opening are what close the interaction:
    // I opened this, it worked, there was nothing inside.
    if (empty) {
      playSfxAt('empty', ev.x, ev.y, { delay: verb === 'break' ? 0.06 : 0.16 });
      // A gust off a shattered barrel; a smaller puff out of a hinge, because
      // the opening is smaller and a lid does not throw its contents about.
      this.effects.spawnWind(
        ev.x,
        ev.y,
        verb === 'break' ? WIND_LIFE : WIND_LIFE * 0.7,
      );
    }
    // THE ITEM JUMPS. The drop itself already exists on the ground — the
    // server placed it — so this is pure presentation over the top of it, and
    // it is what turns a find into a moment the player watches instead of a
    // sprite that was suddenly there.
    if (ev.drop === 'item' && ev.k) {
      this.effects.spawnLootPop(ev.x, ev.y, ev.k, LOOT_POP_LIFE);
      playSfxAt('loot', ev.x, ev.y);
    }
    // And sometimes it was not loot. The server has already spawned the
    // creature; this is the door being kicked rather than opened.
    if (ev.amb) {
      this.camera.addTrauma(0.35);
      playSfxAt('zombie-alert', ev.x, ev.y);
    }
  }

  private lootPromptInfo(): HudLootPrompt | null {
    if (this.zone?.kind === 'camp' || this.locked || this.introLeft > 0) return null;
    const near = this.nearLoot();
    if (!near || !this.config) return null;
    const def = this.config.loot?.[near.k];
    if (!def) return null;
    if (this.canStow(near.k)) {
      return { id: near.id, name: def.name, rarity: def.rarity, full: false };
    }
    // Belt full. If a gun is in hand this is a TRADE, not a refusal — the
    // prompt names what you would be putting down, because that is the half
    // of the decision the player cannot see from the drop's own tooltip.
    const trade = def.pocket === 'hotbar' ? this.swapTargetFor() : null;
    return {
      id: near.id,
      name: def.name,
      rarity: def.rarity,
      full: trade === null,
      swap: trade ?? undefined,
    };
  }

  /**
   * Name of the gun a pickup would trade away, or null if none can be.
   *
   * Mirrors `Room.swap_weapon`: the hand has to hold a GUN. The knife is not
   * tradeable — it is the one weapon that cannot be lost, and a pickup that
   * could consume its cell would put the floor under the whole loadout one
   * misplaced E away. Holstered refuses too: an empty hand is not a choice
   * about which gun to keep.
   */
  private swapTargetFor(): string | null {
    const guns = this.localMeta?.guns;
    if (!guns || this.heldSlot < 0) return null;
    const key = guns.slots[this.heldSlot];
    if (!key) return null;
    const def = this.config?.loot?.[key];
    if (!def || def.pocket !== 'hotbar') return null;
    if (this.config?.weapons?.[key]?.melee) return null;
    return def.name;
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
        scale: drop.s ?? 1,
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

    const prompt = this.riftPrompt();
    if (prompt && this.config) {
      const rift = this.world?.rifts.find((row) => row.id === prompt.id);
      if (rift) {
        const lift = this.config.tileSize * RIFT_TOOLTIP_LIFT_TILES;
        writeTooltipAnchor('rift', view.x(rift.consoleX), view.y(rift.consoleY - lift));
      } else {
        dropTooltipAnchor('rift');
      }
    } else {
      dropTooltipAnchor('rift');
    }

    const buy = this.buyPrompt();
    if (buy && this.config) {
      const stand = this.world?.store?.stands.find((row) => row.id === buy.id);
      if (stand) {
        // Above the PRICE, which is already floating above the table — a
        // tooltip pinned to the table itself would land underneath the tag
        // and the two would read as one stack of unrelated numbers.
        const lift = this.config.tileSize * BUY_TOOLTIP_LIFT_TILES;
        writeTooltipAnchor('buy', view.x(stand.x), view.y(stand.y - lift));
      } else {
        dropTooltipAnchor('buy');
      }
    } else {
      dropTooltipAnchor('buy');
    }

    const lever = this.machinePrompt();
    const fixtures = this.world?.store;
    if (lever && this.config && fixtures?.machineX != null && fixtures.machineY != null) {
      // Above the CROWN rather than above the contact: the cabinet is three
      // tiles tall and a tooltip pinned to its feet would land behind the
      // tray, which is the one part of it the player is watching.
      const lift = this.config.tileSize * MACHINE_TOOLTIP_LIFT_TILES;
      writeTooltipAnchor('machine', view.x(fixtures.machineX), view.y(fixtures.machineY - lift));
    } else {
      dropTooltipAnchor('machine');
    }

    const crate = this.cratePromptInfo() !== null ? this.nearCrate() : null;
    if (crate && this.config) {
      const lift = this.config.tileSize * CRATE_TOOLTIP_LIFT_TILES;
      writeTooltipAnchor('crate', view.x(crate.x), view.y(crate.y - lift));
    } else {
      dropTooltipAnchor('crate');
    }

    this.syncExitGuide(view);
  }

  /**
   * HUD arrow: halfway from the player to the screen edge, pointing at the
   * VOID corridor carved on the map edge.
   *
   * This writes a TARGET only. Where it is actually drawn — and the smoothing
   * that stops the target's per-frame rounding jitter reaching the screen —
   * belongs to `game/exit-guide`.
   */
  private syncExitGuide(view?: ReturnType<typeof projectionFor>): void {
    const pose = this.guidePose();
    if (!pose || this.introLeft > 0) {
      dropExitGuide();
      return;
    }
    const projection = view ?? projectionFor(this.camera);
    const px = projection.rawX(pose.fromX);
    const py = projection.rawY(pose.fromY);
    const dx = projection.rawX(pose.toX) - px;
    const dy = projection.rawY(pose.toY) - py;
    const length = Math.hypot(dx, dy);
    if (length < 1) {
      dropExitGuide();
      return;
    }
    const ux = dx / length;
    const uy = dy / length;
    const point = guidePoint(
      px,
      py,
      ux,
      uy,
      this.canvas.clientWidth,
      this.canvas.clientHeight,
    );
    writeExitGuide(point.x, point.y, Math.atan2(uy, ux));
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

  /**
   * Frame the party walking out of the corridor, looking a little ahead
   * into the forest so the night is in the shot rather than the wall behind.
   */
  private followArriveCamera(dt: number): void {
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
    const gate = world.entrance;
    const look = world.tileSize * 3.5;
    const targetX = gate ? cx + gate.dirX * look : cx;
    const targetY = gate ? cy + gate.dirY * look : cy;
    this.camera.follow(targetX, targetY, world, dt);
  }

  private applyTilePatches(patches: Array<[number, number, number]>): void {
    const world = this.world;
    if (!world || patches.length === 0) return;
    const ts = world.tileSize;
    const openingExit = patches.some(([, , kind]) => kind === VOID);
    for (const [tx, ty, kind] of patches) {
      world.setTile(tx, ty, kind);
    }
    const mid = patches[(patches.length / 2) | 0];
    const mx = mid ? (mid[0] + 0.5) * ts : 0;
    const my = mid ? (mid[1] + 1) * ts : 0;
    if (openingExit) {
      // A corridor appearing in the treeline, not trees slamming shut.
      this.effects.spawnWind(mx, my, WIND_LIFE);
      this.camera.addTrauma(SEAL_TRAUMA);
      playSfx('void', { jitter: 0 });
    } else {
      let first = true;
      for (const [tx, ty] of patches) {
        const x = (tx + 0.5) * ts;
        const y = (ty + 1) * ts;
        this.effects.spawnDust(x, y, 0, 1, 1, 1.6);
        this.effects.spawnDust(x, y, 0, -1, -1, 1.1);
        if (first) {
          this.effects.spawnWind(x, y, WIND_LIFE);
          first = false;
        }
      }
      if (mid && throttled('seal', 0.08, this.time)) {
        playSfxAt('crate-break', mx, my);
      }
      this.camera.addTrauma(SEAL_TRAUMA);
      // The last rank is the door shutting. A second void drone plus a harder
      // shove, so the player feels there is no way back rather than watching
      // trees finish appearing.
      if (world.entrance?.state === 'gone') {
        this.camera.addTrauma(SEAL_TRAUMA_START);
        playSfx('void', { jitter: 0 });
      }
    }
    this.renderer?.stampTiles(world, patches);
    this.minimap.rebuildTiles();
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
