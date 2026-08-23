/**
 * Every event the server can fire has something to SAY when it does.
 *
 * Plain script, no framework, prints `ok` — same shape as `grade.ts` and
 * `boss-clock.ts`. Run it with `bun tests/events.ts` from `client/`.
 *
 * It reads the REAL catalog out of `server/app/events.py`, so it fails if the
 * two sides of the night's script drift apart.
 *
 * THE CLAIM. `docs/design/events.md` says adding an event is a row on each
 * side: one in `EVENTS`, one in `EVENT_PRESENTATION`. That is a promise about
 * two files that nothing enforces, and it has the quietest possible failure
 * mode — a server event with no client row fires, does everything it was
 * written to do, and says NOTHING. The horde arrives with no howl and no card;
 * the lights go out with no explanation. The player experiences it as the game
 * glitching, and there is no error anywhere to find.
 *
 * That is worth a test precisely because it is invisible from both ends: the
 * server is behaving correctly, the client is behaving correctly, and the game
 * is broken in between them.
 *
 * The other direction matters too, though it is merely dead weight rather than
 * a bug: a client row for an event the server no longer has is copy nobody
 * will ever read, and it is how a table rots into a graveyard.
 */

import { readFileSync } from 'node:fs';
import { EVENT_PRESENTATION } from '../src/game/events';

const SOURCE = '../server/app/events.py';

function fail(message: string): never {
  console.error(`FAIL  ${message}`);
  process.exit(1);
}

/**
 * The event keys the server can fire.
 *
 * READ OUT OF THE PYTHON rather than duplicated here, because a copy of the
 * catalog in this file would be a third place to forget — which is the exact
 * class of bug the test exists to catch.
 *
 * It matches `key="..."` inside the `EVENTS` tuple. Deliberately narrow: a
 * looser pattern would pick up `EventDef`'s own field docs and quietly pass
 * by matching nothing real.
 */
function serverEventKeys(): string[] {
  const src = readFileSync(SOURCE, 'utf8');
  const start = src.indexOf('EVENTS: tuple[EventDef, ...] = (');
  if (start < 0) fail(`could not find the EVENTS tuple in ${SOURCE}`);
  // The tuple ends at the first line that closes it at column zero.
  const end = src.indexOf('\n)', start);
  if (end < 0) fail(`could not find the end of the EVENTS tuple in ${SOURCE}`);
  const body = src.slice(start, end);
  const keys = [...body.matchAll(/key="([a-z_]+)"/g)].map((m) => m[1]);
  if (keys.length === 0) fail('parsed the EVENTS tuple and found no keys — the pattern has rotted');
  return keys;
}

const server = serverEventKeys();
const client = Object.keys(EVENT_PRESENTATION);

// --- every server event has a client row ------------------------------------
//
// The one that is invisible from both ends.

for (const key of server) {
  const look = EVENT_PRESENTATION[key];
  if (!look) {
    fail(
      `the server can fire "${key}" and the client has nothing to say about it. ` +
        'It would happen in complete silence — no card, no cue — and read as a glitch.',
    );
  }
  // A row that exists but says nothing is the same failure wearing a hat.
  if (!look.title.trim() || !look.subtitle.trim()) {
    fail(`"${key}" has a presentation row with an empty card`);
  }
  // Trauma is a camera shove: a negative one would pull the lens the wrong
  // way, and an enormous one would take the screen away from the player at
  // exactly the moment an event is asking them to react to something.
  if (!(look.trauma >= 0 && look.trauma <= 1)) {
    fail(`"${key}" asks for a trauma of ${look.trauma}, which is not a 0..1 shove`);
  }
  // A beacon is drawn AT the event's place, so a row that asks for one on an
  // event with no place would silently never mark anything.
  if (look.beacon && !look.sfx) {
    // Not fatal on its own, but a findable thing the player is never told
    // about is a beacon nobody goes looking for.
    fail(`"${key}" marks a place with a beacon but has no cue to send anybody looking`);
  }
}

// --- and no client row is talking to itself ---------------------------------

for (const key of client) {
  if (!server.includes(key)) {
    fail(
      `the client has copy for "${key}" and the server cannot fire it. ` +
        'Dead copy is how this table rots into a graveyard.',
    );
  }
}

// --- the cards are distinct -------------------------------------------------
//
// Two events sharing a title is not a crash, it is worse: the player is told
// the same sentence for two different things and learns to ignore both.

const titles = new Map<string, string>();
for (const [key, look] of Object.entries(EVENT_PRESENTATION)) {
  const seen = titles.get(look.title);
  if (seen) fail(`"${key}" and "${seen}" put the same title on screen: ${look.title}`);
  titles.set(look.title, key);
}

console.log(`ok (${server.length} events, both sides)`);
