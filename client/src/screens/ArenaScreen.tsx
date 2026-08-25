/**
 * The arena: one game canvas plus the HUD overlay.
 *
 * The socket is handed in by `RoomScreen` — it has been open since the lobby.
 * Unmounting this screen disposes the game (see `useGameSession`) but leaves
 * that connection alone, so dropping back to a lobby or a menu is safe.
 *
 * It mounts INVISIBLE and reports back when it has drawn. Between mounting and
 * that first frame the canvas is a blank rectangle — sprite sheets resolving,
 * the terrain layer baking the whole map into its cache — and taking the screen
 * during it is a black flash right where the lobby's camera move is supposed to
 * continue uninterrupted. `RoomScreen` keeps the lobby up until `onFirstFrame`
 * says there is a world here to look at.
 */

import { GameCanvas } from '../components/game/GameCanvas';
import { Hud } from '../components/hud/Hud';
import { useGameSession } from '../hooks/useGameSession';
import { useHud } from '../hooks/useHud';
import { cn } from '../lib/utils';
import type { Connection } from '../net/connection';
import type { WelcomeMessage } from '../net/protocol';

export interface ArenaScreenProps {
  connection: Connection;
  /** The welcome that ended the lobby; the world is built from it. */
  welcome: WelcomeMessage;
  /** False until this screen has drawn; it stays hidden over the lobby. */
  visible: boolean;
  /** Fired on the first drawn frame. */
  onFirstFrame: () => void;
}

export function ArenaScreen({
  connection,
  welcome,
  visible,
  onFirstFrame,
}: ArenaScreenProps) {
  const { hud, canvasRef, minimapRef, error, watch } = useGameSession(
    connection,
    welcome,
    onFirstFrame,
  );
  const snapshot = useHud(hud);

  return (
    // No transition on the reveal. The frame underneath is the same frame this
    // one drew — the whole point is that nothing changes when it appears, and
    // a fade would turn a seamless swap into a visible cross-dissolve.
    <div className={cn('fixed inset-0', !visible && 'invisible')}>
      <GameCanvas ref={canvasRef} />
      <Hud snapshot={snapshot} minimapRef={minimapRef} error={error} onWatch={watch} />
    </div>
  );
}
