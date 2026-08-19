/**
 * What the levels bought, ABOVE the bag.
 *
 * WHY IT IS HERE AND NOT IN A CORNER OF ITS OWN. A skill is the same kind of
 * statement the pocket is — *this is what I am carrying* — and stacking the
 * two into one column is what stops the HUD growing a fifth region. The bag is
 * what you found tonight and can still lose; the tray is what you keep. One
 * above the other, read bottom-up, is a sentence about the run.
 *
 * IT IS A LIST OF ROWS, NOT A GRID OF ICONS, and that is the change. A wall of
 * 16px tiles asks the player to hover eighteen things to find out what they
 * own — which is a spreadsheet with the words hidden. A row is the whole
 * statement at a glance: the icon, the NAME, and how many copies. The rarity
 * is the row's colour, so the same five-colour ladder loot uses is what says
 * how good the shelf is without a single extra glyph.
 *
 * IT IS NEVER EMPTY. A run opens with no skills and the tray says so in one
 * muted word, because a region that appears out of nowhere at the first shop
 * is a region the player has to re-learn mid-run — and "nenhuma" is also the
 * only place the HUD ever admits this system exists before it has paid out.
 *
 * A row at its CAP is marked, because a duplicate past the ceiling still
 * counts up and a number that silently stopped meaning anything is worse than
 * no number at all.
 */

import { useEffect, useRef, useState } from 'react';
import type { HudSkill } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { Panel } from './Panel';
import { SkillIcon } from './SkillIcon';

export interface SkillTrayProps {
  skills: HudSkill[];
  /** The skill that just landed, or null. Plays the row in. */
  reward: HudSkill | null;
  /** How many frames the skill atlas has. Straight off the catalog. */
  frames: number;
}

/**
 * The five ladders, as three tokens each.
 *
 * Written out rather than composed from a template string because Tailwind
 * scans source text for class names — a `border-rarity-${rarity}` would be
 * five classes that never reach the stylesheet.
 */
const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common/60',
  uncommon: 'border-rarity-uncommon/60',
  rare: 'border-rarity-rare/60',
  epic: 'border-rarity-epic/60',
  legendary: 'border-rarity-legendary/70',
};

const RARITY_TEXT: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

export function SkillTray({ skills, reward, frames }: SkillTrayProps) {
  const [hover, setHover] = useState<HudSkill | null>(null);
  const landed = useLanded(reward);

  return (
    <div className="relative flex flex-col items-start gap-px">
      {hover ? (
        /* What it DOES. The row already carries the name, so the card is only
           ever the sentence underneath it — which is the same trade the bag
           makes, and the reason a row can stay one line. */
        <Panel className="pointer-events-none absolute bottom-full left-0 mb-1 w-max max-w-56 px-2 py-1.5">
          <div className={cn('text-[11px] leading-[15px]', RARITY_TEXT[hover.rarity])}>
            {hover.name}
          </div>
          <div className="text-ink-muted text-[10px] leading-[14px]">{hover.blurb}</div>
          {hover.qty >= hover.cap ? (
            <div className="text-ink-muted mt-0.5 text-[10px] leading-[14px]">
              no máximo ({hover.cap})
            </div>
          ) : null}
        </Panel>
      ) : null}

      {skills.length === 0 ? (
        null
      ) : (
        skills.map((skill) => (
          <div
            key={skill.key}
            className={cn(
              /* STACKED WITH NO GAP so the rows read as one shelf that grew,
                 rather than as separate cards that happen to be near each
                 other. The border is the only separator they need. */
              'pointer-events-auto flex w-40 items-center gap-1.5 border bg-panel-inset/85 px-1 py-px',
              RARITY_BORDER[skill.rarity],
              landed === skill.key && 'animate-skill-land',
            )}
            onPointerEnter={() => setHover(skill)}
            onPointerLeave={() => setHover((current) => (current === skill ? null : current))}
          >
            <SkillIcon frame={skill.frame} frames={frames} zoom={1} />
            <span
              className={cn(
                'flex-1 truncate text-[10px] leading-[16px]',
                RARITY_TEXT[skill.rarity],
              )}
            >
              {skill.name}
            </span>
            {/* The count is always drawn, even at one. A number that only
                appears on the second copy makes the first row a different
                shape from every other row on the shelf. */}
            <span
              className={cn(
                'text-[10px] leading-[16px] tabular-nums',
                skill.qty >= skill.cap ? 'text-ink-muted' : 'text-ink',
              )}
            >
              x{skill.qty}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

/**
 * The key of the row that should be playing its entry, or null.
 *
 * Held for a beat rather than read straight off `reward`, because `reward` is
 * cleared the moment the machine's ceremony ends and the row's animation is
 * longer than the frames between those two events. Keyed on the SKILL rather
 * than on a counter so pulling a second copy of something plays it again.
 */
function useLanded(reward: HudSkill | null): string | null {
  const [key, setKey] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!reward) return;
    setKey(reward.key);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setKey(null), 900);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [reward]);

  return key;
}
