/**
 * HUD overlay: composes the four fixed corners over the game canvas.
 *
 * Every layer is `pointer-events: none` (see the `hud-layer` utility) so the
 * canvas keeps receiving aim and fire input underneath.
 *
 * All four corners live inside one `HudScreen`, which bends them onto a curved
 * display and tears them when the signal is bad. Anything added here inherits
 * that by construction — a panel outside the wrapper would visibly float off
 * the glass everything else is painted on.
 *
 * The corners are OFF while a zone introduces itself. For that beat the screen
 * holds the place and your own character standing in it, with the day's name
 * over the middle and nothing else; the HUD coming up is the same moment the
 * controls come back, so it reads as "you're up" rather than as chrome fading
 * in. The title card is deliberately outside that group — it is what the empty
 * frame is for.
 */

import type { RefObject } from 'react';
import type { HudSnapshot } from '../../game/hud-store';
import { cn } from '@/lib/utils';
import { MinimapCanvas } from '../game/MinimapCanvas';
import { BatteryGauge } from './BatteryGauge';
import { ControlsHint } from './ControlsHint';
import { HudScreen } from './HudScreen';
import { NetStats } from './NetStats';
import { StatusLine } from './StatusLine';
import { Vitals } from './Vitals';
import { ZoneTitle } from './ZoneTitle';

export interface HudProps {
  snapshot: HudSnapshot;
  minimapRef: RefObject<HTMLCanvasElement | null>;
  error: string | null;
}

export function Hud({ snapshot, minimapRef, error }: HudProps) {
  // Long enough that the corners arrive rather than appear, short enough that
  // they are settled before the player has taken two steps.
  const chrome = cn(
    'transition-opacity duration-700 ease-out',
    snapshot.introducing && 'opacity-0 duration-200',
  );

  return (
    <HudScreen unstable={snapshot.lantern?.failing ?? false}>
      <div
        className={cn('hud-layer pixel-text top-2.5 left-3 text-[11px] leading-[17px]', chrome)}
      >
        <StatusLine status={snapshot.status} connection={snapshot.connection} error={error} />
        <NetStats net={snapshot.net} />
      </div>

      <div className={cn('hud-layer pixel-text top-2.5 right-3', chrome)}>
        <MinimapCanvas ref={minimapRef} visible={snapshot.inArena} />
      </div>

      <div
        className={cn(
          'hud-layer pixel-text right-3 bottom-2.5 flex flex-col items-end gap-2',
          chrome,
        )}
      >
        <BatteryGauge lantern={snapshot.lantern} />
        <Vitals vitals={snapshot.vitals} />
      </div>

      <div className={cn('hud-layer pixel-text bottom-2.5 left-3', chrome)}>
        <ControlsHint zone={snapshot.zone} />
      </div>

      {/* Last, so the arrival card sits over every corner — it is the one thing
          here that is allowed to own the whole screen, and only for a moment. */}
      <ZoneTitle arrival={snapshot.arrival} />
    </HudScreen>
  );
}
