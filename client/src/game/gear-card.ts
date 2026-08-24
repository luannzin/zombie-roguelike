/**
 * What a piece of gear IS, as a card. One description, four places it appears.
 *
 * A player meets the same object four times — on a shop table, on the ground,
 * in the belt and on the body — and until this existed it introduced itself
 * differently each time: a name and a price at the stall, a name in a prompt,
 * a name and an ammo count on the belt, and the word `steel` on the armour
 * panel. Four surfaces, four vocabularies, and none of them ever said what the
 * thing actually does.
 *
 * SO IT IS ONE FUNCTION AND ONE SHAPE. `gearCard` turns a catalog key into
 * the rows that describe it, and the belt, the armour panel and the shop all
 * render the same card. The alternative — a stat list per surface — is three
 * places to forget a weapon class in, and the store's would be the one nobody
 * looked at.
 *
 * PURE OVER `GameConfig`, and it lives here rather than in a component for the
 * same reason `interaction.ts` does: it is a fact about the catalog, the
 * catalog arrives on the wire, and React must never be the thing that knows
 * how a weapon works.
 *
 * FIVE ROWS EXIST IN THIS WHOLE FILE, AND THAT IS THE DESIGN
 * ==========================================================
 * The first cut of these cards printed everything that was true. A rifle came
 * with damage, cadence, damage per second, range, noise, calibre and weight;
 * a plate came with rating, material, durability, share of blows and weight.
 * Every one of those numbers is real and the card was still WRONG, because a
 * hover card is read in the half second before something reaches you and a
 * seven-row table is not read at all — it is dismissed, and then the player
 * stops hovering, and then the whole system may as well not exist.
 *
 * So there are five kinds of row in the game now and no others:
 *
 *     DANO           what one press is worth
 *     TIROS/S        how often you may press it
 *     ARMADURA       what it takes off a blow
 *     DURABILIDADE   how much is left of it
 *     MUNIÇÃO        what you have, over what you can hold
 *
 * Everything cut was cut on one test: would a player ever choose differently
 * because of it, in the moment they are looking at this card? Range and noise
 * are real and are learned by SHOOTING; weight is real and is already a bar
 * on the bag; a material is already in the object's own name; "acertos aqui"
 * was an interesting fact about anatomy and never once a decision.
 *
 * THE TWO ROWS THAT ARE NOT NUMBERS, and both earn it:
 *
 *   * a shield's ÂNGULO, because a shield's durability is meaningless without
 *     the rule that it only answers what it is facing. It is the one card in
 *     the game where a stat needs its rule beside it or it lies;
 *   * a weapon's ULTIMATE, because that is the single largest thing a player
 *     is choosing between at a shop table and it is invisible everywhere else
 *     until they already own the weapon.
 *
 * AND NOTHING ON A CARD IS ANCHORED ON A CREATURE. An earlier cut resolved
 * armour's fraction against a walker's claw to make it a number — true today,
 * and lying the day there is a second enemy worth comparing against. The fix
 * was upstream: armour is FLAT now (`server/app/armor.py`), so the rating is a
 * number before it ever reaches this file. If a stat here ever needs an
 * example to make sense, the stat is wrong, not the example.
 */

import type { GameConfig, LootRarity } from '../net/protocol';

/** One labelled value on a gear card. */
export interface GearStat {
  label: string;
  value: string;
  /**
   * Draw it as the headline rather than as another row. Exactly one stat per
   * card sets it: the thing you would say out loud about the object. With
   * three rows on a card the headline matters MORE rather than less — it is
   * what the eye lands on, and the other two are what it checks afterwards.
   */
  lead?: boolean;
}

export interface HudGearCard {
  key: string;
  name: string;
  rarity: LootRarity;
  /** Portuguese for what KIND of thing this is — "Fuzil", "Lâmina", "Elmo". */
  kind: string;
  stats: GearStat[];
  /**
   * The ultimate this weapon owns, by name, or absent.
   *
   * A NAME AND NOT A STAT, which is why it is a field rather than a row: the
   * panel above the belt is where an ultimate is explained, and all this has
   * to do is tell somebody standing at a shop table that the thing on it
   * HAS one. That sentence is most of why they would buy a katana over an
   * axe, and until this line existed it was written nowhere they could see it
   * before paying.
   */
  ultimate?: string;
}

/** What a worn or held piece has left, when the card is describing a real one. */
export interface GearWear {
  hp: number;
  max: number;
}

/** Rounds in the reserve behind a weapon, and the ceiling on them. */
export interface GearAmmo {
  have: number;
  max: number;
}

const WEAPON_KIND: Record<string, string> = {
  pistol: 'Pistola',
  smg: 'Submetralhadora',
  shotgun: 'Espingarda',
  rifle: 'Fuzil',
  sniper: 'Precisão',
  minigun: 'Rotativa',
  support: 'Suporte',
  melee: 'Lâmina',
  shield: 'Escudo',
};

/**
 * Portuguese for a worn slot.
 *
 * A FALLBACK AND NOT THE SOURCE. `config.armorSlotNames` is the source and it
 * is what the panel prints; this exists because a card is built from a catalog
 * row, and a piece whose slot the server has renamed should still say
 * something rather than print a raw key. A sixth slot arriving with no entry
 * here reads as its own key, which is ugly and honest.
 */
const ARMOR_KIND: Record<string, string> = {
  head: 'Cabeça',
  arms: 'Braços',
  body: 'Tronco',
  legs: 'Pernas',
  feet: 'Pés',
};

/** Presses per second, to one decimal. See the header for why this replaced RPM. */
function rate(cooldown: number): string {
  return `${(1 / cooldown).toFixed(1)}/s`;
}

/**
 * The card for one catalog key, or null if nothing in the config knows it.
 *
 * `wear` is what a REAL one has left — a plate on a body, a shield on a belt.
 * `ammo` is what is actually in the reserve behind a gun. Both absent means
 * the card is describing the CATALOG ROW rather than an object: a weapon on a
 * shop table, a piece lying in the grass. That distinction is the whole reason
 * they are parameters — the same function has to be able to say "this holds
 * 112" and "this one has 34 left".
 */
export function gearCard(
  config: GameConfig,
  key: string,
  wear?: GearWear,
  ammo?: GearAmmo,
): HudGearCard | null {
  const item = config.loot[key];
  const weapon = config.weapons[key];
  const piece = config.armor[key];
  if (!item && !weapon && !piece) return null;

  const name = item?.name ?? weapon?.name ?? piece?.name ?? key;
  const rarity = item?.rarity ?? piece?.rarity ?? 'common';

  if (piece) return armorCard(config, key, name, rarity, piece, wear);
  if (weapon?.shield) return shieldCard(key, name, rarity, weapon, wear);
  if (weapon?.melee) return bladeCard(config, key, name, rarity, weapon);
  if (weapon) return gunCard(config, key, name, rarity, weapon, ammo);

  // Everything else on the loot catalog is CARGO — it has no stats, it has a
  // price and a weight, and that is already what the bag's own card says.
  return null;
}

/** The ultimate `weapon` owns, by name, or undefined. */
function ultimateName(config: GameConfig, weaponKey: string): string | undefined {
  for (const row of Object.values(config.ultimates)) {
    if (row.weapon === weaponKey) return row.name;
  }
  return undefined;
}

function gunCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
  ammo?: GearAmmo,
): HudGearCard {
  const stats: GearStat[] = [];
  // THE HEADLINE IS WHAT ONE TRIGGER PULL DOES — damage on everything that
  // kills, and HEALING on the one weapon that does not. Per PULL and not per
  // ray: a shotgun spends one shell, and what a player compares against a
  // rifle is what the shell does.
  //
  // A SHELL IS ALSO NOT A PATTERN, so the breakdown rides along in brackets.
  // Hiding six pellets behind one number would make the shotgun look like a
  // rifle that hits for fifty-four at any distance, which is the one thing it
  // is not — and it is the only place on any of these cards where a second
  // number is allowed inside the first.
  if (weapon.heal > 0) {
    stats.push({ label: 'CURA', value: `+${weapon.heal}`, lead: true });
  } else {
    stats.push({
      label: 'DANO',
      value:
        weapon.pellets > 1
          ? `${weapon.shotDamage} (${weapon.pellets}x${weapon.damage})`
          : String(weapon.shotDamage),
      lead: true,
    });
  }
  // HOW OFTEN YOU MAY PRESS IT. Shots per second rather than rounds per
  // minute, which is what this row used to say: a player pressing a button
  // experiences seconds, and "600/min" is a number you have to divide before
  // it means anything. Beside a damage figure in the same card, `9.2/s` and
  // `600/min` are the same fact and only one of them can be multiplied in
  // your head against the number above it.
  if (weapon.fireCooldown > 0) {
    stats.push({ label: 'TIROS/S', value: rate(weapon.fireCooldown) });
  }
  // WHAT YOU HAVE, OVER WHAT YOU CAN HOLD, and it is the reserve rather than
  // the calibre's name. The name told the player which crate to pick up; the
  // count tells them whether to take this fight, which is a decision and not
  // a lookup. Absent on anything that never runs dry — a blade, the field gun
  // — because a card that lists what an object does not have has stopped
  // being a description.
  if (ammo) {
    stats.push({ label: 'MUNIÇÃO', value: `${ammo.have} / ${ammo.max}` });
  } else if (weapon.ammo !== 'none') {
    const cap = config.ammo.max[weapon.ammo];
    if (cap) stats.push({ label: 'MUNIÇÃO', value: `máx ${cap}` });
  }
  return {
    key,
    name,
    rarity,
    kind: WEAPON_KIND[weapon.kind] ?? 'Arma',
    stats,
    ultimate: ultimateName(config, key),
  };
}

function bladeCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
): HudGearCard {
  const steps = weapon.melee?.steps ?? [];
  const chain = steps.reduce((sum, step) => sum + step.damage, 0);
  // THE WHOLE CHAIN'S DAMAGE, because a lâmina is not a weapon you use once.
  // Comparing single swings across blades compares the wrong thing: an axe's
  // first slash is smaller than its finisher and both are the same press held
  // down.
  const stats: GearStat[] = [{ label: 'DANO', value: String(chain), lead: true }];
  // AND HOW FAST THE CHAIN COMES ROUND, in the same unit a gun's trigger uses,
  // so a blade and a pistol can be compared at all. It is the chain's total
  // cooldown rather than one step's: what the player feels is how long they
  // are committed for, and that is all three beats.
  const cycle = steps.reduce((sum, step) => sum + step.cooldown, 0);
  if (cycle > 0) stats.push({ label: 'GOLPES/S', value: rate(cycle / Math.max(1, steps.length)) });
  return {
    key,
    name,
    rarity,
    kind: 'Lâmina',
    stats,
    ultimate: ultimateName(config, key),
  };
}

function shieldCard(
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
  wear?: GearWear,
): HudGearCard {
  const shield = weapon.shield!;
  return {
    key,
    name,
    rarity,
    kind: 'Escudo',
    stats: [
      // DAMAGE IT WILL EAT, in damage points, and it is the headline because
      // it is the only number a shield has. What is left over is what is left
      // of the shield.
      {
        label: 'DURABILIDADE',
        value: wear ? `${wear.hp} / ${wear.max}` : String(shield.hp),
        lead: true,
      },
      // THE ONE RULE ALLOWED ON A CARD, and it is here because without it the
      // number above is a lie by omission: a shield stops everything it is
      // FACING and nothing else, and a player who does not know that reads
      // "126" as a health bar they can stand behind.
      { label: 'ÂNGULO', value: `${Math.round(shield.arcDegrees)}°` },
    ],
  };
}

function armorCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  piece: NonNullable<GameConfig['armor'][string]>,
  wear?: GearWear,
): HudGearCard {
  return {
    key,
    name,
    rarity,
    kind: config.armorSlotNames[piece.slot] ?? ARMOR_KIND[piece.slot] ?? piece.slot,
    stats: [
      // THE RATING, AND IT IS ALREADY A NUMBER. Damage taken off every blow
      // that lands on this part, against anything that throws one.
      { label: 'ARMADURA', value: String(piece.armor), lead: true },
      {
        // Points of damage it will absorb before it comes apart — the same
        // number the bar on the mannequin draws, so the bar and the card
        // cannot disagree.
        label: 'DURABILIDADE',
        value: wear ? `${wear.hp} / ${wear.max}` : String(piece.maxHp),
      },
    ],
  };
}

/**
 * Damage a whole worn set takes off a blow.
 *
 * THE PANEL'S HEADLINE NUMBER. A plate only meets the blows that land on its
 * own part, so the set's contribution is each plate's rating weighted by that
 * part's share of the body: a full set of one material comes out at exactly
 * that material's rating, and a partial one comes out lower in proportion to
 * how much of the body is still bare.
 */
export function setArmor(
  config: GameConfig,
  worn: Array<{ slot: string; armor: number; hp: number }>,
): number {
  let stopped = 0;
  for (const row of worn) {
    if (row.hp <= 0) continue;
    stopped += row.armor * (config.armorCoverage[row.slot] ?? 0);
  }
  return Math.round(stopped);
}
