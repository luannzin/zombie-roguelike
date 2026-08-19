/**
 * The single seam between the game loop and the React HUD.
 *
 * `Game` publishes an immutable snapshot here (throttled — see HUD_INTERVAL);
 * components read it through `useSyncExternalStore`. React never participates
 * in the render loop, and the game core never touches the DOM.
 */

import { Store } from '../lib/store';
import type { LanternReading } from './lantern';
import type { ConnectionStatus } from '../net/connection';
import type { LootRarity, QuestState, ZoneInfo } from '../net/protocol';

export interface HudInventorySlot {
  key: string;
  qty: number;
  name: string;
  rarity: LootRarity;
  frame: number;
  value: number;
  weight: number;
}

export interface HudHotbarSlot {
  key: string;
  name: string;
  rarity: LootRarity;
  frame: number;
  weight: number;
  /**
   * Rounds left for this weapon's calibre, or null for the knife.
   *
   * PER CELL rather than one counter beside the belt, because a party can
   * carry two guns on two calibres and "how many bullets do I have" is not a
   * question with one answer. Null is what makes the blade read as the weapon
   * that never runs out — the cell simply has no number on it.
   */
  ammo: number | null;
}

/** One run objective. The HUD mirrors the server list and never invents a row. */
export type HudQuest = QuestState;

export interface HudHotbar {
  slots: Array<HudHotbarSlot | null>;
  held: number;
  lootFrames: number;
  /** Bumps when the selection changes. Count, not a boolean — 5 Hz plus a patch. */
  picks: number;
}

export interface HudInventory {
  open: boolean;
  cap: number;
  slots: Array<HudInventorySlot | null>;
  weight: number;
  maxWeight: number;
  /** Sum of item values in the bag. In-flight collects are not counted yet. */
  gold: number;
  lootFrames: number;
  /** Bumps the pack when a fly lands. Count, not a boolean — 5 Hz. */
  catches: number;
  /** Full-bag refusals. Same counter contract as the lantern. */
  refusals: number;
}

export interface HudLootPrompt {
  id: string;
  name: string;
  rarity: LootRarity;
  /** No empty slot and no stack of this key. The tooltip turns red. */
  full: boolean;
  /**
   * Set when the belt is full of guns but E would TRADE rather than refuse:
   * the name of the weapon currently in hand, which is what collecting this
   * one would leave on the ground. Absent when the pickup is an ordinary
   * collect, and absent when no trade is legal — holding the knife, or
   * holstered — which is the case that falls back to `full`.
   */
  swap?: string;
}

export interface HudRiftPrompt {
  id: string;
  /**
   * What E does at this console right now.
   *
   *   open   nothing has happened here yet
   *   busy   another pad is already awake — one at a time, so this one refuses
   *   feed   the platform is powered, lamps green, and under its quota
   *   over   the quota is settled and the bag still has something. E keeps
   *          loading: the core waiting at the far end grows.
   *   close  the quota is settled and the pocket is empty. E CALLS THE
   *          PICKUP — lamps red, siren, and every creature on the map turns
   *          toward the clearing. Everything past the quota comes back as one
   *          condensed core once the platform is gone.
   */
  mode: 'open' | 'busy' | 'feed' | 'over' | 'close';
  have: number;
  need: number;
  /** Bag is empty — the press will refuse. */
  empty: boolean;
}

/**
 * Proximity prompt on a shop table.
 *
 * Every refusal is NAMED here rather than hidden, which is the opposite of
 * what the loot prompt does for a full bag. A price the party cannot meet is
 * the point of a shop — you are supposed to look at the AWP and decide to come
 * back for it — so the tooltip states the price and turns red instead of
 * quietly not appearing.
 */
export interface HudBuyPrompt {
  id: string;
  name: string;
  rarity: LootRarity;
  price: number;
  /** The party can cover it. False paints the price in the danger tone. */
  afford: boolean;
  /** Belt full AND no legal trade — holding the knife, or holstered. */
  full: boolean;
  /**
   * Set when the belt is full of guns but E would TRADE rather than refuse:
   * the name of the weapon in hand, which is what buying this one would leave
   * on the floor. Absent on an ordinary purchase.
   */
  swap?: string;
}

/**
 * Proximity prompt on the upgrade machine.
 *
 * `spins` is what the press would spend, and it is on the prompt rather than
 * left to the tray because the answer to "can I pull this" is a number the
 * player has to be able to read while standing at the lever, not one they have
 * to go and find in a corner.
 *
 *   ready   a level is owed and the cabinet is free — E pulls
 *   empty   nothing owed. The lever is shown refusing rather than hidden: a
 *           machine that vanished when you were broke would never teach
 *           anybody what it was for.
 *   busy    somebody else's pull is still running
 */
export interface HudMachinePrompt {
  mode: 'ready' | 'empty' | 'busy';
  spins: number;
}

/** One skill the local player holds, for the tray above the bag. */
export interface HudSkill {
  key: string;
  name: string;
  blurb: string;
  rarity: LootRarity;
  frame: number;
  qty: number;
  /** Copies past this one stop moving the number. The tile says so. */
  cap: number;
}

/** How often the game republishes HUD state. 5 Hz is plenty for text. */
export const HUD_INTERVAL = 0.2;

export interface HudVitals {
  name: string;
  color: string;
  kills: number;
  deaths: number;
  hp: number;
  maxHp: number;
  alive: boolean;
  /**
   * Breath, 0..`staminaMax`. Read from the PREDICTED body, not the roster:
   * SHIFT has to empty the bar on the frame it is pressed, and a value that
   * waited for a snapshot would lag the speed the player can already feel.
   */
  stamina: number;
  staminaMax: number;
  /**
   * The bar was spent to zero and SHIFT is refused until a third of it is
   * back. The HUD says so — an unresponsive key with no explanation reads as
   * a dropped input.
   */
  winded: boolean;
  /** Progression, paid out by the enemies you kill. */
  level: number;
  xpInLevel: number;
  xpToLevel: number;
  gold: number;
}

export interface HudNetStats {
  players: number;
  enemies: number;
  rttMs: number;
  interpMs: number;
  pending: number;
  fps: number;
}

/**
 * One arrival in a zone, announced once.
 *
 * `key` is the zone's, not a counter: the card is a statement about a PLACE, so
 * re-entering the same one replays it and a reconnect into the zone you are
 * already standing in does not. Components key their entry animation off it.
 */
export interface HudArrival {
  key: string;
  zone: ZoneInfo;
}

export interface HudSnapshot {
  connection: ConnectionStatus;
  /** Human-readable connection line. */
  status: string;
  /** True once a `welcome` has been received and a world exists. */
  inArena: boolean;
  vitals: HudVitals | null;
  net: HudNetStats | null;
  /**
   * Battery + switch. Published at 5 Hz like everything else here, which is
   * deliberate: the gauge shows CHARGE, and the per-frame blinking belongs to
   * the light in the world, not to a React re-render.
   */
  lantern: LanternReading | null;
  /** Where the run is. Decides what the HUD offers and what it greys out. */
  zone: ZoneInfo | null;
  /** Set on entering a zone; the title card plays and then leaves it alone. */
  arrival: HudArrival | null;
  /**
   * True while the arrival is still holding the player.
   *
   * The HUD stays OFF the glass for this beat. What is on screen is the place
   * and your own character standing in it, and a full set of corners over that
   * turns an establishing shot into a gameplay frame with a caption. It comes
   * back at the same moment the controls do, which is what makes the HUD
   * arriving read as "you're up".
   *
   * It DEFAULTS TO TRUE, and that default is the whole point. The store is
   * created when the arena mounts and the game only reaches `onWelcome` a
   * moment later, after its sheets have loaded — so a default of `false` would
   * paint the corners at full strength for those frames and then hide them,
   * which is a flash of HUD exactly where the transition is supposed to be
   * seamless. Hidden until something says otherwise; only the end of the hold
   * (or a dropped connection, which has news to show) turns it off.
   */
  introducing: boolean;
  /**
   * Camp walk-out. Chrome off, letterbox on, same as an arrival — the party
   * is leaving and the HUD has nothing to say about it.
   */
  cinematic: boolean;
  /** Living players ready / total, camp only. Null in the forest. */
  ready: { here: number; total: number } | null;
  /** Proximity prompt at the fire. Null when it should not be on screen. */
  prompt: 'ready' | null;
  /** Proximity prompt on a world drop. `full` is a bag that cannot take it. */
  lootPrompt: HudLootPrompt | null;
  /**
   * The verb E offers on the object in reach, or null. A string rather than a
   * flag because the objects do not share a verb any more — see
   * `server/app/crates.py`.
   */
  cratePrompt: string | null;
  /**
   * Proximity prompt on an extraction pad. `open` while dormant, `feed`
   * once the platform is running and the load quest is live.
   */
  riftPrompt: HudRiftPrompt | null;
  /** Proximity prompt on a shop table. Null outside the store. */
  buyPrompt: HudBuyPrompt | null;
  /** Proximity prompt on the upgrade machine. Null outside the store. */
  machinePrompt: HudMachinePrompt | null;
  /**
   * What the levels bought, for the tray ABOVE the bag.
   *
   * It sits there rather than in a corner of its own because a skill is the
   * same kind of statement the pocket is — this is what I am carrying — and
   * the two being one column is what stops the HUD growing a fifth region.
   * Empty until the first pull, and an empty tray draws nothing at all.
   */
  skills: HudSkill[];
  /**
   * Pulls owed. Drawn on the tray as a badge, so a player who levelled in the
   * woods is reminded there is something waiting for them at the shop —
   * which is most of what makes the walk out worth looking forward to.
   */
  spins: number;
  /**
   * The skill that just came out of the machine, or null. Set on the frame the
   * canister is claimed and cleared a beat later; the tray plays its entry off
   * the key changing, exactly the way `arrival` works for a zone.
   */
  reward: HudSkill | null;
  /**
   * The PARTY's money — what the group loaded onto the platforms on the last
   * night out, converted on the way to the shop. Separate from
   * `vitals.gold`, which is the coins this player personally walked over.
   */
  balance: number;
  /**
   * Extraction-exit chevron, 0..1. Pose is written every frame
   * (`exit-guide.ts`); this is only how strongly to draw it.
   *
   * IT IS A NUMBER RATHER THAN A FLAG because the arrow FADES. It burns for a
   * few seconds after the exit opens and then leaves — the column of light
   * over the treeline, the torches at the threshold and the ping from the
   * mouth are what carry navigation from there, and none of them means
   * anything while a chevron is answering the same question for free.
   */
  exitGuide: number;
  /** The pocket. Null before welcome. Open/close is client-local (TAB). */
  inventory: HudInventory | null;
  /** The gun belt. Always on screen; 1/2/3 selects. */
  hotbar: HudHotbar | null;
  /**
   * Run objectives. Empty until the forest entrance seals; the HUD is a
   * mirror — progress as numbers, a done flag, optional risk, and dropping
   * a row is how a task leaves the screen.
   */
  quests: HudQuest[];
}

export const EMPTY_HUD: HudSnapshot = {
  connection: 'connecting',
  status: 'connecting…',
  inArena: false,
  vitals: null,
  net: null,
  lantern: null,
  zone: null,
  arrival: null,
  introducing: true,
  cinematic: false,
  ready: null,
  prompt: null,
  lootPrompt: null,
  cratePrompt: null,
  riftPrompt: null,
  buyPrompt: null,
  machinePrompt: null,
  skills: [],
  spins: 0,
  reward: null,
  balance: 0,
  exitGuide: 0,
  inventory: null,
  hotbar: null,
  quests: [],
};

export type HudStore = Store<HudSnapshot>;

export function createHudStore(): HudStore {
  return new Store<HudSnapshot>(EMPTY_HUD);
}
