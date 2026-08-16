/**
 * Extraction-exit pointer. Generated HUD sprite (`/hud/arrow.png`), not a
 * diamond in CSS and not a sprite in the forest.
 *
 * Sits OUTSIDE HudScreen: the glass would bend it off the screen edge,
 * and the whole point of the pose is that it rides the HUD bezel in the
 * exit's direction. Show/hide is `hud-store` at 5 Hz; the pixels are rAF.
 */

import { useEffect, useRef } from 'react';
import { readExitGuide } from '../../game/exit-guide';

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
      <img
        src="/hud/arrow.png"
        alt=""
        width={13}
        height={9}
        draggable={false}
        className="pixelated h-[18px] w-[26px]"
      />
    </div>
  );
}
