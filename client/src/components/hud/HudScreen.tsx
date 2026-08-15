/**
 * The HUD is a screen, and this is the glass.
 *
 * Everything the player reads is wrapped in one SVG filter that does three
 * things, in this order:
 *
 *   FISH EYE   a barrel displacement (see `lib/lens.ts`) bows the whole overlay
 *              as if it were painted on a curved tube. Static — it is the shape
 *              of the display, not an animation.
 *   TEAR       stretched-horizontal turbulence, driven into the same kind of
 *              displacement, rips the picture into sliding bands. Zero at rest.
 *   SPLIT      the red and blue channels slide apart. Green carries almost all
 *              the luminance, so text stays readable while the edges go
 *              prismatic — which is what makes this read as a bad signal rather
 *              than as blur.
 *
 * The last two only wake up during GLITCH BURSTS, and this is where the file
 * earns its place: bursts are scheduled with a timeout, run for a couple of
 * hundred milliseconds under rAF, and then the attributes are reset to zero and
 * the loop goes back to sleep. A permanently-running rAF that writes zeroes
 * would make a full-screen filter recompute every frame forever.
 *
 * Bursts get shorter-fused and harder when `unstable` is set, which the arena
 * wires to the lantern's last cell. The screen and the lamp fail together: by
 * the time you notice the HUD tearing you have already seen the light drop out,
 * and the two reinforce each other instead of being separate warnings.
 *
 * React is not in this loop. The scheduler mutates filter attributes through
 * refs, exactly like the game mutates canvas pixels — the same rule the rest of
 * the project follows (see the architecture notes in README).
 */

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { barrelMap, HUD_LENS } from '@/lib/lens';
/** Peak horizontal tear, in px, at full burst strength. */
const TEAR_PX = 13;
/** Peak channel separation, in px. Beyond ~3 the text stops being readable. */
const SPLIT_PX = 2.2;
/** Peak whole-overlay jolt, in px. */
const JOLT_PX = 3;

/** Seconds between bursts when the lantern is healthy, and when it is failing. */
const CALM_GAP = [7, 22] as const;
const UNSTABLE_GAP = [0.9, 4.5] as const;
/** Burst length in seconds, and its strength envelope, per state. */
const CALM_BURST = [0.07, 0.19] as const;
const UNSTABLE_BURST = [0.1, 0.34] as const;
const CALM_FORCE = [0.28, 0.7] as const;
const UNSTABLE_FORCE = [0.55, 1] as const;

export interface HudScreenProps {
  /** Tear more, and more often. The arena passes the lantern's failing state. */
  unstable: boolean;
  children: ReactNode;
}

export function HudScreen({ unstable, children }: HudScreenProps) {
  // useId can emit colons, which are legal in an id but not in `url(#…)`.
  const filterId = `hud-screen-${useId().replace(/[^a-zA-Z0-9-]/g, '')}`;

  const root = useRef<HTMLDivElement>(null);
  const warp = useRef<SVGFEImageElement>(null);
  const bulge = useRef<SVGFEDisplacementMapElement>(null);
  const noise = useRef<SVGFETurbulenceElement>(null);
  const tear = useRef<SVGFEDisplacementMapElement>(null);
  const splitLow = useRef<SVGFEOffsetElement>(null);
  const splitHigh = useRef<SVGFEOffsetElement>(null);

  // Read by the burst loop without restarting it.
  const unstableRef = useRef(unstable);
  useEffect(() => {
    unstableRef.current = unstable;
  }, [unstable]);

  // The lens is measured off the WRAPPER, not off `window`. Two reasons, and
  // the first one bites: the filter region is this element's bounding box, so
  // anything else is a lens for a different rectangle — and an effect body can
  // run before that box has been laid out, where `window.innerWidth` is a
  // plausible-looking number that produces a silently flat map.
  //
  // A ResizeObserver answers both (it fires once on observe, with a real box)
  // and matches how the game sizes its canvas. Rebuilds are coalesced to one
  // per frame: a drag-resize fires far faster than a canvas readback wants to
  // run.
  useEffect(() => {
    const box = root.current;
    if (!box) return;
    let pending = 0;

    const build = () => {
      pending = 0;
      const { width, height } = box.getBoundingClientRect();
      if (width < 1 || height < 1) return;

      const map = barrelMap(width, height, HUD_LENS);
      const image = warp.current;
      if (image) {
        image.setAttribute('href', map.url);
        // Safari still resolves feImage through the xlink form.
        image.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', map.url);
      }
      bulge.current?.setAttribute('scale', map.scale.toFixed(2));
    };

    const observer = new ResizeObserver(() => {
      if (pending === 0) pending = requestAnimationFrame(build);
    });
    observer.observe(box);

    return () => {
      observer.disconnect();
      if (pending !== 0) cancelAnimationFrame(pending);
    };
  }, []);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let timer = 0;
    let frame = 0;
    let start = 0;
    let length = 0;
    let force = 0;

    /** Park every animated primitive at "no effect". */
    const settle = () => {
      tear.current?.setAttribute('scale', '0');
      splitLow.current?.setAttribute('dx', '0');
      splitHigh.current?.setAttribute('dx', '0');
      if (root.current) root.current.style.transform = '';
    };

    const step = (now: number) => {
      const progress = (now - start) / length;
      if (progress >= 1) {
        settle();
        schedule();
        return;
      }
      // A half-sine flattened at the top: the fault snaps in, holds, snaps out.
      // A linear ramp reads as a fade, which is the one thing a glitch is not.
      const shove = Math.sin(Math.PI * progress) ** 0.55 * force;

      tear.current?.setAttribute('scale', (shove * TEAR_PX).toFixed(2));
      // Per-frame jitter on top of the envelope, so successive frames of one
      // burst do not interpolate into a smooth slide.
      const split = shove * SPLIT_PX * (0.6 + Math.random() * 0.7);
      splitLow.current?.setAttribute('dx', (-split).toFixed(2));
      splitHigh.current?.setAttribute('dx', split.toFixed(2));
      if (root.current) {
        const jolt = (Math.random() * 2 - 1) * shove * JOLT_PX;
        root.current.style.transform = `translate3d(${jolt.toFixed(2)}px,0,0)`;
      }
      frame = requestAnimationFrame(step);
    };

    const burst = () => {
      const hot = unstableRef.current;
      length = randomIn(hot ? UNSTABLE_BURST : CALM_BURST) * 1000;
      force = randomIn(hot ? UNSTABLE_FORCE : CALM_FORCE);
      // A fresh noise field per burst: reusing one makes every tear identical.
      noise.current?.setAttribute('seed', String(Math.floor(Math.random() * 9999)));
      start = performance.now();
      frame = requestAnimationFrame(step);
    };

    const schedule = () => {
      const gap = randomIn(unstableRef.current ? UNSTABLE_GAP : CALM_GAP);
      timer = window.setTimeout(burst, gap * 1000);
    };

    schedule();
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(frame);
      settle();
    };
  }, []);

  return (
    <>
      <svg className="hud-fx-defs" aria-hidden="true" focusable="false">
        <defs>
          {/*
            The filter region is pinned to the bounding box (the viewport) so
            that lens space and screen space are the same space. The default
            region is 10% larger, which would silently rescale the map.
          */}
          <filter
            id={filterId}
            filterUnits="objectBoundingBox"
            x="0"
            y="0"
            width="100%"
            height="100%"
            colorInterpolationFilters="sRGB"
          >
            <feImage ref={warp} preserveAspectRatio="none" result="lens" />
            <feDisplacementMap
              ref={bulge}
              in="SourceGraphic"
              in2="lens"
              scale="0"
              xChannelSelector="R"
              yChannelSelector="G"
              result="curved"
            />

            <feTurbulence
              ref={noise}
              type="fractalNoise"
              baseFrequency="0.005 0.7"
              numOctaves="1"
              seed="1"
              result="static"
            />
            {/*
              Flatten green to a constant 0.5 — that channel is the vertical
              displacement, and this tear only slides sideways. Alpha is forced
              opaque for the same reason the lens map is.
            */}
            <feColorMatrix
              in="static"
              type="matrix"
              values="1 0 0 0 0  0 0 0 0 0.5  0 0 0 0 0  0 0 0 0 1"
              result="bands"
            />
            <feDisplacementMap
              ref={tear}
              in="curved"
              in2="bands"
              scale="0"
              xChannelSelector="R"
              yChannelSelector="G"
              result="torn"
            />

            {/* Channel split. At dx = 0 the three layers recombine exactly. */}
            <feOffset ref={splitLow} in="torn" dx="0" dy="0" result="lowShift" />
            <feOffset ref={splitHigh} in="torn" dx="0" dy="0" result="highShift" />
            <feColorMatrix
              in="lowShift"
              type="matrix"
              values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
              result="red"
            />
            <feColorMatrix
              in="torn"
              type="matrix"
              values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0"
              result="green"
            />
            <feColorMatrix
              in="highShift"
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"
              result="blue"
            />
            <feBlend in="red" in2="green" mode="screen" result="warmChannels" />
            <feBlend in="warmChannels" in2="blue" mode="screen" />
          </filter>
        </defs>
      </svg>

      <div ref={root} className="hud-screen" style={{ filter: `url(#${filterId})` }}>
        {children}
      </div>
    </>
  );
}

function randomIn([lo, hi]: readonly [number, number]): number {
  return lo + Math.random() * (hi - lo);
}
