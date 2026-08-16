/**
 * Big centre beat for a new objective. The words arrive large, hold so they
 * can be read, then fly into the quest card under the minimap.
 *
 * The dock is a FLIP: one layout measure, then a transform. React is not in
 * the frame loop — the travel is a CSS transition.
 */

import { useLayoutEffect, useRef, useState } from 'react';
import type { HudQuest } from '../../game/hud-store';

export const QUEST_ANNOUNCE_IN_MS = 420;
export const QUEST_ANNOUNCE_HOLD_MS = 900;
export const QUEST_ANNOUNCE_DOCK_MS = 560;

/** Row type is 11px; this is 22px. Dock scale is that ratio. */
const DOCK_SCALE = 0.5;

export interface QuestAnnounceProps {
  quest: HudQuest;
  dock: HTMLElement | null;
  onLanded: () => void;
}

export function QuestAnnounce({ quest, dock, onLanded }: QuestAnnounceProps) {
  const textRef = useRef<HTMLParagraphElement>(null);
  const dockRef = useRef(dock);
  const onLandedRef = useRef(onLanded);
  const [docking, setDocking] = useState(false);
  const landed = useRef(false);

  dockRef.current = dock;
  onLandedRef.current = onLanded;

  useLayoutEffect(() => {
    const finish = () => {
      if (landed.current) return;
      landed.current = true;
      onLandedRef.current();
    };

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      finish();
      return;
    }

    const start = window.setTimeout(
      () => setDocking(true),
      QUEST_ANNOUNCE_IN_MS + QUEST_ANNOUNCE_HOLD_MS,
    );
    return () => window.clearTimeout(start);
  }, []);

  useLayoutEffect(() => {
    if (!docking) return;
    const text = textRef.current;
    const finish = () => {
      if (landed.current) return;
      landed.current = true;
      onLandedRef.current();
    };
    if (!text) {
      finish();
      return;
    }

    const from = text.getBoundingClientRect();
    const to = dockRef.current?.getBoundingClientRect();
    if (!to || to.width < 1 || to.height < 1) {
      text.style.opacity = '0';
      const fade = window.setTimeout(finish, 160);
      return () => window.clearTimeout(fade);
    }

    const dx = to.left + to.width / 2 - (from.left + from.width / 2);
    const dy = to.top + to.height / 2 - (from.top + from.height / 2);
    const ease = 'cubic-bezier(0.23, 1, 0.32, 1)';
    text.style.transition = `transform ${QUEST_ANNOUNCE_DOCK_MS}ms ${ease}, opacity ${QUEST_ANNOUNCE_DOCK_MS}ms ${ease}`;
    text.style.transform = `translate(${dx}px, ${dy}px) scale(${DOCK_SCALE})`;
    text.style.opacity = '0';

    const end = window.setTimeout(finish, QUEST_ANNOUNCE_DOCK_MS);
    return () => window.clearTimeout(end);
  }, [docking]);

  return (
    <div className="pointer-events-none fixed inset-0 z-10 flex items-center justify-center">
      <p
        ref={textRef}
        className="animate-quest-announce pixel-text text-ink max-w-[16em] text-center text-[22px] leading-[26px] tracking-[0.18em] uppercase drop-shadow-[0_2px_0_var(--hud-text-shadow)]"
      >
        {quest.label}
      </p>
    </div>
  );
}
