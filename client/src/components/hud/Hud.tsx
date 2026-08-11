/**
 * HUD overlay: composes the four fixed corners over the game canvas.
 *
 * Every layer is `pointer-events: none` (see the `hud-layer` utility) so the
 * canvas keeps receiving aim and fire input underneath.
 */

import type { RefObject } from 'react';
import type { HudSnapshot } from '../../game/hud-store';
import { MinimapCanvas } from '../game/MinimapCanvas';
import { ControlsHint } from './ControlsHint';
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
    <>
      <div className="hud-layer top-2.5 left-3 text-xs leading-[1.6]">
        <StatusLine status={snapshot.status} connection={snapshot.connection} error={error} />
        <NetStats net={snapshot.net} />
      </div>

      <div className="hud-layer top-2.5 right-3">
        <MinimapCanvas ref={minimapRef} visible={snapshot.inArena} />
      </div>

      <div className="hud-layer right-3 bottom-2.5">
        <Vitals vitals={snapshot.vitals} />
      </div>

      <div className="hud-layer bottom-2.5 left-3">
        <ControlsHint />
      </div>
    </>
  );
}
