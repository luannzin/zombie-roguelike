/**
 * The boss's animation is on the SERVER's clock, and this is what pins it.
 *
 * Plain script, no framework, prints `ok` — same shape as `grade.ts` and
 * `exit-path.ts`. Run it with `bun tests/boss-clock.ts` from `client/`.
 *
 * It reads the REAL atlas manifest, so it fails if `make_sawyer.py` stops
 * emitting a clip, a facing or an event frame the fight is timed off.
 *
 * THE CLAIM. `server/app/boss.py` splits a move into three states — windup,
 * strike, recover — because the hitbox opens between them. The art does not
 * split it, because a swing is one clip. So `t` on the wire is the CLIP's
 * playhead and runs straight through all three, and this checks that the
 * client draws it that way.
 *
 * It is written down because the first cut did the arithmetic on this side
 * instead, and the failure mode was specific and awful: the animation
 * RESTARTED on the frame the bar landed. The player watched the windup, the
 * bar came down, the sprite jumped back to frame zero, and they took
 * thirty-four damage from a boss who appeared to be winding up again. This
 * test is what found it.
 *
 * Three angles on the one claim: the playhead only ever moves forward through
 * a move, it is ON the event frame at the moment the server opens the hitbox,
 * and it never runs off the end of a clip that does not loop.
 */

import { readFileSync } from 'node:fs';
import { clipFor, clipTime, bossFacing } from '../src/render/boss';
import type { BossAtlas, BossClip } from '../src/render/boss';
import type { BossRow, BossState } from '../src/net/protocol';

let checks = 0;

function assert(condition: boolean, message: string): void {
  checks++;
  if (!condition) throw new Error(message);
}

/** The shipped manifest, as the atlas the renderer would have built from it. */
function realAtlas(): BossAtlas {
  const manifest = JSON.parse(
    readFileSync('../assets/processed/sawyer/manifest.json', 'utf8'),
  );
  const clips: Record<string, BossClip> = {};
  for (const [name, row] of Object.entries<any>(manifest.clips)) {
    clips[name] = {
      images: {},
      single: null,
      frames: row.frames,
      fps: row.fps,
      loop: row.loop === true,
      events: row.events ?? {},
    };
  }
  return {
    frameWidth: manifest.frameWidth,
    frameHeight: manifest.frameHeight,
    anchorX: manifest.anchor.x,
    anchorY: manifest.anchor.y,
    footprint: manifest.footprint,
    heightTiles: manifest.height,
    clips,
    crescent: null,
    burst: null,
  };
}

function rowOf(s: BossState, t: number, move?: string): BossRow {
  return {
    id: 'sawyer', x: 0, y: 0, ax: 0, ay: 1,
    hp: 100, max: 100, s, t, m: move ?? null,
  };
}

const atlas = realAtlas();

// --- the sheet still has what the fight is built on --------------------------
for (const name of ['idle', 'walk', 'chop', 'rip', 'rev', 'death', 'sweep', 'arrive']) {
  assert(atlas.clips[name] !== undefined, `the atlas lost the '${name}' clip`);
}
for (const [clip, event] of [
  ['chop', 'hit'], ['rip', 'release'], ['rev', 'roar'],
  ['sweep', 'spin'], ['arrive', 'impact'],
] as const) {
  assert(
    typeof atlas.clips[clip].events[event] === 'number',
    `'${clip}' lost its '${event}' frame — the fight is timed off it`,
  );
}
assert(atlas.anchorY < 1, 'the anchor is his ground contact, not the frame bottom');
assert(
  atlas.footprint.w < atlas.frameWidth / 16,
  'the footprint is his stance, never the frame — a hitbox off frameWidth is seven tiles wide',
);

// --- a move's playhead runs forward, once, through one clip ------------------
for (const move of ['chop', 'rip', 'rev'] as const) {
  const clip = atlas.clips[move];
  const length = clip.frames / clip.fps;
  const hit = Object.values(clip.events)[0] / clip.fps;

  assert(clipFor(rowOf('windup', 0, move)) === move, `${move}: windup plays its own clip`);
  assert(clipFor(rowOf('strike', 0, move)) === move, `${move}: so does the strike`);
  assert(clipFor(rowOf('recover', 0, move)) === move, `${move}: and the recovery`);

  // THE ONE THAT MATTERS. `t` is the CLIP'S playhead and the server runs it
  // straight through the three states of a move, so the frame the hitbox
  // opens on is the frame the art says the blow lands on. Simulated here the
  // way `boss.py` sends it: one clock, never reset mid-swing.
  let last = -1;
  const walk: Array<[BossState, number]> = [];
  let clock = 0;
  for (; clock < hit; clock += 0.02) walk.push(['windup', clock]);
  for (const end = clock + 0.14; clock < end; clock += 0.02) walk.push(['strike', clock]);
  for (const end = clock + length; clock < end; clock += 0.02) walk.push(['recover', clock]);
  for (const [state, t] of walk) {
    const now = clipTime(rowOf(state, t, move), atlas);
    assert(now >= last - 1e-9, `${move}: the playhead went backwards at ${state} ${t}`);
    assert(now <= length + 1e-9, `${move}: the playhead ran off the end of the clip`);
    last = now;
  }
  // And it is ON the event frame when the strike begins — not near it.
  const atStrike = clipTime(rowOf('strike', hit, move), atlas);
  assert(
    Math.abs(atStrike - hit) < 1e-6,
    `${move}: the strike draws ${atStrike.toFixed(3)}s in, the art lands at ${hit.toFixed(3)}s`,
  );
}

// --- states that are their own clip -----------------------------------------
assert(clipFor(rowOf('arrive', 0)) === 'arrive', 'the cinematic plays the cinematic');
assert(clipFor(rowOf('dead', 0)) === 'death', 'dying plays the collapse');
assert(clipFor(rowOf('walk', 0)) === 'walk', 'walking walks');
assert(clipFor(rowOf('idle', 0)) === 'idle', 'idling idles');
assert(clipFor(rowOf('sleep', 0)) === 'idle', 'asleep falls back to the idle sheet');
assert(
  clipTime(rowOf('arrive', 1.2), atlas) === 1.2,
  'a whole-clip state uses its own time raw',
);

// --- a move with no name does not crash the frame picker ---------------------
assert(clipFor(rowOf('windup', 0)) === 'chop', 'an unnamed move falls back to the chop');

// --- facings, and the bias toward the side rows -----------------------------
assert(bossFacing(1, 0) === 'right', 'east is right');
assert(bossFacing(-1, 0) === 'left', 'west is left');
assert(bossFacing(0, 1) === 'down', 'south is down');
assert(bossFacing(0, -1) === 'up', 'north is up');
// Diagonals go to the SIDE rows: that is where the weapon reads.
assert(bossFacing(0.7, 0.7) === 'right', 'south-east reads as a side view');
assert(bossFacing(-0.7, -0.7) === 'left', 'north-west reads as a side view');

console.log(`ok (${checks} checks)`);
