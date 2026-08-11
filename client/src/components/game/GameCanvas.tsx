/**
 * The game surface. React mounts this canvas once and never touches it again —
 * `Game` owns every pixel and the rAF loop that draws them.
 */

import type { RefObject } from 'react';

export interface GameCanvasProps {
  ref: RefObject<HTMLCanvasElement | null>;
}

export function GameCanvas({ ref }: GameCanvasProps) {
  return <canvas ref={ref} className="pixelated block h-screen w-screen" />;
}
