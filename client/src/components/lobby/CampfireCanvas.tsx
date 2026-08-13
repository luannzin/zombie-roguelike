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
  className?: string;
}

export function CampfireCanvas({ members, className }: CampfireCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<LobbyScene | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const scene = new LobbyScene(canvas);
    sceneRef.current = scene;
    void scene.start();
    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

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
