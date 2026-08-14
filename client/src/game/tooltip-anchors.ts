/**
 * Screen-space anchors for world tooltips.
 *
 * The game writes these every frame from the same camera the canvas used.
 * `Tooltip` reads them in its own rAF and sets a transform — no React state,
 * so the HUD contract (no per-frame renders) stays intact. Show/hide still
 * comes from `hud-store` at 5 Hz.
 */

export interface TooltipAnchor {
  x: number;
  y: number;
}

const anchors = new Map<string, TooltipAnchor>();

export function writeTooltipAnchor(id: string, x: number, y: number): void {
  const existing = anchors.get(id);
  if (existing) {
    existing.x = x;
    existing.y = y;
    return;
  }
  anchors.set(id, { x, y });
}

export function readTooltipAnchor(id: string): TooltipAnchor | null {
  return anchors.get(id) ?? null;
}

export function dropTooltipAnchor(id: string): void {
  anchors.delete(id);
}

export function clearTooltipAnchors(): void {
  anchors.clear();
}
