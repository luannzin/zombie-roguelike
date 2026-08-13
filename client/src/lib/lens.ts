/**
 * Barrel ("fish eye") displacement map, as a PNG data URL.
 *
 * SVG's `feDisplacementMap` bends a layer by reading a second image: the red
 * channel of each texel says how far to move that pixel horizontally, the green
 * channel vertically, with 0.5 meaning "don't". So a lens is not code that runs
 * per pixel — it is a small picture of where every pixel should come from, and
 * the compositor does the sampling. This builds that picture once per size and
 * hands back the data URL plus the `scale` the filter must be given.
 *
 * The profile is the classic barrel: sample at `p * (1 + k(r² - 1))`, which
 * leaves the four edge midpoints (r = 1) exactly where they are, magnifies the
 * middle, and pulls the CORNERS inward — corners sit at r = √2, well past the
 * fixed ring. That last part is the whole point here, because a HUD lives in
 * its corners: a lens that fades out at the rim would bulge an empty middle and
 * leave every panel untouched.
 *
 * `lens` is expressed as the fraction of a half-screen that a corner travels,
 * so it is aspect-independent and readable: 0.02 means "corners come in by 2%
 * of half the screen", about 19px across a 1920px viewport.
 *
 * Encoding note: the spec's displacement is `scale * (channel - 0.5)` with the
 * channel in 0..1, so the usable range is ±scale/2 and `scale` comes back as
 * twice the peak displacement. Alpha is forced opaque — a translucent map gets
 * premultiplied on the way in and the field comes out wrong.
 */

import { createSurface } from './canvas';

export interface LensMap {
  /** PNG data URL for `feImage`. */
  url: string;
  /** What `feDisplacementMap.scale` must be set to for this map. */
  scale: number;
}

/**
 * The map is a smooth quadratic field, so it is generated small and stretched
 * across the viewport by the filter, which reconstructs it closely enough that
 * a bigger map changes nothing visible.
 *
 * What IS visible: browsers resample the displaced layer with nearest
 * neighbour, so a 1px line crossing the lens steps rather than curving
 * smoothly. That is left alone deliberately — the alternative is a filtered,
 * softened HUD, and this game's type is a pixel face that must not be blurred.
 * Stepping reads as pixel art; blur reads as a mistake.
 */
const RESOLUTION = 96;

export function barrelMap(width: number, height: number, lens: number): LensMap {
  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const offsets = new Float32Array(RESOLUTION * RESOLUTION * 2);
  let peak = 0;

  for (let row = 0; row < RESOLUTION; row++) {
    const v = ((row + 0.5) / RESOLUTION) * 2 - 1;
    for (let col = 0; col < RESOLUTION; col++) {
      const u = ((col + 0.5) / RESOLUTION) * 2 - 1;
      // Negative inside the fixed ring (content spreads outward = magnified),
      // positive outside it (content is drawn from further out = pulled in).
      const bow = lens * (u * u + v * v - 1);
      const dx = u * bow * halfWidth;
      const dy = v * bow * halfHeight;
      const index = (row * RESOLUTION + col) * 2;
      offsets[index] = dx;
      offsets[index + 1] = dy;
      peak = Math.max(peak, Math.abs(dx), Math.abs(dy));
    }
  }

  const scale = Math.max(1, peak * 2);
  const surface = createSurface(RESOLUTION, RESOLUTION, 'lens');
  const image = surface.ctx.createImageData(RESOLUTION, RESOLUTION);
  for (let i = 0; i < RESOLUTION * RESOLUTION; i++) {
    const pixel = i * 4;
    image.data[pixel] = Math.round((0.5 + offsets[i * 2] / scale) * 255);
    image.data[pixel + 1] = Math.round((0.5 + offsets[i * 2 + 1] / scale) * 255);
    image.data[pixel + 2] = 0;
    image.data[pixel + 3] = 255;
  }
  surface.ctx.putImageData(image, 0, 0);

  return { url: surface.canvas.toDataURL('image/png'), scale };
}
