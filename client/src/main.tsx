import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';
import { router } from './app/routes';
import { installAudioUnlock, primeAudio, toggleMuted } from './audio';
import './styles/index.css';

const container = document.getElementById('root');
if (!container) throw new Error('#root is missing from index.html');

/**
 * Sound the player meets before the game loop exists: the menu, the campfire,
 * and the walk out of it.
 *
 * Decoded on the first gesture rather than on load, because nothing can be
 * decoded before there is a context and there is no context before a gesture.
 * That first gesture is a menu click, which is minutes of lobby ahead of the
 * first arrival — so by the time the day names itself, the sting that names it
 * is in memory. `Game` primes the combat set on top of this.
 */
const OPENING_SOUNDS = [
  'ui-hover',
  'ui-click',
  'ui-back',
  'ui-error',
  'fire',
  'summon',
  'kindle',
  'ready',
  'unready',
  'void',
  'arrive',
];

// Page-lifetime, deliberately outside React: StrictMode mounts components
// twice and this must install exactly once.
installAudioUnlock(() => void primeAudio(OPENING_SOUNDS));

/**
 * Mute, on M, everywhere.
 *
 * Global rather than in `game/input.ts` because it is the one control that has
 * to work on the title screen and in a room and mid-run alike — a player who
 * wants the sound off is usually not in the frame where they can pause. It
 * ignores repeats and anything typed into a field, so muting is never a
 * side effect of naming yourself MMM.
 */
window.addEventListener('keydown', (event) => {
  if (event.key !== 'm' && event.key !== 'M') return;
  if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target?.isContentEditable) return;
  const tag = target?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  toggleMuted();
});

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
