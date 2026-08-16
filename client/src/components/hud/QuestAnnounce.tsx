/**
 * Top-centre beat for a new objective, then a fly into the quest card —
 * the same hold-then-travel as a collect into the bag (`LootFly`).
 *
 * Pose is written in rAF, never component state. The overlay lives on
 * `document.body` so it is not warped by the HUD glass; the landing point
 * is `warpHudPoint`'d so it still hits the cell the player sees. Type is
 * the HUD's 11px, nowrap — a long name stays one line.
 */

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { HUD_LENS, warpHudPoint } from '@/lib/lens';
import type { HudQuest } from '../../game/hud-store';

/** How long the words sit at top-centre before they travel. */
export const QUEST_FLY_HOLD = 0.7;
/** Top-centre → card row. Same travel as a loot fly. */
export const QUEST_FLY_TRAVEL = 0.62;
export const QUEST_FLY_LIFE = QUEST_FLY_HOLD + QUEST_FLY_TRAVEL;

/** Hold sits here, not on the vertical centre — a task, not a title. */
const HOLD_Y = 0.2;
/** Announce is the HUD's 11px; land at the same size. */
const LAND_SCALE = 1;

export interface QuestAnnounceProps {
  quest: HudQuest;
  dock: HTMLElement | null;
  onLanded: () => void;
}

export function QuestAnnounce({ quest, dock, onLanded }: QuestAnnounceProps) {
  const nodeRef = useRef<HTMLParagraphElement>(null);
  const dockRef = useRef(dock);
  const onLandedRef = useRef(onLanded);
  dockRef.current = dock;
  onLandedRef.current = onLanded;

  useEffect(() => {
    const el = nodeRef.current;
    if (!el) return;

    const finish = () => {
      onLandedRef.current();
    };

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      finish();
      return;
    }

    let age = 0;
    let last = performance.now();
    let raf = 0;
    let done = false;

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      age += dt;

      const fromX = window.innerWidth / 2;
      const fromY = window.innerHeight * HOLD_Y;
      const box = dockRef.current?.getBoundingClientRect();
      const ready = !!box && box.width > 1 && box.height > 1;
      if (age >= QUEST_FLY_HOLD && !ready) {
        age = QUEST_FLY_HOLD - 0.0001;
      }

      if (age >= QUEST_FLY_LIFE) {
        el.style.visibility = 'hidden';
        if (!done) {
          done = true;
          finish();
        }
        return;
      }

      let x = fromX;
      let y = fromY;
      let scale = 1;
      let alpha = 1;

      if (age < QUEST_FLY_HOLD) {
        const pop = Math.min(1, age / 0.12);
        const bob = Math.sin(age * 7.5) * 3;
        x = fromX;
        y = fromY + bob;
        scale = 0.96 + 0.2 * pop;
        alpha = pop;
      } else if (box) {
        const t = (age - QUEST_FLY_HOLD) / QUEST_FLY_TRAVEL;
        const ease = 1 - (1 - t) ** 3;
        const raw = warpHudPoint(
          box.left + box.width / 2,
          box.top + box.height / 2,
          window.innerWidth,
          window.innerHeight,
          HUD_LENS,
        );
        x = fromX + (raw.x - fromX) * ease;
        y = fromY + (raw.y - fromY) * ease;
        scale = 1.16 - (1.16 - LAND_SCALE) * ease;
        alpha = t > 0.82 ? 1 - (t - 0.82) / 0.18 : 1;
      }

      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${scale})`;
      el.style.opacity = String(alpha);
      el.style.visibility = 'visible';
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [quest.id]);

  return createPortal(
    <p
      ref={nodeRef}
      className="pixel-text text-ink pointer-events-none fixed top-0 left-0 z-20 whitespace-nowrap text-center text-[11px] leading-[17px] tracking-[0.08em] uppercase drop-shadow-[0_2px_0_var(--hud-text-shadow)]"
      style={{ visibility: 'hidden' }}
      aria-hidden="true"
    >
      {quest.label}
    </p>,
    document.body,
  );
}
