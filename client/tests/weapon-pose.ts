/**
 * The held weapon: its pose, its atlas, and what each class of weapon does.
 *
 * Plain script, no framework, prints `ok` — the same shape as `grade.ts`,
 * `shadows.ts` and the server's checks. Run it with `bun tests/weapon-pose.ts`
 * from `client/`.
 *
 * WHAT IT IS ACTUALLY GUARDING. Everything a player sees a weapon do is one
 * rigid transform applied to three points of one atlas frame, and nothing at
 * runtime notices when that transform is wrong — a muzzle a few pixels off is
 * a tracer leaving somebody's hip, which reads as "the gun feels bad" and
 * never as an error. The three claims below are the ones that cannot be
 * checked by looking at the game:
 *
 *   1. the muzzle, the port and the support hand are the SAME pose, mirrored
 *      together, so a shot, its brass and the off hand cannot disagree;
 *   2. recoil raises the muzzle whichever way the body faces — the one place
 *      the mirror is deliberately asymmetric, and the bug it replaced;
 *   3. the atlas really carries an action frame for every firearm, appended
 *      after the closed frames rather than interleaved with them.
 */

import { readFileSync } from 'node:fs';

import type { WeaponConfig } from '../src/net/protocol';
import { weaponFeel } from '../src/game/weapon-feel';
import {
  gunHand,
  gunMuzzle,
  gunPort,
  gunPose,
  gunSupport,
  type GunAtlas,
  type GunMuzzleArgs,
} from '../src/render/guns';

let checks = 0;

function assert(condition: boolean, message: string): void {
  checks++;
  if (!condition) throw new Error(message);
}

function near(a: number, b: number, tolerance: number, message: string): void {
  assert(Math.abs(a - b) <= tolerance, `${message}: ${a} vs ${b}`);
}

// The REAL atlas, out of the generator's own output. A hand-written fixture
// would keep passing after `make_guns.py` stopped emitting action frames,
// which is the failure this file exists to catch.
const manifest = JSON.parse(
  readFileSync('../assets/processed/guns/manifest.json', 'utf8'),
) as { frames: number; items: GunAtlas['items'] };

const guns: GunAtlas = {
  // Nothing under test draws, so the bitmap is never touched.
  image: null as unknown as HTMLImageElement,
  frameWidth: 20,
  frameHeight: 9,
  frames: manifest.frames,
  items: manifest.items,
};

const base = (over: Partial<GunMuzzleArgs> = {}): GunMuzzleArgs => ({
  x: 100,
  y: 100,
  ax: 1,
  ay: 0,
  // `PLAYER_HALF_HEIGHT` — the grip is measured off the feet, not the middle.
  halfHeight: 3.6,
  weapon: 'ak47',
  guns,
  ...over,
});

// --- the atlas contract ------------------------------------------------------
{
  const items = manifest.items;
  const closed = Object.values(items).map((item) => item.frame);
  for (const [key, item] of Object.entries(items)) {
    if (key === 'knife') {
      assert(item.cycleFrame === undefined, 'a blade has no action to open');
      continue;
    }
    assert(item.cycleFrame !== undefined, `${key} has no action frame`);
    assert(item.portX !== undefined && item.portY !== undefined, `${key} has no port`);
    assert(
      !closed.includes(item.cycleFrame!),
      `${key}'s action frame collides with a closed frame — the list must be APPENDED`,
    );
    assert(item.cycleFrame! < manifest.frames, `${key}'s action frame is past the sheet`);
    // The port is behind the muzzle: brass out of the front of the barrel is
    // the bug the port was added to fix.
    assert(item.portX! < item.muzzleX, `${key}'s port is not behind its muzzle`);
  }
}

// --- the player sheet's HOLDING rows -----------------------------------------
{
  // The second pose block, appended by `process_sprites.py` from the second
  // three rows `make_player.py` now draws. Two claims, and both are about the
  // APPEND: a walk row that moved would repoint every other sheet's meaning
  // of "row 1", and a missing hold row is a player who goes back to strolling
  // with their arms down while holding a rifle — which is exactly what this
  // looked like before, so nothing on screen would say it had regressed.
  const player = JSON.parse(
    readFileSync('../assets/processed/player/manifest.json', 'utf8'),
  ) as { rows: Record<string, number> };
  const walk = ['down', 'left', 'right', 'up'];
  walk.forEach((view, i) => {
    assert(player.rows[view] === i, `the walk row "${view}" must stay at ${i}`);
    const held = player.rows[`hold-${view}`];
    assert(held !== undefined, `the player sheet has no hold-${view} row`);
    assert(held! >= walk.length, `hold-${view} must be APPENDED, not interleaved`);
  });
}

// --- one pose, three readers -------------------------------------------------
{
  const args = base();
  const spec = guns.items.ak47;
  const hand = gunHand(args);
  const muzzle = gunMuzzle(args);
  const port = gunPort(args);
  const support = gunSupport(args);

  // Aimed due east with no kick, the frame lies along +x and every point is
  // its own frame offset from the grip.
  near(muzzle.x - hand.x, spec.muzzleX - spec.gripX, 0.001, 'muzzle sits along the barrel');
  near(muzzle.y - hand.y, spec.muzzleY - spec.gripY, 0.001, 'muzzle keeps its own row');
  near(port.x - hand.x, spec.portX! - spec.gripX, 0.001, 'port sits where the atlas says');
  assert(port.x < muzzle.x, 'the port is behind the muzzle in the world too');
  assert(
    support.x > hand.x && support.x < muzzle.x,
    'the off hand is on the barrel, between the grip and the muzzle',
  );
}

// --- the grip is on the body, at the height of a hand -------------------------
{
  // MEASURED OFF THE FEET. The box is 7.2 px tall and the sprite standing on
  // it is 16, so anything measured from the box's CENTRE lands around the
  // character's chin — which is exactly where every weapon in this game used
  // to be held. The coat runs rows 8..12 of the cell, so the grip has to sit
  // inside that band and nowhere near the head (rows 1..8).
  const feet = 100 + 3.6;
  const spriteTop = feet - 16;
  const hand = gunHand(base({ ax: 1, ay: 0 }));
  assert(hand.y > spriteTop + 8, `the grip is below the head: ${hand.y - spriteTop}`);
  assert(hand.y < spriteTop + 13, `and not below the coat: ${hand.y - spriteTop}`);

  // OFF THE CENTRELINE when the body faces the camera or away from it, and
  // ON it in profile. A weapon on the midline of a body walking away is a
  // weapon behind sixteen pixels of back.
  const profile = gunHand(base({ ax: 1, ay: 0 }));
  assert(Math.abs(profile.y - hand.y) < 0.001, 'in profile there is no side offset');
  const away = gunHand(base({ ax: 0, ay: -1 }));
  const toward = gunHand(base({ ax: 0, ay: 1 }));
  assert(Math.abs(away.x - 100) > 2, 'facing away, the weapon clears the body');
  assert(Math.abs(toward.x - 100) > 2, 'facing the camera, it clears the body too');
  assert(
    Math.sign(away.x - 100) !== Math.sign(toward.x - 100),
    'the side follows the mirror, so it swaps between the two vertical facings',
  );
}

// --- the mirror --------------------------------------------------------------
{
  const right = gunMuzzle(base({ ax: 1, ay: 0 }));
  const left = gunMuzzle(base({ ax: -1, ay: 0 }));
  const body = base();
  assert(right.x > body.x, 'aiming right, the barrel is to the right');
  assert(left.x < body.x, 'aiming left, the barrel is to the left');
  // MIRRORED, NOT ROTATED: the barrel keeps its height above the chest line
  // when the body turns round, which is what `flip` on the frame's y is for.
  near(left.y, right.y, 0.001, 'a mirrored weapon does not change height');

  const port = gunPort(base({ ax: -1, ay: 0 }));
  assert(port.x > left.x, 'mirrored, the port is still behind the muzzle');
}

// --- recoil raises the muzzle both ways --------------------------------------
{
  // `kick` is negative for climb (see `EntityVisuals.kickGun`), sprite-local,
  // and negated for a left-facing body by `gunPose`. Both must rise on SCREEN,
  // where up is -y.
  const restRight = gunMuzzle(base({ ax: 1, ay: 0 }));
  const kickRight = gunMuzzle(base({ ax: 1, ay: 0, kick: -0.4 }));
  assert(kickRight.y < restRight.y, 'aiming right, recoil lifts the muzzle');

  const restLeft = gunMuzzle(base({ ax: -1, ay: 0 }));
  const kickLeft = gunMuzzle(base({ ax: -1, ay: 0, kick: -0.4 }));
  assert(kickLeft.y < restLeft.y, 'aiming left, recoil still lifts the muzzle');

  // And the whole pose agrees about it, including the hand the arm reaches to.
  const posed = gunPose(base({ ax: -1, ay: 0, kick: -0.4 }));
  assert(posed.flip === -1, 'a left-facing weapon is mirrored');
}

// --- pump and lift -----------------------------------------------------------
{
  const rest = gunHand(base());
  const pumped = gunHand(base({ pump: -2 }));
  assert(pumped.x < rest.x, 'a slide travelling back pulls the grip back down the aim');

  const lifted = gunHand(base({ lift: 2 }));
  near(lifted.y, rest.y - 2, 0.001, 'lift is screen-space and up');
  near(lifted.x, rest.x, 0.001, 'lift never moves the weapon along its own barrel');
}

// --- the knife ---------------------------------------------------------------
{
  // Held IN, at the body: the blade is what reaches forward, never the arm.
  const knife = gunHand(base({ weapon: 'knife' }));
  const rifle = gunHand(base({ weapon: 'ak47' }));
  assert(knife.x < rifle.x, 'the blade is carried closer in than a rifle');

  // A SWING CARRIES THE GRIP WITH IT, and the thrust is what there is to
  // carry: the blade is held at `hold` 0, so a sweep with no thrust rotates
  // an offset of zero length and the hand correctly stays put. Mid-swing the
  // step's `swingThrust` is pushing the grip out along the BLADE, and that is
  // the offset which must leave the aim line — the arm following the cursor
  // while the knife swung off the end of it is the bug `swing` was added for.
  // Aimed in PROFILE so the reading is the swing alone: on a vertical facing
  // the shoulder offset (`GUN_GRIP_SIDE`) is also in the sum and the two
  // partly cancel, which would make this measure nothing in particular.
  const thrust = { weapon: 'knife', ax: 1, ay: 0, pump: 2.4 } as const;
  const swung = gunHand(base({ ...thrust, swing: 0.8 }));
  const still = gunHand(base(thrust));
  assert(swung.x < still.x, 'the thrust swings off the aim line as the blade goes');
  assert(swung.y > still.y, 'and travels down the arc with it');
  assert(Math.abs(swung.x - still.x) > 0.5, 'by a distance somebody can see');
}

// --- what a class of weapon does --------------------------------------------
function row(over: Partial<WeaponConfig>): WeaponConfig {
  return {
    name: 'test',
    kind: 'pistol',
    ammo: 'pistol',
    damage: 10,
    pellets: 1,
    spreadDegrees: 0,
    shotDamage: 10,
    fireCooldown: 0.15,
    range: 100,
    muzzle: 6,
    noise: 100,
    aimDelay: 0,
    fireOnRelease: false,
    scopeZoom: 0,
    shotPitch: 1,
    kick: 1,
    trauma: 0.1,
    gunKick: 0.2,
    gunPump: 2,
    tracerLife: 0.08,
    tracerWidth: 1,
    flash: 0.8,
    casings: 1,
    lightRadius: 50,
    lightLife: 0.1,
    ...over,
  } as WeaponConfig;
}

{
  const pistol = weaponFeel(row({ kind: 'pistol', fireCooldown: 0.15 }));
  assert(pistol.hands === 1, 'a pistol is a sidearm');
  assert(pistol.action === 'slide', 'a pistol has a slide');
  assert(!pistol.audible, 'a slide is inside its own gunshot');
  assert(pistol.cycle > 0 && pistol.cycle < 0.15, 'the action shuts before the next round');

  const rifle = weaponFeel(row({ kind: 'rifle', fireCooldown: 0.1 }));
  assert(rifle.hands === 2, 'a rifle is a shoulder weapon');
  assert(rifle.sway < pistol.sway, 'a shouldered weapon is steadier than a held-out one');

  const shotgun = weaponFeel(row({ kind: 'shotgun', fireCooldown: 0.88, pellets: 6 }));
  assert(shotgun.action === 'pump', 'a shotgun pumps');
  assert(shotgun.audible, 'a forend is its own event and is heard');
  assert(shotgun.eject < shotgun.cycle, 'brass clears the port before the action shuts');

  const awp = weaponFeel(row({ kind: 'sniper', fireCooldown: 1.46 }));
  assert(awp.audible, 'a bolt is heard');
  assert(awp.cycle > shotgun.cycle, 'the bolt is the slowest mechanism on the belt');
  assert(awp.cycle < 1.46, 'and it is still shut before the next round');

  const blade = weaponFeel(row({ kind: 'melee', fireCooldown: 0.4 }));
  assert(blade.action === 'none' && blade.cycle === 0, 'a blade has no mechanism');
  assert(!blade.audible, 'and makes no mechanical noise');

  // A catalog row this client has never heard of must still be holdable.
  const unknown = weaponFeel(row({ kind: 'crossbow' as WeaponConfig['kind'] }));
  assert(unknown.action === 'none', 'an unknown kind falls back to a plain held object');
}

console.log(`ok (${checks} checks)`);
