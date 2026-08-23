/**
 * The boss's name and his health, across the top of the screen.
 *
 * The only enemy in this game the HUD is ever told about by name. Everything
 * else is a body in a world you look at; a plate with a name on it is the
 * game saying THIS one is the subject, and the bar under it is the only
 * progress bar in the run that is about somebody else.
 *
 * IT IS A STRUCK PLATE, NOT A PROGRESS BAR, and every decision below follows
 * from that one sentence.
 *
 *   NO NUMBER      `ProgressBar` shows "62 / 100" because the player's own
 *                  health is a resource they budget with. His is a DISTANCE —
 *                  the question is "am I getting anywhere", and 1840 / 2460
 *                  answers it worse than a line does.
 *   THE BEVEL      five ramp steps down the height of a 14px bar: dark at
 *                  both edges, bright through the middle. A bar filled with
 *                  one flat colour is a progress indicator in a settings
 *                  dialog. The ramp is in `styles/index.css` like every other
 *                  colour in this game.
 *   THE SEGMENTS   five, cut into the fill in the plate's own dark rather
 *                  than drawn over it. They are what turns "the bar is quite
 *                  full" into a number a player can actually hold — you learn
 *                  a boss in segments, and "he's down to three" is a thing
 *                  somebody can say out loud to the rest of the party.
 *   GOLD           the game's own gold, the ramp the coin and the payout are
 *                  struck from — not a meter colour. `--hp-*` ramps green to
 *                  red as a resource drains, and his health does not ramp; it
 *                  is one distance crossed once. The enrage is the only thing
 *                  that changes it, and it changes it to the game's one red,
 *                  so what the player reads is a change of temperature rather
 *                  than a change of object.
 *
 * WHAT MAKES IT FEEL LIKE DAMAGE. Two fills, not one:
 *
 *   the LEAD    tracks his health instantly. This is the truth.
 *   the CHASE   a paler bar that lags a quarter of a second behind it, so
 *               every hit leaves a bright wound on the bar that closes up
 *               after it. A body with 2460 health moves the bar about a pixel
 *               a shot, and a pixel is not feedback; the gap between the two
 *               fills is what a player actually reads as "that landed".
 *
 * The whole thing is CSS — the chase is a longer transition on the same width.
 * No timers, no rAF, nothing this component has to own, and it degrades to an
 * honest bar under `prefers-reduced-motion`.
 *
 * IT SURVIVES HIS DEATH, and `Game.hudBoss` decides for how long
 * (`BOSS_BAR_LINGER`). The payoff of a two-minute fight is watching the bar
 * reach zero, and a panel that unmounts when hp hits 0 takes that away on the
 * exact frame it is worth something. What this file owns is only the fade.
 */

import { useEffect, useState } from 'react';
import type { HudBoss } from '../../game/hud-store';
import { cn } from '@/lib/utils';

/**
 * How long the panel outlives a null row, in ms. THE FADE, and nothing more.
 *
 * It used to be 2.6 seconds, on the theory that the panel should hold itself
 * up through his collapse. It never did: the row does not go null when he
 * dies — he simply stops sending rows, so the client keeps the dead one — so
 * the hold only ever ran on the MAP CHANGE, which is the one moment the bar
 * should be gone at once. A player walked out of the yard with an empty bar
 * following them into the shop. The retirement moved upstream to
 * `Game.hudBoss`, and this is now only long enough for the opacity to run.
 */
const SLAIN_HOLD = 600;
/** How many divisions. Five is countable at a glance; ten is a ruler. */
const SEGMENTS = 5;

export interface BossBarProps {
  boss: HudBoss | null;
  className?: string;
}

export function BossBar({ boss, className }: BossBarProps) {
  // Held only so the fade can run after the row goes. `Game.hudBoss` is
  // what decides that it should go — see SLAIN_HOLD.
  const [held, setHeld] = useState<HudBoss | null>(null);

  useEffect(() => {
    if (boss) {
      setHeld(boss);
      return;
    }
    if (!held) return;
    const timer = window.setTimeout(() => setHeld(null), SLAIN_HOLD);
    return () => window.clearTimeout(timer);
  }, [boss, held]);

  const row = boss ?? held;
  if (!row) return null;

  // NOT SHOWN DURING THE ARRIVAL. `engaged` is negative until the cinematic
  // ends, and a health bar over a boss who is still in the air is the game
  // spoiling its own entrance — the shadow is supposed to be the reveal.
  const shown = row.engaged >= 0;
  const fraction = Math.max(0, Math.min(1, row.fraction));
  const ramp = row.enraged ? 'rage' : 'fill';

  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-x-0 top-7 z-20 flex flex-col items-center gap-2',
        'transition-[opacity,transform] duration-[600ms] ease-out motion-reduce:transition-none',
        shown ? 'translate-y-0 opacity-100' : '-translate-y-4 opacity-0',
        className,
      )}
      aria-hidden={!shown}
    >
      {/* THE NAME. Wide-tracked caps with a hard shadow under it — it is read
          over a moving, burning scene, and a soft glow on this font at this
          size turns into a smudge. */}
      <div className="flex flex-col items-center gap-[3px]">
        <div
          className="text-[17px] leading-[17px] tracking-[0.42em] uppercase"
          style={{
            color: 'var(--ink)',
            // The indent cancels the trailing letter-space so wide tracking
            // still reads as centred.
            textIndent: '0.42em',
            textShadow: '0 2px 0 rgb(0 0 0 / 0.95), 0 0 12px rgb(0 0 0 / 0.8)',
          }}
        >
          {row.name}
        </div>
        <div
          className="text-[9px] leading-[9px] tracking-[0.3em] uppercase"
          style={{
            color: row.enraged ? 'var(--boss-rage-mid)' : 'var(--ink-muted)',
            textIndent: '0.3em',
            textShadow: '0 1px 0 rgb(0 0 0 / 0.95)',
          }}
        >
          {row.enraged ? 'enfurecido' : row.title}
        </div>
      </div>

      <div className="relative w-[min(58vw,600px)]">
        {/* THE PLATE. One hairline, one inset, no radius — this game has no
            rounded corners in it anywhere. */}
        <div
          className="relative h-[14px] w-full overflow-hidden"
          style={{
            background: 'var(--boss-plate)',
            boxShadow:
              'inset 0 0 0 1px var(--boss-edge), 0 0 0 1px rgb(0 0 0 / 0.9), 0 2px 10px rgb(0 0 0 / 0.55)',
          }}
        >
          {/* THE CHASE. Behind, muted, and slower — the wound left by a hit. */}
          <div
            className={cn(
              'absolute inset-y-px left-px transition-[width] duration-[560ms] ease-out',
              'motion-reduce:transition-none',
            )}
            style={{
              width: `calc(${fraction * 100}% - 2px)`,
              background: `var(--boss-${ramp}-hi)`,
              opacity: 0.32,
            }}
          />
          {/* THE LEAD. His actual health, moving the frame the hit lands. */}
          <div
            className={cn(
              'absolute inset-y-px left-px transition-[width] duration-[90ms] ease-linear',
              'motion-reduce:transition-none',
            )}
            style={{
              width: `calc(${fraction * 100}% - 2px)`,
              background: [
                'linear-gradient(to bottom,',
                `var(--boss-${ramp}-edge) 0 1px,`,
                `var(--boss-${ramp}-lo) 1px 3px,`,
                `var(--boss-${ramp}-mid) 3px 6px,`,
                `var(--boss-${ramp}-hi) 6px 8px,`,
                `var(--boss-${ramp}-mid) 8px 10px,`,
                `var(--boss-${ramp}-lo) 10px 11px,`,
                `var(--boss-${ramp}-edge) 11px 12px)`,
              ].join(' '),
            }}
          />
          {/* THE CROWN. One pixel of the ramp's top step along the fill's
              upper edge — the specular that says "struck metal" and not
              "coloured rectangle". S14's rule for painted metal, in CSS. */}
          <div
            className="absolute left-px top-px h-px transition-[width] duration-[90ms] ease-linear motion-reduce:transition-none"
            style={{
              width: `calc(${fraction * 100}% - 2px)`,
              background: `var(--boss-${ramp}-crown)`,
              opacity: 0.55,
            }}
          />
          {/* THE SEGMENTS, cut in the plate's own dark. Drawn over the fill so
              they divide it, and over the empty track so the divisions are
              still there when the bar is low — a bar whose ticks vanish with
              its fill stops being countable exactly when counting matters. */}
          {Array.from({ length: SEGMENTS - 1 }, (_, i) => (
            <div
              key={i}
              className="absolute inset-y-0 w-[2px]"
              style={{
                left: `${((i + 1) / SEGMENTS) * 100}%`,
                background: 'var(--boss-tick)',
              }}
            />
          ))}
        </div>

        {/* END CAPS. Two short verticals past each end of the plate, in the
            lit edge. They are the difference between a bar that was placed on
            the screen and a bar that is mounted in it. */}
        <div
          className="absolute -left-[3px] top-[-2px] h-[18px] w-px"
          style={{ background: 'var(--boss-edge-lit)', opacity: 0.7 }}
        />
        <div
          className="absolute -right-[3px] top-[-2px] h-[18px] w-px"
          style={{ background: 'var(--boss-edge-lit)', opacity: 0.7 }}
        />
      </div>
    </div>
  );
}
