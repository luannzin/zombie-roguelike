/**
 * One objective inside the quest card.
 *
 * Ghost rows exist only so the announce has a place to land — same type, no
 * ink. Live rows sit in the card (and play the land fade). Shown is the same
 * without the fade, used when the whole card is already leaving. Done rows
 * rise, hold, then leave.
 */

import { cn } from '@/lib/utils';
import type { HudQuest } from '../../game/hud-store';

export type QuestRowMode = 'ghost' | 'live' | 'shown' | 'leaving';

export interface QuestRowProps {
  quest: HudQuest;
  mode: QuestRowMode;
  dockRef?: (node: HTMLElement | null) => void;
  onGone?: (id: string) => void;
}

export function QuestRow({ quest, mode, dockRef, onGone }: QuestRowProps) {
  const done = quest.done || mode === 'leaving';
  const countTone = done
    ? 'text-ink-accent'
    : quest.risk
      ? 'text-hp-low'
      : 'text-ink';

  return (
    <div
      className={cn(
        'flex items-start justify-between gap-2 text-[11px] leading-[17px] tracking-[0.08em] uppercase',
        mode === 'ghost' && 'opacity-0',
        mode === 'live' && 'animate-quest-land',
        mode === 'leaving' && 'animate-quest-leave',
      )}
      onAnimationEnd={(event) => {
        if (event.target !== event.currentTarget) return;
        if (mode === 'leaving') onGone?.(quest.id);
      }}
    >
      <span
        ref={mode === 'ghost' ? dockRef : undefined}
        className={cn('min-w-0 text-left break-words', done ? 'text-ink-muted' : 'text-ink')}
      >
        {quest.label}
      </span>
      <span
        key={done ? 'done' : 'live'}
        className={cn(
          'inline-block shrink-0 tabular-nums tracking-[0.08em]',
          countTone,
          done && mode !== 'ghost' && 'animate-quest-done',
        )}
      >
        {quest.have}/{quest.need}
      </span>
    </div>
  );
}
