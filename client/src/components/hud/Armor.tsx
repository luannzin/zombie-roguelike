/**
 * WHAT THIS BODY IS WEARING — as a body, not as a list.
 *
 * This panel used to be three labelled rows with thin meters beside them:
 * CABEÇA / TRONCO / PERNAS, a material name, a bar. Every number on it was
 * true and the whole thing was still wrong, because armour in this game is
 * OBJECTS — a helmet, a pair of bracers, a breastplate, trousers, boots — and
 * what it read as was three sliders. A player could pick up a pair of steel
 * greaves, put them on, and never once see greaves.
 *
 * So there are five slots now and they are drawn as a FIGURE:
 *
 *        [ ]        the helmet
 *     [ ][ ][ ]     a bracer, the breastplate, the other bracer
 *        [ ]        the trousers
 *        [ ]        the boots
 *
 * The counts are the silhouette. One box, then three, then one, then one, is a
 * person seen from the front — and a hole in it is a part of you that the next
 * blow can land on with nothing in the way, which is a far louder sentence
 * than an empty row was. The shape is not decided here: it comes off
 * `config.armorBodyLayout`, so a sixth slot is a row in `armor.py` and a shape
 * in two generators, and this file does not change.
 *
 * ONLY THE ARMS ARE A PAIR. The legs and the boots were drawn as two boxes as
 * well, on the argument that they are pairs on a body — and what that produced
 * was four rows of doubles where the widest part of the figure was not the
 * shoulders. The arms are the only part of a person that sticks out sideways,
 * so they are the only part that is two boxes wide. Both of their boxes hover
 * the same card, because they are the same object.
 *
 * IT IS COLLAPSED BY DEFAULT, LIKE THE BAG, AND C EXPANDS IT
 * ==========================================================
 * The two drawers are deliberately separate keys: the bag answers "what am I
 * carrying out" and this answers "what is keeping me alive", and folding them
 * into one toggle would make a player checking their helmet look at their loot
 * as well, in the corner of the screen they are fighting toward.
 *
 * COLLAPSED IS NOT EMPTY. It still says the SET, the rating and how much of
 * the body is covered, because "am I still protected" has to be answerable
 * without a keypress — that was the old panel's one genuine virtue and losing
 * it would have been a bad trade. What expanding buys is WHICH piece and WHAT
 * it is, which is a question you ask between fights.
 *
 * THE LEFT COLUMN IS THE SET AND THE RIGHT IS THE BODY. The set is what a
 * player is BUILDING — it is what the ultimate panel's requirements count, and
 * "Sombra 3/5" is the same number in both places — and the mannequin is what
 * they currently HAVE. Reading left to right is reading the plan and then the
 * state of it.
 */

import { useEffect, useRef, useState } from 'react';
import type { HudArmor, HudArmorSlot, HudShield } from '../../game/hud-store';
import { writeInventoryAnchor, dropInventoryAnchor } from '../../game/inventory-anchors';
import type { HudGearCard } from '../../game/gear-card';
import type { LootRarity } from '../../net/protocol';
import { cn } from '@/lib/utils';
import { GearCardBody } from './GearCard';
import { HoverCard, type HoverAnchor } from './HoverCard';
import { LootIcon } from './LootIcon';
import { Panel } from './Panel';
import { TooltipKey } from './Tooltip';

export interface ArmorProps {
  armor: HudArmor | null;
}

/**
 * The fill and the text, by MATERIAL rather than by how full a bar is.
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

const MATERIAL_BORDER: Record<LootRarity, string> = {
  common: 'border-rarity-common',
  uncommon: 'border-rarity-uncommon',
  rare: 'border-rarity-rare',
  epic: 'border-rarity-epic',
  legendary: 'border-rarity-legendary',
};

interface HoverState {
  card: HudGearCard;
  frame?: number;
  anchor: HoverAnchor;
}

export function Armor({ armor }: ArmorProps) {
  const [hover, setHover] = useState<HoverState | null>(null);

  if (!armor) return null;

  const onHover = (card: HudGearCard, anchor: HoverAnchor, frame?: number) =>
    setHover({ card, anchor, frame });
  const onLeave = () => setHover(null);

  const rows = groupRows(armor.slots);

  return (
    <div className="flex flex-col items-end gap-1.5">
      <Panel className="w-44 px-2.5 py-2">
        {/*
          THE HEADER IS THE COLLAPSED PANEL, and it stays exactly where it is
          when the drawer opens. That is the whole reason it is outside the
          animated box below: the one number a player glances at mid-fight —
          what a blow costs them — must not move a pixel because they happened
          to press C.
        */}
        <div className="flex items-baseline justify-between gap-2 text-[11px] leading-[11px]">
          <span className="text-ink-muted tracking-[0.06em]">ARMADURA</span>
          <div className="flex items-baseline gap-1.5">
            {/*
              DAMAGE the set takes off a blow, as one number. It is the only
              arithmetic worth doing for the player — each plate answering the
              blows that land on its own part — and it is in damage points
              rather than as a percentage because this sits directly above a
              health bar counted in the same units. `-5` next to `100` is a
              sentence; `56%` next to `100` is two unrelated numbers.
            */}
            <span className="text-ink tabular-nums">{armor.armor}</span>
            <span aria-hidden className="text-ink-muted">
              ▸
            </span>
            <TooltipKey>C</TooltipKey>
          </div>
        </div>

        {/*
          THE SET, ON THE COLLAPSED PANEL TOO. "Sombra 3/5" is the sentence the
          ultimate panel is counting against, and a player deciding whether the
          helmet on the shop table is worth buying needs it without opening a
          drawer.
        */}
        <SetLine set={armor.set} />

        <div
          className="mt-1.5 grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none"
          style={{ gridTemplateRows: armor.open ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="border-track-border flex items-start gap-2 border-t pt-2">
              {/* THE BODY. Right-hand column, because the panel is
                  right-aligned and the figure is the thing the eye should
                  land on first coming in from the screen edge. */}
              <div className="flex flex-1 flex-col items-center gap-1">
                {rows.map((row, index) => (
                  <div key={index} className="flex items-center gap-1">
                    {row.map((cell, position) => (
                      <ArmorCell
                        key={`${cell.slot.slot}-${position}`}
                        slot={cell.slot}
                        index={cell.index}
                        // ONLY THE FIRST BOX OF A PAIR PUBLISHES THE ANCHOR.
                        // A collect fly aims at one point, and two boxes
                        // racing to write the same id would make the sprite
                        // land on whichever of a player's arms rendered last.
                        anchored={cell.anchored}
                        onHover={onHover}
                        onLeave={onLeave}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>

            {/*
              THE SHIELD SITS UNDER THE FIGURE, SEPARATED. It lives on the
              belt, not on the body, and it does something categorically
              different — it stops a blow rather than taking a share of it — so
              it is on this panel (because the question is "what is between me
              and the next hit") but never in the mannequin.
            */}
            {armor.shield ? (
              <ShieldRow shield={armor.shield} onHover={onHover} onLeave={onLeave} />
            ) : null}
          </div>
        </div>
      </Panel>

      {/*
        ONE CARD FOR THE WHOLE PANEL rather than one per cell. Only one cell can
        be under the pointer, and nine portals racing to place themselves at the
        same corner of the screen is nine measurements of the same viewport.
      */}
      {hover ? (
        <HoverCard anchor={hover.anchor} fitKey={hover.card.key}>
          <GearCardBody card={hover.card} frame={hover.frame} />
        </HoverCard>
      ) : null}
    </div>
  );
}

/**
 * "SOMBRA 3/5", or a muted line when there is nothing on.
 *
 * NAMED EVEN WHEN THE SET IS PARTIAL, and the count is what makes that honest:
 * three of five leather pieces IS wearing Sombra as far as every rule in the
 * game is concerned (`ultimates.SET_PIECES`), and a header that only appeared
 * at five would hide the exact threshold the player is being asked to reach.
 */
function SetLine({ set }: { set: HudArmor['set'] }) {
  if (!set.name || set.pieces <= 0) {
    return (
      <p className="text-ink-muted/60 mt-1 text-[10px] leading-[10px]">sem conjunto</p>
    );
  }
  return (
    <p className="mt-1 flex items-baseline justify-between gap-2 text-[10px] leading-[10px]">
      <span className={cn('truncate tracking-[0.04em]', set.rarity ? MATERIAL_TEXT[set.rarity] : 'text-ink')}>
        {set.name.toUpperCase()}
      </span>
      <span className="text-ink-muted shrink-0 tabular-nums">
        {set.pieces} / {set.total}
      </span>
    </p>
  );
}

interface BodyCell {
  slot: HudArmorSlot;
  /** The slot's index in `config.armorSlots` — what a `worn` fly aims at. */
  index: number;
  anchored: boolean;
}

/**
 * The mannequin's rows, built from the layout the server ships.
 *
 * THE PAIR IS SPLIT AROUND THE SINGLE, which is the one piece of arrangement
 * this file decides for itself and it is a drawing decision rather than a data
 * one: a row holding a two-cell slot and a one-cell slot is a torso, and a
 * torso is arm / chest / arm. Everything else — which slots share a row, how
 * many boxes each gets — comes off `config.armorBodyLayout`.
 */
function groupRows(slots: HudArmorSlot[]): BodyCell[][] {
  const byRow = new Map<number, HudArmorSlot[]>();
  for (const slot of slots) {
    const list = byRow.get(slot.row);
    if (list) list.push(slot);
    else byRow.set(slot.row, [slot]);
  }
  return [...byRow.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, group]) => {
      const pairs = group.filter((slot) => slot.cells >= 2);
      const singles = group.filter((slot) => slot.cells < 2);
      const cell = (slot: HudArmorSlot, anchored: boolean): BodyCell => ({
        slot,
        index: slots.indexOf(slot),
        anchored,
      });
      return [
        ...pairs.map((slot) => cell(slot, true)),
        ...singles.map((slot) => cell(slot, true)),
        ...pairs.map((slot) => cell(slot, false)),
      ];
    });
}

/**
 * One box on the figure: the piece's own sprite, its material's border, and a
 * hairline of durability under it.
 *
 * THE DURABILITY IS A LINE ACROSS THE BOTTOM OF THE BOX rather than a bar
 * beside it. It is not a resource you spend on purpose, it is a thing you
 * notice — so it belongs ON the object, the way wear belongs on an object, and
 * it costs the layout two pixels instead of a row.
 */
function ArmorCell({
  slot,
  index,
  anchored,
  onHover,
  onLeave,
}: {
  slot: HudArmorSlot;
  index: number;
  anchored: boolean;
  onHover: (card: HudGearCard, anchor: HoverAnchor, frame?: number) => void;
  onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  // The fly target for a plate picked up or bought. Same contract as a bag
  // cell's anchor — see `HotbarSlot` — and the index is the position in
  // `config.armorSlots`, which is what `dest: "worn"` carries.
  useEffect(() => {
    const el = ref.current;
    const id = `armor-${index}`;
    if (!el || !anchored) return;
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
  }, [index, anchored]);

  const rarity = slot.rarity;
  const ratio = slot.maxHp > 0 ? slot.hp / slot.maxHp : 0;

  return (
    <div
      ref={ref}
      data-armor-slot={slot.slot}
      title={slot.name ?? slot.label}
      className={cn(
        'bg-panel-inset relative size-7 border shadow-[inset_0_0_0_1px_var(--surface)]',
        rarity ? MATERIAL_BORDER[rarity] : 'border-track-border',
        // A BARE BOX IS HOLLOW, not zeroed. Half the contrast and nothing in
        // it, so it reads as "nothing here" rather than as "something here
        // that has run out" — two different sentences, and the player has to
        // be able to tell them apart at a glance.
        !slot.key && 'opacity-45',
        // A BARE BOX IS NOT HOVERABLE. There is nothing to describe, and a
        // card that said "nothing" is a card the player learns to dismiss. It
        // also keeps the mouse with the canvas everywhere the panel has no
        // answer — see `HotbarSlot`.
        slot.card ? 'pointer-events-auto cursor-pointer' : null,
      )}
      onPointerEnter={() => {
        const el = ref.current;
        if (!el || !slot.card) return;
        const box = el.getBoundingClientRect();
        onHover(
          slot.card,
          { x: box.left + box.width / 2, top: box.top, bottom: box.bottom },
          slot.frame ?? undefined,
        );
      }}
      onPointerLeave={onLeave}
    >
      {slot.frame === null ? null : (
        <LootIcon
          frame={slot.frame}
          zoom={1.5}
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
        />
      )}
      {slot.key ? (
        <span
          aria-hidden
          className={cn(
            'absolute inset-x-0 bottom-0 h-[2px] origin-left',
            'transition-transform duration-[120ms] ease-linear motion-reduce:transition-none',
            rarity ? MATERIAL_FILL[rarity] : 'bg-neutral',
          )}
          style={{ transform: `scaleX(${Math.min(1, Math.max(0, ratio))})` }}
        />
      ) : null}
    </div>
  );
}

/**
 * The shield's row. Under the figure and separated by a rule, because it lives
 * on the belt rather than on the body and does something categorically
 * different — it stops a blow rather than taking a share of one. It is on this
 * panel at all because the question a player asks here is "how much is between
 * me and the next hit", and the answer includes the thing in their hand.
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
        'border-track-border mt-2 border-t pt-2',
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
            // raised shield takes the accent; the lowered one is as quiet as a
            // bare box.
            shield.up ? 'text-ink-accent' : 'text-ink-muted',
          )}
        >
          {shield.up ? 'ESCUDO ▲' : 'ESCUDO'}
        </span>
        <span className="text-ink-muted shrink-0 tabular-nums">
          {Math.max(0, Math.round((shield.hp / Math.max(1, shield.maxHp)) * 100))}%
        </span>
      </div>
      <div className="border-track-border bg-track relative h-1.5 overflow-hidden border">
        <div
          className={cn(
            'h-full shadow-[inset_0_-1px_0_var(--meter-shade)]',
            'transition-[width] duration-[120ms] ease-linear motion-reduce:transition-none',
            shield.up ? 'bg-ink-accent' : 'bg-neutral',
          )}
          style={{
            width: `${Math.min(100, Math.max(0, (shield.hp / Math.max(1, shield.maxHp)) * 100))}%`,
          }}
        />
      </div>
    </div>
  );
}
