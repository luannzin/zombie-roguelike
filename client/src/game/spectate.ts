/**
 * WHOSE SCREEN YOU ARE WATCHING WHEN YOU ARE NOT PLAYING ON YOUR OWN.
 *
 * There are exactly two ways to stop being in a night without the run ending,
 * and this file exists because they turned out to be the same problem:
 *
 *   DOWNED    you are on the floor and nothing brings you back but the party
 *             reaching the next zone or laying you on a platform. Solo that
 *             is a wipe; in company it is a clock running on everybody else.
 *   EXITED    you crossed the corridor first and the zone does not turn over
 *             until the rest of the party has too (`Room._tick_exit_quest`).
 *
 * Both leave a player holding a controller with nothing to control, for
 * anywhere between ten seconds and the rest of the night, WHILE THE MOST
 * INTERESTING PART OF THE RUN IS HAPPENING TO SOMEBODY ELSE. A black screen
 * there is the worst thing a co-op game can do with that time — it takes the
 * player out of the room at the exact moment their friends are shouting about
 * whether to come back for them.
 *
 * SO THE CAMERA MOVES TO SOMEBODY WHO IS STILL PLAYING, and it is a real
 * camera on a real body rather than a map or a summary. What that buys is the
 * thing a summary cannot: you watch the person deciding whether to walk to
 * your body, and they know you are watching.
 *
 * WHY THIS IS A FILE AND NOT FOUR FIELDS ON `Game`
 * ===============================================
 * The same three questions get asked on three different clocks — the HUD needs
 * the list five times a second, the camera needs the target every frame, and a
 * keypress needs the next one on the edge — and every one of them has to agree
 * about who is watchable. Answered inline they would be three loops with three
 * slightly different ideas of "still playing", and the one that drifts is the
 * camera, which is the one nobody notices is wrong because it simply keeps
 * following a body that is now on the floor.
 *
 * NOTHING HERE MUTATES, DRAWS OR SENDS. Same contract `interaction.ts` keeps
 * and for the same reason: it takes a view and returns an answer.
 *
 * A NOTE ON WHY THERE IS NO SERVER HALF. Spectating is a CAMERA, and the
 * server has no cameras. Every body the client can watch is already on the
 * wire — the party is a handful of rows in every snapshot, sent to everybody,
 * because the fov has always been a TEAM field (`updateVision` makes every
 * living player a viewer). So watching a teammate reveals nothing a client did
 * not already have, and there is no cheat here to close.
 */

import type { PlayerMeta, PlayerState } from '../net/protocol';

/** One body the spectator may point the camera at. */
export interface SpectateTarget {
  id: string;
  name: string;
  /** Their nameplate colour, so the list reads as the party does. */
  color: string;
  /** For the strip's own little health pip. */
  hp: number;
  maxHp: number;
  /** They are carrying somebody. The strip says so — it is usually YOU. */
  carrying: boolean;
}

/**
 * WHY the local player is spectating, or null when they are not.
 *
 * The two are not interchangeable on screen even though they share a camera:
 * one is a body on the floor that the party can still do something about, and
 * the other is a player who is finished and waiting. The copy differs and so
 * does the tone — see `components/hud/Spectate.tsx`.
 */
export type SpectateReason = 'downed' | 'exited';

/** Everything the three questions below read, and nothing else. */
export interface SpectateState {
  localId: string;
  /** Every body on the wire, keyed by id. `Game`'s own live roster. */
  meta: ReadonlyMap<string, PlayerMeta>;
  /** The same bodies' tick rows — this is where `down` and `out` live. */
  rows: ReadonlyMap<string, PlayerState>;
  /** The local player's own predicted body, which leads its roster row. */
  localDowned: boolean;
  localExited: boolean;
  /** A cinematic owns the camera; spectating must not fight it for one. */
  locked: boolean;
}

/**
 * Why the local player is watching somebody else, or null.
 *
 * SOLO IS NOT SPECTATING. Alone, going down IS the wipe, and the death card is
 * already covering the screen with the only thing worth reading; pointing a
 * camera at an empty forest behind it would be a second answer to a question
 * that has one. Crossing the exit alone turns the zone over on the same frame,
 * so there is nothing to wait for either. Both cases fall out of the same
 * test — is there anybody still playing — which is also the test that ends
 * spectating when the last teammate goes down.
 */
export function spectateReason(s: SpectateState): SpectateReason | null {
  if (s.locked) return null;
  if (!s.localDowned && !s.localExited) return null;
  if (!liveIds(s).length) return null;
  return s.localExited ? 'exited' : 'downed';
}

/**
 * The party, in a stable order, for the strip and for cycling.
 *
 * SORTED BY ID AND NOT BY DISTANCE, LOOT OR ANYTHING ELSE THAT MOVES. The list
 * is something the player learns the shape of — "my mate is the second one" —
 * and a list that reorders itself while they are pressing the key to step
 * through it is a list that cannot be stepped through at all.
 */
export function spectateTargets(s: SpectateState): SpectateTarget[] {
  return liveIds(s)
    .map((id) => {
      const meta = s.meta.get(id);
      const row = s.rows.get(id);
      return {
        id,
        name: meta?.name ?? '???',
        color: meta?.color ?? '#ffffff',
        hp: row?.hp ?? 0,
        maxHp: meta?.mods?.maxHp ?? 100,
        // USUALLY YOU. A downed player watching the party wants to know which
        // of them has their body over their shoulder before anything else on
        // this strip, and it is the one fact the little health pip cannot say.
        carrying: !!row?.carry,
      };
    })
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/**
 * The body to point the camera at, given who was being watched.
 *
 * IT REPAIRS ITSELF RATHER THAN BEING REPAIRED. The watched player can go down
 * mid-look — which is exactly the moment a spectator is watching hardest — so
 * this takes the last choice as a HINT and falls back to the first live body
 * instead of asking every caller to check first. Null means nobody is left,
 * which is a wipe and a card over the top of it.
 */
export function spectateTarget(s: SpectateState, watching: string | null): string | null {
  const live = liveIds(s);
  if (!live.length) return null;
  if (watching && live.includes(watching)) return watching;
  return live[0];
}

/**
 * The next body along, wrapping. `step` is +1 or -1.
 *
 * A CYCLE AND NOT A PICKER, because the common case is two or three people and
 * the common gesture is "show me the other one". The strip is clickable for
 * the case where it is four and you want a particular one.
 */
export function spectateStep(
  s: SpectateState,
  watching: string | null,
  step: number,
): string | null {
  const live = liveIds(s);
  if (!live.length) return null;
  const at = watching ? live.indexOf(watching) : -1;
  if (at < 0) return live[0];
  const next = (at + step + live.length) % live.length;
  return live[next];
}

/**
 * Everybody still playing, sorted, ids only.
 *
 * "STILL PLAYING" IS ONE DEFINITION AND IT LIVES HERE, which is the whole
 * reason this module exists: a body is watchable if it is alive, not on the
 * floor, and has not already walked out of the zone. Getting any of those
 * wrong somewhere else produces a camera that follows a corpse — and a camera
 * following a corpse looks exactly like a camera that has frozen.
 */
function liveIds(s: SpectateState): string[] {
  const ids: string[] = [];
  for (const [id, row] of s.rows) {
    if (id === s.localId) continue;
    if (!row.alive || row.down || row.out) continue;
    ids.push(id);
  }
  ids.sort();
  return ids;
}
