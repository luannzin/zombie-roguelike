/**
 * What the levels bought, ABOVE the bag.
 *
 * WHY IT IS HERE AND NOT IN A CORNER OF ITS OWN. A skill is the same kind of
 * statement the pocket is — *this is what I am carrying* — and stacking the
 * two into one column is what stops the HUD growing a fifth region. The bag is
 * what you found tonight and can still lose; the tray is what you keep. One
 * above the other, read bottom-up, is a sentence about the run.
 *
 * ONE TILE PER SKILL: icon, rarity border, and the stack count. The NAME is
 * not on the tile and that is deliberate — eighteen labelled rows would be a
 * spreadsheet in the corner of a horror game. The name and what it does live
 * in the hover card, which is the same trade the bag already makes.
 *
 * A tile at its CAP is marked, because a duplicate past the ceiling still
 * counts up and a number that silently stopped meaning anything is worse than
 * no number at all.
 *
 * The tray is EMPTY until the first pull and draws nothing at all when it is —
 * a run opens with no skills, and an empty frame labelled "skills" would be
 * the HUD explaining a system the player has not met yet.
 */

import { useEffect, useRef, useState } from 'react';
import type { HudSkill } from '../../game/hud-store';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { Panel } from './Panel';
import { SkillIcon } from './SkillIcon';

export interface SkillTrayProps {
  skills: HudSkill[];
  /** Pulls owed. Drawn as a badge so a level earned in the woods is not lost. */
  spins: number;
  /** The skill that just landed, or null. Plays the tile in. */
  reward: HudSkill | null;
  /** How many frames the skill atlas has. Straight off the catalog. */
  frames: number;
}

const RARITY_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

const RARITY_TEXT: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

export function SkillTray({ skills, spins, reward, frames }: SkillTrayProps) {
  const [hover, setHover] = useState<HudSkill | null>(null);
  const landed = useLanded(reward);

  if (skills.length === 0 && spins <= 0) return null;

  return (
    <div className="relative flex flex-col items-start gap-1">
      {hover ? (
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

      {spins > 0 ? (
        /* The reminder, and it only exists because the machine is a zone away.
           A level earned in the middle of the woods is spendable at the shop
           and nowhere else, so something has to carry that fact across the
           night — otherwise the reward for levelling is a number that moved. */
        <div className="text-rarity-legendary animate-pulse text-[10px] leading-[14px]">
          {spins} {spins === 1 ? 'giro guardado' : 'giros guardados'}
        </div>
      ) : null}

      {skills.length > 0 ? (
        <div className="flex flex-wrap items-end gap-1">
          {skills.map((skill) => (
            <div
              key={skill.key}
              className={cn(
                'pointer-events-auto relative border bg-panel-inset p-px',
                RARITY_BORDER[skill.rarity],
                landed === skill.key && 'animate-skill-land',
              )}
              onPointerEnter={() => setHover(skill)}
              onPointerLeave={() => setHover((current) => (current === skill ? null : current))}
            >
              <SkillIcon frame={skill.frame} frames={frames} zoom={2} />
              {skill.qty > 1 ? (
                <span
                  className={cn(
                    'absolute right-0 bottom-0 px-0.5 text-[10px] leading-[10px]',
                    skill.qty >= skill.cap ? 'text-ink-muted' : 'text-ink',
                  )}
                >
                  {skill.qty}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The key of the tile that should be playing its entry, or null.
 *
 * Held for a beat rather than read straight off `reward`, because `reward` is
 * cleared the moment the machine's ceremony ends and the tile's animation is
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
