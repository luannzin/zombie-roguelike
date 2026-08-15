/**
 * The game's sound, in one import.
 *
 * `engine`  the context, the buses and the unlock rule
 * `library` the generated catalog and its decoded buffers
 * `sfx`     one-shots: variants, detune, and world position
 * `beds`    the looping ambience and the crossfades between places
 *
 * The layering rule matches the rest of the client: audio knows about a
 * listener at a point and sounds at other points, and nothing about players,
 * zombies or zones. Whoever calls it owns that meaning.
 */

export {
  installAudioUnlock,
  unlockAudio,
  getAudioSettings,
  setBusVolume,
  setMuted,
  toggleMuted,
  onAudioSettingsChange,
  BUSES,
  type AudioSettings,
  type Bus,
} from './engine';

export { loadAudioManifest, primeAudio, soundEntry, type SoundEntry } from './library';

export {
  playSfx,
  playSfxAt,
  setAudioListener,
  spatial,
  throttled,
  resetSfxState,
  type PlayOptions,
} from './sfx';

export { setBeds, setBedRate, stopBeds } from './beds';
