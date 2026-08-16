/**
 * Held-gun atlas: one side-view frame per weapon, pointing right.
 *
 * Produced by server/tools/make_guns.py and served from /guns/.
 * The client rotates around `grip` and flips when aim is left.
 * Ground / HUD icons stay on the loot atlas — this sheet is IN HAND.
 *
 * Hand and muzzle math live here so the drawn barrel and the tracer
 * share one origin. Duplicating it in the entity layer is how a shot
 * used to leave the hip.
 */

import { loadImage, loadJson } from '../lib/image';

export interface GunFrame {
  frame: number;
  gripX: number;
  gripY: number;
  muzzleX: number;
  muzzleY: number;
  /**
   * World px along aim from the body centre to the grip: how far in front
   * of the character this weapon is CARRIED. A gun is at arm's length; the
   * knife is held in against the body and its value is negative.
   * Falls back to `GUN_HAND_ALONG` for an atlas that predates the field.
   */
  hold?: number;
  /** Multiplier on the drawn frame. 1 for everything but the knife. */
  scale?: number;
}

export interface GunAtlas {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, GunFrame>;
}

/**
 * World px along aim from body centre to the grip, for a weapon whose atlas
 * row does not carry its own `hold`. Held out at arm's length — see
 * `GunFrame.hold`, which is what actually decides it per weapon.
 */
export const GUN_HAND_ALONG = 3.0;
/** World px up from body centre to the chest / grip line. */
export const GUN_HAND_LIFT = 4.5;

export interface GunMuzzleArgs {
  x: number;
  y: number;
  ax: number;
  ay: number;
  weapon?: string | null;
  guns?: GunAtlas | null;
  pump?: number;
  kick?: number;
}

interface GunManifest {
  tile: number;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  items: Record<string, GunFrame>;
}

const ROOT = '/guns';

let atlasPromise: Promise<GunAtlas | null> | null = null;

export function loadGuns(): Promise<GunAtlas | null> {
  atlasPromise ??= fetchGuns();
  return atlasPromise;
}

async function fetchGuns(): Promise<GunAtlas | null> {
  try {
    const manifest = await loadJson<GunManifest>(`${ROOT}/manifest.json`);
    const image = await loadImage(`${ROOT}/sheet.png`);
    return {
      image,
      frameWidth: manifest.frameWidth,
      frameHeight: manifest.frameHeight,
      frames: manifest.frames,
      items: manifest.items,
    };
  } catch (err) {
    console.warn('[guns] no gun atlas, weapons draw as the old aim line:', err);
    return null;
  }
}

/** The weapon's atlas row, or undefined for an empty hand / unloaded atlas. */
function specOf(args: GunMuzzleArgs): GunFrame | undefined {
  return args.weapon && args.guns ? args.guns.items[args.weapon] : undefined;
}

/**
 * Grip in world pixels — the sprite rotates around this.
 *
 * How far out the hand sits is the WEAPON's, not this module's: a rifle is
 * pushed away from the chest and a knife is tucked against it, and one
 * constant for both puts the blade out where a barrel would be.
 */
export function gunHand(args: GunMuzzleArgs): { x: number; y: number } {
  const pump = args.pump ?? 0;
  const along = (specOf(args)?.hold ?? GUN_HAND_ALONG) + pump;
  return {
    x: args.x + args.ax * along,
    y: args.y - GUN_HAND_LIFT + args.ay * along,
  };
}

/** Barrel tip in world pixels. Tracers and flashes start here. */
export function gunMuzzle(args: GunMuzzleArgs): { x: number; y: number } {
  const hand = gunHand(args);
  const spec = specOf(args);
  if (!spec) {
    return { x: hand.x + args.ax * 6, y: hand.y + args.ay * 6 };
  }
  const angle = Math.atan2(args.ay, args.ax);
  const flip = args.ax < 0 ? -1 : 1;
  const kick = flip < 0 ? -(args.kick ?? 0) : (args.kick ?? 0);
  const theta = angle + kick;
  // Scaled with the sprite, or the tracer leaves a barrel the player is not
  // looking at.
  const scale = spec.scale ?? 1;
  const dx = (spec.muzzleX - spec.gripX) * scale;
  const dy = (spec.muzzleY - spec.gripY) * flip * scale;
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  return {
    x: hand.x + dx * cos - dy * sin,
    y: hand.y + dx * sin + dy * cos,
  };
}
