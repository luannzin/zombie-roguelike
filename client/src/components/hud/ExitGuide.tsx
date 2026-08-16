/**
 * Extraction-exit caret. Gold HUD chrome, not a sprite in the forest.
 *
 * Sits OUTSIDE HudScreen: the glass would bend it off the geometric
 * midpoint, and the whole point of the pose is that it is always on
 * screen, halfway from the player to the edge in the exit's direction.
 * Show/hide is `hud-store` at 5 Hz; the pixels are rAF.
 */

import { useEffect, useRef } from 'react';
import { readExitGuide } from '../../game/exit-guide';
import { PixelCaret } from './PixelCaret';

export interface ExitGuideProps {
  visible: boolean;
}

export function ExitGuide({ visible }: ExitGuideProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!visible) return;
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      const pose = readExitGuide();
      if (pose) {
        el.style.transform =
          `translate(${Math.round(pose.x)}px, ${Math.round(pose.y)}px)`
          + ` translate(-50%, -50%) rotate(${pose.angle}rad)`;
        el.style.visibility = 'visible';
      } else {
        el.style.visibility = 'hidden';
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
      className="pointer-events-none fixed top-0 left-0 z-10"
      style={{ visibility: 'hidden' }}
      aria-hidden="true"
    >
      <PixelCaret />
    </div>
  );
}
