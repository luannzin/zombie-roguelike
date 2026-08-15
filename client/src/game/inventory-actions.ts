/**
 * HUD bag actions that have to hit the socket.
 *
 * React never owns the connection. `Game` binds the senders in `start()`
 * and clears them in `dispose()`.
 */

type DropFn = (slot: number) => void;

let dropFn: DropFn | null = null;

export function bindInventoryDrop(fn: DropFn | null): void {
  dropFn = fn;
}

export function requestInventoryDrop(slot: number): void {
  dropFn?.(slot);
}
