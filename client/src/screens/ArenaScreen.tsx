/**
 * The arena: one game canvas plus the HUD overlay.
 *
 * The socket is handed in by `RoomScreen` — it has been open since the lobby.
 * Unmounting this screen disposes the game (see `useGameSession`) but leaves
 * that connection alone, so dropping back to a lobby or a menu is safe.
 */

import { GameCanvas } from '../components/game/GameCanvas';
import { Hud } from '../components/hud/Hud';
import { useGameSession } from '../hooks/useGameSession';
import { useHud } from '../hooks/useHud';
import type { Connection } from '../net/connection';
import type { WelcomeMessage } from '../net/protocol';

export interface ArenaScreenProps {
  connection: Connection;
  /** The welcome that ended the lobby; the world is built from it. */
  welcome: WelcomeMessage;
}

export function ArenaScreen({ connection, welcome }: ArenaScreenProps) {
  const { hud, canvasRef, minimapRef, error } = useGameSession(connection, welcome);
  const snapshot = useHud(hud);

  return (
    <>
      <GameCanvas ref={canvasRef} />
      <Hud snapshot={snapshot} minimapRef={minimapRef} error={error} />
    </>
  );
}
