/**
 * Mounts the campfire and feeds it the roster. React never touches these
 * pixels — same contract as `GameCanvas`, so the scene owns its own rAF loop
 * and releases it on unmount.
 */

import { useEffect, useRef } from 'react';
import { LobbyScene, type LobbyMember } from '@/game/lobby-scene';
import { cn } from '@/lib/utils';

export interface CampfireCanvasProps {
  members: readonly LobbyMember[];
  /** Room code (or any string): decides which clearing gets generated. */
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
