/**
 * What is between this body and the next blow: three worn parts, and the
 * shield when there is one.
 *
 * DIRECTLY ABOVE THE VITALS, because it answers the same question the health
 * bar answers, one layer further out — and because the two are read together
 * or not at all. A player glancing here wants one thing: am I still covered.
 *
 * THREE ROWS, ALWAYS, INCLUDING THE BARE ONES. A panel that only listed what
 * you owned would be empty for the first half of most runs and would change
 * height every time something broke, which is the worst possible moment for
 * the HUD to move. The empty rows are the information: they are the parts a
 * blow can land on with nothing in the way, and their order is the body's —
 * head, chest, legs, top to bottom, the way you look at a person.
 *
 * THE BARS ARE THIN AND THE NUMBERS ARE ABSENT. Durability is not a resource
 * you spend on purpose, it is a thing you notice — so the row reads as a
 * silhouette of how much is left rather than as a counter to do arithmetic
 * on. The one number that would matter, "how many more hits", is not knowable
 * anyway: it depends on what is hitting you.
 *
 * HOVERING A ROW SAYS WHAT IS ON THAT PART. The panel is deliberately terse —
 * a slot, a material and a bar — and terse is only honest if the detail is one
 * gesture away. It is the same card the belt hovers and the shop shows,
 * because it is the same object: somebody can pick up a pair of steel greaves
 * and never find out what they did, and that is the hole this closes.
 */

import { useEffect, useRef, useState } from 'react';
import type { HudArmor, HudArmorSlot, HudShield } from '../../game/hud-store';
import { writeInventoryAnchor, dropInventoryAnchor } from '../../game/inventory-anchors';
import type { HudGearCard } from '../../game/gear-card';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { GearCardBody } from './GearCard';
import { HoverCard, type HoverAnchor } from './HoverCard';
import { Panel } from './Panel';

export interface ArmorProps {
  armor: HudArmor | null;
}

/**
 * The fill, by MATERIAL rather than by how full the bar is.
 *
 * A meter that ramped from green to red as it wore down would be saying "this
 * is getting dangerous", and it is not — a cracked steel plate still stops
 * more than a fresh cloth one. What the colour is for is the LADDER: the
 * player learns "green is leather" in one pickup and then never has to read a
 * name again. Full class strings so Tailwind's scanner sees every variant.
 */
const MATERIAL_FILL: Record<LootRarity, string> = {
  common: 'bg-rarity-common',
  uncommon: 'bg-rarity-uncommon',
  rare: 'bg-rarity-rare',
  epic: 'bg-rarity-epic',
  legendary: 'bg-rarity-legendary',
};

const MATERIAL_TEXT: Record<LootRarity, string> = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

interface HoverState {
  card: HudGearCard;
  frame?: number;
  anchor: HoverAnchor;
}

export function Armor({ armor }: ArmorProps) {
  const [hover, setHover] = useState<HoverState | null>(null);

  if (!armor) return null;

  return (
    <Panel className="w-40 px-2.5 py-2">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted tracking-[0.06em]">ARMADURA</span>
        {/*
          DAMAGE the set takes off a walker's claw, as one number. It is the
          only arithmetic worth doing for the player — three plates each
          answering the blows that land on their own part — and it is in
          damage points rather than as a percentage because this sits directly
          above a health bar counted in the same units. `-5` next to `100` is
          a sentence; `56%` next to `100` is two unrelated numbers.
        */}
        <span className="text-ink tabular-nums">{armor.armor}</span>
      </div>

      <div className="flex flex-col gap-1.5">
        {armor.slots.map((slot, index) => (
          <ArmorRow
            key={slot.slot}
            slot={slot}
            index={index}
            onHover={(card, anchor) => setHover({ card, anchor })}
            onLeave={() => setHover(null)}
          />
        ))}
      </div>

      {/*
        THE SHIELD SITS UNDER THE PLATES, SEPARATED. It lives on the belt, not
        on the body, and it does something categorically different — it stops
        a blow rather than taking a share of it — so it is on this panel
        (because the question is "what is between me and the next hit") but
        never in the same list.
      */}
      {armor.shield ? (
        <ShieldRow
          shield={armor.shield}
          onHover={(card, anchor) => setHover({ card, anchor })}
          onLeave={() => setHover(null)}
        />
      ) : null}

      {/*
        ONE CARD FOR THE WHOLE PANEL rather than one per row. Only one row can
        be under the pointer, and four portals racing to place themselves at
        the same corner of the screen is four measurements of the same
        viewport.
      */}
      {hover ? (
        <HoverCard anchor={hover.anchor} fitKey={hover.card.key}>
          <GearCardBody card={hover.card} frame={hover.frame} />
        </HoverCard>
      ) : null}
    </Panel>
  );
}

/**
 * The shield's row. Under the plates and separated by a rule, because it
 * lives on the belt rather than on the body and does something categorically
 * different — it stops a blow rather than taking a share of one. It is on
 * this panel at all because the question a player asks here is "how much is
 * between me and the next hit", and the answer includes the thing in their
 * hand.
 */
function ShieldRow({
  shield,
  onHover,
  onLeave,
}: {
  shield: HudShield;
  onHover: (card: HudGearCard, anchor: HoverAnchor) => void;
  onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={ref}
      className={cn(
        'mt-2 border-track-border border-t pt-2',
        shield.card ? 'pointer-events-auto cursor-pointer' : null,
      )}
      onPointerEnter={() => {
        const el = ref.current;
        if (!el || !shield.card) return;
        const box = el.getBoundingClientRect();
        onHover(shield.card, { x: box.left + box.width / 2, top: box.top, bottom: box.bottom });
      }}
      onPointerLeave={onLeave}
    >
          <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
            <span
              className={cn(
                'truncate tracking-[0.04em]',
                // UP is the whole state, and it is the one thing on this panel
                // that changes on a mouse button rather than over a night. The
                // raised shield takes the accent; the lowered one is as quiet
                // as a bare row.
                shield.up ? 'text-ink-accent' : 'text-ink-muted',
              )}
            >
              {shield.up ? 'ESCUDO ▲' : 'ESCUDO'}
            </span>
            <span className="text-ink-muted shrink-0 tabular-nums">
              {Math.max(0, Math.round((shield.hp / Math.max(1, shield.maxHp)) * 100))}%
            </span>
          </div>
      <Bar
        ratio={shield.hp / Math.max(1, shield.maxHp)}
        fill={shield.up ? 'bg-ink-accent' : 'bg-neutral'}
      />
    </div>
  );
}

function ArmorRow({
  slot,
  index,
  onHover,
  onLeave,
}: {
  slot: HudArmorSlot;
  index: number;
  onHover: (card: HudGearCard, anchor: HoverAnchor) => void;
  onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  // The fly target for a plate picked up or bought. Same contract as a bag
  // cell's anchor — see `HotbarSlot` — and the index is the position in
  // `config.armorSlots`, which is what `dest: "worn"` carries.
  useEffect(() => {
    const el = ref.current;
    const id = `armor-${index}`;
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

  const rarity = slot.rarity;
  const ratio = slot.maxHp > 0 ? slot.hp / slot.maxHp : 0;

  return (
    <div
      ref={ref}
      data-armor-slot={slot.slot}
      // A BARE ROW IS NOT HOVERABLE. There is nothing to describe, and a card
      // that said "nothing" is a card the player learns to dismiss. It also
      // keeps the mouse with the canvas everywhere the panel has no answer —
      // see `HotbarSlot`.
      className={cn(slot.card ? 'pointer-events-auto cursor-pointer' : null)}
      onPointerEnter={() => {
        const el = ref.current;
        if (!el || !slot.card) return;
        const box = el.getBoundingClientRect();
        onHover(slot.card, { x: box.left + box.width / 2, top: box.top, bottom: box.bottom });
      }}
      onPointerLeave={onLeave}
    >
      <div className="mb-0.5 flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
        <span className="text-ink-muted shrink-0 tracking-[0.04em]">{slot.label}</span>
        {/*
          The MATERIAL, not the piece's full name: "couro" fits, "Jaqueta de
          couro" does not, and the material is the half that carries the
          numbers. The slot's own label on the left already says which piece
          this is.
        */}
        <span
          className={cn('truncate', rarity ? MATERIAL_TEXT[rarity] : 'text-ink-muted opacity-50')}
        >
          {slot.material ?? '—'}
        </span>
      </div>
      <Bar ratio={ratio} fill={rarity ? MATERIAL_FILL[rarity] : 'bg-neutral'} bare={!slot.key} />
    </div>
  );
}

function Bar({ ratio, fill, bare = false }: { ratio: number; fill: string; bare?: boolean }) {
  const clamped = Math.min(1, Math.max(0, ratio));
  return (
    <div
      className={cn(
        'border-track-border bg-track relative h-1.5 overflow-hidden border',
        // A bare part is a hollow track, not a zeroed bar. Same footprint, no
        // fill, and half the contrast — it reads as "nothing here" rather than
        // as "something here that has run out", which are different sentences
        // and the player has to be able to tell them apart at a glance.
        bare && 'opacity-40',
      )}
    >
      <div
        className={cn(
          'h-full shadow-[inset_0_-1px_0_var(--meter-shade)]',
          'transition-[width] duration-[120ms] ease-linear',
          'motion-reduce:transition-none',
          fill,
        )}
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  );
}

