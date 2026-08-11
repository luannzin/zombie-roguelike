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

export class InputController {
  readonly movement: MovementInput = { up: false, down: false, left: false, right: false };
  shooting = false;
  mouseX = 0;
  mouseY = 0;

  constructor(private readonly canvas: HTMLCanvasElement) {
    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    window.addEventListener('blur', this.onBlur);
    canvas.addEventListener('mousemove', this.onMouseMove);
    canvas.addEventListener('mousedown', this.onMouseDown);
    window.addEventListener('mouseup', this.onMouseUp);
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  private onKeyDown = (e: KeyboardEvent) => {
    const key = KEY_MAP[e.code];
    if (key) {
      this.movement[key] = true;
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
