/**
 * THE ULTIMATE OF THE WEAPON IN HAND. One rectangle, directly above the belt.
 *
 * WHY IT IS ABOVE THE BELT AND NOT BESIDE THE VITALS. Everything in the
 * right-hand column answers "what is happening to my body" — health, breath,
 * armour, light. This answers "what can the thing in my hands DO", which is
 * the belt's question, and it changes when the belt changes. A player who
 * presses 2 must see this panel change on the same frame, and two panels that
 * change together belong next to each other.
 *
 * THE WHOLE STATE MACHINE IS ON ONE LINE, AND THAT IS THE DESIGN
 * ==============================================================
 * An ultimate has five states and the player has to be able to tell them apart
 * at a glance, mid-fight, without hovering:
 *
 *     LOCKED      grey mark, muted name, a dashed track where the bar goes
 *     CHARGING    the mark as drawn, the name in ink, the bar filling
 *     READY       the mark glowing, the name in the accent, "R" lit
 *     ACTIVE      the bar DRAINING and the panel ringed
 *     (and back to CHARGING, because spending it empties the bar)
 *
 * There is no cooldown state, because there is no cooldown: firing spends the
 * bar and the bar refills by playing. That was a deliberate decision in
 * `server/app/ultimates.py` and this panel is where it becomes visible — a
 * timer would need a sixth treatment saying "wait", and what this says
 * instead is "go and earn it".
 *
 * THE LOCK EXPLAINS ITSELF ON HOVER AND NOWHERE ELSE. A permanent requirement
 * list would be three more lines of text in the corner the player is fighting
 * toward, for a question that is asked once per build and then never again.
 * The panel says LOCKED at all times and says WHY when asked.
 */

import { useRef, useState } from 'react';
import type { HudUltimate } from '../../game/hud-store';
import { cn } from '@/lib/utils';
import { HoverCard, type HoverAnchor } from './HoverCard';
import { Panel } from './Panel';
import { UltimateIcon } from './UltimateIcon';

export interface UltimateProps {
  ultimate: HudUltimate | null;
}

export function Ultimate({ ultimate }: UltimateProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<HoverAnchor | null>(null);

  // NO PANEL AT ALL for a weapon with no ultimate, rather than an empty one
  // saying so. This is the opposite call to the armour panel's empty rows and
  // the skill tray's "nenhuma", and the difference is what the absence MEANS:
  // a bare armour slot is a hole in you, and a knife having no ultimate is not
  // a gap in anything — it is simply what a knife is. A permanent "—" over the
  // belt would be the HUD apologising for the weapon.
  if (!ultimate) return null;

  const active = ultimate.active > 0;
  const state = ultimate.locked ? 'locked' : ultimate.ready || active ? 'ready' : 'charging';
  // ACTIVE DRAINS AND EVERYTHING ELSE FILLS, and it is the same bar. One meter
  // that runs both ways is what makes the window read as the ultimate being
  // SPENT rather than as a second, unrelated timer appearing somewhere.
  const fill = active
    ? ultimate.active / Math.max(0.001, ultimate.duration)
    : ultimate.charge;

  return (
    <>
      <div
        ref={ref}
        // The mouse is taken back PER PANEL here, unlike the belt's per-cell
        // rule, because this panel is one thing — there is no empty cell in it
        // to leave transparent, and the whole rectangle is the hover target
        // for the one card it has.
        className="pointer-events-auto cursor-help"
        onPointerEnter={() => {
          const el = ref.current;
          if (!el) return;
          const box = el.getBoundingClientRect();
          setAnchor({ x: box.left + box.width / 2, top: box.top, bottom: box.bottom });
        }}
        onPointerLeave={() => setAnchor(null)}
      >
        <Panel
          className={cn(
            'w-44 px-2.5 py-2 transition-shadow duration-200 motion-reduce:transition-none',
            // THE RING IS THE ACTIVE STATE and it is on the PANEL rather than
            // on the icon, because what is active is not the mark — it is the
            // weapon in your hands, for the next few seconds, and the whole
            // rectangle going hot is the closest this HUD gets to saying so.
            active && 'shadow-[0_0_0_1px_var(--ult-flash),0_0_12px_-2px_var(--ult-flash)]',
          )}
          // Replayed on every activation: remounting is what restarts the
          // keyframe, exactly the way the belt replays its pick animation.
          key={ultimate.fires}
        >
          <div className="flex items-center gap-2">
            <UltimateIcon frame={ultimate.frame} state={state} zoom={1.6} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span
                className={cn(
                  'truncate text-[11px] leading-[11px] tracking-[0.04em]',
                  ultimate.locked
                    ? 'text-ink-muted'
                    : ultimate.ready || active
                      ? 'text-ink-accent'
                      : 'text-ink',
                )}
              >
                {/* THE PADLOCK IS PART OF THE NAME, not a badge beside it. At
                    eleven pixels a separate glyph is another thing to find;
                    prefixed, the state is read in the same saccade as the
                    name. */}
                {ultimate.locked ? `🔒 ${ultimate.name}` : ultimate.name}
              </span>
              <Status ultimate={ultimate} active={active} />
            </div>
          </div>

          <Meter
            fill={fill}
            locked={ultimate.locked}
            ready={ultimate.ready}
            active={active}
          />
        </Panel>
      </div>

      {anchor ? (
        <HoverCard anchor={anchor} fitKey={`${ultimate.key}-${ultimate.locked}`}>
          <Card ultimate={ultimate} />
        </HoverCard>
      ) : null}
    </>
  );
}

/**
 * The one line under the name, and it says a different thing in every state.
 *
 * It is deliberately NOT a percentage while charging. A player watching a bar
 * fill does not need the number — the bar is the number — and "62%" beside a
 * bar that is 62% full is the HUD saying the same thing twice in a corner that
 * has no room for it. What the line spends itself on instead is the WEAPON's
 * name, which is the fact a player still needs while learning that this panel
 * follows their hand.
 */
function Status({ ultimate, active }: { ultimate: HudUltimate; active: boolean }) {
  if (active) {
    return (
      <span className="text-ink-accent text-[10px] leading-[10px] tabular-nums">
        ATIVA · {ultimate.active.toFixed(1)}s
      </span>
    );
  }
  if (ultimate.locked) {
    // THE COUNT AND NOT THE NAMES. "1 requisito" fits; "Lâmina, Conjunto
    // Sombra" does not, and a truncated requirement is worse than a number
    // pointing at a hover that has room for the whole list.
    const missing = ultimate.requirements.filter((row) => !row.met).length;
    return (
      <span className="text-ink-muted text-[10px] leading-[10px]">
        {missing === 1 ? 'falta 1 requisito' : `faltam ${missing} requisitos`}
      </span>
    );
  }
  if (ultimate.ready) {
    return (
      <span className="text-ink-accent text-[10px] leading-[10px] tracking-[0.08em]">
        PRONTA · R
      </span>
    );
  }
  return (
    <span className="text-ink-muted truncate text-[10px] leading-[10px]">
      {ultimate.weapon}
    </span>
  );
}

/**
 * The bar. Same footprint in every state, because a panel that changed height
 * as it charged would move the belt under it — and the belt is the one thing
 * on this screen that must never move.
 */
function Meter({
  fill,
  locked,
  ready,
  active,
}: {
  fill: number;
  locked: boolean;
  ready: boolean;
  active: boolean;
}) {
  const clamped = Math.min(1, Math.max(0, fill));
  return (
    <div
      className={cn(
        'border-track-border bg-track relative mt-1.5 h-1.5 overflow-hidden border',
        // A LOCKED TRACK IS HOLLOW, exactly as a bare armour slot is, and for
        // the same reason: "nothing is happening here" and "something here has
        // run out" are different sentences and the player has to be able to
        // tell them apart without reading a word.
        locked && 'opacity-35',
      )}
    >
      <div
        className={cn(
          'h-full shadow-[inset_0_-1px_0_var(--meter-shade)]',
          // 120ms, the same as the armour bars. It is short enough that a
          // full minigun burst still reads as continuous growth and long
          // enough that the 5 Hz republish does not arrive as five steps.
          'transition-[width] duration-[120ms] ease-linear',
          'motion-reduce:transition-none',
          ready || active ? 'bg-ink-accent' : 'bg-neutral',
        )}
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  );
}

/**
 * The hover card: what it does, and every requirement with a tick or a cross.
 *
 * THE LIST IS SHOWN EVEN WHEN EVERY ROW IS MET. A list that vanished on
 * success would teach this system to exactly one player — the one who was
 * looking at it while it was still locked — and the second person in the party
 * would never find out that their armour is what unlocked their katana.
 */
function Card({ ultimate }: { ultimate: HudUltimate }) {
  return (
    <div className="flex w-max max-w-[15rem] flex-col gap-1">
      <div className="flex flex-col">
        <span className={ultimate.locked ? 'text-ink-muted' : 'text-ink-accent'}>
          {ultimate.locked ? `🔒 ${ultimate.name}` : `⚡ ${ultimate.name}`}
        </span>
        <span className="text-ink-muted">Ultimate · {ultimate.weapon}</span>
      </div>

      {/* WHAT IT DOES, in a sentence, and it comes off the catalog rather than
          out of this file — the same rule a skill's blurb keeps. A component
          that knew what an ultimate does would be a second place to describe
          one, and the server's would be the one nobody updated. */}
      <p className="border-track-border text-ink mt-0.5 border-t pt-1 whitespace-normal">
        {ultimate.blurb}
      </p>

      <div className="border-track-border mt-0.5 flex flex-col border-t pt-1">
        <span className="text-ink-muted mb-0.5">requer:</span>
        {ultimate.requirements.map((row) => (
          <p key={row.tag} className="flex justify-between gap-4">
            <span className={row.met ? 'text-ink' : 'text-hp-low'}>
              {row.met ? '✓' : '✗'} {row.label}
            </span>
            {/* THE COUNT ONLY ON THE ROWS THAT HAVE ONE. A weapon requirement
                is true or false — you are holding it or you are not — and
                printing "1/1" beside a katana would invent a progress bar for
                a binary. An armour requirement is two of three, and hiding
                that number is what would make "get the set" read as an
                all-or-nothing wall rather than as one more helmet. */}
            {row.need === undefined ? null : (
              <span
                className={cn('tabular-nums', row.met ? 'text-ink-muted' : 'text-ink-muted')}
              >
                {row.have} / {row.need}
              </span>
            )}
          </p>
        ))}
      </div>

      {ultimate.locked ? null : (
        <p className="border-track-border text-ink-muted mt-0.5 border-t pt-1">
          {ultimate.ready ? 'pressione R' : 'carrega lutando com esta arma'}
        </p>
      )}
    </div>
  );
}
