/**
 * Raw input collection. Produces movement/shoot/block booleans and the mouse
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

/**
 * RUN. Held, not toggled — and both shifts answer, because which hand is on
 * the movement keys decides which one is free.
 */
const SPRINT_KEYS = ['ShiftLeft', 'ShiftRight'];
/** Toggles the lantern. Physical key, so it lands on F under any layout. */
const LANTERN_KEY = 'KeyF';
/** Ready at the campfire. Physical key, so it lands on E under any layout. */
const READY_KEY = 'KeyE';
/** Expand the pocket. Tab is the key, not a code under a letter. */
const INVENTORY_KEY = 'Tab';
/**
 * Expand the armour mannequin. C, for "character".
 *
 * A SECOND DRAWER KEY AND NOT A SECOND TAB. The bag and the body are two
 * different questions — what am I carrying out, and what is keeping me alive —
 * and folding them into one toggle would mean a player checking their helmet
 * had to look at their loot as well, in a corner of the screen they are
 * fighting toward. It is a physical code like every other one here, so it
 * lands on C under any layout.
 */
const ARMOR_KEY = 'KeyC';
/**
 * THE ULTIMATE. R, and it is the only key in the game bound to a verb the
 * client does not predict at all.
 *
 * An EDGE, filtered against auto-repeat like the lantern's: holding R must
 * not spray the socket with activations that the server will refuse thirty
 * times a second. What happens is decided entirely server-side off what is in
 * the player's hands — see `protocol.MSG_ULT` — so there is nothing local to
 * latch and nothing to hold.
 */
const ULTIMATE_KEY = 'KeyR';
/** Two gun slots, then the blade on 3. See `server/app/weapons.py`. */
const HOTBAR_KEYS: Record<string, number> = {
  Digit1: 0,
  Digit2: 1,
  Digit3: 2,
  Numpad1: 0,
  Numpad2: 1,
  Numpad3: 2,
};

/**
 * The medical cells, on the keys straight after the belt's.
 *
 * A SEPARATE MAP AND A SEPARATE CALLBACK, not three more entries in
 * `HOTBAR_KEYS`, because they are not the same verb. A belt key SWAPS what is
 * in your hands and is free and instant; a medical key SPENDS something and
 * plants the body for seconds. Folding them into one handler would make the
 * two feel like neighbours on a strip, which is exactly the mistake that would
 * get a kit burned by somebody reaching for the knife.
 *
 * They are physical codes like everything else here, so they land on 4, 5 and
 * 6 under any layout. The COUNT lives on the server (`medical.MEDICAL_SLOTS`,
 * shipped as `config.medicalSlots`); a cell the loadout does not have is a key
 * the room refuses, which is cheaper than plumbing the config down here.
 */
const MEDICAL_KEYS: Record<string, number> = {
  Digit4: 0,
  Digit5: 1,
  Digit6: 2,
  Numpad4: 0,
  Numpad5: 1,
  Numpad6: 2,
};

export class InputController {
  readonly movement: MovementInput = { up: false, down: false, left: false, right: false };
  shooting = false;
  /**
   * SHIFT is down. A REQUEST to run and nothing more: whether the body
   * actually runs is decided against its breath, in `simulation.isRunning`,
   * by the same code the server runs.
   */
  sprinting = false;
  /**
   * RIGHT MOUSE is down. A REQUEST to raise the shield and nothing more:
   * whether it actually goes up is decided against what is in the hand and
   * what is left of the shield, in `Game.blocking`, by the same rule the
   * server runs.
   *
   * The second mouse button in the game. The context menu was already
   * suppressed on this canvas long before there was anything to put on the
   * button — see `onContextMenu` — so nothing about the page changes.
   */
  blocking = false;
  mouseX = 0;
  mouseY = 0;

  /**
   * Fired once per press of the lantern key — an EDGE, not a held state.
   * Auto-repeat is filtered out: holding F must not strobe the lamp thirty
   * times a second. The resulting on/off rides the input packet from `Lantern`.
   */
  onToggleLantern: (() => void) | null = null;
  /**
   * Fired once per press of E — interact. A nearby drop is collect; a crate
   * in reach is smash; the camp fire is ready. Same edge contract as the
   * lantern key.
   */
  onInteract: (() => void) | null = null;
  /**
   * E COMING BACK UP, and on losing focus. One object in the game is a HOLD
   * rather than a press (the vault — see `Room.cancel_force`), and this is the
   * edge that lets go of it. Fired unconditionally: whether a channel was
   * running is the game's question, not the keyboard's.
   */
  onInteractEnd: (() => void) | null = null;
  /** Expand the pocket. Tab is the key, not a code under a letter. */
  onToggleInventory: (() => void) | null = null;
  /** Expand the armour mannequin. See `ARMOR_KEY`. */
  onToggleArmor: (() => void) | null = null;
  /** Fire the ultimate of the weapon in hand. See `ULTIMATE_KEY`. */
  onUltimate: (() => void) | null = null;
  /** Fired once per 1/2/3. `slot` is 0..2 — 2 is the knife. Edge, not held. */
  onHotbar: ((slot: number) => void) | null = null;
  /** A medical cell was pressed. See `MEDICAL_KEYS` for why it is its own. */
  onMedical: ((cell: number) => void) | null = null;

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
    if (SPRINT_KEYS.includes(e.code)) {
      this.sprinting = true;
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
      return;
    }
    if (e.code === INVENTORY_KEY && !e.repeat) {
      this.onToggleInventory?.();
      e.preventDefault();
      return;
    }
    if (e.code === ARMOR_KEY && !e.repeat) {
      this.onToggleArmor?.();
      e.preventDefault();
      return;
    }
    if (e.code === ULTIMATE_KEY && !e.repeat) {
      this.onUltimate?.();
      e.preventDefault();
      return;
    }
    const slot = HOTBAR_KEYS[e.code];
    if (slot !== undefined && !e.repeat) {
      this.onHotbar?.(slot);
      e.preventDefault();
      return;
    }
    const cell = MEDICAL_KEYS[e.code];
    if (cell !== undefined && !e.repeat) {
      this.onMedical?.(cell);
      e.preventDefault();
    }
  };

  private onKeyUp = (e: KeyboardEvent) => {
    const key = KEY_MAP[e.code];
    if (key) {
      this.movement[key] = false;
      e.preventDefault();
      return;
    }
    if (SPRINT_KEYS.includes(e.code)) this.sprinting = false;
    if (e.code === READY_KEY) this.onInteractEnd?.();
  };

  private onBlur = () => {
    this.movement.up = this.movement.down = this.movement.left = this.movement.right = false;
    this.shooting = false;
    // A window that lost focus under a held SHIFT never sees the keyup, and a
    // body that came back sprinting on nobody's finger would empty the bar.
    // Same for the shield: a body still braced behind one nobody is holding
    // would be slow for no reason the player can see.
    this.sprinting = false;
    this.blocking = false;
    // A window that lost focus mid-hold never sees the keyup either, and a
    // vault that kept opening off a finger nobody has on the key is the same
    // bug as the sprint above with a payout attached.
    this.onInteractEnd?.();
  };

  private onMouseMove = (e: MouseEvent) => {
    const rect = this.canvas.getBoundingClientRect();
    this.mouseX = e.clientX - rect.left;
    this.mouseY = e.clientY - rect.top;
  };

  private onMouseDown = (e: MouseEvent) => {
    if (e.button === 0) this.shooting = true;
    if (e.button === 2) this.blocking = true;
  };

  private onMouseUp = (e: MouseEvent) => {
    if (e.button === 0) this.shooting = false;
    if (e.button === 2) this.blocking = false;
  };
}
