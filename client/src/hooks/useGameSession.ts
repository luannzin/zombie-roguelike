/**
 * Owns one `Game` instance for as long as the arena is mounted.
 *
 * The socket is NOT created here — it belongs to `useRoomSession` and has been
 * open since the lobby. This hook only builds the game that reads it, from the
 * `welcome` that ended the lobby phase. A later welcome (forest after camp) is
 * the same player on a new map: `Game.onWelcome` handles it. Rebuilding here
 * would reset the input sequence while the server still holds the camp's ack.
 *
 * The effect cleanup is load-bearing, not a formality: it is what stops the
 * rAF loop, unsubscribes from the socket and removes the window listeners.
 * StrictMode double-mounts in dev and Vite's react-refresh re-runs this on
 * every save, so without a working `dispose()` each edit would stack another
 * game loop.
 */

import { useEffect, useRef, useState } from 'react';
import { Game } from '../game/game';
import { createHudStore } from '../game/hud-store';
import type { Connection } from '../net/connection';
import type { WelcomeMessage } from '../net/protocol';

export interface GameSession {
  hud: ReturnType<typeof createHudStore>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  minimapRef: React.RefObject<HTMLCanvasElement | null>;
  /** Set when the game could not start at all (not a dropped connection). */
  error: string | null;
}

export function useGameSession(
  connection: Connection,
  welcome: WelcomeMessage,
  /** Called once the game has drawn a frame. See `Game.onFirstFrame`. */
  onFirstFrame?: () => void,
): GameSession {
  // Lazy initializer: one store for the lifetime of the component.
  const [hud] = useState(createHudStore);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const minimapRef = useRef<HTMLCanvasElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Held in a ref rather than a dependency: a caller passing an inline arrow
  // would otherwise tear down and rebuild the whole game on every render.
  const ready = useRef(onFirstFrame);
  ready.current = onFirstFrame;

  // Identity is the player, not the welcome object. Embark sends a second
  // welcome with the same playerId; that must not tear the Game down.
  const playerId = welcome.playerId;

  useEffect(() => {
    const canvas = canvasRef.current;
    const minimapCanvas = minimapRef.current;
    if (!canvas || !minimapCanvas) return;

    let cancelled = false;
    const game = new Game({
      canvas,
      minimapCanvas,
      hud,
      connection,
      welcome,
      onFirstFrame: () => ready.current?.(),
    });

    game.start().catch((err: unknown) => {
      console.error(err);
      if (!cancelled) setError('failed to start — see console');
    });

    return () => {
      cancelled = true;
      game.dispose();
    };
    // `welcome` is the one that created this identity. Later welcomes for the
    // same playerId arrive on the socket and Game.onWelcome applies them.
  }, [hud, connection, playerId]);

  return { hud, canvasRef, minimapRef, error };
}
