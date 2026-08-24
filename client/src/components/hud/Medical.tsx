/**
 * THE MEDICAL BELT: the cells on the keys straight after the weapons, and the
 * only way health comes back.
 *
 * It sits beside the weapon belt and is deliberately NOT part of it. The two
 * strips answer different questions and reward different reflexes: a belt key
 * swaps what is in your hands, costs nothing and is instant; a medical key
 * SPENDS something and plants the body for seconds. Rendering them as one row
 * would make the last weapon and the first kit neighbours on a strip, which is
 * exactly how a kit gets burned by somebody reaching for the knife.
 *
 * THE CELLS ARE THE BELT'S CELLS. Same box, same size, same key number in the
 * same corner — because they ARE the same gesture, a number key that puts
 * something in play, and two panels stacked in one corner drawing the same
 * gesture at two different sizes reads as two unrelated systems. What keeps
 * them apart is the gap and the label, not the geometry.
 *
 * EMPTY CELLS ARE DRAWN, AND THAT IS THE WHOLE PANEL.
 *
 * The bag renders gaps because a gap there means "there is room". An empty
 * medical cell means something else entirely — "you have one left" — and with
 * a run that does not come back, that is the most important number on the
 * glass after the health bar. So every cell is always there, an empty one is
 * a visibly empty socket rather than an absence, and the count is legible
 * without anybody having to add up what is present.
 *
 * THE CELL BEING SPENT FILLS AS IT GOES. The same 0..1 the ring over the body
 * runs on, so the two cannot disagree, and it fills from the bottom like
 * something draining into you. It is the cell rather than a separate bar
 * because what the player wants to know mid-heal is not "how long" — they can
 * see that on their own body — it is WHICH ONE IS GOING, and with cells that
 * look alike that question needs answering where the cells are.
 *
 * WHAT IT HEALS IS ON THE CELL, where a gun's rounds are. The duration is not:
 * it is drawn, once per use, as the fill — and the two numbers competing for
 * the same 40px box is what made the old cells twice the size of everything
 * else in the corner.
 */

import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { HudMedical, HudMedicalSlot } from '../../game/hud-store';
import { writeInventoryAnchor, dropInventoryAnchor } from '../../game/inventory-anchors';
import { incomingCount, subscribeLootFlies } from '../../game/loot-flies';
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
      <div className="flex items-center gap-1.5">
        {medical.slots.map((slot, index) => (
          <MedicalCell
            key={index}
            index={index}
            slot={slot}
            progress={medical.using === index ? medical.progress : 0}
          />
        ))}
      </div>
    </Panel>
  );
}

function MedicalCell({
  index,
  slot,
  progress,
}: {
  index: number;
  slot: HudMedicalSlot;
  progress: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // A kit in the air IS the sprite: the cell stays empty until the fly lands,
  // exactly as a belt cell does. See `loot-flies.anchorFor`.
  const incoming = useSyncExternalStore(
    subscribeLootFlies,
    () => incomingCount(index, 'med'),
    () => 0,
  );
  const filled = slot.key !== null && incoming <= 0;
  const spending = progress > 0;

  useEffect(() => {
    const el = ref.current;
    const id = `medical-${index}`;
    if (!el) {
      dropInventoryAnchor(id);
      return;
    }
    let raf = 0;
    const tick = () => {
      const box = el.getBoundingClientRect();
      if (box.width >= 8 && box.height >= 8) {
        writeInventoryAnchor(id, box.left + box.width / 2, box.top + box.height / 2);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      dropInventoryAnchor(id);
    };
  }, [index]);

  return (
    <div
      ref={ref}
      className={cn(
        'relative size-10 overflow-hidden border bg-panel-inset shadow-[inset_0_0_0_1px_var(--surface)]',
        filled ? 'border-rarity-uncommon/70' : 'border-track-border',
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

      {filled ? (
        <LootIcon
          frame={slot.frame}
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
        />
      ) : (
        // An empty socket, not a blank. A cross with nothing in it reads as
        // "this held medicine and does not", which is the sentence that
        // matters; an empty box reads as decoration.
        <span
          aria-hidden
          className="text-ink-muted/40 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[18px] leading-none"
        >
          +
        </span>
      )}

      <span className="text-ink-muted absolute top-px left-0.5 text-[11px] leading-[11px] tabular-nums">
        {slot.hotkey}
      </span>
      {filled ? (
        <span className="text-ink-muted absolute right-0.5 bottom-px text-[11px] leading-[11px] tabular-nums">
          +{slot.heal}
        </span>
      ) : null}
    </div>
  );
}
