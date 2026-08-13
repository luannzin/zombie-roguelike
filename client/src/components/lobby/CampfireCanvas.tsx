/**
 * Mounts the campfire and feeds it the camp and the roster. React never touches
 * these pixels — same contract as `GameCanvas`, so the scene owns its own rAF
 * loop and releases it on unmount.
 *
 * Two inputs, and they arrive at different times. `camp` is the map the server
 * sent in `hello`: hand it over and the scene stops drawing its own clearing
 * and starts drawing the real one. `members` is the roster, which changes every
 * time somebody joins or leaves. Both are pushed into the scene through
 * effects rather than through props on a re-render, because the scene is not a
 * React tree — it is a canvas with a loop in it.
 */

import { useEffect, useRef } from 'react';
import { LobbyScene, type CampView, type LobbyMember } from '@/game/lobby-scene';
import { cn } from '@/lib/utils';

export interface CampfireCanvasProps {
  members: readonly LobbyMember[];
  /**
   * The server's camp. Omitted on the title screen, which has no room and
   * therefore no map — the scene generates a clearing of its own instead.
   */
  camp?: CampView | null;
  /** Room code (or any string): decides which clearing the fallback grows. */
  seed?: string;
  /**
   * Where the fire sits in the canvas, as 0..1 fractions. Defaults to centred.
   * The title screen moves it down and left, out from under the menu.
   */
  anchorX?: number;
  anchorY?: number;
  className?: string;
}

export function CampfireCanvas({
  members,
  camp = null,
  seed = '',
  anchorX = 0.5,
  anchorY = 0.42,
  className,
}: CampfireCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<LobbyScene | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Anchor is read once per scene; it is a framing decision, not state.
    const scene = new LobbyScene(canvas, hashSeed(seed), { x: anchorX, y: anchorY });
    sceneRef.current = scene;
    void scene.start();
    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
  }, [seed, anchorX, anchorY]);

  // Before the roster, so the first party is placed against the real map rather
  // than against the fallback clearing and then shunted.
  useEffect(() => {
    sceneRef.current?.setCamp(camp);
  }, [camp]);

  // Runs after the mount effect above, so the first roster is never dropped.
  // `setMembers` diffs by id: re-sending an unchanged list is a no-op, not a
  // re-summon.
  useEffect(() => {
    sceneRef.current?.setMembers(members);
  }, [members]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn('pixelated block h-full w-full', className)}
    />
  );
}

/** FNV-1a over the room code: the same code always grows the same clearing. */
function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
