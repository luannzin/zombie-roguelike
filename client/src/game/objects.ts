/**
 * The object vocabulary, client side.
 *
 * `server/app/crates.py` owns what a barrel, a boot and an altar ARE — which
 * sheet they draw from, which verb E offers, what the prompt says, how big a
 * target they are — and ships the whole table in `welcome.config.objects`.
 * This module is the client's copy of it and nothing more: no table of its
 * own, no fallback list of kinds, no guess about which sheet a `bus` uses.
 * Adding an object is a row in that Python file and a sheet in
 * `make_objects.py`, and nothing here changes.
 *
 * It is module state rather than a field threaded through the renderer for
 * the same reason `theme/palette` is: the depth sort needs to resolve a
 * sheet name for every live object every frame, and passing the catalog down
 * five call sites to answer a lookup that is constant for the whole session
 * is ceremony. `welcome` always lands before the map it describes, so the
 * table is populated before anything can ask it a question.
 */

import type { ObjectDef } from '../net/protocol';

/**
 * What a press does. `break` is a barrel coming apart and is the only verb a
 * BULLET can also trigger; `open` is a lid, a door or a slab, and it ignores
 * gunfire — a car boot does not come open because somebody shot near it.
 */
export type ObjectVerb = 'break' | 'open';

let catalog: Record<string, ObjectDef> = {};

export function setObjectCatalog(defs: Record<string, ObjectDef> | undefined): void {
  catalog = defs ?? {};
}

export function objectDef(kind: string): ObjectDef | null {
  return catalog[kind] ?? null;
}

/**
 * The scenery sheet this object draws from, or the kind itself.
 *
 * The fallback is not a guess — it is the honest answer for a client that
 * somehow has an object the config did not describe: ask the atlas for a
 * sheet of that name and draw nothing when there isn't one, rather than
 * silently drawing a barrel where a bus should be.
 */
export function objectSheet(kind: string): string {
  return catalog[kind]?.sheet ?? kind;
}

/** Which row of that sheet. Every vehicle shares one sheet; this picks it. */
export function objectVariant(kind: string): number {
  return catalog[kind]?.variant ?? 0;
}

export function objectVerb(kind: string): ObjectVerb {
  return catalog[kind]?.verb === 'break' ? 'break' : 'open';
}

/** Sheets whose contents are forced rather than lifted. See `crateOpenSound`. */
const HEAVY_SHEETS = new Set(['vehicle', 'altar']);

/**
 * Which of the three container sounds this object makes.
 *
 * Off the SHEET rather than off a list of keys, because the sheet is already
 * the answer to "what is this made of and how big is it": everything on
 * `vehicle.png` is a panel somebody has to force and everything on `altar.png`
 * is stone that has to be pushed, while a lid on `box`, `chest` or `stash` is
 * a hinge that creaks and knocks. Adding a sixth vehicle inherits the right
 * sound without touching this file, which is the same reason the verb and the
 * prompt come off the server's row instead of a switch here.
 */
export function crateOpenSound(kind: string, verb: ObjectVerb): string {
  if (verb === 'break') return 'crate-break';
  return HEAVY_SHEETS.has(objectSheet(kind)) ? 'object-heavy' : 'object-open';
}

/** The HUD line. Portuguese, authored server-side with the rest of the row. */
export function objectLabel(kind: string): string {
  return catalog[kind]?.label ?? 'E';
}

/**
 * Seconds this object plants you for. 0 for everything but the vault.
 *
 * The prompt reads it so a press that is about to cost four seconds SAYS so
 * before it is pressed — a slow open the player only finds out about once they
 * are already committed is a trap rather than a decision, and the whole design
 * of `open_time` is that choosing when to pay it is the interesting part.
 */
export function objectOpenTime(kind: string): number {
  return catalog[kind]?.openTime ?? 0;
}

/** Footprint width in tiles. A vehicle is four; almost everything else is one. */
export function objectTilesW(kind: string): number {
  return catalog[kind]?.tilesW ?? 1;
}

/**
 * Shot box, in world pixels, bottom-centred on the contact.
 *
 * Falls back to the config's generic crate box so a client that met an
 * unknown kind still has something to test a ray against — but the real
 * numbers are per-object, because a bus is four tiles long and a toolbox is
 * one, and a single box for both means either shooting through the bus or
 * hitting the toolbox from two tiles away.
 */
export function objectHitBox(
  kind: string,
  fallbackW: number,
  fallbackH: number,
): { w: number; h: number } {
  const def = catalog[kind];
  return { w: def?.hitW ?? fallbackW, h: def?.hitH ?? fallbackH };
}
