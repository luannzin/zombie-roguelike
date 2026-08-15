/**
 * The audio page of the options menu.
 *
 * One row per bus, and the buses are a PLAYER-FACING grouping rather than an
 * engineering one (see `audio/engine.ts`): the split exists so that somebody
 * who wants the guns and the growling quieter does not lose their own
 * footsteps, the fire, or the bag doing it. That is why `sfx` is narrow enough
 * to be labelled with what is actually in it.
 *
 * State lives in the audio engine, not here — it is written to `localStorage`
 * and read by a graph that is not part of React. `useSyncExternalStore` is the
 * seam, the same shape as `useHud`: the engine publishes, components read.
 *
 * Every change is applied LIVE and ramped, so dragging a fader while the game
 * is audible is how you find the number you want. There is no apply button and
 * nothing to confirm.
 */

import { useSyncExternalStore } from 'react';
import { BUSES, getAudioSettings, onAudioSettingsChange, setBusVolume, type Bus } from '@/audio';
import { HudSlider } from './HudSlider';

/** Copy for each row. Portuguese, like the rest of the interface. */
const ROWS: Record<Bus, { label: string; hint?: string }> = {
  ui: { label: 'Sons de interface' },
  ambient: { label: 'Som ambiente', hint: 'fogueira, vento, noite' },
  sfx: { label: 'Efeitos sonoros', hint: 'tiros e zumbis' },
  misc: { label: 'Som misc', hint: 'passos, itens, lanterna' },
};

export function AudioOptions() {
  const settings = useSyncExternalStore(onAudioSettingsChange, getAudioSettings, getAudioSettings);

  return (
    <div className="flex flex-col gap-5">
      {BUSES.map((bus) => (
        <HudSlider
          key={bus}
          label={ROWS[bus].label}
          hint={ROWS[bus].hint}
          value={settings.volumes[bus] * 100}
          onChange={(value) => setBusVolume(bus, value / 100)}
        />
      ))}
    </div>
  );
}
