/**
 * Raw input collection. Produces movement/shoot booleans and the mouse
 * position in CSS pixels; converting the mouse to world space needs the
 * camera, so that happens in game.ts.
 */

import type { MovementInput } from '../net/protocol';

const KEY_MAP: Record<string, keyof MovementInput> = {
  KeyW: 'up',
  ArrowUp: 'up',
  KeyS: 'down',
  ArrowDown: 'down',
  KeyA: 'left',
  ArrowLeft: 'left',
  KeyD: 'right',
  ArrowRight: 'right',
};

/** Toggles the lantern. Physical key, so it lands on F under any layout. */
const LANTERN_KEY = 'KeyF';
/** Ready at the campfire. Physical key, so it lands on E under any layout. */
const READY_KEY = 'KeyE';

export class InputController {
  readonly movement: MovementInput = { up: false, down: false, left: false, right: false };
  shooting = false;
  mouseX = 0;
  mouseY = 0;

  /**
   * Fired once per press of the lantern key — an EDGE, not a held state.
   * Auto-repeat is filtered out: holding F must not strobe the lamp thirty
   * times a second. The resulting on/off rides the input packet from `Lantern`.
   */
  onToggleLantern: (() => void) | null = null;
  /**
   * Fired once per press of E — interact. Camp fire is ready; a nearby drop
   * is collect. Same edge contract as the lantern key.
   */
  onInteract: (() => void) | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    window.addEventListener('blur', this.onBlur);
    window.addEventListener('mouseup', this.onMouseUp);
    canvas.addEventListener('mousemove', this.onMouseMove);
    canvas.addEventListener('mousedown', this.onMouseDown);
    canvas.addEventListener('contextmenu', this.onContextMenu);
  }

  /**
   * Remove every listener. The four `window` listeners in particular outlive
   * the canvas, so without this a remounted game keeps the old instance alive
   * and both react to the same keypress.
   */
  dispose(): void {
    window.removeEventListener('keydown', this.onKeyDown);
    window.removeEventListener('keyup', this.onKeyUp);
    window.removeEventListener('blur', this.onBlur);
    window.removeEventListener('mouseup', this.onMouseUp);
    this.canvas.removeEventListener('mousemove', this.onMouseMove);
    this.canvas.removeEventListener('mousedown', this.onMouseDown);
    this.canvas.removeEventListener('contextmenu', this.onContextMenu);
    this.onBlur();
  }

  private onContextMenu = (e: MouseEvent) => {
    e.preventDefault();
  };

  private onKeyDown = (e: KeyboardEvent) => {
    const key = KEY_MAP[e.code];
    if (key) {
      this.movement[key] = true;
      e.preventDefault();
      return;
    }
    if (e.code === LANTERN_KEY && !e.repeat) {
      this.onToggleLantern?.();
      e.preventDefault();
      return;
    }
    if (e.code === READY_KEY && !e.repeat) {
      this.onInteract?.();
      e.preventDefault();
    }
  };

  private onKeyUp = (e: KeyboardEvent) => {
    const key = KEY_MAP[e.code];
    if (key) {
      this.movement[key] = false;
      e.preventDefault();
    }
  };

  private onBlur = () => {
    this.movement.up = this.movement.down = this.movement.left = this.movement.right = false;
    this.shooting = false;
  };

  private onMouseMove = (e: MouseEvent) => {
    const rect = this.canvas.getBoundingClientRect();
    this.mouseX = e.clientX - rect.left;
    this.mouseY = e.clientY - rect.top;
  };

  private onMouseDown = (e: MouseEvent) => {
    if (e.button === 0) this.shooting = true;
  };

  private onMouseUp = (e: MouseEvent) => {
    if (e.button === 0) this.shooting = false;
  };
}
