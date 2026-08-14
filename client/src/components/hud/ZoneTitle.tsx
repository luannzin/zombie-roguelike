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
 * named. It deliberately does not run DURING the move: a title over a
 * travelling camera is two things asking to be read at once.
 *
 * It plays into an EMPTY frame. `game.ts` holds the player still and facing the
 * camera for INTRO_TIME and the HUD keeps its corners off the glass for the
 * same beat, so for three seconds the screen is the clearing, one character
 * standing in it, and the day's name. That is the whole point of the card: it
 * is not a caption over gameplay, it is the moment the player is told where
 * they are before they are allowed to go anywhere.
 *
 * Everything FADES. An earlier version wiped and flickered the type in, which
 * read as a title sequence rather than as arriving somewhere quiet — the camp
 * is the calm before the night, and the card should feel like it.
 *
 * Four parts, and each one is doing a job:
 *
 *   WASH      a dark gradient from the top and bottom edges. Not a full-screen
 *             dim — the point is to make the type legible over a live scene
 *             while leaving the middle of the frame, where the character is,
 *             completely clear.
 *   RULES     hairlines that draw out from the centre, one above and one below.
 *             They are what make the title arrive rather than appear.
 *   TITLE     big, wide-tracked, rising a few pixels as it fades up.
 *   SUBTITLE  the smaller line, held back a beat so the two are read in order,
 *             its tracking closing as it settles.
 *
 * Everything is CSS keyframes on a mount, not per-frame state: the whole card
 * exists for three seconds and React must never be in the frame loop (see the
 * HUD contract in components/AGENTS.md). Remounting on `key` is what replays it.
 */

import { useEffect, useState } from 'react';
import type { HudArrival } from '../../game/hud-store';

/**
 * How long the card stays mounted, in ms.
 *
 * Cut against INTRO_TIME in game/game.ts: the type has to be gone BEFORE the
 * controls come back, so the HUD rises into an empty frame instead of arriving
 * underneath a title. Lengthening one without the other closes that gap.
 */
const CARD_MS = 3000;

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

      <div className="relative flex flex-col items-center gap-4">
        <div className="animate-zone-rule bg-panel-border h-px w-0" />

        <h2 className="animate-zone-title pixel-text text-ink text-[44px] leading-[48px] tracking-[0.22em] uppercase opacity-0 drop-shadow-[0_3px_0_var(--hud-text-shadow)]">
          {arrival.zone.title}
        </h2>

        <p className="animate-zone-subtitle pixel-text text-ink-accent text-[22px] leading-[26px] tracking-[0.34em] uppercase opacity-0">
          {arrival.zone.subtitle}
        </p>

        <div className="animate-zone-rule bg-panel-border h-px w-0 [animation-delay:140ms]" />
      </div>
    </div>
  );
}
