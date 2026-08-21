/**
 * Held-gun atlas: the pose maths and the frames a weapon is drawn from.
 *
 * Produced by server/tools/make_guns.py and served from /guns/.
 * The client rotates around `grip` and flips when aim is left.
 * Ground / HUD icons stay on the loot atlas — this sheet is IN HAND.
 *
 * ONE POSE, THREE READERS. The grip, the muzzle and the ejection port are all
 * the same rigid transform applied to three points of one frame, so it is
 * derived here — once — and the entity layer draws the sprite through the very
 * same numbers. Duplicating any part of it in the renderer is how a shot used
 * to leave the hip; guessing the port separately is how brass would start
 * falling out of the barrel.
 *
 * The atlas carries a CLOSED frame and an OPEN one per firearm (`cycleFrame`).
 * Nothing here decides which is drawn — that is the action clock in
 * `game/entity-visuals.ts` — but both frames share a grip, which is what lets
 * the renderer swap them mid-shot without the weapon jumping in the hand.
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
  /**
   * The same weapon with its action OPEN — slide to the rear, port showing.
   * Absent on the knife, which has nothing that reciprocates, and absent on
   * any atlas built before the action frames existed. Both are handled the
   * same way: no cycle frame means the weapon simply never opens.
   */
  cycleFrame?: number;
  /** The ejection port in frame pixels. Brass leaves from HERE, not the bore. */
  portX?: number;
  portY?: number;
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
/**
 * World px ABOVE THE FEET to the grip line, and the reason it is measured
 * from the feet rather than from the body's centre.
 *
 * It used to be 4.5 px up from the centre of the collision box, which is a
 * measurement of the wrong thing: the box is 7.2 px tall (`PLAYER_HALF_HEIGHT`
 * is 3.6) and the SPRITE standing on it is 16, so "up from the middle of the
 * box" put the grip somewhere around the character's chin. Every weapon in
 * the game was being held across its owner's face — which is the thing the
 * new player art made impossible to keep ignoring, because the new head is a
 * face rather than a dark cap.
 *
 * The sprite's own anatomy is what decides it (`server/tools/make_player.py`):
 * the coat runs rows 8..12 of the 16px cell and the sleeve ends in a hand
 * pixel at row 10-11, so the grip is five and a half pixels off the floor the
 * boots are standing on. Measured that way it is true for a body of any box
 * size, which is why the box's own height is an argument rather than a
 * constant here.
 */
export const GUN_GRIP_ABOVE_FEET = 5.5;
/**
 * World px the grip sits to one SIDE of the body's centreline when the body
 * is facing toward the camera or away from it.
 *
 * Nobody holds a weapon out of the middle of their chest, and at this size
 * that is not a detail — it is whether the weapon is visible at all. A body
 * walking AWAY has its weapon drawn behind it (see the entity layer), and a
 * rifle behind a sixteen-pixel back, on the centreline, is a rifle nobody can
 * see: the player loses track of what they are holding every time they walk
 * north. Off the midline it clears the silhouette on both vertical facings.
 *
 * It fades out with the heading rather than switching, because a weapon that
 * jumped two pixels sideways as the aim crossed the diagonal would be a twitch
 * on every mouse sweep. In profile it is zero — a weapon held out in front of
 * a body already clears it — so this only ever pays for the two facings that
 * need it.
 */
const GUN_GRIP_SIDE = 4.2;
/**
 * How far along the grip-to-muzzle span the off hand sits. Just past half:
 * far enough forward to be holding the weapon rather than the trigger hand,
 * short of the point where a barrel gets hot.
 */
const SUPPORT_ALONG = 0.55;

export interface GunMuzzleArgs {
  x: number;
  y: number;
  ax: number;
  ay: number;
  /**
   * The body's collision half-height. Its FEET are `y + halfHeight`, which is
   * what the grip line is measured from — see `GUN_GRIP_ABOVE_FEET`.
   *
   * Required rather than defaulted: a caller that does not know how tall the
   * thing holding the weapon is cannot place the weapon on it, and a default
   * would be a second copy of the player's box waiting to go stale the day
   * anything else picks a gun up.
   */
  halfHeight: number;
  weapon?: string | null;
  guns?: GunAtlas | null;
  pump?: number;
  kick?: number;
  /**
   * Screen-space radians the weapon is swung off the aim — a melee arc in
   * flight (`EntityVisuals.gunFeelOf().swing`), 0 for anything holding a gun.
   *
   * It rotates the HAND as well as the sprite, and that is the point of it
   * being here rather than only in the draw call. `hold` and `pump` push the
   * grip out along the AIM, which is correct for a barrel and wrong for a
   * blade a third of the way through a sweep: the arm would stay pointed at
   * the cursor while the knife swung off the end of it. Rotating the offset
   * with the blade is what makes the hand travel with the swing.
   */
  swing?: number;
  /**
   * World px the grip rides UP from the chest line — the weapon breathing,
   * the walk under it, and the dip a holstered weapon comes back out of.
   *
   * Screen-space vertical and never rotated with the aim, because that is
   * what the motion actually is: a weapon rises and falls IN THE FRAME as
   * the body carrying it does. Rotated with the barrel it would become a
   * push along the aim, which is `pump`, and the two would fight.
   */
  lift?: number;
}

/** The weapon's rigid transform for this frame: where it is and how it lies. */
export interface GunPose {
  /** The grip, in world px. The sprite turns around this. */
  x: number;
  y: number;
  /** Screen-space radians the frame is rotated by, kick and swing folded in. */
  theta: number;
  /** -1 when the aim is left and the frame is mirrored, +1 otherwise. */
  flip: number;
  /** The frame's draw scale. Folded into the zoom by the entity layer. */
  scale: number;
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
export function gunSpec(args: GunMuzzleArgs): GunFrame | undefined {
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
  const along = (gunSpec(args)?.hold ?? GUN_HAND_ALONG) + pump;
  // Off the FEET, not off the box's centre. See `GUN_GRIP_ABOVE_FEET`.
  const lift = GUN_GRIP_ABOVE_FEET - args.halfHeight + (args.lift ?? 0);
  // And off the centreline, on the side the sprite is mirrored to. See
  // `GUN_GRIP_SIDE` — zero in profile, full when facing the camera or away.
  const side = GUN_GRIP_SIDE * Math.abs(args.ay) * (args.ax < 0 ? -1 : 1);
  const swing = args.swing ?? 0;
  // The common case — a gun, no swing — skips two trig calls and the
  // rounding they would put on a value that has not changed.
  if (swing === 0) {
    return {
      x: args.x + args.ax * along - args.ay * side,
      y: args.y - lift + args.ay * along + args.ax * side,
    };
  }
  const cos = Math.cos(swing);
  const sin = Math.sin(swing);
  const dx = args.ax * cos - args.ay * sin;
  const dy = args.ay * cos + args.ax * sin;
  return {
    x: args.x + dx * along - dy * side,
    y: args.y - lift + dy * along + dx * side,
  };
}

/**
 * The whole pose in one place: grip, rotation, mirror and scale.
 *
 * A GUN'S KICK IS MIRRORED AND A BLADE'S SWING IS NOT, and the asymmetry is
 * the whole reason they are two arguments. `kick` is sprite-local — "the
 * muzzle rises", which is a different screen rotation depending on which way
 * the body faces — so it is negated with the flip. `swing` is already screen
 * space: "the blade is HERE", resolved against the same handedness the white
 * arc is drawn with. Mirroring it would uncross the two slashes of the chain
 * every time the player aimed left.
 */
export function gunPose(args: GunMuzzleArgs): GunPose {
  const hand = gunHand(args);
  const spec = gunSpec(args);
  const flip = args.ax < 0 ? -1 : 1;
  const kick = flip < 0 ? -(args.kick ?? 0) : (args.kick ?? 0);
  return {
    x: hand.x,
    y: hand.y,
    theta: Math.atan2(args.ay, args.ax) + kick + (args.swing ?? 0),
    flip,
    scale: spec?.scale ?? 1,
  };
}

/**
 * A point of the atlas frame, in world px, under the current pose.
 *
 * Frame pixels are measured from the grip, scaled with the sprite and
 * mirrored with it — a muzzle computed off a different pose than the one
 * drawn is a shot leaving a barrel the player is not looking at.
 */
function framePoint(args: GunMuzzleArgs, fx: number, fy: number): { x: number; y: number } {
  const pose = gunPose(args);
  const spec = gunSpec(args);
  if (!spec) {
    return { x: pose.x + args.ax * 6, y: pose.y + args.ay * 6 };
  }
  const dx = (fx - spec.gripX) * pose.scale;
  const dy = (fy - spec.gripY) * pose.flip * pose.scale;
  const cos = Math.cos(pose.theta);
  const sin = Math.sin(pose.theta);
  return {
    x: pose.x + dx * cos - dy * sin,
    y: pose.y + dx * sin + dy * cos,
  };
}

/** Barrel tip in world pixels. Tracers and flashes start here. */
export function gunMuzzle(args: GunMuzzleArgs): { x: number; y: number } {
  const spec = gunSpec(args);
  return framePoint(args, spec?.muzzleX ?? 0, spec?.muzzleY ?? 0);
}

/**
 * Where the support hand lies along the barrel, in world pixels.
 *
 * Derived from the frame rather than picked: a little over half way from the
 * grip to the muzzle is the handguard on every weapon on this sheet, because
 * the sheet draws every weapon at its real proportion. A constant number of
 * pixels forward would put the off hand on the AWP's barrel and past the end
 * of an MP7.
 */
export function gunSupport(args: GunMuzzleArgs): { x: number; y: number } {
  const spec = gunSpec(args);
  if (!spec) return gunHand(args);
  return framePoint(
    args,
    spec.gripX + (spec.muzzleX - spec.gripX) * SUPPORT_ALONG,
    spec.gripY + (spec.muzzleY - spec.gripY) * SUPPORT_ALONG,
  );
}

/**
 * The ejection port in world pixels — where the brass comes out.
 *
 * An atlas row without one falls back to the muzzle, which is where every
 * casing in this game used to be born: a shell leaving the front of the
 * barrel alongside the bullet, on the frame the trigger was pulled. The port
 * is a few pixels back and to the side, and that difference — plus the delay
 * the action clock puts on it — is the whole difference between brass thrown
 * out of a working mechanism and sparks coming off a muzzle.
 */
export function gunPort(args: GunMuzzleArgs): { x: number; y: number } {
  const spec = gunSpec(args);
  return framePoint(args, spec?.portX ?? spec?.muzzleX ?? 0, spec?.portY ?? spec?.muzzleY ?? 0);
}
