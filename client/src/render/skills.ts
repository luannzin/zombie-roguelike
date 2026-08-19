/**
 * Skill atlas: the eighteen icons, and the canister they come out of.
 *
 * Produced by server/tools/make_skills.py and served from /skills/.
 * Frame index comes from `welcome.config.skills[key].frame` — the client never
 * invents a skill, exactly as it never invents a loot item.
 *
 * TWO SHEETS, AND NEITHER IS DRAWN ON THE CANVAS. The ICONS are drawn on the
 * HUD tray above the bag; the TIN is the sprite that comes out of the machine,
 * hangs over the winner's head and flies into that tray. Both of those are DOM
 * (`SkillCanIcon`, `LootFly`), so what this module ships is the GEOMETRY — how
 * big a frame is, which frame a rarity uses, where the label window sits — and
 * the images, so the fetch is shared and happens once.
 *
 * The tin was drawn on the canvas, lying on the machine's tray, until the
 * payout became a pickup like every other pickup. `lit` survives that as the
 * additive copy the world draw used; nothing reads it today.
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
