# Pixel-Art Direction

Visual language extracted from the reference sheets. Rules, not descriptions —
enough to draw a **new** object that reads as the same artist's hand.

**Scope caveat.** The references are not one single set. Eight of nine share one
language and are the basis for this spec. Two are excluded or fenced off:

- **Statue sheet** (grayscale, black background, pre-rendered soft anti-aliasing,
  smooth gradients) — a different school entirely. Not part of this spec.
- **Weapon icon sheet** (flat side elevation, no ground plane) — a separate
  *icon* sub-mode, specified in §21. It shares the palette and outline logic but
  not the camera.

---

## 1. Camera

| rule | value |
| --- | --- |
| projection | axonometric. No perspective, no vanishing point |
| pitch | ~55–60° above horizon (high 3/4). Top plane visible, never dominant |
| yaw | 45° — two vertical planes visible, roughly equal weight |
| variant A | strict 2:1 dimetric (true iso) for man-made boxy objects |
| variant B | loosened free-3/4 for organic mass (rock, foliage) |
| forbidden | true top-down (90°), true side (0°), lens tilt, foreshortening ramps |

The object rotates **into** the camera; the camera never moves. Every asset in a
set shares one yaw. No per-object rotation.

## 2. Volume construction

Form is a **stack of convex masses**, never one hull.

- Break the object into 3–7 sub-blobs. Each sub-blob gets its own full ramp.
- Sub-blob boundaries read by **value step**, not by line.
- No smooth gradient anywhere. Volume = facet + band.
- Mass sizes descend roughly `1 : 0.6 : 0.4`. Equal-sized blobs read as pattern,
  not as form.

## 3. Plane proportions

| plane | share of silhouette | ramp step |
| --- | --- | --- |
| top (lit) | 35–45% | 3–4 |
| upper-left side (key) | 25–30% | 3 |
| lower-right side (shade) | 25–35% | 1–2 |

Height : footprint runs **1.1:1 → 1.6:1**. Objects are tall. Squat is wrong.

## 4. Pixel density

- Strict 1:1 pixel grid. One resolution per sheet. Zero anti-aliasing, zero
  sub-pixel work, zero soft brush.
- Prop working sizes: **16 / 24 / 32 / 48 / 64 px** footprint. Hero prop 128 max.
- All pixels square. Never scale by a non-integer factor.
- Detail frequency stays constant across an asset — no fine noise adjacent to
  flat mass.

## 5. Pixel cluster structure

- Minimum meaningful cluster is **2×2**. An orphan single pixel is allowed only
  as a specular hit or an edge break — 3 per sprite maximum.
- Slopes run in clean lengths: 1:1, 1:2, 2:1, 1:4. Never `3-2-3-2` jitter.
- No jaggies (a broken run mid-line), no doubles (a 1px protrusion off a clean
  edge).
- Texture is **clustered shape**, never scattered noise. Dithering appears only
  as a deliberate two-tone material band (rock grit), one band per sprite max.

## 6. Outline

**Selective, hue-tinted, never pure black.**

| where | treatment |
| --- | --- |
| exterior silhouette | 1px, colour = darkest ramp step, hue −15°, value −25% |
| exterior bottom edge | outline darkens further (contact), still 1px |
| exterior top-lit edge | outline may drop entirely — light eats the line |
| interior form breaks | **no line** — value step only |
| man-made / hard-surface class | closed 1px outline all round, higher contrast |
| organic class | broken outline, absent along the lit crest |

Outline is 1px at every asset size. It never thickens.

## 7. Shading method

Hard cel bands on a fixed 5-step ramp per material:

```
0  outline / contact    darkest, most hue-shifted, coolest
1  core shadow
2  base                 largest area
3  key light
4  specular accent      smallest area, <=5% of pixels
```

- Step 2 owns the most pixels. Step 4 owns the fewest.
- The terminator follows form curvature — never a straight cut.
- **No bounce light** on the shade side, except a single 1px rim at the base of
  round masses.
- No gradients, no soft falloff, no additive glow (emissive material aside, §14).

## 8. Light direction

- One key light. Azimuth **135° (upper-left)**, elevation **~60°**.
- Identical across every asset in the world. Never re-light per object.
- No fill light, no opposite-side rim.
- Ambient exists only as ramp step 2 — it is the "unlit" reference, not black.

## 9. Shadow construction

The ground shadow is a **separate flat element**, not projected geometry.

| property | value |
| --- | --- |
| shape | ellipse / soft blob echoing the *footprint*, not the silhouette |
| width | 0.9–1.15 × footprint width |
| height | 0.28–0.35 × its own width |
| offset | right **+8–15%** of sprite width, down **+3–6%** |
| colour | flat multiply: background hue, value −30%, sat +10% toward blue |
| edge | one soft step (2 alpha bands max) or a single hard flat blob |
| tall objects | shadow stretches down-right, same offset ratio |

The shadow never carries detail, and overlapping shadows never stack darker.

## 10. Ambient occlusion

- A 1–2px darkening band where mass meets ground, **inside** the sprite, sitting
  above the drop shadow.
- 1px darkening where a sub-blob tucks behind another.
- AO tone is ramp step 0. Never black, never a foreign hue.
- Local contact only. No global AO wash, no vignette.

## 11. Colour palette

Global palette of **32–48 colours**: 6–8 ramps × 5 steps, plus 2–3 shared
neutrals.

Ramp construction for a material hue `H`:

| step | value (L) | saturation | hue shift |
| --- | --- | --- | --- |
| 0 | 18–24 | +10% | H − 18° (toward blue/violet) |
| 1 | 32–40 | +6% | H − 10° |
| 2 | 50–58 | base | H |
| 3 | 66–74 | −5% | H + 8° (toward yellow) |
| 4 | 80–88 | −18% | H + 14° |

- **Hue shifts on every step.** A ramp that only changes value is wrong.
- Shadows go cool, lights go warm. Never the reverse.
- Ramps share endpoints across materials where possible — palette economy is
  what makes a world look authored rather than assembled.
- Canvas / background: desaturated neutral (sage-grey, warm sand, muted violet).
  Never white, never pure black.

## 12. Saturation

- Base step sits at **S ≈ 25–45%**. Nothing screams.
- Saturation peaks in the mid-to-shadow range and **drops at the highlight**.
  Highlights desaturate toward a warm off-white, never toward pure white.
- One accent hue per sprite, S 60–75%, occupying ≤8% of pixels. That accent is
  the eye anchor and there is only ever one.

## 13. Contrast

- **High silhouette contrast** against the background: ≥35 L between the object's
  darkest step and the canvas. Readability first.
- **Moderate internal contrast**: step 1 → step 4 spans ~55 L, not 100.
- Pure `#000` and `#FFF` never appear.
- Contrast is a hierarchy tool. The focal mass gets the full 5-step ramp;
  background sub-masses get steps 1–3 only.

## 14. Material rendering

Material reads through **cluster geometry and specular behaviour**, not through
texture noise.

| material | cluster shape | specular | edge |
| --- | --- | --- | --- |
| stone / rock | flat angular facets, 4–8px chips, straight breaks | none; step 4 as a thin crest only | chipped, irregular |
| crystal / ice | tall prisms, parallel 1px inner lines | hard 2×2 white-warm hit per face | sharp, near-straight |
| foliage | lobed clumps, 3–5px bites out of the edge | none; light is a broad top-plane wash | ragged, notched |
| bark / wood | long banded strips along the grain axis | none | straight, slightly frayed |
| dirt / organic mass | round overlapping bulbs | soft 2px crown per bulb | bumpy, no straight runs |
| painted metal | large flat planes, one value each | one long 1–2px streak along the form's length | closed hard outline |
| bare metal | as above, plus a tight step-4 to step-1 jump | narrow, high contrast, near white | closed hard outline |
| glass | flat step-3 fill, two parallel diagonal 1px streaks | the streaks *are* the material | outlined, tinted cool |
| cloth / fabric | wide soft bands, low step count (3 tones) | none | soft, drooping |
| cardboard / paper | flat planes, sparse 2px scuffs | none | clean, with 1px torn nicks |
| emissive | flat step-4 core + one step-3 halo ring, no glow blur | is its own source; ignores §8 | no outline on the lit face |

Rule of thumb: change **how the pixels clump** before changing how many colours
you use.

## 15. Silhouette design

- Must read at 1× against a flat background, in solid black, with zero interior
  detail. Test this first, always.
- Asymmetric. Perfect bilateral symmetry is banned for organic assets and
  tolerated only for man-made ones.
- Bite negative space **into** the edge — 2–4px notches at irregular intervals —
  so the outline is never a smooth arc.
- The top contour carries the identity. Distinguish assets by their upper
  profile, not by colour.
- One dominant direction of thrust per asset. No two-headed shapes.

## 16. Level of detail

Detail budget scales with size, and smaller variants **delete** detail rather
than shrinking it.

| footprint | sub-masses | ramp steps | accent |
| --- | --- | --- | --- |
| 64px | 5–7 | 5 | yes |
| 48px | 4–5 | 5 | yes |
| 32px | 3–4 | 4 (drop step 4) | optional |
| 24px | 2–3 | 3 (drop steps 0, 4 merged) | no |
| 16px | 1–2 | 3 | no |

The ladder keeps one shared design DNA: same hue, same top contour, same lean.
A size ladder is a family, not five separate drawings.

## 17. Object proportions

- Chunky and slightly squashed. Real-world proportion is a starting point, then
  the readable feature is enlarged 15–30% and everything else compressed.
- The base is wider than the crown for grounded objects; the reverse only for
  objects meant to read as unstable.
- Repeated elements are sized to a `1 : 0.7 : 0.5` rhythm. Never uniform.

## 18. Depth cues

Ranked by strength, all of which are in play:

1. **Overlap** — near masses cut into far masses, with 1px AO at the seam.
2. **Shadow offset** — the constant down-right offset fixes the ground plane.
3. **Top-plane brightness** — anything facing up is brighter; that alone conveys
   pitch.
4. **Value compression with distance** — background elements lose steps 0 and 4,
   sitting entirely in the middle of the ramp.
5. **Vertical position** — lower on the canvas reads as nearer. Sorting is by
   footprint baseline, never by sprite top.

No atmospheric hue shift, no blur, no scale-based DOF.

## 19. Ground contact

- Every world asset sits on its offset shadow. Nothing floats.
- The contact edge is the darkest part of the sprite — a 1–2px band, ramp step 0.
- The footprint is narrower than the widest part of the object; a slight
  undercut sells the mass.
- Objects that emerge from ground get 2–4px of skirt debris/tuft breaking the
  ellipse, so the silhouette and the shadow are not two concentric shapes.

## 20. Overall visual identity

> Chunky, cel-banded, high-3/4 props on a neutral field. Warm single key from the
> upper-left, cool hue-shifted shadows, one accent hue per object, a tinted 1px
> outline that gives way where the light hits, and a soft offset ground shadow
> that plants everything. Readable in silhouette at 1× before any colour lands.

Three things make it cohere and any one of them broken kills the set: **one light
direction**, **one shared palette with hue-shifted ramps**, **one ground-shadow
convention**.

## 21. Icon sub-mode

For inventory/UI items, not world props:

- Camera drops to **flat side elevation**, orthographic, no ground plane.
- Framing: item on a saturated flat field, presented at a slight down-right
  diagonal, long axis roughly 15–20° off horizontal.
- Outline becomes **fully closed and higher contrast** than world props.
- Drop shadow becomes a **hard offset silhouette copy** (down-right 2–3px, single
  flat dark tone), not an ellipse.
- The palette, the 5-step ramps, the hue-shift rule and the cluster rules all
  carry over unchanged.
- Keying: an item's variant/tier is signalled by the accent hue only. Geometry
  stays close across a tier family.

---

## Checklist before an asset ships

1. Silhouette in solid black, at 1×, on the canvas colour — is it identifiable?
2. Light from 135°/60° — no exceptions, no second source?
3. Exactly 5 ramp steps, each with a hue shift, no invented colours?
4. Step 2 the largest area, step 4 under 5%?
5. One accent hue, under 8% of pixels?
6. Ground shadow present, offset down-right, correct ellipse ratio?
7. 1–2px contact AO inside the sprite, above the shadow?
8. No orphan pixels beyond the 3 allowed, no jaggies, no doubles?
9. Outline 1px, hue-tinted, broken on the lit crest?
10. No pure black, no pure white, no anti-aliased pixel?
11. Height:footprint within 1.1–1.6?
12. Sits next to two existing assets without either looking foreign?
