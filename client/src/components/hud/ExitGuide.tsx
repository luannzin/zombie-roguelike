/**
 * Extraction-exit pointer. Generated HUD sprite (`/hud/arrow.png`), not a
 * diamond in CSS and not a sprite in the forest.
 *
 * Sits OUTSIDE HudScreen: the glass would bend it off the screen edge, and the
 * pose is a screen-space point of its own. Show/hide is `hud-store` at 5 Hz;
 * the pixels are rAF, and the smoothing behind them is `game/exit-guide`.
 *
 * NOTHING IS ROUNDED HERE. The arrow is a smoothed, sub-pixel transform on a
 * composited layer — rounding the translate would put the per-frame jitter
 * straight back after the smoothing had just taken it out, which is what the
 * old version did.
 */

import { useEffect, useRef } from 'react';
import { stepExitGuide } from '../../game/exit-guide';

export interface ExitGuideProps {
  visible: boolean;
}

/** Source pixels of `/hud/arrow.png`, drawn at 2x so the grid stays crisp. */
const ARROW_W = 21;
const ARROW_H = 13;
const ARROW_SCALE = 2;

export function ExitGuide({ visible }: ExitGuideProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!visible) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const pose = stepExitGuide(dt);
      if (pose) {
        el.style.transform =
          `translate3d(${pose.x.toFixed(2)}px, ${pose.y.toFixed(2)}px, 0)`
          + ` translate(-50%, -50%) rotate(${pose.angle.toFixed(4)}rad)`;
        el.style.opacity = '1';
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
      className="pointer-events-none fixed top-0 left-0 z-10 will-change-transform transition-opacity duration-150"
      style={{ opacity: 0 }}
      aria-hidden="true"
    >
      <img
        src="/hud/arrow.png"
        alt=""
        width={ARROW_W}
        height={ARROW_H}
        draggable={false}
        className="pixelated block"
        style={{
          width: ARROW_W * ARROW_SCALE,
          height: ARROW_H * ARROW_SCALE,
          filter: 'drop-shadow(0 0 6px rgb(0 0 0 / 0.85))',
        }}
      />
    </div>
  );
}
