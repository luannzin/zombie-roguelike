/**
 * The single seam between the game loop and the React HUD.
 *
 * `Game` publishes an immutable snapshot here (throttled — see HUD_INTERVAL);
 * components read it through `useSyncExternalStore`. React never participates
 * in the render loop, and the game core never touches the DOM.
 */

import { Store } from '../lib/store';
import type { HudGearCard } from './gear-card';
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
   * What this weapon IS, for the hover card. Built by `gearCard` off the
   * catalog, so the belt, the armour panel and the shop describe the same
   * object the same way.
   */
  card: HudGearCard | null;
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

/**
 * ONE MEDICAL CELL, filled or empty.
 *
 * Empty cells are REAL ROWS rather than gaps, unlike the bag's — and the
 * difference is what the panel is for. A bag with three empty slots says
 * "there is room"; a medical belt with an empty cell says "you have one left",
 * which is a much more important sentence and one the player needs to be able
 * to read without counting.
 */
export interface HudMedicalSlot {
  key: string | null;
  name: string | null;
  frame: number;
  /** Points of health, for the cell's own label. */
  heal: number;
  /** Seconds it plants you for. The other half of the decision. */
  useTime: number;
  weight: number;
  /** Which key spends it — `4`, `5`. Rendered on the cell. */
  hotkey: string;
}

export interface HudMedical {
  slots: HudMedicalSlot[];
  /**
   * 0..1 through a use, or 0. Drives the cell's own fill as well as the ring
   * over the body, so the two cannot disagree about how far along it is.
   */
  progress: number;
  /**
   * The cell being spent, or -1. The panel highlights it — with two cells that
   * look alike, "which one am I burning" is a question worth answering.
   */
  using: number;
}

/**
 * The object under E: what pressing it does, and what it will COST.
 *
 * `seconds` is 0 for every object in the game except the vault. It is on the
 * prompt rather than discovered on the press because `open_time`'s whole
 * design is that choosing WHEN to pay it is the interesting part — a slow open
 * the player only learns about once they are already planted is a trap, not a
 * decision.
 */
export interface HudCratePrompt {
  /** The verb, authored server-side beside the drop table. */
  label: string;
  /** Seconds it plants you for. 0 means it resolves on the press. */
  seconds: number;
}

/** The named thing you are fighting. */
export interface HudBoss {
  name: string;
  title: string;
  /** 0..1. The bar's own fill; the number is deliberately never shown. */
  fraction: number;
  /** Past half health. The bar changes colour and the plate marks it. */
  enraged: boolean;
  /**
   * He is going down. The bar holds, empty, for the length of the collapse
   * rather than vanishing on the frame he dies — the payoff of a two-minute
   * fight is watching that bar reach zero, and a panel that unmounts at zero
   * takes it away at exactly the wrong moment.
   */
  slain: boolean;
  /**
   * Seconds since the fight became winnable, or negative during the
   * cinematic. The panel slides in off this rather than off a mount
   * transition, so a client that joins mid-fight gets the bar immediately
   * instead of watching it introduce itself.
   */
  engaged: number;
}

export type HudQuest = QuestState;

export interface HudHotbar {
  slots: Array<HudHotbarSlot | null>;
  held: number;
  /** Bumps when the selection changes. Count, not a boolean — 5 Hz plus a patch. */
  picks: number;
}

/**
 * One part of the body and what is protecting it.
 *
 * ALWAYS PRESENT, EVEN BARE. A row with nothing in it is not missing
 * information — it is the information: that is a part the next blow can land
 * on with nothing in the way, and a panel that only listed what you owned
 * would go quiet at exactly the moment the player most needs to look at it.
 */
export interface HudArmorSlot {
  /** `head` / `arms` / `body` / `legs` / `feet`. */
  slot: string;
  /** Portuguese, off `config.armorSlotNames`. */
  label: string;
  key: string | null;
  name: string | null;
  rarity: LootRarity | null;
  /** `cloth` / `leather` / `steel` / `kevlar`. Null when the part is bare. */
  material: string | null;
  /**
   * The loot atlas frame for this piece, or null when the part is bare.
   *
   * THE CELL DRAWS THE OBJECT, which is the whole of what changed about this
   * panel. It used to draw a label and a thin meter — three rows of a
   * spreadsheet about a costume — and a player could pick up a pair of steel
   * greaves and never see what they had. The same sprite that was lying in
   * the grass is now sitting on the body, in the place on the body it goes.
   */
  frame: number | null;
  /** Which row of the mannequin, top to bottom. Off `config.armorBodyLayout`. */
  row: number;
  /**
   * How many boxes this slot draws on its row. TWO means a PAIR — the arms,
   * the legs and the boots — and both boxes show the same piece, because both
   * boxes ARE the same piece. A person has two arms and one set of bracers.
   */
  cells: number;
  /** Damage taken off every blow that lands here. 0 when the part is bare. */
  armor: number;
  hp: number;
  maxHp: number;
  /**
   * The hover card, carrying THIS piece's remaining durability rather than
   * the catalog's ceiling. Null on a bare part — there is nothing to describe,
   * and a card that said "nothing" would be a card you learn to dismiss.
   */
  card: HudGearCard | null;
}

/** The shield, when there is one on the belt. */
export interface HudShield {
  key: string;
  name: string;
  hp: number;
  maxHp: number;
  /** It is up RIGHT NOW. Local, off the button — not a five-hertz value. */
  up: boolean;
  card: HudGearCard | null;
}

/**
 * WHAT THE BODY IS DRESSED AS, as opposed to what it is protected by.
 *
 * The panel headlines this rather than a material, because "what am I wearing"
 * is a question about an IDENTITY once armour carries tags — a set of leather
 * is not just worse steel, it is the thing that unlocks a blade's ultimate.
 * `pieces` over `total` is what the ultimate panel's requirement row is
 * counting, so the two surfaces are reading the same number.
 */
export interface HudArmorSet {
  /** "Sombra", "Muralha"… or null with nothing on. */
  name: string | null;
  /** The dominant material's colour, so the header reads as its rung. */
  rarity: LootRarity | null;
  /** Pieces of that set actually worn. */
  pieces: number;
  /** Pieces there are to wear. `config.armorSlots.length`. */
  total: number;
}

export interface HudArmor {
  /**
   * The mannequin is expanded. Client-local, like the bag's — the server has
   * no opinion about whether somebody is looking at their own kit.
   *
   * COLLAPSED IS THE DEFAULT AND IT IS NOT EMPTY: collapsed still says the
   * set, the rating and how much of the body is covered, because "am I still
   * protected" has to be answerable without a keypress. What expanding buys is
   * WHICH piece and WHAT it is, which is a question you ask between fights.
   */
  open: boolean;
  slots: HudArmorSlot[];
  shield: HudShield | null;
  /**
   * DAMAGE the whole set takes off a blow.
   *
   * The one piece of arithmetic worth doing for the player: a plate only
   * answers the blows that land on ITS part, so a full set of one material is
   * exactly that material's rating and a partial set is less. It sits above a
   * health bar counted in the same units, which is the point — `-5` beside
   * `100` is a sentence.
   */
  armor: number;
  /** The set's identity. See `HudArmorSet`. */
  set: HudArmorSet;
  /** Durability left across every worn piece, and the ceiling on it. */
  hp: number;
  maxHp: number;
}

/**
 * ONE REQUIREMENT ROW ON THE ULTIMATE PANEL.
 *
 * Built from `config.ultimateTags`, never from a table here: a requirement is
 * a tag, a tag has a name and a source on the wire, and a HUD that kept its
 * own Portuguese for them would be a second place for "Conjunto Sombra" to be
 * renamed out of step.
 */
export interface HudUltimateRequirement {
  tag: string;
  /** Portuguese. For an armour tag this is the SET's name. */
  label: string;
  met: boolean;
  /**
   * ARMOUR REQUIREMENTS COUNT AND WEAPON REQUIREMENTS DO NOT, which is the
   * whole reason `source` rides the wire. Holding a katana is true or false;
   * wearing Sombra is two of three, and a row that could only say "no" would
   * hide the fact that the player is one helmet away.
   */
  have?: number;
  need?: number;
}

/**
 * THE ULTIMATE OF THE WEAPON IN HAND, or null when it has none.
 *
 * It follows the belt: 1/2/3 changes what this panel is about, which is the
 * one rule the whole feature rests on. There is no selected ultimate and no
 * second belt to learn.
 */
export interface HudUltimate {
  key: string;
  name: string;
  blurb: string;
  /** Indexes the ultimate icon atlas (`/ultimates/sheet.png`). */
  frame: number;
  /** The weapon that owns it, by name. */
  weapon: string;
  /** Something in `requirements` is not met. The bar does not fill either. */
  locked: boolean;
  requirements: HudUltimateRequirement[];
  /** 0..1 of the way to a full bar. Always 0 while locked. */
  charge: number;
  /** The bar is full and R would fire. */
  ready: boolean;
  /**
   * Seconds left of an OPEN window, or 0. Only the empower ultimates ever
   * have one — a crescent and a pulse are over on the frame they are pressed.
   */
  active: number;
  /** The window's full length, so the panel can draw it draining. */
  duration: number;
  /**
   * Bumps every time THIS player fires one. A count and not a flag, for the
   * reason every other one-shot on this store is: the panel replays its own
   * flash off the number changing, and at 5 Hz a boolean would be missed.
   */
  fires: number;
}

export interface HudInventory {
  open: boolean;
  cap: number;
  slots: Array<HudInventorySlot | null>;
  weight: number;
  maxWeight: number;
  /** Sum of item values in the bag. In-flight collects are not counted yet. */
  gold: number;
  /** Bumps the pack when a fly lands. Count, not a boolean — 5 Hz. */
  catches: number;
  /** Full-bag refusals. Same counter contract as the lantern. */
  refusals: number;
}

export interface HudLootPrompt {
  id: string;
  name: string;
  rarity: LootRarity;
  /** E would refuse. The tooltip says why — see `reason`. */
  full: boolean;
  /**
   * WHY it is refused, because "Inventário Cheio" is a lie for two of the
   * three cases and a player standing over a box of rifle rounds with an
   * empty bag has no way to find that out.
   *
   *   bag       no free cell and no stack — the only case the old copy fit
   *   calibre   AMMUNITION for a gun nobody in your hands can fire. Not a
   *             refusal about space at all: the box is fine, it is not yours
   *   reserve   ammunition you CAN fire and are already carrying the most of
   *
   * Absent when nothing is refused.
   */
  reason?: 'bag' | 'calibre' | 'reserve';
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
   *   feed   the platform is powered, lamps green, and the bag has something
   *          in it. ONE MODE, over the quota and under it: E tips the whole
   *          pack in either way, and past the quota what goes in grows the
   *          core waiting at the far end. The count beside the prompt is what
   *          says which side of the bill the party is on.
   *   close  the quota is settled and the pocket is empty. E CALLS THE
   *          PICKUP — lamps red, siren, and every creature on the map turns
   *          toward the clearing. Everything past the quota comes back as one
   *          condensed core once the platform is gone.
   */
  mode: 'open' | 'busy' | 'feed' | 'close';
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
  /**
   * What is on the table, described. Shown WITHOUT being asked for — a shop
   * is where a player decides what to spend a night's extraction on, and
   * deciding that from a name and a number is deciding blind. Null for the
   * ammunition crates, whose whole offer is already the two numbers on the
   * prompt line.
   */
  card?: HudGearCard | null;
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
  /**
   * Rounds this press would hand over. Set on an AMMUNITION CRATE and absent
   * on a stall, which is what the card branches on: a crate is bought over and
   * over and the number is the whole offer, where a weapon is bought once and
   * its name is.
   */
  rounds?: number;
  /**
   * The reserve is already at its cap. The crate's version of `full` — named
   * apart from it because the refusals are different sentences: a belt with no
   * room is a thing you can fix by trading, and a full magazine pouch is a
   * thing you fix by shooting.
   */
  stocked?: boolean;
}

/**
 * Proximity prompt on the upgrade machine.
 *
 * `spins` is what the press would spend, and it is on the prompt rather than
 * left to the tray because the answer to "can I pull this" is a number the
 * player has to be able to read while standing at the lever, not one they have
 * to go and find in a corner.
 *
 *   ready   a level is owed and the cabinet is free — E pulls, for nothing
 *   buy     no level owed, but the party can cover `price` — E pulls for gold
 *   broke   no level owed and the balance will not reach `price`
 *   busy    somebody else's pull is still running
 *
 * THERE IS NO "NOTHING TO DO HERE" STATE ANY MORE. The cabinet used to go
 * quiet with nothing owed and say where levels come from; it now names a
 * price instead, because a machine that will always take money is a machine
 * the party keeps walking back to — and the levels teach themselves in the
 * woods, where the announce card fires on the body that earned one.
 */
export interface HudMachinePrompt {
  mode: 'ready' | 'buy' | 'broke' | 'busy';
  spins: number;
  /**
   * What the next BOUGHT pull costs. Shown in every mode but `busy`, including
   * `ready`: somebody holding a free spin still wants to know what the one
   * after it will run them BEFORE they spend the free one.
   */
  price: number;
}

/**
 * The merchant, and what he will do for money.
 *
 * A PROMPT OF HIS OWN rather than a mode on `HudMachinePrompt`. The cabinet
 * sells SKILLS and he sells OBJECTS, and a party pressing one lever for both
 * would have no idea which of the two they were bargaining with — which is
 * also why the two fixtures stand at opposite ends of the room.
 */
export interface HudRerollPrompt {
  /**
   * `buy` — he will do it. `broke` — the purse will not cover the next rung.
   * `empty` — the party has bought the whole shelf and there is nothing left
   * to shuffle, which is a refusal rather than a purchase: charging for a
   * reroll of nothing is the one thing a price ladder must never do.
   */
  mode: 'buy' | 'broke' | 'empty';
  /** What the NEXT one costs. Doubles per purchase, resets each night. */
  price: number;
  /** How many tables are still holding something. */
  left: number;
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
   * ON THE FLOOR. Not a respawn timer — nothing stands this body up except
   * the party reaching the next zone, and if nobody is left standing to get
   * them there the run is over. The HUD says so in place of the vitals,
   * because a health bar reading zero over a body that is not coming back is
   * the wrong information.
   */
  downed: boolean;
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

/**
 * HOW MANY OF THE PARTY ARE STILL ON THEIR FEET.
 *
 * The only warning anybody gets that the run is one blow from ending, and it
 * is a COUNT rather than a list because that is the question being asked in
 * the half-second it gets read. Null solo — one of one is not information,
 * it is the health bar restated, and a "1/1 up" pip on a solo screen would be
 * permanent furniture that never changes.
 */
export interface HudParty {
  up: number;
  total: number;
}

/**
 * The run is over. Present only while the death card holds, and cleared by the
 * `welcome` that puts the party back at the fire.
 */
export interface HudWipe {
  /** The night it ended ON — by the time the reset lands the day is 1 again. */
  day: number;
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

/**
 * One mid-run announcement: a card at the upper third, read and gone.
 *
 * `key` is the EVENT, not the kind of event — `level-7`, never `level` —
 * because the card is a one-shot that replays on the key changing and the
 * store never clears it. Two levels in one night with the same key would
 * announce once.
 */
export interface HudAnnounce {
  key: string;
  title: string;
  subtitle: string;
  /**
   * Group gold this card is about, or absent when it is not about money.
   *
   * The card STATES the number once, with a coin beside it; it does not count.
   * The counting already happens on the `Balance` row, driven by the coins
   * flying to it off the platforms — so a card that also animated would be
   * React in the frame loop for a number the canvas is already animating.
   */
  amount?: number;
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
  /**
   * The run ended. Everything else on the glass is irrelevant while this is
   * set — `HudScreen` draws the card over the top and nothing under it needs
   * to know.
   */
  wipe: HudWipe | null;
  /** How many of the party are still up. Null solo — see `HudParty`. */
  party: HudParty | null;
  /** The two medical cells, and whatever is being spent out of them. */
  medical: HudMedical | null;
  /** Set on entering a zone; the title card plays and then leaves it alone. */
  arrival: HudArrival | null;
  /**
   * The last thing worth interrupting the player for, or null before there
   * has been one. Same one-shot contract `arrival` has — set it and forget
   * it; `Announce` owns how long it stays up.
   */
  announce: HudAnnounce | null;
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
  /**
   * THE BOSS BAR, or null — which is every frame of every night but one.
   *
   * A whole object rather than a pile of loose fields, so the panel is a
   * single presence test and so "no boss" cannot be half true. It is the only
   * enemy in the game the HUD has ever been told about by name: everything
   * else is a body in a world you look at, and a health bar with a name over
   * it is the game saying THIS one is the subject.
   */
  boss: HudBoss | null;
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
  cratePrompt: HudCratePrompt | null;
  /**
   * Proximity prompt on an extraction pad. `open` while dormant, `feed`
   * once the platform is running and the load quest is live.
   */
  riftPrompt: HudRiftPrompt | null;
  /** Proximity prompt on a shop table. Null outside the store. */
  buyPrompt: HudBuyPrompt | null;
  /** Proximity prompt on the upgrade machine. Null outside the store. */
  machinePrompt: HudMachinePrompt | null;
  /** Proximity prompt on the merchant himself. Null outside the store. */
  rerollPrompt: HudRerollPrompt | null;
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
   * What is between this body and the next blow: three worn parts and the
   * shield. Beside the vitals rather than beside the belt, because it answers
   * a question about the BODY — the same question the health bar answers,
   * one layer further out.
   */
  armor: HudArmor | null;
  /**
   * What R does with the weapon in hand, or null when it does nothing.
   *
   * ABOVE the belt rather than beside the vitals, because it is a statement
   * about the thing in your hands and not about your body — and because it
   * changes when the belt changes, so the two want to be read in one glance.
   */
  ultimate: HudUltimate | null;
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
  wipe: null,
  party: null,
  medical: null,
  arrival: null,
  announce: null,
  introducing: true,
  cinematic: false,
  boss: null,
  ready: null,
  prompt: null,
  lootPrompt: null,
  cratePrompt: null,
  riftPrompt: null,
  buyPrompt: null,
  machinePrompt: null,
  rerollPrompt: null,
  skills: [],
  spins: 0,
  reward: null,
  balance: 0,
  exitGuide: 0,
  inventory: null,
  hotbar: null,
  armor: null,
  ultimate: null,
  quests: [],
};

export type HudStore = Store<HudSnapshot>;

export function createHudStore(): HudStore {
  return new Store<HudSnapshot>(EMPTY_HUD);
}
