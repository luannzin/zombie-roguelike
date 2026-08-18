/**
 * Skill atlas: the eighteen icons, and the canister they come out of.
 *
 * Produced by server/tools/make_skills.py and served from /skills/.
 * Frame index comes from `welcome.config.skills[key].frame` — the client never
 * invents a skill, exactly as it never invents a loot item.
 *
 * TWO SHEETS, THREE PLACES. The ICONS are drawn on the HUD tray above the bag,
 * and again — scaled into the canister's window — on the canister itself. The
 * CANISTER is drawn in the world when a machine pays out, and once more as the
 * sprite that flies into the tray. Everything else about a skill is text.
 *
 * `can` takes the darkness multiply like any prop; `lit` is the additive copy
 * and carries only the parts that emit, so a legendary lying on a tray in a
 * dark glade is visible from the far end of the lane and a common one is not.
 */

import { loadImage, loadJson } from '../lib/image';

export interface SkillAtlas {
  image: HTMLImageElement;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  frameOf: Record<string, number>;
  /** The canister body, in rarity order. */
  can: HTMLImageElement;
  /** The same canister's emissive pass, for the additive draw. */
  lit: HTMLImageElement;
  canWidth: number;
  canHeight: number;
  /** Rarity order of the canister frames. */
  rarities: string[];
  /** `[x, y, w, h]` of the window the icon is stamped into, in frame pixels. */
  window: [number, number, number, number];
}

interface SkillManifest {
  icons: { file: string; frameWidth: number; frameHeight: number; frames: number };
  frames: Record<string, number>;
  can: {
    file: string;
    litFile: string;
    frameWidth: number;
    frameHeight: number;
    frames: number;
    rarities: string[];
    window: [number, number, number, number];
  };
}

const ROOT = '/skills';

let atlasPromise: Promise<SkillAtlas | null> | null = null;

export function loadSkills(): Promise<SkillAtlas | null> {
  atlasPromise ??= fetchSkills();
  return atlasPromise;
}

async function fetchSkills(): Promise<SkillAtlas | null> {
  try {
    const manifest = await loadJson<SkillManifest>(`${ROOT}/manifest.json`);
    const [image, can, lit] = await Promise.all([
      loadImage(`${ROOT}/${manifest.icons.file}`),
      loadImage(`${ROOT}/${manifest.can.file}`),
      loadImage(`${ROOT}/${manifest.can.litFile}`),
    ]);
    return {
      image,
      frameWidth: manifest.icons.frameWidth,
      frameHeight: manifest.icons.frameHeight,
      frames: manifest.icons.frames,
      frameOf: manifest.frames,
      can,
      lit,
      canWidth: manifest.can.frameWidth,
      canHeight: manifest.can.frameHeight,
      rarities: manifest.can.rarities,
      window: manifest.can.window,
    };
  } catch (err) {
    console.warn('[skills] no skill atlas:', err);
    atlasPromise = null;
    return null;
  }
}

/** Which canister frame a rarity uses. Falls back to the first. */
export function canFrame(atlas: SkillAtlas, rarity: string): number {
  const index = atlas.rarities.indexOf(rarity);
  return index >= 0 ? index : 0;
}

/**
 * Draw one canister with its icon in the window, centred on `(cx, bottom)`.
 *
 * The three passes go in one call because their order is not negotiable and
 * splitting them across call sites is how an icon ends up painted over the
 * emissive rim: body, then icon, then the lit copy on top additively.
 */
export function drawCanister(
  ctx: CanvasRenderingContext2D,
  atlas: SkillAtlas,
  rarity: string,
  iconFrame: number,
  cx: number,
  bottom: number,
  scale: number,
  glow = 1,
): void {
  const frame = canFrame(atlas, rarity);
  const w = atlas.canWidth * scale;
  const h = atlas.canHeight * scale;
  const left = Math.round(cx - w / 2);
  const top = Math.round(bottom - h);
  ctx.drawImage(
    atlas.can,
    frame * atlas.canWidth, 0, atlas.canWidth, atlas.canHeight,
    left, top, w, h,
  );

  const [wx, wy, ww, wh] = atlas.window;
  ctx.drawImage(
    atlas.image,
    iconFrame * atlas.frameWidth, 0, atlas.frameWidth, atlas.frameHeight,
    left + wx * scale, top + wy * scale, ww * scale, wh * scale,
  );

  if (glow > 0) {
    const previous = ctx.globalCompositeOperation;
    const alpha = ctx.globalAlpha;
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = alpha * Math.min(1, glow);
    ctx.drawImage(
      atlas.lit,
      frame * atlas.canWidth, 0, atlas.canWidth, atlas.canHeight,
      left, top, w, h,
    );
    ctx.globalAlpha = alpha;
    ctx.globalCompositeOperation = previous;
  }
}
