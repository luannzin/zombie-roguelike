/**
 * THE MEDICAL BELT: two cells, on 4 and 5, and the only way health comes back.
 *
 * It sits beside the weapon belt and is deliberately NOT part of it. The two
 * strips answer different questions and reward different reflexes: a belt key
 * swaps what is in your hands, costs nothing and is instant; a medical key
 * SPENDS something and plants the body for seconds. Rendering them as one row
 * of five would make 3 and 4 neighbours on a strip, which is exactly how a kit
 * gets burned by somebody reaching for the knife.
 *
 * EMPTY CELLS ARE DRAWN, AND THAT IS THE WHOLE PANEL.
 *
 * The bag renders gaps because a gap there means "there is room". An empty
 * medical cell means something else entirely — "you have one left" — and with
 * a run that does not come back, that is the most important number on the
 * glass after the health bar. So both cells are always there, an empty one is
 * a visibly empty socket rather than an absence, and the count is legible
 * without anybody having to add up what is present.
 *
 * THE CELL BEING SPENT FILLS AS IT GOES. The same 0..1 the ring over the body
 * runs on, so the two cannot disagree, and it fills from the bottom like
 * something draining into you. It is the cell rather than a separate bar
 * because what the player wants to know mid-heal is not "how long" — they can
 * see that on their own body — it is WHICH ONE IS GOING, and with two cells
 * that look alike that question needs answering where the cells are.
 *
 * No hover card. The two kits are described by two numbers each — what they
 * heal and how long they take — and both are printed on the cell, because they
 * are the entire decision and re-reading them is something the player does
 * mid-fight rather than at leisure.
 */

import type { HudMedical, HudMedicalSlot } from '../../game/hud-store';
import { Panel } from './Panel';
import { LootIcon } from './LootIcon';
import { cn } from '@/lib/utils';

export interface MedicalProps {
  medical: HudMedical | null;
}

export function Medical({ medical }: MedicalProps) {
  if (!medical) return null;

  return (
    <Panel className="w-44 px-2.5 py-2">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">REMÉDIOS</span>
        <span className="text-ink-muted tabular-nums">
          {medical.slots.map((slot) => slot.hotkey).join(' ')}
        </span>
      </div>
      <div className="flex items-stretch gap-1.5">
        {medical.slots.map((slot, index) => (
          <MedicalCell
            key={index}
            slot={slot}
            progress={medical.using === index ? medical.progress : 0}
          />
        ))}
      </div>
    </Panel>
  );
}

function MedicalCell({ slot, progress }: { slot: HudMedicalSlot; progress: number }) {
  const filled = slot.key !== null;
  const spending = progress > 0;

  return (
    <div
      className={cn(
        'relative flex min-w-0 flex-1 flex-col items-center gap-0.5 overflow-hidden border px-1 py-1',
        filled ? 'border-rarity-uncommon/70 bg-panel-inset' : 'border-track-border bg-track',
      )}
    >
      {/*
        The drain. Under the icon and over the ground, rising from the bottom —
        a kit going INTO you rather than a bar counting down beside you. It is
        the same 0..1 the ring over the body uses.
      */}
      {spending ? (
        <span
          aria-hidden
          className="bg-rarity-uncommon/30 pointer-events-none absolute inset-x-0 bottom-0"
          style={{ height: `${Math.round(progress * 100)}%` }}
        />
      ) : null}

      <span className="relative flex h-7 w-7 items-center justify-center">
        {filled ? (
          <LootIcon frame={slot.frame} zoom={1.6} />
        ) : (
          // An empty socket, not a blank. A cross with nothing in it reads as
          // "this held medicine and does not", which is the sentence that
          // matters; an empty box reads as decoration.
          <span aria-hidden className="text-ink-muted/40 text-[18px] leading-none">+</span>
        )}
      </span>

      <span
        className={cn(
          'relative text-[10px] leading-[10px] tabular-nums',
          filled ? 'text-ink' : 'text-ink-muted/50',
        )}
      >
        {filled ? `+${slot.heal}` : '—'}
      </span>
      <span className="text-ink-muted relative text-[9px] leading-[9px] tabular-nums">
        {filled ? `${slot.useTime.toFixed(1)}s` : slot.hotkey}
      </span>
    </div>
  );
}
