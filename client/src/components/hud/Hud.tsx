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
 */

import type { RefObject } from 'react';
import type { HudSnapshot } from '../../game/hud-store';
import { MinimapCanvas } from '../game/MinimapCanvas';
import { BatteryGauge } from './BatteryGauge';
import { ControlsHint } from './ControlsHint';
import { HudScreen } from './HudScreen';
import { NetStats } from './NetStats';
import { StatusLine } from './StatusLine';
import { Vitals } from './Vitals';

export interface HudProps {
  snapshot: HudSnapshot;
  minimapRef: RefObject<HTMLCanvasElement | null>;
  error: string | null;
}

export function Hud({ snapshot, minimapRef, error }: HudProps) {
  return (
    <HudScreen unstable={snapshot.lantern?.failing ?? false}>
      <div className="hud-layer pixel-text top-2.5 left-3 text-[11px] leading-[17px]">
        <StatusLine status={snapshot.status} connection={snapshot.connection} error={error} />
        <NetStats net={snapshot.net} />
      </div>

      <div className="hud-layer pixel-text top-2.5 right-3">
        <MinimapCanvas ref={minimapRef} visible={snapshot.inArena} />
      </div>

      <div className="hud-layer pixel-text right-3 bottom-2.5 flex flex-col items-end gap-2">
        <BatteryGauge lantern={snapshot.lantern} />
        <Vitals vitals={snapshot.vitals} />
      </div>

      <div className="hud-layer pixel-text bottom-2.5 left-3">
        <ControlsHint />
      </div>
    </HudScreen>
  );
}
