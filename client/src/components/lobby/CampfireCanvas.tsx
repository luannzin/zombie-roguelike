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
 *
 * The rest shot — where the fire sits in the viewport — is not a prop. It lives
 * in `render/framing.ts` so the title screen and the lobby cannot pick different
 * numbers. The launch still takes that displacement back to centre.
 */

import { useEffect, useRef } from 'react';
import { LobbyScene, type CampView, type LobbyMember } from '@/game/lobby-scene';
import { useIsMobile } from '@/hooks/use-media-query';
import { cn } from '@/lib/utils';
import { campFireAnchor } from '@/render/framing';

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
   * Flip to true to run the launch: the camera swooshes onto the local player
   * and pushes in to game scale. One-way — see `LobbyScene.beginLaunch`.
   */
  launching?: boolean;
  /** Seconds the launch takes. Must match whatever is timing the handover. */
  launchSeconds?: number;
  className?: string;
}

export function CampfireCanvas({
  members,
  camp = null,
  seed = '',
  launching = false,
  launchSeconds = 1,
  className,
}: CampfireCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<LobbyScene | null>(null);
  // Same rest shot on the title screen and in the lobby — see framing.ts.
  const { x: anchorX, y: anchorY } = campFireAnchor(useIsMobile());

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const scene = new LobbyScene(canvas, hashSeed(seed), { x: anchorX, y: anchorY });
    sceneRef.current = scene;
    void scene.start();
    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
    // Anchor is deliberately NOT a dependency: it is live framing, pushed in
    // below. Rebuilding the scene to move the camera would restart the fire.
  }, [seed]);

  useEffect(() => {
    sceneRef.current?.setAnchor(anchorX, anchorY);
  }, [anchorX, anchorY]);

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

  // Last, so the launch always sees the final roster and can find the local
  // seat to aim at.
  useEffect(() => {
    if (launching) sceneRef.current?.beginLaunch(launchSeconds);
  }, [launching, launchSeconds]);

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
