/**
 * The shadow field's arithmetic. Run: `bun tests/shadows.ts` from `client/`.
 *
 * Only `lightAt` — the part with a decision in it. The stamping needs a canvas
 * and is judged by looking, like the rest of the finish.
 */

import { addShadowLight, beginShadows, lightAt } from '../src/render/shadows';

let checks = 0;
function ok(what: string, pass: boolean): void {
  if (!pass) throw new Error(`FAIL: ${what}`);
  checks++;
}
function near(a: number, b: number, eps = 0.001): boolean {
  return Math.abs(a - b) <= eps;
}

// Nothing burning: no cast, at any point.
beginShadows();
const dark = lightAt(10, 10);
ok('unlit has no cast', dark.k === 0);

// One light to the west: the shadow points east, away from it.
beginShadows();
addShadowLight(0, 0, 1, 100);
const east = lightAt(50, 0);
ok('points away from the light', near(east.dx, 1) && near(east.dy, 0));
ok('half way out is half way out', near(east.t, 0.5, 0.02));
ok('a light in range casts', east.k > 0);

// Out of reach is out of the field entirely.
ok('past the reach casts nothing', lightAt(101, 0).k === 0);

// Two equal lights either side: the marks argue and cancel.
beginShadows();
addShadowLight(-50, 0, 1, 100);
addShadowLight(50, 0, 1, 100);
ok('symmetric lights cancel', lightAt(0, 0).k === 0);

// Two unequal lights: the stronger one wins the direction without owning it.
beginShadows();
addShadowLight(-50, 0, 1, 100);
addShadowLight(50, 0, 0.25, 100);
const mixed = lightAt(0, 0);
ok('the stronger light decides the side', mixed.dx > 0.99);
ok('but the weaker one still counts', mixed.k < 1);

// Standing on top of a light is a pool, not a rake: t is 0 at the source.
beginShadows();
addShadowLight(0, 0, 1, 100);
ok('at the source the cast is shortest', near(lightAt(0.0005, 0).t, 0, 0.01));

// Power below the noise floor is not a light.
beginShadows();
addShadowLight(0, 0, 0.01, 100);
ok('a dying flash stops casting', lightAt(10, 0).k === 0);

console.log(`ok (${checks} checks)`);
