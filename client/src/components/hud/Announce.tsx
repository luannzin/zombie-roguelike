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
 */

import { useEffect, useState } from 'react';
import type { HudAnnounce } from '../../game/hud-store';

/** How long the card is on screen, in ms. */
export const ANNOUNCE_MS = 2200;

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

  const duration = `${ANNOUNCE_MS}ms`;

  return (
    <div
      key={key}
      className="hud-layer inset-x-0 top-[26%] flex flex-col items-center"
      aria-hidden="true"
    >
      <div className="relative flex flex-col items-center gap-2.5">
        <div
          className="animate-zone-rule bg-panel-border h-px w-0"
          style={{ animationDuration: duration }}
        />

        <h2
          className="animate-zone-title pixel-text text-ink text-[24px] leading-[26px] tracking-[0.18em] uppercase opacity-0 drop-shadow-[0_2px_0_var(--hud-text-shadow)]"
          style={{ animationDuration: duration }}
        >
          {announce.title}
        </h2>

        {announce.subtitle ? (
          <p
            /* No tracking utility: `zone-subtitle` animates letter-spacing
               itself, and a class here would be overridden for the whole run
               and then win at the end — a jump on the last frame. */
            className="animate-zone-subtitle pixel-text text-ink-accent text-[13px] leading-[15px] uppercase opacity-0"
            style={{ animationDuration: duration }}
          >
            {announce.subtitle}
          </p>
        ) : null}
      </div>
    </div>
  );
}
