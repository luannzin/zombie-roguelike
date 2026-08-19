/**
 * The way out, pointed at. A generated HUD sprite (`/hud/chevron.png`), not a
 * shape in CSS and not a marker in the forest.
 *
 * Sits OUTSIDE HudScreen: the glass would bend it off the screen edge, and the
 * pose is a screen-space point of its own. Show/hide is `hud-store` at 5 Hz;
 * the pixels are rAF, and the smoothing behind them is `game/exit-guide`.
 *
 * NOTHING IS ROUNDED HERE. The chevron is a smoothed, sub-pixel transform on a
 * composited layer — rounding the translate would put the per-frame jitter
 * straight back after the smoothing had just taken it out, which is what the
 * old version did.
 *
 * IT IS A TRIANGLE AND IT BLINKS, and those two are one decision.
 *
 * A permanent marker answers "which way out" forever, which means the world
 * never has to — the column of light over the treeline, the four torches at
 * the threshold and the ping from the mouth all become decoration the moment
 * something on the glass is doing their job. A marker that simply faded out
 * after ten seconds had the opposite problem: a party that turned the wrong
 * way at second twelve had nothing left to ask.
 *
 * So it PULSES. A long first burst while the news is news, then it goes dark,
 * then it comes back for a couple of seconds every few — long enough to catch
 * somebody who has lost their bearings, dark long enough that most of the run
 * out is read off the map. And what survives being flashed is AREA, not line:
 * the old dart is a thin thing that reads by its length, which is right for a
 * steady pointer and wrong for one that is only on screen half a second at a
 * time. The triangle is the same information as one solid mass.
 */

import { useEffect, useRef } from 'react';
import { snapExitGuide, stepExitGuide } from '../../game/exit-guide';

export interface ExitGuideProps {
  /** 1 while there is an uncrossed way out. Zero unmounts the chevron. */
  strength: number;
}

/** Source pixels of `/hud/chevron.png`, drawn at 2x so the grid stays crisp. */
const CHEVRON_PX = 17;
const CHEVRON_SCALE = 2;

/**
 * The blink, in seconds.
 *
 * LEAD is the first burst — it opens solid, because the frame the exit is
 * carved is the frame the whole party has to turn around, and a pointer that
 * was already blinking then would be asking them to wait for it. Everything
 * after that is ON up, OFF dark, forever, with EDGE seconds of ramp at each
 * end of a pulse so it breathes in rather than snapping on.
 */
const LEAD = 5;
const LEAD_FADE = 1.1;
const ON = 2.4;
const OFF = 4.6;
const EDGE = 0.35;

/**
 * How lit the chevron is at `age` seconds after the exit opened, 0..1.
 *
 * Pure, and on the render clock rather than in the store, because the ramps
 * are shorter than the HUD's 200 ms republish — pushed through the snapshot
 * this would arrive as two steps and a pop.
 */
export function blinkAt(age: number): number {
  if (age <= LEAD) return 1;
  const out = LEAD + LEAD_FADE;
  if (age <= out) return 1 - (age - LEAD) / LEAD_FADE;
  const phase = (age - out) % (ON + OFF);
  if (phase >= ON) return 0;
  const edge = Math.min(EDGE, ON / 2);
  if (phase < edge) return phase / edge;
  const tail = ON - phase;
  return tail < edge ? tail / edge : 1;
}

export function ExitGuide({ strength }: ExitGuideProps) {
  const ref = useRef<HTMLDivElement>(null);
  const visible = strength > 0;

  useEffect(() => {
    if (!visible) return;
    const el = ref.current;
    if (!el) return;
    // The module's drawn pose is whatever last night's exit left behind.
    // Easing in from that would sweep the chevron across the glass on the one
    // frame the party is being told to turn round.
    snapExitGuide();
    let raf = 0;
    let age = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      age += dt;
      const pose = stepExitGuide(dt);
      if (pose) {
        el.style.transform =
          `translate3d(${pose.x.toFixed(2)}px, ${pose.y.toFixed(2)}px, 0)`
          + ` translate(-50%, -50%) rotate(${pose.angle.toFixed(4)}rad)`;
        el.style.opacity = blinkAt(age).toFixed(3);
      } else {
        el.style.opacity = '0';
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      ref={ref}
      className="pointer-events-none fixed top-0 left-0 z-10 will-change-transform"
      style={{ opacity: 0 }}
      aria-hidden="true"
    >
      <img
        src="/hud/chevron.png"
        alt=""
        width={CHEVRON_PX}
        height={CHEVRON_PX}
        draggable={false}
        className="pixelated block"
        style={{
          width: CHEVRON_PX * CHEVRON_SCALE,
          height: CHEVRON_PX * CHEVRON_SCALE,
          filter: 'drop-shadow(0 0 6px rgb(0 0 0 / 0.85))',
        }}
      />
    </div>
  );
}
