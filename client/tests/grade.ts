/**
 * The grade stack's envelopes and composition.
 *
 * Plain script, no framework, prints `ok` — the same shape as the server's
 * checks. Run it with `bun tests/grade.ts` from `client/`.
 *
 * `post/grade.ts` is pure arithmetic over plain objects and imports nothing
 * from the DOM, which is exactly why it is the half of the post chain worth
 * testing: the shader can only be judged by looking at it, but "a layer that
 * finished its release is gone" and "a partial layer leaves the rest of the
 * look alone" are claims that either hold or do not.
 */

import { GradeStack, NEUTRAL, type Grade } from '../src/render/post/grade';

let checks = 0;

function assert(condition: boolean, message: string): void {
  checks++;
  if (!condition) throw new Error(message);
}

function near(actual: number, expected: number, message: string, epsilon = 1e-6): void {
  assert(Math.abs(actual - expected) <= epsilon, `${message}: ${actual} != ${expected}`);
}

/** Step in small slices, the way a frame loop would. */
function run(stack: GradeStack, seconds: number, step = 1 / 60): Grade {
  for (let t = 0; t < seconds; t += step) stack.step(step);
  return stack.resolve();
}

const base: Grade = { ...NEUTRAL, exposure: 1, saturation: 1, vignette: 0.3 };

// An empty stack is its base, untouched.
{
  const stack = new GradeStack(base);
  const out = stack.resolve();
  near(out.exposure, 1, 'empty stack exposure');
  near(out.vignette, 0.3, 'empty stack vignette');
}

// A pulse rises, then leaves — and takes itself off the stack.
{
  const stack = new GradeStack(base);
  stack.pulse('hit', { exposure: 0.5 }, { attack: 0.1, hold: 0.1, release: 0.2 });
  const peak = run(stack, 0.15);
  assert(peak.exposure < 0.6, `pulse should reach its peak, got ${peak.exposure}`);
  assert(stack.has('hit'), 'pulse should still be on the stack mid-envelope');
  const after = run(stack, 0.6);
  near(after.exposure, 1, 'pulse should return the base exactly');
  assert(!stack.has('hit'), 'a finished pulse must drop itself');
}

// A hold stays up until it is released, however long that is.
{
  const stack = new GradeStack(base);
  stack.hold('danger', { vignette: 0.9 }, { attack: 0.1, release: 0.2 });
  const held = run(stack, 5);
  near(held.vignette, 0.9, 'hold should sit at full weight');
  assert(stack.has('danger'), 'a hold must not expire on its own');
  stack.release('danger');
  const gone = run(stack, 0.5);
  near(gone.vignette, 0.3, 'released hold should return the base');
  assert(!stack.has('danger'), 'a released hold must drop itself');
}

// A partial layer says nothing about the fields it does not name. This is the
// property the whole design rests on: an event may not silently reset a look.
{
  const stack = new GradeStack({ ...base, saturation: 0.7, bloom: 0.6 });
  stack.hold('scope', { vignette: 1 }, { attack: 0 });
  const out = run(stack, 0.5);
  near(out.vignette, 1, 'named field should be taken');
  near(out.saturation, 0.7, 'unnamed saturation must survive the layer');
  near(out.bloom, 0.6, 'unnamed bloom must survive the layer');
}

// Two layers compose rather than fighting: each sees the answer below it.
{
  const stack = new GradeStack({ ...base, exposure: 0 });
  stack.hold('a', { exposure: 1 }, { attack: 0 });
  stack.hold('b', { saturation: 0 }, { attack: 0 });
  const out = run(stack, 0.5);
  near(out.exposure, 1, 'first layer survives the second');
  near(out.saturation, 0, 'second layer applies');
}

// Triples interpolate per channel, not by reference.
{
  const stack = new GradeStack({ ...base, gain: [1, 1, 1] });
  stack.hold('warm', { gain: [1.2, 1, 0.8] }, { attack: 0 });
  const out = run(stack, 0.5);
  near(out.gain[0], 1.2, 'gain red');
  near(out.gain[2], 0.8, 'gain blue');
  near(NEUTRAL.gain[0], 1, 'NEUTRAL must not have been mutated');
}

// A base crossfade lands exactly on its target.
{
  const stack = new GradeStack(base);
  stack.setBase({ ...NEUTRAL, exposure: 2, vignette: 0 }, 0.5);
  const out = run(stack, 1.2);
  near(out.exposure, 2, 'crossfade should land on the new base', 1e-3);
  near(out.vignette, 0, 'crossfade should land on the new base', 1e-3);
}

// Retriggering a pulse mid-release carries on from where the screen is.
{
  const stack = new GradeStack(base);
  stack.pulse('hit', { exposure: 0 }, { attack: 0.05, hold: 0, release: 1 });
  run(stack, 0.3);
  const mid = stack.resolve().exposure;
  assert(mid > 0 && mid < 1, `should be mid-release, got ${mid}`);
  stack.pulse('hit', { exposure: 0 }, { attack: 0.05, hold: 0, release: 1 });
  const retriggered = stack.resolve().exposure;
  assert(
    retriggered <= mid + 1e-9,
    `a retrigger must not drop the weight back to zero (${mid} -> ${retriggered})`,
  );
}

console.log(`ok (${checks} checks)`);
