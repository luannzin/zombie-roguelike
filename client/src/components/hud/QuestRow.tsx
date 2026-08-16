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
import { QuestCount } from './QuestCount';

export type QuestRowMode = 'ghost' | 'live' | 'shown' | 'leaving';

export interface QuestRowProps {
  quest: HudQuest;
  mode: QuestRowMode;
  dockRef?: (node: HTMLElement | null) => void;
  onGone?: (id: string) => void;
}

export function QuestRow({ quest, mode, dockRef, onGone }: QuestRowProps) {
  const done = quest.done || mode === 'leaving';

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 whitespace-nowrap text-[11px] leading-[17px] tracking-[0.08em] uppercase',
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
        className={cn('text-left whitespace-nowrap', done ? 'text-ink-muted' : 'text-ink')}
      >
        {quest.label}
      </span>
      <QuestCount
        key={done ? 'done' : 'live'}
        have={quest.have}
        need={quest.need}
        gold={quest.gold}
        risk={quest.risk}
        done={done}
        className={done && mode !== 'ghost' ? 'animate-quest-done' : undefined}
      />
    </div>
  );
}
