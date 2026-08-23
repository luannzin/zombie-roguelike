/**
 * What a piece of gear IS, as a card. One description, four places it appears.
 *
 * A player meets the same object four times — on a shop table, on the ground,
 * in the belt and on the body — and until now it introduced itself
 * differently each time: a name and a price at the stall, a name in a prompt,
 * a name and an ammo count on the belt, and the word `steel` on the armour
 * panel. Four surfaces, four vocabularies, and none of them ever said what the
 * thing actually does. Somebody can pick up a pair of steel greaves and not
 * notice.
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
 * how a weapon works. `Game` calls it and puts the result on the HUD snapshot;
 * the components render rows they do not have to understand.
 *
 * THE LABELS ARE HERE AND THE NUMBERS ARE HERE, TOGETHER. A row is a unit and
 * a name that only mean anything as a pair — "ALCANCE" and "8.2t" split across
 * two files is a number in one place and its meaning in another. The rule this
 * repository keeps is that the SERVER does not own wording; both halves of
 * this are client-side either way.
 *
 * EVERY ROW IS A REAL NUMBER IN A REAL UNIT. That is the rule, and the first
 * cut of this file broke it everywhere: it led with "abate em 3 tiros",
 * "absorve 56%" and "aguenta 61/61" — three INTERPRETATIONS of numbers the
 * player never got to see. A stat block is for comparing two objects, and you
 * cannot compare two interpretations: 56% of what, against which blow?
 *
 * So the cards say `DANO 9`, `ARMADURA 5`, `DURABILIDADE 61`, and the units
 * are the game's own — damage points, tiles, kilos, rounds a minute. The only
 * two derived rows left are the ones a player would work out anyway and get
 * wrong (`DPS`, and how many blows a plate survives), and each is labelled as
 * the count it is.
 *
 * AND NOTHING ON A CARD IS ANCHORED ON A CREATURE. An earlier cut resolved
 * armour's fraction against a walker's claw to make it a number — "a walker
 * hits for 9, five of it stops here" — which is true today and starts lying
 * the day there is a second kind of enemy worth comparing against. The fix
 * was upstream: armour is FLAT now (`server/app/armor.py`), so the rating is
 * a number before it ever reaches this file and there is nothing to resolve.
 * If a stat here ever needs an example to make sense, the stat is wrong, not
 * the example.
 */

import type { GameConfig, LootRarity } from '../net/protocol';

/** One labelled value on a gear card. */
export interface GearStat {
  label: string;
  value: string;
  /**
   * Draw it as the headline rather than as another row. Exactly one stat per
   * card sets it: the thing you would say out loud about the object — a
   * gun's shots-to-kill, a plate's absorption, a shield's block. A card of
   * eight equal rows is a spreadsheet, and nobody reads a spreadsheet with
   * something walking toward them.
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
}

/** What a worn or held piece has left, when the card is describing a real one. */
export interface GearWear {
  hp: number;
  max: number;
}

const WEAPON_KIND: Record<string, string> = {
  pistol: 'Pistola',
  smg: 'Submetralhadora',
  shotgun: 'Espingarda',
  rifle: 'Fuzil',
  sniper: 'Precisão',
  melee: 'Lâmina',
  shield: 'Escudo',
};

const ARMOR_KIND: Record<string, string> = {
  head: 'Cabeça',
  body: 'Tronco',
  legs: 'Pernas',
};

function tiles(px: number, config: GameConfig): string {
  return `${(px / config.tileSize).toFixed(1)}t`;
}

function kg(value: number): string {
  return `${value.toFixed(1)}kg`;
}

/**
 * The card for one catalog key, or null if nothing in the config knows it.
 *
 * `wear` is what a REAL one has left — a plate on a body, a shield on a belt.
 * Absent means the card is describing the catalog row rather than an object:
 * a weapon on a shop table, a piece on the ground.
 */
export function gearCard(
  config: GameConfig,
  key: string,
  wear?: GearWear,
): HudGearCard | null {
  const item = config.loot[key];
  const weapon = config.weapons[key];
  const piece = config.armor[key];
  if (!item && !weapon && !piece) return null;

  const name = item?.name ?? weapon?.name ?? piece?.name ?? key;
  const rarity = item?.rarity ?? piece?.rarity ?? 'common';

  if (piece) return armorCard(config, key, name, rarity, piece, wear);
  if (weapon?.shield) return shieldCard(key, name, rarity, weapon, item, wear);
  if (weapon?.melee) return bladeCard(config, key, name, rarity, weapon, item);
  if (weapon) return gunCard(config, key, name, rarity, weapon, item);

  // Everything else on the loot catalog is CARGO — it has no stats, it has a
  // price and a weight, and that is already what the bag's own card says.
  return null;
}

function gunCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
  item: GameConfig['loot'][string] | undefined,
): HudGearCard {
  const stats: GearStat[] = [];
  // THE HEADLINE IS THE DAMAGE, because that is the number that exists. Per
  // TRIGGER PULL, not per ray: a shotgun spends one shell and the thing a
  // player wants to compare against a rifle is what the shell does.
  //
  // A SHELL IS ALSO NOT A PATTERN, so the breakdown rides along in brackets —
  // hiding six pellets behind one number would make the shotgun look like a
  // rifle that hits for fifty-four at any distance, which is the one thing
  // it is not.
  stats.push({
    label: 'DANO',
    value:
      weapon.pellets > 1
        ? `${weapon.shotDamage} (${weapon.pellets}x${weapon.damage})`
        : String(weapon.shotDamage),
    lead: true,
  });
  if (weapon.fireCooldown > 0) {
    stats.push({ label: 'CADÊNCIA', value: `${Math.round(60 / weapon.fireCooldown)}/min` });
    // ONE OF THE TWO DERIVED ROWS LEFT, and it earns its place: damage and
    // cadence are both real and both meaningless alone — a Deagle and a P90
    // swap places depending on which of the two you look at. It is the
    // multiplication a player would do in their head and get wrong.
    stats.push({
      label: 'DANO/S',
      value: String(Math.round(weapon.shotDamage / weapon.fireCooldown)),
    });
  }
  if (weapon.range > 0) stats.push({ label: 'ALCANCE', value: tiles(weapon.range, config) });
  // NOISE IS A STAT HERE BECAUSE IT IS A STAT IN THE GAME. Sound is the only
  // long-range sense the creatures have, and the two suppressed weapons cost
  // real money for exactly this row — a shop that did not show it would be
  // selling the `S` in USP-S as a naming quirk.
  //
  // A ZERO IS NEVER PRINTED, here or anywhere else on these cards. "RUÍDO
  // 0.0t" is not a stat, it is a field that did not apply — and a card that
  // lists the things an object does NOT have is a card that has stopped being
  // a description.
  if (weapon.noise > 0) stats.push({ label: 'RUÍDO', value: tiles(weapon.noise, config) });
  const calibre = config.loot[config.ammo.boxes[weapon.ammo] ?? '']?.name;
  if (calibre) stats.push({ label: 'MUNIÇÃO', value: calibre });
  if (item) stats.push({ label: 'PESO', value: kg(item.weight) });
  return { key, name, rarity, kind: WEAPON_KIND[weapon.kind] ?? 'Arma', stats };
}

function bladeCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
  item: GameConfig['loot'][string] | undefined,
): HudGearCard {
  const steps = weapon.melee?.steps ?? [];
  const chain = steps.reduce((sum, step) => sum + step.damage, 0);
  const finisher = steps[steps.length - 1];
  const stats: GearStat[] = [];
  // THE WHOLE CHAIN'S DAMAGE, because a lâmina is not a weapon you use once.
  // Comparing single swings across blades is comparing the wrong thing: an
  // axe's first slash is smaller than its finisher and both are the same
  // press held down.
  stats.push({ label: 'DANO', value: String(chain), lead: true });
  if (steps.length) {
    // THE THREE BEATS, in order. Two slashes and a cut, and the shape of the
    // chain — small, small, big — is most of what a blade feels like.
    stats.push({ label: 'GOLPES', value: steps.map((step) => step.damage).join(' / ') });
  }
  if (finisher) {
    stats.push({ label: 'ALCANCE', value: tiles(finisher.reach, config) });
    stats.push({ label: 'ARCO', value: `${Math.round(finisher.arcDegrees)}°` });
    if (finisher.maxTargets > 1) {
      stats.push({ label: 'CORTA ATÉ', value: `${finisher.maxTargets} corpos` });
    }
  }
  if (weapon.noise > 0) stats.push({ label: 'RUÍDO', value: tiles(weapon.noise, config) });
  if (item) stats.push({ label: 'PESO', value: kg(item.weight) });
  return { key, name, rarity, kind: 'Lâmina', stats };
}

function shieldCard(
  key: string,
  name: string,
  rarity: LootRarity,
  weapon: NonNullable<GameConfig['weapons'][string]>,
  item: GameConfig['loot'][string] | undefined,
  wear?: GearWear,
): HudGearCard {
  const shield = weapon.shield!;
  const stats: GearStat[] = [
    // DAMAGE IT WILL EAT, in damage points, and that is the headline because
    // it is the only number a shield has. What is left over is what is left
    // of the shield.
    {
      label: 'DURABILIDADE',
      value: wear ? `${wear.hp} / ${wear.max}` : String(shield.hp),
      lead: true,
    },
    // The RULE still has to be stated somewhere — everything else in this
    // game takes a share of a blow and this takes all of it — but it is a row
    // now rather than a headline standing in for a number.
    { label: 'BLOQUEIO', value: 'total' },
    { label: 'ÂNGULO', value: `${Math.round(shield.arcDegrees)}°` },
    // THE ONE PERCENTAGE LEFT ON ANY CARD, and it stays because a multiplier
    // has no other honest unit: the walk it multiplies is already the product
    // of a skill, a carry weight and a sprint, so quoting an absolute speed
    // here would be a number that is wrong for most bodies most of the time.
    { label: 'VELOCIDADE', value: `${Math.round((shield.speed - 1) * 100)}%` },
  ];
  if (item) stats.push({ label: 'PESO', value: kg(item.weight) });
  return { key, name, rarity, kind: 'Escudo', stats };
}

function armorCard(
  config: GameConfig,
  key: string,
  name: string,
  rarity: LootRarity,
  piece: NonNullable<GameConfig['armor'][string]>,
  wear?: GearWear,
): HudGearCard {
  const stats: GearStat[] = [
    // THE RATING, AND IT IS ALREADY A NUMBER. Damage taken off every blow
    // that lands on this part, against anything that throws one.
    { label: 'ARMADURA', value: String(piece.armor), lead: true },
    { label: 'MATERIAL', value: piece.materialName },
    {
      // Points of damage it will absorb before it comes apart — the same
      // number the bar on the panel draws, so the bar and the card agree.
      label: 'DURABILIDADE',
      value: wear ? `${wear.hp} / ${wear.max}` : String(piece.maxHp),
    },
  ];
  // WHERE THE BLOWS GO, as the count it actually is. `armorCoverage` is the
  // share of the SPRITE this part occupies — head 7 rows, torso 4, legs 3 of
  // fifteen — so it is honest to say it in blows: roughly seven of every
  // fifteen land here. That a helmet answers more than twice as many hits as
  // a pair of greaves is the least guessable thing about this system and the
  // reason somebody would buy one first.
  const share = config.armorCoverage[piece.slot] ?? 0;
  if (share > 0) {
    stats.push({ label: 'ACERTOS AQUI', value: `${Math.round(share * 15)} em 15` });
  }
  stats.push({ label: 'PESO', value: kg(piece.weight) });
  return { key, name, rarity, kind: ARMOR_KIND[piece.slot] ?? piece.slot, stats };
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
