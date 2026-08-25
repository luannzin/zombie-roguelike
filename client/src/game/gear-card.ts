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
 * So there are six kinds of row in the game now and no others:
 *
 *     DANO           what one press is worth
 *     TIROS/S        how often you may press it
 *     ARMADURA       what it takes off a blow
 *     DURABILIDADE   how much is left of it
 *     MUNIÇÃO        what you have, over what you can hold
 *     TEMPO          how long it plants you — medicine, and only medicine
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
 * MEDICINE GETS A CARD FOR THE SAME REASON A PLATE DOES, and its second row
 * is the only one in the file where SMALL IS GOOD. The two kits trade on
 * different axes — a lot of health after a long time, or less of it almost
 * instantly (`server/app/medical.py`) — and a card that printed both numbers
 * without saying which way each one points would make the light kit look
 * strictly worse than the heavy one. That is what `GearStat.better` is for,
 * and it is why comparison could not be "bigger is greener".
 *
 * THE ARROWS: A CARD COMPARES ITSELF AGAINST THE THING IT WOULD TAKE THE
 * PLACE OF
 * ========================================================================
 * `compareGear` marks each row up, down or level against the piece the player
 * already has in that place, and the surfaces that describe an object the
 * player does NOT own yet — a drop in the grass, a table in the shop — pass
 * that piece in. The belt's own cells and the armour panel's do not, because
 * those cards ARE the current thing and an object compared against itself is
 * a column of level arrows saying nothing.
 *
 * NO COUNTERPART MEANS NO ARROWS, and that is deliberate rather than a
 * shortcut. An empty gun cell, a bare slot, a first lâmina — the honest
 * comparison there is "against nothing", and a card of green arrows for a
 * first helmet reads as a recommendation rather than as a measurement. The
 * absence of arrows is what says "there is nothing here to weigh this
 * against"; the panel behind the player already says the slot is bare, in a
 * drawing of their own body, which is a louder sentence than an arrow.
 *
 * ROWS ARE MATCHED BY LABEL, which is the whole reason the label alphabet
 * above is short and fixed. Two cards of the same kind carry the same rows in
 * the same order, so a match is a lookup rather than a schema; a row the
 * counterpart does not have is left alone rather than counted as a win,
 * because "this one has ammunition and that one does not" is a difference in
 * KIND and an arrow would be claiming it is a difference in degree.
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
  /**
   * The magnitude behind `value`, for comparison. Separate from the string
   * because `value` is a SENTENCE — `54 (6x9)`, `9 / 30`, `126` — and reading
   * a number back out of it would be a parser that breaks the first time
   * somebody adds a unit. A stat with no `n` is one that cannot be compared
   * and simply never grows an arrow.
   */
  n?: number;
  /**
   * Which way is better. Everything on these cards is `high` except a heal's
   * duration, which is the one number you want to be small — and that is
   * exactly why the field exists rather than a blanket rule: a comparison
   * that painted "plants you for three seconds" green because three is more
   * than one would be worse than showing nothing at all.
   */
  better?: 'low' | 'high';
  /**
   * Filled in by `compareGear`, never by the builders. Absent means there was
   * nothing to compare against — see `compareGear` for why that is a silent
   * absence rather than a green arrow.
   */
  delta?: 'up' | 'down' | 'same';
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
  const kit = config.medical[key];
  if (!item && !weapon && !piece && !kit) return null;

  const name = item?.name ?? weapon?.name ?? piece?.name ?? key;
  const rarity = item?.rarity ?? piece?.rarity ?? 'common';

  if (kit) return medicalCard(key, name, rarity, kit);
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
    stats.push({ label: 'CURA', value: `+${weapon.heal}`, n: weapon.heal, lead: true });
  } else {
    stats.push({
      label: 'DANO',
      value:
        weapon.pellets > 1
          ? `${weapon.shotDamage} (${weapon.pellets}x${weapon.damage})`
          : String(weapon.shotDamage),
      // THE SHELL, not the pellet: what the row compares is what the row
      // leads with, or a shotgun would read as nine damage beside a rifle's
      // thirty-six and the arrow would say the opposite of the number.
      n: weapon.shotDamage,
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
    stats.push({
      label: 'TIROS/S',
      value: rate(weapon.fireCooldown),
      n: 1 / weapon.fireCooldown,
    });
  }
  // WHAT YOU HAVE, OVER WHAT YOU CAN HOLD, and it is the reserve rather than
  // the calibre's name. The name told the player which crate to pick up; the
  // count tells them whether to take this fight, which is a decision and not
  // a lookup. Absent on anything that never runs dry — a blade, the field gun
  // — because a card that lists what an object does not have has stopped
  // being a description.
  if (ammo) {
    stats.push({ label: 'MUNIÇÃO', value: `${ammo.have} / ${ammo.max}`, n: ammo.have });
  } else if (weapon.ammo !== 'none') {
    const cap = config.ammo.max[weapon.ammo];
    if (cap) stats.push({ label: 'MUNIÇÃO', value: `máx ${cap}`, n: cap });
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
  const stats: GearStat[] = [{ label: 'DANO', value: String(chain), n: chain, lead: true }];
  // AND HOW FAST THE CHAIN COMES ROUND, in the same unit a gun's trigger uses,
  // so a blade and a pistol can be compared at all. It is the chain's total
  // cooldown rather than one step's: what the player feels is how long they
  // are committed for, and that is all three beats.
  const cycle = steps.reduce((sum, step) => sum + step.cooldown, 0);
  if (cycle > 0) {
    const beat = cycle / Math.max(1, steps.length);
    stats.push({ label: 'GOLPES/S', value: rate(beat), n: 1 / beat });
  }
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
        n: wear ? wear.hp : shield.hp,
        lead: true,
      },
      // THE ONE RULE ALLOWED ON A CARD, and it is here because without it the
      // number above is a lie by omission: a shield stops everything it is
      // FACING and nothing else, and a player who does not know that reads
      // "126" as a health bar they can stand behind.
      { label: 'ÂNGULO', value: `${Math.round(shield.arcDegrees)}°`, n: shield.arcDegrees },
    ],
  };
}

/**
 * A kit, as a card. TWO ROWS, AND THEY POINT IN OPPOSITE DIRECTIONS.
 *
 * That is the whole reason medicine gets a card rather than a number on the
 * cell: the two kits are not a ladder, they are a trade. One puts a lot back
 * and plants you for nearly three seconds; the other puts less back and is
 * over before anything reaches you. A player who has only ever read the heal
 * figure has been told that the heavy kit is simply the better one, which is
 * the opposite of what `server/app/medical.py` was built to say.
 *
 * NO DURABILITY, NO WEIGHT, NO PRICE. Medicine is not cargo — both kits are
 * `value=0` and the bag's own bar already carries what they cost the walk —
 * and a kit is spent whole or not at all, so there is nothing left of one to
 * report.
 */
function medicalCard(
  key: string,
  name: string,
  rarity: LootRarity,
  kit: NonNullable<GameConfig['medical'][string]>,
): HudGearCard {
  return {
    key,
    name,
    rarity,
    kind: 'Remédio',
    stats: [
      { label: 'CURA', value: `+${kit.heal}`, n: kit.heal, lead: true },
      // THE COST OF THE VERB, and the one row in this file where less is
      // better. Seconds standing still in the open, unable to answer anything
      // that walks up — see `Room.use_medical`. A card that only printed the
      // heal would be describing half the object.
      {
        label: 'TEMPO',
        value: `${kit.useTime.toFixed(1)}s`,
        n: kit.useTime,
        better: 'low',
      },
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
      { label: 'ARMADURA', value: String(piece.armor), n: piece.armor, lead: true },
      {
        // Points of damage it will absorb before it comes apart — the same
        // number the bar on the mannequin draws, so the bar and the card
        // cannot disagree.
        label: 'DURABILIDADE',
        value: wear ? `${wear.hp} / ${wear.max}` : String(piece.maxHp),
        n: wear ? wear.hp : piece.maxHp,
      },
    ],
  };
}

/**
 * The same card, with every row marked against what the player already has.
 *
 * PURE, AND IT RETURNS A COPY. The builders above describe an OBJECT and know
 * nothing about who is looking at it; this is the one function that knows
 * there is a player, and keeping the two apart is what lets the belt and the
 * armour panel render an uncompared card without a flag threaded through
 * `gearCard`.
 *
 * `current` is the thing `card` would take the place of — the plate on that
 * part of the body, the lâmina in the cell, the gun that would be traded
 * away. NULL MEANS NO ARROWS AT ALL, which is the case that matters most to
 * get right: an empty gun cell or a bare slot has no counterpart, and a
 * column of green arrows there would be the card recommending a purchase
 * rather than measuring one. Silence is the honest answer.
 *
 * Rows are matched by LABEL, never by position: a shotgun's card has a row a
 * rifle's does not, and comparing `stats[2]` to `stats[2]` across those two
 * would line damage up against ammunition. A row with no counterpart, or with
 * no `n` on either side, is returned untouched — a difference in KIND is not
 * a difference in degree, and an arrow can only ever claim the second.
 */
export function compareGear(
  card: HudGearCard,
  current: HudGearCard | null,
): HudGearCard {
  if (!current) return card;
  const mine = new Map(current.stats.map((stat) => [stat.label, stat]));
  return {
    ...card,
    stats: card.stats.map((stat) => {
      const other = mine.get(stat.label);
      if (stat.n === undefined || other?.n === undefined) return stat;
      if (stat.n === other.n) return { ...stat, delta: 'same' as const };
      const bigger = stat.n > other.n;
      const good = (stat.better ?? 'high') === 'low' ? !bigger : bigger;
      return { ...stat, delta: good ? ('up' as const) : ('down' as const) };
    }),
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
