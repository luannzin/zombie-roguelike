/**
 * One run objective. Top-centre, no panel — a line, not a widget.
 *
 * Copy is `label: have/need`. Done recedes the words and pops the count in
 * accent (the check). Risk paints the count in the danger tone. A row that
 * the server dropped plays the leave animation here; the log unmounts it
 * when that animation ends.
 */

import { cn } from '@/lib/utils';
import type { HudQuest } from '../../game/hud-store';

export interface QuestRowProps {
  quest: HudQuest;
  index: number;
  leaving: boolean;
  onGone: (id: string) => void;
}

export function QuestRow({ quest, index, leaving, onGone }: QuestRowProps) {
  const countTone = quest.done
    ? 'text-ink-accent'
    : quest.risk
      ? 'text-hp-low'
      : 'text-ink';

  return (
    <p
      className={cn(
        'pixel-text text-center text-[11px] leading-[17px] tracking-[0.14em] uppercase',
        leaving ? 'animate-quest-out' : 'animate-quest-in',
      )}
      style={leaving ? undefined : { animationDelay: `${180 + index * 55}ms` }}
      onAnimationEnd={(event) => {
        if (!leaving) return;
        if (event.target !== event.currentTarget) return;
        onGone(quest.id);
      }}
    >
      <span className={quest.done ? 'text-ink-muted' : 'text-ink'}>{quest.label}</span>
      <span className="text-ink-muted">: </span>
      <span
        key={quest.done ? 'done' : 'live'}
        className={cn('inline-block', countTone, quest.done && 'animate-quest-done')}
      >
        {quest.have}/{quest.need}
      </span>
    </p>
  );
}
