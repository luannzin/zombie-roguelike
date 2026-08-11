/**
 * The arena: one game canvas plus the HUD overlay.
 *
 * Unmounting this screen disposes the game (see `useGameSession`), so it is
 * safe to route away to a menu or another room.
 */

import { GameCanvas } from '../components/game/GameCanvas';
import { Hud } from '../components/hud/Hud';
import { useGameSession } from '../hooks/useGameSession';
import { useHud } from '../hooks/useHud';

export function ArenaScreen() {
  const { hud, canvasRef, minimapRef, error } = useGameSession();
  const snapshot = useHud(hud);

  return (
    <>
      <GameCanvas ref={canvasRef} />
      <Hud snapshot={snapshot} minimapRef={minimapRef} error={error} />
    </>
  );
}
