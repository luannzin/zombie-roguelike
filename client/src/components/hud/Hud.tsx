/**
 * HUD overlay: composes the four fixed corners over the game canvas.
 *
 * Every layer is `pointer-events: none` (see the `hud-layer` utility) so the
 * canvas keeps receiving aim and fire input underneath.
 *
 * All four corners live inside one `HudScreen`, which bends them onto a curved
 * display and tears them when the signal is bad. World tooltips do not: they
 * sit outside the glass, pinned to a thing in the scene, the same way the
 * letterbox does. A HUD panel outside the wrapper would visibly float off the
 * glass everything else is painted on.
 *
 * The corners are OFF while a zone introduces itself. For that beat the screen
 * holds the place and your own character standing in it, with the day's name
 * over the middle and nothing else; the HUD coming up is the same moment the
 * controls come back, so it reads as "you're up" rather than as chrome fading
 * in. The title card is deliberately outside that group — it is what the empty
 * frame is for.
 *
 * They start hidden and fade UP; they are never faded down from visible on
 * arrival. `introducing` defaults to true in the store for exactly that reason
 * (see hud-store.ts) — the alternative is one painted frame of full-strength
 * HUD before the game has said anything, which is a flash in the middle of the
 * one transition that has to be seamless.
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
import { ZONE_INTRO_MS, ZoneTitle } from './ZoneTitle';
import { ReadyCount } from './ReadyCount';
import { InteractPrompt } from './InteractPrompt';
import { Inventory } from './Inventory';
import { LootFly } from './LootFly';
import { LootPrompt } from './LootPrompt';

export interface HudProps {
  snapshot: HudSnapshot;
  minimapRef: RefObject<HTMLCanvasElement | null>;
  error: string | null;
}

export function Hud({ snapshot, minimapRef, error }: HudProps) {
  // Slow up, fast down. Coming back is the beat that says the controls are
  // yours, so it gets time; going away is housekeeping and should not linger.
  const chrome = cn(
    'transition-opacity duration-700 ease-out',
    (snapshot.introducing || snapshot.cinematic) && 'opacity-0 duration-200',
  );

  return (
    <>
      {/*
        The letterbox, picked up from the lobby — OUTSIDE HudScreen on purpose.
        The lobby paints the same `zone-bars` unfiltered; putting this under the
        glass's fish-eye bends the soft edge and reads as the bars jumping taller
        on the exact frame the title lands. Same element, same stops, same space.
        It is rendered off `introducing` rather than off `arrival` because that
        flag is true in the store's INITIAL snapshot (see hud-store.ts) — so the
        bars exist on the arena's very first painted frame, which is the frame
        the lobby left them at full. Keying them off `arrival` would mount them
        a few frames later, and those frames are a flash of undimmed scene at
        exactly the seam this is here to hide.
      */}
      {snapshot.introducing || snapshot.cinematic ? (
        <div
          className={cn(
            'zone-bars',
            snapshot.introducing ? 'animate-zone-bars-hold' : 'opacity-100',
          )}
          style={
            snapshot.introducing ? { animationDuration: `${ZONE_INTRO_MS}ms` } : undefined
          }
          aria-hidden="true"
        />
      ) : null}

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

        <div
          className={cn(
            'hud-layer pixel-text bottom-2.5 left-3 flex flex-col items-start gap-2',
            chrome,
          )}
        >
          <Inventory inventory={snapshot.inventory} />
          <ControlsHint zone={snapshot.zone} />
        </div>

        <div
          className={cn(
            'hud-layer pixel-text top-2.5 left-1/2 -translate-x-1/2',
            chrome,
          )}
        >
          <ReadyCount ready={snapshot.ready} />
        </div>

        {/* Last, so the arrival card sits over every corner — it is the one thing
            here that is allowed to own the whole screen, and only for a moment. */}
        <ZoneTitle arrival={snapshot.arrival} />
      </HudScreen>

      {/*
        World tooltips sit OUTSIDE the glass. They are pinned to a thing in
        the scene (the fire, later a chest), and the fish-eye would pull them
        off that thing. Show/hide is still the store; the screen position is
        written by the game loop.
      */}
      <InteractPrompt prompt={snapshot.prompt} />
      <LootPrompt prompt={snapshot.lootPrompt} />
      <LootFly lootFrames={snapshot.inventory?.lootFrames ?? 1} />
    </>
  );
}
