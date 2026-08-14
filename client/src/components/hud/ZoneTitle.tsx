/**
 * The card that names the place you just arrived in.
 *
 * "Preparação" over "Dia 1"; later "Dia 3" over "21:58 da noite". Both strings
 * are the server's (see server/app/zones.py) — this component knows how an
 * arrival FEELS and nothing about what any particular one says.
 *
 * It lands on the beat the camera stops. The lobby performs the push-in onto
 * your character (see `game/lobby-scene.ts`) and the arena mounts on the frame
 * it finishes, which is when this mounts too — motion settles, then the day is
 * named. It deliberately does not run DURING the move: a title over a travelling
 * camera is two things asking to be read at once.
 *
 * Four parts, and each one is doing a job:
 *
 *   WASH      a dark gradient from the top and bottom edges. Not a full-screen
 *             dim — the point is to make the type legible over a live scene
 *             while leaving the middle of the frame, where the character is,
 *             completely clear.
 *   RULE      a hairline that draws out from the centre before the words land.
 *             It is what makes the title arrive rather than appear.
 *   TITLE     big, wide-tracked, revealed by a wipe. It also flickers once as
 *             it settles, on the same generator-that-is-not-coping idea the
 *             menu sign uses.
 *   SUBTITLE  the smaller line, held back a beat so the two are read in order.
 *   SWEEP     one bright band travelling across the type, once. A title that
 *             merely fades in is a subtitle; the sweep is what makes it an
 *             announcement.
 *
 * Everything is CSS keyframes on a mount, not per-frame state: the whole card
 * exists for two seconds and React must never be in the frame loop (see the
 * HUD contract in components/AGENTS.md). Remounting on `key` is what replays it.
 */

import { useEffect, useState } from 'react';
import type { HudArrival } from '../../game/hud-store';

/**
 * How long the card stays mounted, in ms. Comfortably past the camera's
 * ARRIVAL_TIME so the type finishes clearing after the push-in has settled.
 */
const CARD_MS = 3400;

export interface ZoneTitleProps {
  arrival: HudArrival | null;
}

export function ZoneTitle({ arrival }: ZoneTitleProps) {
  const key = arrival?.key ?? null;
  // Tracked separately from the prop: the store keeps the last arrival forever
  // (it is also what greys the battery out), and the card is a one-shot.
  const [showing, setShowing] = useState<string | null>(key);

  useEffect(() => {
    if (!key) return;
    setShowing(key);
    const timer = window.setTimeout(() => setShowing(null), CARD_MS);
    return () => window.clearTimeout(timer);
  }, [key]);

  if (!arrival || showing !== key) return null;

  return (
    <div
      key={key}
      className="hud-layer inset-0 flex flex-col items-center justify-center"
      aria-hidden="true"
    >
      {/* Legibility, from the edges in. The middle of the frame stays clear so
          the character the camera is pushing onto is never behind a scrim. */}
      <div className="animate-zone-wash absolute inset-0 bg-[linear-gradient(to_bottom,var(--surface)_0%,transparent_38%,transparent_62%,var(--surface)_100%)] opacity-0" />

      <div className="relative flex flex-col items-center gap-3">
        <div className="animate-zone-rule bg-ink-accent h-px w-0" />

        <h2 className="animate-zone-title pixel-text text-ink relative overflow-hidden text-[44px] leading-[48px] tracking-[0.22em] uppercase opacity-0 drop-shadow-[0_3px_0_var(--hud-text-shadow)]">
          {arrival.zone.title}
          <span className="animate-zone-sweep pointer-events-none absolute inset-0 bg-[linear-gradient(100deg,transparent_38%,var(--ink-accent)_50%,transparent_62%)] mix-blend-overlay" />
        </h2>

        <p className="animate-zone-subtitle pixel-text text-ink-accent text-[22px] leading-[26px] tracking-[0.34em] uppercase opacity-0">
          {arrival.zone.subtitle}
        </p>

        <div className="animate-zone-rule bg-panel-border h-px w-0 [animation-delay:120ms]" />
      </div>
    </div>
  );
}
