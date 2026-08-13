/**
 * Owns one `Game` instance for as long as the arena is mounted.
 *
 * The socket is NOT created here — it belongs to `useRoomSession` and has been
 * open since the lobby. This hook only builds the game that reads it, from the
 * `welcome` that ended the lobby phase.
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

export function useGameSession(connection: Connection, welcome: WelcomeMessage): GameSession {
  // Lazy initializer: one store for the lifetime of the component.
  const [hud] = useState(createHudStore);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const minimapRef = useRef<HTMLCanvasElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const minimapCanvas = minimapRef.current;
    if (!canvas || !minimapCanvas) return;

    let cancelled = false;
    const game = new Game({ canvas, minimapCanvas, hud, connection, welcome });

    game.start().catch((err: unknown) => {
      console.error(err);
      if (!cancelled) setError('failed to start — see console');
    });

    return () => {
      cancelled = true;
      game.dispose();
    };
  }, [hud, connection, welcome]);

  return { hud, canvasRef, minimapRef, error };
}
