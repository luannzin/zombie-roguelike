/**
 * Screen-space centres for the HUD bag.
 *
 * The inventory writes these from layout (backpack + each slot). The collect
 * fly reads them every frame so an item can leave the world and land on a
 * cell without a React render. Same contract as `tooltip-anchors`.
 */

export interface InventoryAnchor {
  x: number;
  y: number;
}

const anchors = new Map<string, InventoryAnchor>();

export function writeInventoryAnchor(id: string, x: number, y: number): void {
  const existing = anchors.get(id);
  if (existing) {
    existing.x = x;
    existing.y = y;
    return;
  }
  anchors.set(id, { x, y });
}

export function readInventoryAnchor(id: string): InventoryAnchor | null {
  return anchors.get(id) ?? null;
}

export function dropInventoryAnchor(id: string): void {
  anchors.delete(id);
}

export function clearInventoryAnchors(): void {
  anchors.clear();
}
