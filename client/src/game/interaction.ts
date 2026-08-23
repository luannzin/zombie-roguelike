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

import type { GameConfig, LootState, PlayerMeta } from '../net/protocol';
import type { HudBuyPrompt, HudLootPrompt, HudRiftPrompt } from './hud-store';
import { objectLabel, objectTilesW } from './objects';
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
export function canStow(s: InteractionState, key: string): boolean {
  const catalog = s.config?.loot ?? {};
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
    const guns = s.meta?.guns;
    const owns = (guns?.slots ?? []).some(
      (cell) => cell !== null && s.config?.weapons?.[cell]?.ammo === calibre,
    );
    if (!owns) return false;
    const cap = s.config?.ammo?.max?.[calibre];
    return cap === undefined || (s.ammo[calibre] ?? 0) < cap;
  }
  if (def?.pocket === 'hotbar') {
    const guns = s.meta?.guns;
    if (!guns) return true;
    return guns.slots.some((cell) => cell === null);
  }
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
export function cratePromptInfo(s: InteractionState): string | null {
  if (s.locked || s.introHold) return null;
  if (nearLoot(s)) return null;
  if (riftPrompt(s)) return null;
  const near = nearCrate(s);
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
export function riftPrompt(s: InteractionState): HudRiftPrompt | null {
  if (s.locked || s.introHold) return null;
  // Mid-pour there is nothing to offer: the server refuses a second press
  // for the length of one, and a key prompt that does nothing when pressed
  // is worse than no prompt at all.
  if (s.pouring) return null;
  const rift = nearRift(s);
  if (!rift) return null;
  const empty = s.pocketGold() <= 0;
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

export function lootPromptInfo(s: InteractionState): HudLootPrompt | null {
  if (s.zoneKind === 'camp' || s.locked || s.introHold) return null;
  const near = nearLoot(s);
  if (!near || !s.config) return null;
  const def = s.config.loot?.[near.k];
  if (!def) return null;
  if (canStow(s, near.k)) {
    return { id: near.id, name: def.name, rarity: def.rarity, full: false };
  }
  // Belt full. If a gun is in hand this is a TRADE, not a refusal — the
  // prompt names what you would be putting down, because that is the half
  // of the decision the player cannot see from the drop's own tooltip.
  const trade = def.pocket === 'hotbar' ? swapTargetFor(s) : null;
  return {
    id: near.id,
    name: def.name,
    rarity: def.rarity,
    full: trade === null,
    swap: trade ?? undefined,
  };
}
