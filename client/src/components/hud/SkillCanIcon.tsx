/**
 * The tin a skill comes out of, as two CSS windows onto the skill atlas.
 *
 * It is the only sprite in this HUD that is a COMPOSITE: the body is one frame
 * of `/skills/can.png` picked by rarity, and the label picture is a frame of
 * `/skills/sheet.png` scaled into the window the manifest declares. Stamping
 * eighteen labels into five tins offline would be ninety frames of art that
 * all say the same thing twice.
 *
 * THE GEOMETRY IS READ, NOT WRITTEN HERE. Frame size, rarity order and the
 * label window all ride `manifest.json`, so the tin can be redrawn at another
 * size — it already has been, from a 16x24 aerosol tube to a 16x18 food tin —
 * without a number in this file moving. `loadSkills()` caches its promise, so
 * asking for the atlas here costs the same fetch the renderer already made.
 */

import { useEffect, useState } from 'react';
import { loadSkills, type SkillAtlas } from '../../render/skills';
import { cn } from '@/lib/utils';

export interface SkillCanIconProps {
  /** Which colourway. Anything unknown falls back to the first frame. */
  rarity: string;
  /** Index into the icon sheet — `config.skills[key].frame`. */
  frame: number;
  /** Screen pixels per source pixel. 2 — a drop's zoom, see `LootFly`. */
  zoom?: number;
  className?: string;
}

export function SkillCanIcon({ rarity, frame, zoom = 2, className }: SkillCanIconProps) {
  const atlas = useSkillAtlas();
  if (!atlas) return null;

  const tier = Math.max(0, atlas.rarities.indexOf(rarity));
  const [wx, wy, ww, wh] = atlas.window;
  const width = atlas.canWidth * zoom;
  const height = atlas.canHeight * zoom;

  return (
    <div
      aria-hidden="true"
      className={cn('pixelated relative shrink-0', className)}
      style={{
        width,
        height,
        backgroundImage: 'url(/skills/can.png)',
        backgroundRepeat: 'no-repeat',
        backgroundSize: `${atlas.rarities.length * width}px ${height}px`,
        backgroundPosition: `${-tier * width}px 0`,
      }}
    >
      <div
        className="pixelated absolute"
        style={{
          left: wx * zoom,
          top: wy * zoom,
          width: ww * zoom,
          height: wh * zoom,
          backgroundImage: 'url(/skills/sheet.png)',
          backgroundRepeat: 'no-repeat',
          backgroundSize: `${atlas.frames * ww * zoom}px ${wh * zoom}px`,
          backgroundPosition: `${-frame * ww * zoom}px 0`,
        }}
      />
    </div>
  );
}

/**
 * The atlas, once, shared by every tin on screen.
 *
 * Nothing renders until it resolves — a tin drawn at a guessed size and then
 * corrected a frame later is a sprite that visibly changes shape mid-flight,
 * and the fly it belongs to is only a second long.
 */
function useSkillAtlas(): SkillAtlas | null {
  const [atlas, setAtlas] = useState<SkillAtlas | null>(null);

  useEffect(() => {
    let live = true;
    void loadSkills().then((loaded) => {
      if (live) setAtlas(loaded);
    });
    return () => {
      live = false;
    };
  }, []);

  return atlas;
}
