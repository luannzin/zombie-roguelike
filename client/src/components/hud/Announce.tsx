/**
 * The card for something that just happened TO YOU, mid-run.
 *
 * `ZoneTitle` is the same object one size up, and the two are deliberately
 * one language: rules drawing out from the centre, type coming into focus,
 * a second line held back a beat. What they do not share is the FRAME they
 * play into. An arrival owns the whole screen — the game is holding the
 * player still, the HUD corners are off the glass, and the card is the only
 * thing to read. This one lands while the player is walking, shooting, or
 * being chased, so every choice here is about being legible in a frame that
 * is already busy without stealing it:
 *
 *   SMALLER   24px against the title's 44px, and one rule instead of two.
 *             A full-size title over live gameplay reads as a cutscene that
 *             did not pause anything.
 *   HIGHER    upper third, not the middle. The middle is where the player's
 *             own body is and where they are aiming; a card there covers the
 *             one thing they cannot look away from.
 *   SHORTER   `ANNOUNCE_MS`, well under the arrival's three seconds — it is
 *             news, not an establishing shot. It reuses the `zone-*`
 *             keyframes at a shorter `animation-duration`, which is the
 *             convention those keyframes are written for: percentages, timed
 *             by the caller.
 *   NO SLASH  the bar crossing the arrival title is a title-sequence
 *             flourish. Firing it every time something happens would wear
 *             it out, and it is the one beat of that card nothing else has.
 *
 * It is a ONE-SHOT keyed on `announce.key`, exactly like `ZoneTitle`: the
 * store keeps the last one forever (nothing has to clear it), and a new key
 * remounts the card and replays it. So the key must change per event, not
 * per kind of event — `level-7`, not `level`.
 *
 * Everything is CSS keyframes on mount. React is never in the frame loop.
 *
 * `AnnounceDock` is the SECOND VARIANT: the same card, read at the same size,
 * that then FLIES INTO A HUD PANEL instead of fading where it stands. It
 * exists because a new objective is the same kind of news a level-up is — the
 * game telling you something changed — and the quest log used to announce it
 * in a plain 11px line of its own, a second visual language for one beat. The
 * fly is what says where the news went: the row the player will read for the
 * rest of the night is the thing the card turned into. Same argument as a
 * collect flying into the bag.
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { HUD_LENS, warpHudPoint } from '@/lib/lens';
import type { HudAnnounce } from '../../game/hud-store';

/** How long the card is on screen, in ms. */
export const ANNOUNCE_MS = 2200;

/**
 * Docked variant: how long the card is held before it travels. Shorter than
 * `ANNOUNCE_MS` — the fly is the second half of the beat, and the panel it
 * lands in keeps the words afterwards, so the card does not have to.
 */
export const DOCK_HOLD_MS = 1500;
/** Card → panel row. Same travel as a loot fly, with room for the arc. */
export const DOCK_TRAVEL_MS = 700;
/** Held here, not on the vertical centre — a task, not a title. */
const DOCK_Y = 0.2;
/**
 * WHERE THE `zone-*` KEYFRAMES ARE AT REST.
 *
 * Those tracks are a whole life — materialise, hold, leave — and every part
 * ends at `opacity: 0`. The in-place card wants that. This one MUST NOT have
 * it: the exit is the beat the fly replaces, and playing both means the words
 * evaporate on the launch frame and what travels to the panel is nothing at
 * all. So the docked card runs the same track stretched so its held pose
 * (72%) lands exactly on `DOCK_HOLD_MS`, and the animations are then killed
 * rather than allowed to reach the fade — from there the pose is ours, written
 * per frame.
 */
const HELD_AT = 0.72;
/** The subtitle is 13px; the row it becomes is 11px. */
const DOCK_LAND_SCALE = 11 / 13;
/** Held tracking of `zone-subtitle`, and the row's. The trip closes the gap. */
const HELD_TRACKING = 0.34;
const ROW_TRACKING = 0.08;

export interface AnnounceProps {
  announce: HudAnnounce | null;
}

export function Announce({ announce }: AnnounceProps) {
  const key = announce?.key ?? null;
  const [showing, setShowing] = useState<string | null>(key);

  useEffect(() => {
    if (!key) return;
    setShowing(key);
    const timer = window.setTimeout(() => setShowing(null), ANNOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [key]);

  if (!announce || showing !== key) return null;

  return (
    <div
      key={key}
      className="hud-layer inset-x-0 top-[26%] flex flex-col items-center"
      aria-hidden="true"
    >
      <AnnounceCard announce={announce} duration={ANNOUNCE_MS} />
    </div>
  );
}

export interface AnnounceDockProps {
  announce: HudAnnounce;
  /** The row the card becomes. Null until the panel has laid it out. */
  dock: HTMLElement | null;
  onLanded: () => void;
}

/**
 * The card, then a fly into `dock`.
 *
 * WHAT TRAVELS IS THE SUBTITLE — the objective itself — and nothing else.
 * The rule and the title are the frame the news arrived in; they are told
 * ("Novo Objetivo"), not carried, so they fade where they stand while the
 * line the player has to remember goes to the panel and becomes the row.
 * A whole card shrinking into a corner is a card being put away; one line
 * crossing the screen and landing in the log is the HUD being TOLD something.
 *
 * The trip is a MORPH, not a move: over the same 700ms the line loses the
 * subtitle's wide `0.34em` tracking for the row's `0.08em`, drops from 13px to
 * 11px, and trades the accent ink for the row's. It arrives already looking
 * like what it is about to be, so the handover to the real row is a crossfade
 * between two identical things.
 *
 * It flies STRAIGHT, and nothing else moves. No arc, no wind-up, no bob: the
 * line has to come to rest exactly on the row it becomes, and every bit of
 * swing is a frame where it does not line up with the thing underneath it.
 * A loot fly can lob because it lands in a slot the size of a fist; this lands
 * on its own glyphs.
 *
 * Pose is written in rAF, never component state. The overlay lives on
 * `document.body` so it is not warped by the HUD glass; the landing point is
 * `warpHudPoint`'d so it still hits the cell the player sees.
 */
export function AnnounceDock({ announce, dock, onLanded }: AnnounceDockProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef(dock);
  const onLandedRef = useRef(onLanded);
  dockRef.current = dock;
  onLandedRef.current = onLanded;

  useEffect(() => {
    const el = nodeRef.current;
    if (!el) return;

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      onLandedRef.current();
      return;
    }

    const part = (name: string) =>
      el.querySelector<HTMLElement>(`[data-announce="${name}"]`);
    const sub = part('subtitle');
    const leaving = [part('rule'), part('title'), part('amount')].filter(
      (node): node is HTMLElement => node !== null,
    );

    const hold = DOCK_HOLD_MS / 1000;
    const travel = DOCK_TRAVEL_MS / 1000;
    const life = hold + travel;

    let age = 0;
    let last = performance.now();
    let raf = 0;
    let done = false;
    let launched = false;
    /* Offset of the travelling line from the card's centre, measured once the
       card is frozen. Everything below aims the LINE at the row and derives
       the card's own position from it. */
    let lineOffset = 0;

    const launch = () => {
      launched = true;
      /* Kill the tracks before they reach their fade (see `HELD_AT`), keeping
         the pose they are in. From here the pose is written per frame. */
      for (const node of [...leaving, sub]) {
        if (!node) continue;
        const style = getComputedStyle(node);
        node.style.letterSpacing = style.letterSpacing;
        node.style.animation = 'none';
        node.style.opacity = '1';
      }
      if (sub) {
        sub.style.color = 'var(--ink)';
        lineOffset =
          sub.offsetTop + sub.offsetHeight / 2 - el.offsetHeight / 2;
      }
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      age += dt;

      const fromX = window.innerWidth / 2;
      const fromY = window.innerHeight * DOCK_Y;
      const box = dockRef.current?.getBoundingClientRect();
      const ready = !!box && box.width > 1 && box.height > 1;
      /* Nothing to aim at yet: hold on the last frame of the hold rather
         than flying to a corner. */
      if (age >= hold && !ready) age = hold - 0.0001;

      if (age >= life) {
        el.style.visibility = 'hidden';
        if (!done) {
          done = true;
          onLandedRef.current();
        }
        return;
      }

      let x = fromX;
      let y = fromY;
      let scale = 1;

      if (age >= hold && box) {
        if (!launched) launch();

        const t = (age - hold) / travel;
        const ease = 1 - (1 - t) ** 3;
        const raw = warpHudPoint(
          box.left + box.width / 2,
          box.top + box.height / 2,
          window.innerWidth,
          window.innerHeight,
          HUD_LENS,
        );

        scale = 1 - (1 - DOCK_LAND_SCALE) * ease;

        /* The LINE is what flies; the card is carried behind it. */
        const lineFromY = fromY + lineOffset;
        x = fromX + (raw.x - fromX) * ease;
        y = lineFromY + (raw.y - lineFromY) * ease - lineOffset * scale;

        const track =
          HELD_TRACKING + (ROW_TRACKING - HELD_TRACKING) * ease;
        if (sub) {
          sub.style.letterSpacing = `${track}em`;
          /* Only the last sliver fades — the real row crossfades up under it. */
          sub.style.opacity = String(t > 0.9 ? 1 - (t - 0.9) / 0.1 : 1);
        }
        /* The frame the news came in does not travel: it lifts and is gone
           inside the first third of the trip. */
        const shed = Math.min(1, t / 0.28);
        for (const node of leaving) node.style.opacity = String(1 - shed);
      }

      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${scale})`;
      el.style.visibility = 'visible';
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [announce.key]);

  return createPortal(
    <div
      ref={nodeRef}
      className="pointer-events-none fixed top-0 left-0 z-20 flex flex-col items-center"
      style={{ visibility: 'hidden' }}
      aria-hidden="true"
    >
      <AnnounceCard announce={announce} duration={DOCK_HOLD_MS / HELD_AT} />
    </div>,
    document.body,
  );
}

/**
 * The card itself. `duration` times the `zone-*` keyframes, which are written
 * in percentages for exactly this reason.
 */
function AnnounceCard({
  announce,
  duration,
}: {
  announce: HudAnnounce;
  duration: number;
}) {
  const ms = `${duration}ms`;

  return (
    <div className="relative flex flex-col items-center gap-2.5">
      <div
        data-announce="rule"
        className="animate-zone-rule bg-panel-border h-px w-0"
        style={{ animationDuration: ms }}
      />

      <h2
        data-announce="title"
        className="animate-zone-title pixel-text text-ink text-[24px] leading-[26px] tracking-[0.18em] whitespace-nowrap uppercase opacity-0 drop-shadow-[0_2px_0_var(--hud-text-shadow)]"
        style={{ animationDuration: ms }}
      >
        {announce.title}
      </h2>

      {announce.subtitle ? (
        <p
          data-announce="subtitle"
          /* No tracking utility: `zone-subtitle` animates letter-spacing
             itself, and a class here would be overridden for the whole run
             and then win at the end — a jump on the last frame. */
          className="animate-zone-subtitle pixel-text text-ink-accent text-[13px] leading-[15px] whitespace-nowrap uppercase opacity-0"
          style={{ animationDuration: ms }}
        >
          {announce.subtitle}
        </p>
      ) : null}

      {/*
        THE TAKE, when the card is about money. It STATES the number and does
        not count: the counting is already happening on the `Balance` row,
        driven by the coins flying to it off the platforms, and a second
        animated number on the same screen would be the same event told
        twice at two different speeds.

        It rides the SUBTITLE's own keyframes rather than getting its own, so
        the amount and the line above it arrive together as one statement.
        The coin is the HUD's `/hud/coin.png` at its native 8px — the same
        disc the bag and the balance use, because a price denominated in a
        coin the player does not already recognise is a second currency.
      */}
      {announce.amount != null ? (
        <p
          data-announce="amount"
          className="animate-zone-subtitle pixel-text flex items-center gap-1.5 text-[17px] leading-[19px] text-[var(--fx-gold-text)] opacity-0"
          style={{ animationDuration: ms }}
        >
          <img
            src="/hud/coin.png"
            alt=""
            width={8}
            height={8}
            className="size-[11px] [image-rendering:pixelated]"
          />
          +{announce.amount}
        </p>
      ) : null}
    </div>
  );
}
