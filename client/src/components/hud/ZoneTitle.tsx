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
 * The BARS are not here. They start in the lobby, under the push-in, and are
 * already at full when the arena takes the screen — see `Hud`, which owns them
 * for the whole hold. Fading them in from this component would mean fading them
 * in a few frames AFTER the arena's first paint, which is a flash of bright
 * scene followed by a dim, right at the seam.
 *
 * Three parts, and each one is doing a job:
 *
 *   RULES     hairlines that draw out from the centre, one above and one below.
 *             They are what make the title arrive rather than appear.
 *   TITLE     big, wide-tracked, rising a few pixels as it fades up,
 *             coming into focus from a soft blur at 0.95 scale.
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
 * How long the arrival takes on screen, in ms — the bars, the card, and the
 * gap before the HUD returns.
 *
 * It must match INTRO_TIME in game/game.ts, which is the same beat measured on
 * the game clock: the type has to be gone BEFORE the controls come back, so
 * the HUD rises into an empty frame instead of arriving underneath a title.
 */
export const ZONE_INTRO_MS = 3000;

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
    const timer = window.setTimeout(() => setShowing(null), ZONE_INTRO_MS);
    return () => window.clearTimeout(timer);
  }, [key]);

  if (!arrival || showing !== key) return null;

  return (
    <div
      key={key}
      className="hud-layer inset-0 flex flex-col items-center justify-center"
      aria-hidden="true"
    >
      <div className="relative flex flex-col items-center gap-4">
        <div className="animate-zone-rule bg-panel-border h-px w-0" />

        <div className="animate-zone-title opacity-0">
          <h2 className="pixel-text text-ink text-[44px] leading-[48px] tracking-[0.22em] uppercase drop-shadow-[0_3px_0_var(--hud-text-shadow)]">
            {arrival.zone.title}
          </h2>
        </div>

        <p className="animate-zone-subtitle pixel-text text-ink-accent text-[22px] leading-[26px] tracking-[0.34em] uppercase opacity-0">
          {arrival.zone.subtitle}
        </p>

        <div className="animate-zone-rule bg-panel-border h-px w-0 [animation-delay:140ms]" />
      </div>
    </div>
  );
}
