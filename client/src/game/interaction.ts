/**
 * What E is offering right now, and whether it would be refused.
 *
 * One question, asked from three places on two different clocks: `publishHud`
 * needs it five times a second to draw the tooltip, `syncTooltipAnchors` needs
 * it every frame to place that tooltip in the world, and `sendInteract` needs
 * it on the keypress to decide what to put on the socket. It used to live
 * inline in `game.ts` between the HUD builders and the crate effects, which
 * meant reading it required the orchestrator's whole field list.
 *
 * NOTHING HERE MUTATES, SENDS, DRAWS OR MAKES A NOISE. Every function takes an
 * `InteractionState` — a read-only view of the few things a reach test needs —
 * and returns an answer. The refusal SOUND, the packet and the HUD patch all
 * stay with `Game`, because those are decisions about what to DO with the
 * answer. That split is what makes this file safe to read on its own: there is
 * no ordering, no lifetime and no side effect to hold in your head.
 *
 * TWO RULES ARE MIRRORED FROM THE SERVER AND ARE THE REASON THIS IS NOT
 * PRESENTATION. `canStow` re-derives `Room.collect_loot` + `Inventory.add` +
 * `ammo.Reserve`, and `swapTargetFor` re-derives `Room.swap_weapon`. They are
 * duplicated on purpose: a prompt colours a tooltip at frame rate and cannot
 * wait for a round trip. The server still decides; this only decides what the
 * tooltip PROMISES, and a disagreement shows up as a green prompt the server
 * then ignores. Change either rule and change both files.
 *
 * Every reach test measures FEET (the collision box centre plus
 * `playerHalfHeight`) to the target's contact point, against a range in
 * `welcome.config`. That is the same measurement the matching server handler
 * makes, which is what keeps "close enough" one fact rather than two.
 */

import { compareGear, gearCard, type HudGearCard } from './gear-card';
import type {
  GameConfig, LootState, PackState, PlayerMeta, PlayerState,
} from '../net/protocol';
import type {
  HudBuyPrompt, HudCarryPrompt, HudCratePrompt, HudLootPrompt, HudRiftPrompt,
} from './hud-store';
import { objectLabel, objectOpenTime, objectTilesW } from './objects';
import type { LocalPlayer } from './prediction';
import type { AmmoBox, CratePiece, Rift, Stand, TileMap } from './world';

/**
 * Everything a reach test or a prompt reads, and nothing else.
 *
 * The nullable fields are nullable exactly where `Game`'s own are: before the
 * first `welcome` there is no config, no map and no predicted body, and every
 * function here answers null or false in that window rather than being gated
 * on a check its caller had to remember.
 */
export interface InteractionState {
  config: GameConfig | null;
  world: TileMap | null;
  /** The predicted local body. Positions are box CENTRES, not feet. */
  local: LocalPlayer | null;
  /** World drops by id — `Game`'s live ground list. */
  loot: ReadonlyMap<string, LootState>;
  /** Backpacks on the ground, by id. Almost always empty. */
  packs: ReadonlyMap<string, PackState>;
  /**
   * Every other body's tick row, by id. This is where `down`, `out` and
   * `held_by` live, and it is what the carry reach walks.
   */
  bodies: ReadonlyMap<string, PlayerState>;
  /** Every body's identity, for naming whoever is on the floor in front of you. */
  party: ReadonlyMap<string, PlayerMeta>;
  /** The id of the body in the local player's arms, or null. */
  carrying: string | null;
  /** The local player's own roster row: bag, belt, mods. */
  meta: PlayerMeta | null;
  /** Rounds by calibre, the client's predicted mirror of the reserve. */
  ammo: Readonly<Record<string, number>>;
  /** Belt cell in hand, -1 holstered. CLIENT-AUTHORED — see `Game.heldSlot`. */
  heldSlot: number;
  zoneKind: string | undefined;
  /** The party's purse, for whether a price can be met. */
  balance: number;
  /**
   * Catalog value sitting in the pocket, flies excluded — `HudInventory.gold`.
   *
   * A THUNK rather than a number, and that is deliberate: it walks the whole
   * loot catalog, only `riftPrompt` wants it, and `riftPrompt` returns early
   * on most frames (locked, mid-intro, mid-pour, or no pad in reach). Passing
   * the value eagerly would move that walk onto every frame of the run for the
   * benefit of the few where a player is actually stood at a console.
   */
  pocketGold: () => number;
  /** `departing || arriving` — the body is a puppet and E is not offered. */
  locked: boolean;
  /** Still inside the arrival hold, before controls are handed back. */
  introHold: boolean;
  /** This client's own ready flag, which leads the roster by a packet. */
  localReady: boolean;
  departing: boolean;
  /** Mid-pour: the server refuses a second press for the length of one. */
  pouring: boolean;
  /**
   * Mid-channel: a heal or a vault is running. Same rule as `pouring` and a
   * separate flag because they are separate refusals on the server — a body
   * can only be doing one of the three, but the client learns about them from
   * different fields.
   */
  channelling: boolean;
}

// --- reach: what is in front of the feet -------------------------------------

/** Feet of the local body in world pixels, or null before the first welcome. */
function feet(s: InteractionState): { x: number; y: number } | null {
  const config = s.config;
  const local = s.local;
  if (!config || !local) return null;
  return { x: local.state.x, y: local.state.y + config.playerHalfHeight };
}

export function nearFire(s: InteractionState): boolean {
  const world = s.world;
  const config = s.config;
  const at = feet(s);
  if (!world || !config || !at) return false;
  const fire = world.fires[0];
  if (!fire) return false;
  const range = (config.readyRangeTiles ?? config.hearthTiles) * config.tileSize;
  return Math.hypot(at.x - fire.x, at.y - fire.y) <= range;
}

/**
 * The object E is offering, or null.
 *
 * Distance runs feet to the nearest point of the FOOTPRINT, mirroring
 * `crates.nearest`. A bus is four tiles long: measured centre to centre,
 * standing at its rear doors is standing two tiles away from the object,
 * and the prompt would refuse on the exact spot the art is pointing at.
 */
export function nearCrate(s: InteractionState): CratePiece | null {
  const config = s.config;
  const world = s.world;
  const at = feet(s);
  if (!config || !world || !at) return null;
  const range = config.crateBreakTiles * config.tileSize;
  let best: CratePiece | null = null;
  let bestD2 = range * range;
  for (const crate of world.crates) {
    if (crate.opened) continue;
    const half = objectTilesW(crate.kind) * config.tileSize * 0.5;
    const dx = Math.max(0, Math.abs(crate.x - at.x) - half);
    const dy = crate.y - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      best = crate;
    }
  }
  return best;
}

export function nearLoot(s: InteractionState): LootState | null {
  const config = s.config;
  const at = feet(s);
  if (!config || !at) return null;
  const range = config.lootCollectTiles * config.tileSize;
  let best: LootState | null = null;
  let bestD2 = range * range;
  for (const drop of s.loot.values()) {
    const dx = drop.x - at.x;
    const dy = drop.y - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      best = drop;
    }
  }
  return best;
}

/**
 * The downed teammate close enough to get your hands under, or null.
 *
 * MIRROR OF `Room._body_in_reach`, including the two things that are easy to
 * leave out of a client copy and impossible to see missing: a body somebody
 * else is already carrying is skipped (two carriers would be two writers of
 * one position), and the reach is measured FEET TO FEET like every other one
 * in this file.
 */
export function nearBody(s: InteractionState): PlayerState | null {
  const config = s.config;
  const at = feet(s);
  if (!config || !at) return null;
  const range = config.carryReachTiles * config.tileSize;
  let best: PlayerState | null = null;
  let bestD2 = range * range;
  for (const row of s.bodies.values()) {
    // The local body is never in `bodies` — see `Game.interactionState` — so
    // there is nothing to skip here beyond the two rules the server keeps.
    if (!row.down || row.held_by) continue;
    const dx = row.x - at.x;
    const dy = row.y + config.playerHalfHeight - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = row;
    }
  }
  return best;
}

/**
 * The local player's OWN pack, if they are standing at it. Mirror of
 * `Room._pack_in_reach`.
 *
 * Somebody else's is deliberately invisible to this: it is not a refusal the
 * player can do anything about, and a prompt that appeared over a teammate's
 * bag only to say no would teach them to walk over and try.
 */
export function nearPack(s: InteractionState): PackState | null {
  const config = s.config;
  const at = feet(s);
  if (!config || !at) return null;
  const range = config.carryReachTiles * config.tileSize;
  let best: PackState | null = null;
  let bestD2 = range * range;
  for (const pack of s.packs.values()) {
    if (pack.by !== s.meta?.id) continue;
    const dx = pack.x - at.x;
    const dy = pack.y - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = pack;
    }
  }
  return best;
}

export function nearRift(s: InteractionState): Rift | null {
  const config = s.config;
  const world = s.world;
  const at = feet(s);
  if (!config || !world || !at) return null;
  const range = config.riftActivateTiles * config.tileSize;
  let best: Rift | null = null;
  let bestD2 = range * range;
  for (const rift of world.rifts) {
    const dx = rift.consoleX - at.x;
    const dy = rift.consoleY - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = rift;
    }
  }
  return best;
}

/**
 * The stall the local player could buy from, or null.
 *
 * Measured from the FEET to the table's contact, mirroring
 * `Room._stand_in_reach`, so the prompt on screen and the check on the
 * server agree. Sold tables are skipped: an empty table is not something to
 * be standing at.
 */
export function nearStand(s: InteractionState): Stand | null {
  const config = s.config;
  const fixtures = s.world?.store;
  const at = feet(s);
  if (!config || !fixtures || !at) return null;
  const range = config.storeBuyTiles * config.tileSize;
  let best: Stand | null = null;
  let bestD2 = range * range;
  for (const stand of fixtures.stands) {
    if (stand.sold) continue;
    const dx = stand.x - at.x;
    const dy = stand.y - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = stand;
    }
  }
  return best;
}

/**
 * The ammunition crate the local player could buy from, or null.
 *
 * Same measurement `nearStand` makes and against the same reach, because the
 * server checks both with one constant (`STORE_BUY_DIST`) — a crate that
 * answered at a different distance from the table beside it would be a second
 * idea of "standing at something" in one room.
 *
 * A CRATE IS NEVER SKIPPED FOR BEING SPENT. `nearStand` steps over a sold
 * table because an empty table is not something to stand at; a crate never
 * empties, so the only thing that can take it out of the prompt is walking
 * away from it.
 */
export function nearAmmoBox(s: InteractionState): AmmoBox | null {
  const config = s.config;
  const fixtures = s.world?.store;
  const at = feet(s);
  if (!config || !fixtures || !at) return null;
  const range = config.storeBuyTiles * config.tileSize;
  let best: AmmoBox | null = null;
  let bestD2 = range * range;
  for (const box of fixtures.boxes) {
    const dx = box.x - at.x;
    const dy = box.y - at.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = box;
    }
  }
  return best;
}

// --- legality: the two rules mirrored off the server -------------------------

/**
 * Whether a pickup of `key` would be accepted, mirroring `Room.collect_loot`.
 *
 * See the file header: this is a duplicate of a server rule on purpose, and
 * the two have to move together.
 */
/**
 * Why a box of rounds would be refused, or null if it would not be.
 *
 * AMMUNITION ANSWERS TO YOUR OWN BELT, and to nothing else. Mirrors
 * `Room.collect_loot`: a calibre you are not carrying is refused (the rifle
 * rounds belong to whoever brought the rifle) and a reserve already at its cap
 * is refused too — the box stays on the ground and is still there on the way
 * back, which is exactly what a player wants from ammunition they cannot use
 * yet.
 *
 * IT RETURNS WHICH REFUSAL RATHER THAN A BOOLEAN, and that is the whole point
 * of it being its own function. The three refusals in this game are three
 * different sentences and only one of them is about space: a player standing
 * over a box of rifle rounds with an empty bag was being told "Inventário
 * Cheio", which is not true, does not explain anything, and teaches them that
 * the prompt lies. What they need to know is that the box belongs to whoever
 * brought the rifle.
 */
export function ammoRefusal(
  s: InteractionState,
  calibre: string | undefined,
): 'calibre' | 'reserve' | null {
  if (!calibre) return 'calibre';
  const guns = s.meta?.guns;
  const owns = (guns?.slots ?? []).some(
    (cell) => cell !== null && s.config?.weapons?.[cell]?.ammo === calibre,
  );
  if (!owns) return 'calibre';
  const cap = s.config?.ammo?.max?.[calibre];
  if (cap !== undefined && (s.ammo[calibre] ?? 0) >= cap) return 'reserve';
  return null;
}

export function canStow(s: InteractionState, key: string, hp?: number): boolean {
  const catalog = s.config?.loot ?? {};
  const def = catalog[key];
  if (def?.pocket === 'ammo') return ammoRefusal(s, def.ammo) === null;
  if (def?.pocket === 'med') {
    // MEDICINE REFUSES WHEN BOTH CELLS ARE FULL, and it refuses rather than
    // swapping — unlike a gun cell. Two kits are a QUANTITY, not alternatives,
    // so quietly dropping one to pick up another would be the game throwing
    // away the exact resource the player bent down to stockpile. The drop
    // stays on the ground, which is the same answer a full ammunition reserve
    // gives. Mirrors `Room.collect_loot` + `Medical.add`.
    const cells = s.meta?.med;
    if (!cells) return true;
    return cells.some((cell) => cell === null || cell === undefined);
  }
  if (def?.pocket === 'worn') {
    // ONE REFUSAL, AND IT IS THE ONLY ONE THIS CATEGORY NEEDS: the piece you
    // are already wearing, in the same or better condition. Everything else
    // goes on — including a piece that is WORSE than what is there, because
    // "worse" is not something the game gets to decide for you. Mirrors
    // `Room.wear_armor`.
    const piece = s.config?.armor?.[key];
    if (!piece) return false;
    const worn = s.meta?.armor?.[piece.slot];
    if (!worn || worn.k !== key) return true;
    return worn.hp < (hp ?? piece.maxHp);
  }
  if (def?.pocket === 'hotbar') {
    const guns = s.meta?.guns;
    if (!guns) return true;
    const weapon = s.config?.weapons?.[key];
    // A LÂMINA ALWAYS HAS ROOM, because its cell is never empty and picking
    // one up is a replacement rather than a stow. The only refusal is the
    // blade already in the cell: a pickup that changed nothing and dropped
    // what it replaced reads as the game taking something off you. Mirrors
    // `Hotbar.can_stow`.
    if (weapon?.melee) {
      const cell = s.config ? guns.slots[s.config.bladeSlot] : null;
      return cell !== key;
    }
    // AT MOST ONE SHIELD, EVER. Not a technical limit — a belt holding two
    // riot shields is a belt with no guns on it at all.
    if (weapon?.shield && holdsShield(s)) return false;
    const gunCells = s.config?.gunSlots ?? guns.slots.length;
    return guns.slots.slice(0, gunCells).some((cell) => cell === null);
  }
  // NO PACK, NO CARGO. Mirror of `Room.collect_loot`: the bag is on the ground
  // somewhere because this player picked a teammate up, and a body with no bag
  // has nowhere to put a relic.
  //
  // IT REFUSES ONLY THE POCKET, and every branch above has already returned -
  // rounds, a plate, a bandage and a weapon are not in the bag and never were.
  // That is the whole reason the five containers are separate: what a rescue
  // costs is the NIGHT'S TAKINGS, not the ability to survive the walk back.
  if (s.meta && s.meta.pack === false) return false;
  const inv = s.meta?.inv;
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

/**
 * Name of the gun a pickup would trade away, or null if none can be.
 *
 * Mirrors `Room.swap_weapon`: the hand has to hold a GUN. The knife is not
 * tradeable — it is the one weapon that cannot be lost, and a pickup that
 * could consume its cell would put the floor under the whole loadout one
 * misplaced E away. Holstered refuses too: an empty hand is not a choice
 * about which gun to keep.
 */
export function swapTargetFor(s: InteractionState): string | null {
  const guns = s.meta?.guns;
  if (!guns || s.heldSlot < 0) return null;
  const key = guns.slots[s.heldSlot];
  if (!key) return null;
  const def = s.config?.loot?.[key];
  if (!def || def.pocket !== 'hotbar') return null;
  if (s.config?.weapons?.[key]?.melee) return null;
  return def.name;
}

/**
 * What picking `key` up would DISPLACE, when the pickup is a swap rather than
 * a stow. Null when nothing comes off.
 *
 * The counterpart of `swapTargetFor`, and deliberately a different function:
 * that one answers "the belt is full, what can I give up", which is a
 * REFUSAL turned into a choice. This one answers "this always fits, and here
 * is what it lands on top of" — which is the blade cell and the three worn
 * parts, the places in this game where there is no such thing as empty.
 */
export function replacedBy(s: InteractionState, key: string): string | null {
  const piece = s.config?.armor?.[key];
  if (piece) {
    const worn = s.meta?.armor?.[piece.slot];
    return worn ? (s.config?.loot?.[worn.k]?.name ?? null) : null;
  }
  if (!s.config?.weapons?.[key]?.melee) return null;
  const cell = s.meta?.guns?.slots[s.config.bladeSlot];
  // THE KNIFE IS NOT AN OBJECT and is never named as something you give up:
  // it is the promise that the cell is full, and it does not land on the
  // floor when a better lâmina replaces it. Mirrors `Room.swap_blade`.
  if (!cell || cell === s.config.startingBlade) return null;
  return s.config.loot?.[cell]?.name ?? null;
}

/**
 * The card for what the player ALREADY HAS in the place `key` would go, or
 * null when that place is empty.
 *
 * THE THIRD MIRRORED RULE IN THIS FILE, and it exists for the same reason the
 * other two do: a comparison drawn at frame rate cannot wait for a round trip.
 * It answers the question "what am I weighing this against" for every surface
 * that describes an object the player does not own yet — a drop in the grass,
 * a table in the shop — and `compareGear` turns the answer into arrows.
 *
 * FOUR CATEGORIES, FOUR ANSWERS, and each one is the object that would
 * actually be given up:
 *
 *   worn      the plate on that part of the body, WITH ITS WEAR, because a
 *             cracked steel breastplate is genuinely worse than a fresh cloth
 *             one and the card has to be able to say so
 *   blade     whatever is in the blade cell, knife included. The knife is not
 *             an object the party owns, but it is a real weapon with real
 *             numbers and "is this axe better than the knife" is the first
 *             comparison anybody makes in a run
 *   shield    the shield on the belt, with what is left of it
 *   gun       the gun in hand, or — holstered, or holding steel — the first
 *             gun on the belt. Not always a REPLACEMENT (a free cell takes it
 *             without giving anything up), but always the thing the player is
 *             deciding between, which is what the arrows are for
 *
 * MEDICINE HAS NO COUNTERPART AND GETS NO ARROWS. A kit never displaces
 * another kit — the belt refuses a third rather than swapping one away (see
 * `canStow`) — so there is nothing being weighed against anything, and a card
 * of arrows would be inventing a decision the game does not ask for.
 */
export function currentGear(s: InteractionState, key: string): HudGearCard | null {
  const config = s.config;
  if (!config) return null;

  const piece = config.armor[key];
  if (piece) {
    const worn = s.meta?.armor?.[piece.slot];
    if (!worn) return null;
    return gearCard(config, worn.k, { hp: worn.hp, max: worn.max });
  }

  const weapon = config.weapons[key];
  if (!weapon) return null;
  const slots = s.meta?.guns?.slots ?? [];

  if (weapon.melee) {
    const blade = slots[config.bladeSlot];
    // Not against itself. A lâmina carries no wear, so an identical key is an
    // identical card, and a column of level dashes is noise beside a prompt
    // that already says you are carrying this one.
    if (!blade || blade === key) return null;
    return gearCard(config, blade);
  }
  if (weapon.shield) {
    const worn = s.meta?.shield;
    return worn ? gearCard(config, worn.k, { hp: worn.hp, max: worn.max }) : null;
  }

  const gunCells = config.gunSlots;
  const held = s.heldSlot;
  const inHand =
    held >= 0 && held < gunCells ? slots[held] : null;
  const other = inHand ?? slots.slice(0, gunCells).find((cell) => !!cell) ?? null;
  // A gun does not compare itself against itself. Standing over a second AK
  // with one already in hand, every row would read level and the card would
  // be three dashes saying "this is the thing you have".
  if (!other || other === key) return null;
  return gearCard(config, other);
}

/** `gearCard` for `key`, marked against whatever the player already has. */
function offeredGear(
  s: InteractionState,
  key: string,
  wear?: { hp: number; max: number },
): HudGearCard | null {
  const config = s.config;
  if (!config) return null;
  const card = gearCard(config, key, wear);
  return card ? compareGear(card, currentGear(s, key)) : null;
}

// --- prompts: the answer the tooltip and the keypress both read --------------

export function readyPrompt(s: InteractionState): 'ready' | null {
  if (s.zoneKind !== 'camp' || s.departing || s.introHold) return null;
  if (s.localReady) return null;
  if (nearCrate(s)) return null;
  return nearFire(s) ? 'ready' : null;
}

/**
 * The line E is offering on the object in front of you, or null.
 *
 * A STRING RATHER THAN A FLAG, because the objects no longer share a verb:
 * a barrel says destroy, a boot says search, a chest says open. The wording
 * is authored server-side next to the object's drop table
 * (`crates.ObjectType.label`) so the promise and the prompt cannot drift.
 */
export function cratePromptInfo(s: InteractionState): HudCratePrompt | null {
  if (s.locked || s.introHold) return null;
  // Mid-channel there is nothing to offer. The server refuses a second press
  // for the length of one — and for a vault it refuses somebody else's press
  // too — so a prompt that did nothing when pressed is worse than no prompt.
  // Same rule the pad's prompt already applies to a pour.
  if (s.pouring || s.channelling) return null;
  if (nearLoot(s)) return null;
  if (riftPrompt(s)) return null;
  const near = nearCrate(s);
  if (!near) return null;
  return { label: objectLabel(near.kind), seconds: objectOpenTime(near.kind) };
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
export function riftPrompt(s: InteractionState): HudRiftPrompt | null {
  if (s.locked || s.introHold) return null;
  // Mid-pour there is nothing to offer: the server refuses a second press
  // for the length of one, and a key prompt that does nothing when pressed
  // is worse than no prompt at all.
  if (s.pouring) return null;
  const rift = nearRift(s);
  if (!rift) return null;
  // NO BAG IS NOT AN EMPTY BAG, and here the difference is the loudest press
  // in the game. A carrier's pocket reads zero forever, so treating that as
  // "nothing left to give" would offer them the pickup call the moment they
  // walked up to a settled pad — with their whole night still lying in the
  // grass where they picked their teammate up. Mirror of `Room.activate_rift`.
  const noPack = s.meta?.pack === false;
  const empty = !noPack && s.pocketGold() <= 0;
  if (rift.state === 'dormant') {
    const busy = s.world?.rifts.some(
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
  // quota is paid and whether the pocket still has anything. LOADING IS ONE
  // VERB. It used to be two — `feed` under the quota, `over` past it — and the
  // difference was never a difference in what E did: the press has always
  // emptied the bag, and since `Room._begin_pour` dropped its ceiling it
  // empties all of it either way. Two lines for one act only ever asked the
  // player to work out which of them they were reading. Overshoot is on the
  // count beside the prompt, which is where a number belongs.
  // Loading is offered on EVERY pad, last one included — the payout at the end
  // of the night is what was fed, so value loaded past the quota is banked
  // whether or not there is another console left to carry a core to.
  const mode = rift.ready && empty ? 'close' : 'feed';
  return {
    id: rift.id,
    mode,
    have: rift.fed,
    need: rift.need,
    empty,
  };
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
export function buyPrompt(s: InteractionState): HudBuyPrompt | null {
  if (s.locked || s.introHold) return null;
  if (s.zoneKind !== 'store') return null;
  const stand = nearStand(s);
  // THE TABLE WINS A TIE. The two reaches only overlap on the frame somebody
  // is standing exactly between a stall and a crate, and when they do, the
  // expensive irreversible purchase is the one the player meant — a press that
  // spent four gold on rounds when it meant to buy an AK is a worse mistake in
  // both directions than the other way round.
  if (!stand) return ammoPrompt(s);
  const item = s.config?.loot?.[stand.key];
  // A full belt is a TRADE here exactly as it is on a world drop, and the
  // tooltip has to say whose gun is being given up — otherwise E silently
  // costs the player the weapon in their hands.
  const room = canStow(s, stand.key);
  const swap = room ? null : swapTargetFor(s);
  return {
    id: stand.id,
    name: item?.name ?? stand.key,
    rarity: item?.rarity ?? 'common',
    price: stand.price,
    afford: stand.price <= s.balance,
    full: !room && swap === null,
    // WHAT IS ON THE TABLE, DESCRIBED, WITHOUT BEING ASKED FOR. Everywhere
    // else in this game a card is something you hover; here it is something
    // you walk into, because the shop is the one place a player spends a
    // whole night's extraction and a name plus a price is not enough to spend
    // it on. The catalog row rather than a worn one — nothing on a shelf has
    // been used.
    //
    // AND MARKED AGAINST WHAT THE PLAYER IS ALREADY CARRYING, which is the
    // half the stall could never supply. A shop is a comparison by
    // definition: the party is not asking "is this good", they are asking "is
    // this better than the thing I walked in with", and answering that off
    // two stat blocks held in your head is what makes an expensive counter
    // feel like a gamble instead of a decision.
    card: offeredGear(s, stand.key),
    swap: swap ?? undefined,
  };
}

/**
 * What E is offering on an ammunition crate, or null.
 *
 * THE REFUSALS ARE NAMED, exactly as they are on a table: a calibre you are
 * not carrying, a reserve already full, and a price the party cannot cover are
 * three different sentences, and hiding any of them would leave a player
 * standing at a crate wondering why the key does nothing.
 *
 * `canStow` is not reused here even though it answers two of the three, and
 * that is deliberate: it answers about the box on the FLOOR — whether this
 * player may pick that drop up — and a crate is not a drop. Reusing it would
 * tie the shop's refusal to a function whose whole job is the forest's.
 */
function ammoPrompt(s: InteractionState): HudBuyPrompt | null {
  const box = nearAmmoBox(s);
  if (!box) return null;
  const item = s.config?.loot?.[box.key];
  const guns = s.meta?.guns;
  const owns = (guns?.slots ?? []).some(
    (cell) => cell !== null && s.config?.weapons?.[cell]?.ammo === box.calibre,
  );
  // A calibre nobody in the room owns has no crate at all, so this is the
  // four-player case: the rifle crate is on the wall because a teammate
  // brought the rifle, and it is not this player's to buy out of.
  if (!owns) return null;
  const cap = s.config?.ammo?.max?.[box.calibre];
  const stocked = cap !== undefined && (s.ammo[box.calibre] ?? 0) >= cap;
  return {
    id: box.id,
    name: item?.name ?? box.key,
    rarity: item?.rarity ?? 'common',
    price: box.price,
    afford: box.price <= s.balance,
    full: false,
    rounds: box.rounds,
    stocked,
  };
}

/**
 * What E offers on a body, or on your own bag. Null when neither is in reach.
 *
 * ONE PROMPT FOR BOTH HALVES OF ONE TRADE. Picking somebody up costs the bag;
 * walking back for the bag costs putting them down. Two components would have
 * been two vocabularies for a decision the player has to see as one.
 *
 * THE BODY WINS A TIE, and the tie is real: you put the pack down at your own
 * feet, so the frame after a rescue the two reaches overlap exactly. A press
 * meant for a teammate that picked a bag up instead would undo the rescue on
 * the frame it happened.
 */
export function carryPrompt(s: InteractionState): HudCarryPrompt | null {
  if (s.locked || s.introHold) return null;
  if (s.pouring || s.channelling) return null;
  if (!s.local?.alive) return null;

  // ARMS FULL: the only thing E can do is set them down. Offered wherever the
  // player is standing, because putting somebody down anywhere is legal - what
  // changes is whether it MEANS anything, and that is the pad.
  if (s.carrying) {
    const held = s.party.get(s.carrying);
    return {
      mode: 'drop',
      name: held?.name,
      color: held?.color,
      // THE ONE PLACE PUTTING A BODY DOWN DOES SOMETHING. Everywhere else it
      // is just letting go; on a deck it is loading them for the flight, and
      // the copy has to say so BEFORE the press or the whole rescue ends with
      // a player standing next to a platform wondering what to do next.
      onPad: onDeck(s),
    };
  }

  const body = nearBody(s);
  if (body) {
    const who = s.party.get(body.id);
    return { mode: 'lift', name: who?.name, color: who?.color };
  }

  const pack = nearPack(s);
  if (!pack) return null;
  // A pack you cannot pick up because your arms are full is not a refusal
  // about the pack, so it says which. It happens constantly - the bag is at
  // the feet of the body you just lifted.
  return { mode: 'pack', count: pack.n };
}

/** Whether the local player is standing on an extraction deck. */
function onDeck(s: InteractionState): boolean {
  const config = s.config;
  const world = s.world;
  const at = feet(s);
  if (!config || !world || !at) return false;
  // The CONSOLE's reach, mirroring `Room._revive_on_deck` - a body at the edge
  // of a five-by-two skid is on the platform in every sense a player cares
  // about, and a promise that failed on a pixel would be the cruellest bug
  // this game could ship.
  const range = config.riftActivateTiles * config.tileSize;
  for (const rift of world.rifts) {
    if (rift.state !== 'open' || rift.closeAt !== null) continue;
    const dx = rift.deckX - at.x;
    const dy = rift.deckY - at.y;
    if (dx * dx + dy * dy <= range * range) return true;
  }
  return false;
}

export function lootPromptInfo(s: InteractionState): HudLootPrompt | null {
  if (s.zoneKind === 'camp' || s.locked || s.introHold) return null;
  const near = nearLoot(s);
  if (!near || !s.config) return null;
  const def = s.config.loot?.[near.k];
  if (!def) return null;
  // WHAT IS LYING THERE, DESCRIBED, and marked against what is already on the
  // body — the same card the shop shows, for the same reason. A drop costs no
  // gold, but it costs the thing it replaces: the plate coming off, the
  // lâmina hitting the grass, the gun traded away. Until this existed the only
  // way to find out whether the axe in front of you beat the one in your hand
  // was to pick it up and read the belt afterwards, by which point the old one
  // was on the floor behind you.
  //
  // A WORN PIECE CARRIES ITS OWN WEAR ONTO THE CARD. `near.hp` is set only on
  // a plate that has been on somebody — a cracked breastplate somebody swapped
  // out has to still read as cracked, or the card would be advertising a fresh
  // one and the arrows would be comparing a catalog ceiling against a real
  // number.
  const piece = s.config.armor?.[near.k];
  const wear =
    piece && near.hp !== undefined ? { hp: near.hp, max: piece.maxHp } : undefined;
  const card = offeredGear(s, near.k, wear);
  const frame = def.frame;

  if (canStow(s, near.k, near.hp)) {
    // A LÂMINA AND A PLATE ARE ALWAYS SWAPS, so they name what they replace
    // even though nothing is refusing them. The cell is never empty and the
    // part is often not bare, and "you are about to put down the axe" is the
    // half of the decision the drop's own tooltip cannot show.
    const swap = replacedBy(s, near.k);
    return {
      id: near.id,
      name: def.name,
      rarity: def.rarity,
      full: false,
      swap: swap ?? undefined,
      card,
      frame,
    };
  }

  // REFUSED — AND THE COPY HAS TO NAME THE RIGHT REFUSAL, which is where this
  // branch used to be badly wrong. Trading is a rule about GUN CELLS: a gun
  // that will not fit may be exchanged for the gun in your hands, and nothing
  // else in the game may. The old code asked `pocket === 'hotbar'` instead,
  // which is true of every lâmina and every shield — so standing over the axe
  // you were already carrying offered to trade your RIFLE for it, an exchange
  // `Room.take_weapon` has never made and never could (a blade goes through
  // `swap_blade`, which has no gun cell in it at all). The prompt was
  // promising something the server would silently ignore, on the one press
  // where being wrong costs the player their firearm.
  //
  // A SHIELD IS THE CASE THAT PROVES THE RULE IS ABOUT CELLS AND NOT ABOUT
  // OBJECTS: it does live in a gun cell, so a full belt really can trade for
  // one — but a SECOND shield cannot be taken at all, and those two refusals
  // arrive at this line looking identical.
  const weapon = s.config.weapons?.[near.k];
  const tradeable =
    def.pocket === 'hotbar' &&
    !weapon?.melee &&
    !(weapon?.shield && holdsShield(s));
  const trade = tradeable ? swapTargetFor(s) : null;
  return {
    id: near.id,
    name: def.name,
    rarity: def.rarity,
    full: trade === null,
    // WHICH refusal, so the copy can be true. There are six of them and only
    // ONE is about the pocket, which is the word "cheio" this prompt spent a
    // long time saying to all of them.
    reason: trade !== null ? undefined : refusal(s, near.k, def.pocket, def.ammo),
    swap: trade ?? undefined,
    card,
    frame,
  };
}

/**
 * WHY a pickup was refused, in the player's terms.
 *
 * One function because the alternative is a chain of conditionals inside the
 * prompt builder, and the prompt builder is where the wrong answer already
 * lived once. Every branch here mirrors the matching refusal in `canStow`,
 * which mirrors the server's — so a new container arrives as one row in three
 * places rather than as a sentence nobody wrote.
 */
function refusal(
  s: InteractionState,
  key: string,
  pocket: string | undefined,
  calibre: string | undefined,
): NonNullable<HudLootPrompt['reason']> {
  if (pocket === 'ammo') return ammoRefusal(s, calibre) ?? 'bag';
  // NO BAG AT ALL, which is not the same sentence as a full one and is the
  // one refusal in this list the player can fix by walking somewhere.
  if (s.meta?.pack === false) return 'nopack';
  // BOTH CELLS FULL. Not "mochila cheia": medicine has never been in the
  // pocket (`server/app/medical.py`), so a player with four empty bag slots
  // was being told their bag was full and had no way to find out otherwise.
  if (pocket === 'med') return 'med';
  // THE PIECE YOU ARE ALREADY WEARING, in the same or better condition. The
  // only refusal a worn slot has — a WORSE piece still goes on, because
  // "worse" is not the game's call to make.
  if (pocket === 'worn') return 'worn';
  const weapon = s.config?.weapons?.[key];
  // THE BLADE YOU ARE ALREADY CARRYING. The cell is never empty and it always
  // swaps, so this is the single thing that can refuse a lâmina: a pickup
  // that changed nothing and dropped what it replaced.
  if (weapon?.melee) return 'blade';
  // AT MOST ONE SHIELD, EVER. Not a technical limit — a belt holding two riot
  // shields is a belt with no guns on it. A shield refused for any OTHER
  // reason fell through to the belt's own refusal below, because it is in a
  // gun cell like anything else.
  if (weapon?.shield && holdsShield(s)) return 'shield';
  return 'bag';
}

/** Whether a shield is already on the belt. Mirrors `Hotbar.holds_shield`. */
function holdsShield(s: InteractionState): boolean {
  return (s.meta?.guns?.slots ?? []).some(
    (cell) => !!cell && !!s.config?.weapons?.[cell]?.shield,
  );
}
