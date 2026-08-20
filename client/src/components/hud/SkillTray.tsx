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
import { dropInventoryAnchor, writeInventoryAnchor } from '../../game/inventory-anchors';
import { SKILL_TRAY_ANCHOR } from '../../game/loot-flies';
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
  const box = useTrayAnchor();

  return (
    <div ref={box} className="relative flex flex-col items-start gap-px">
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
                 other. The border is the only separator they need.

                 SIZED UP ONE NOTCH. At 10px in a 160px row the shelf was the
                 smallest type on the screen, under a bag whose own labels are
                 bigger — and this is the half of that column the player KEEPS.
                 The icon stays 16px because it is pixel art and the only step
                 up available is double, which would make the tile the subject
                 of a row that exists to be read as words. */
              'pointer-events-auto flex w-48 items-center gap-2 border bg-panel-inset/85 px-1.5 py-0.5',
              RARITY_BORDER[skill.rarity],
              landed === skill.key && 'animate-skill-land',
            )}
            onPointerEnter={() => setHover(skill)}
            /* BY KEY, NOT BY IDENTITY. `skills` is rebuilt from the catalog on
               every HUD publish — five times a second — so the object under
               the cursor is a different object from the one `setHover` was
               given a moment ago, and an identity test never matched. The card
               stayed up until the pointer happened to enter another row. */
            onPointerLeave={() =>
              setHover((current) => (current?.key === skill.key ? null : current))
            }
          >
            <SkillIcon frame={skill.frame} frames={frames} zoom={1} />
            <span
              className={cn(
                'flex-1 truncate text-[11px] leading-[18px]',
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
                'text-[11px] leading-[18px] tabular-nums',
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
 * Publish the tray's own box as the target a payout tin flies at.
 *
 * ONE ANCHOR FOR THE WHOLE TRAY, not one per row, because on a first copy the
 * row does not exist yet — it is what the landing CREATES. Aiming at the shelf
 * and letting the row appear underneath is also the honest reading of what
 * happened: the skill went into the collection, and the collection then grew
 * a line for it.
 *
 * Written every frame from layout rather than once on mount, for the reason
 * every other anchor in this HUD is: the shelf moves down the screen as the
 * bag below it opens, and a tin aimed at where the tray was half a second ago
 * lands beside it.
 *
 * Unconditional, unlike a bag cell's — the tray is 0x0 with nothing pulled
 * yet, and that empty box sits exactly where the first row is about to be.
 */
function useTrayAnchor() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const el = ref.current;
      if (el) {
        const rect = el.getBoundingClientRect();
        writeInventoryAnchor(SKILL_TRAY_ANCHOR, rect.left + rect.width / 2, rect.top);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      dropInventoryAnchor(SKILL_TRAY_ANCHOR);
    };
  }, []);

  return ref;
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
