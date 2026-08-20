# Pixel-Art Direction — v2

Visual language for every pixel this game ships. Rules, not descriptions —
enough to draw a **new** object that reads as the same artist's hand.

**Section numbers are stable across v1 and v2.** Generators cite `§2`, `§7`,
`§14` in their own comments; a renumber would silently point every one of them
at the wrong rule. New law goes in new sections at the end.

**Scope caveat.** The references are not one single set. Eight of nine share one
language and are the basis for this spec. Two are excluded or fenced off:

- **Statue sheet** (grayscale, pre-rendered soft anti-aliasing, smooth
  gradients) — a different school entirely. Not part of this spec.
- **Weapon icon sheet** (flat side elevation, no ground plane) — a separate
  *icon* sub-mode, specified in §21. It shares the palette and outline logic
  but not the camera.

---

## What v2 changed, and why

v1 specified ONE camera for every solid object: 45° yaw, near corner pointed at
the viewer, strict 2:1 dimetric. Everything boxy in the game was built on it —
crates, supply boxes, chests, stashes, altar plinths, the extraction skid, the
merchant's kit.

**It produced lozenges.** Three separate failures, all from the same cause:

- Corner-on, the two visible vertical planes are both HALF faces receding at
  the camera slope. There is no square face anywhere to carry height, so a tall
  object is just slanted edges — a gem, not a box.
- The footprint is a rhombus, so the contact line falls away from the near
  corner in both directions and the bottom of the shape comes to a POINT. It
  does not sit on the floor; a row of them reads as diamonds hovering over the
  ground.
- The lid is a rhombus too, and it takes ~60% of the silhouette — over the
  35-45% §3 asks for. The top plane stops being depth and becomes the subject.

The fix is not a new camera. It is a **second yaw**, and which one an object
takes is decided by what the object IS (§1). The pitch, the key light, the
ramps, the painter and every other section are untouched: the crate standing
next to a rock is lit by the same key it always was, and only its yaw moved.

New in v2: §1 (two yaws, and the rule for picking), §2 (face-on construction),
§3 (the depth rule and round tops), §22 (light is art direction too), and an
amended §21 (mass before identity on icons; HUD sizes are a language).

---

## 1. Camera

| rule | value |
| --- | --- |
| projection | axonometric. No perspective, no vanishing point |
| pitch | ~55–60° above horizon (high 3/4). Top plane visible, never dominant |
| yaw A — **architecture** | **face-on.** Axes square to the screen: one front plane, one top plane sheared back, one shade sliver |
| yaw B — **props / organic** | free 3/4, corner-on, for mass that has no front (rock, foliage, bone, rubble) |
| depth axis | up and to the **RIGHT**, `SLOPE = 0.5` (2 px back, 1 px up) |
| forbidden | true top-down (90°), true side (0°), lens tilt, foreshortening ramps, per-object rotation |

**Which yaw an object takes is not a style choice.** Ask one question: *does it
have a front?* A crate has a front — it is a box somebody stacked, and a face
you walk up to. A skid is entered. A shop table is approached. A cabinet is
operated. All of those are **architecture** and take yaw A. A boulder, a bush,
a heap of bones and a pile of rubble have no front, and taking one away from
them costs nothing — those are **props** and take yaw B.

Everything in a set shares its yaw. The two yaws share the tile grid, the
slope, the key and the ramps, so a face-on crate and a corner-on rock stand in
the same clearing without either looking imported.

## 2. Volume construction

Form is a **stack of convex masses**, never one hull.

- Break the object into 3–7 sub-blobs. Each sub-blob gets its own full ramp.
- Sub-blob boundaries read by **value step**, not by line.
- No smooth gradient anywhere. Volume = facet + band.
- Mass sizes descend roughly `1 : 0.6 : 0.4`. Equal-sized blobs read as pattern,
  not as form.

### 2a. The face-on solid (yaw A)

Four parts, in this order, and none of them is optional:

1. **FRONT** — a rectangle square to the screen. It owns the most pixels and it
   is what the silhouette is read from. Its bottom edge is **FLAT**: the object
   is standing on a floor, and a contact line that slopes is an object that is
   not touching it.
2. **TOP** — the front's upper edge pushed back along the depth axis: up and to
   the right, `SLOPE` px up per px back. A parallelogram, never a rhombus.
3. **SHADE SIDE** — the sliver between them, on the right, running back from the
   front's right edge. Right, because the key is at 135° (§8): the lit planes
   are the top and the left, so the plane that must be visible and dark is the
   right-hand one. Shearing the other way puts the shade where the light is.
4. **TERMINATOR** — one step down along the seam where the top meets the front.
   A value step, no line (§6).

Then §10's contact AO inside the bottom edge, and §9's shadow under it.

### 2b. Openings

A hole is the strongest depth cue a sprite can carry, because it is the one
thing that cannot be read as paint on a flat plane. Where an object is
genuinely hollow — a cart's tilt, a pipe, a mouth — draw the cross-section:

- an ellipse cut at the camera slope, not a rectangle;
- filled with a step BELOW the shade side, so it is darker than any lit surface
  on the sprite;
- with one band of lit floor at the bottom of the cavity, so the hole has a
  bottom and does not read as a black disc stuck on;
- ringed by whatever holds it open (a hoop, a lip, a jamb), lit on its crown
  and shaded underneath.

## 3. Plane proportions

| plane | share of silhouette | ramp step |
| --- | --- | --- |
| top (lit) | 35–45% | 3–4 |
| front (key) | 40–50% | 3 |
| shade side | 10–20% | 1–2 |

Height : footprint runs **1.1:1 → 1.6:1**. Objects are tall. Squat is wrong.

### 3a. Depth is derived, not authored

Run back from the camera:

```
depth = max(2, round(width * 0.32))
```

**Derived, because a sheet of unrelated objects has to agree about the camera.**
Two props standing beside each other with hand-picked depths are two objects at
two pitches, and the eye reads that as one of them being wrong long before it
can say which. Under 2px the top plane is a line and the object flattens back
into an elevation.

Author the depth only where the object's REAL depth is the point — a shelf is a
shallow thing, and deriving its depth from its width makes it a cabinet.

### 3b. Round tops

A pedestal, a barrel head, a drum, a spool: the top plane is an **ellipse**, not
a parallelogram, and it is not finished until it has an EDGE.

- Ellipse height = `radius * SLOPE * squash`. `squash` shortens the run back,
  never the width — a surface seen from lower down keeps its front edge and
  loses its depth.
- Under the near arc go 1–2 rows of the material's own edge, **following the
  curve**: the board thickness you would see standing in front of it. Right of
  the arc's centre those rows take the shade step.
- Without that edge the top is a flat lighter patch sitting where a top ought to
  be — the same failure a corner-on box has, one plane short.

## 4. Pixel density

- Strict 1:1 pixel grid. One resolution per sheet. Zero anti-aliasing, zero
  sub-pixel work, zero soft brush.
- Prop working sizes: **16 / 24 / 32 / 48 / 64 px** footprint. Hero prop 128 max.
- All pixels square. Never scale by a non-integer factor. **This binds the HUD
  too**: a sprite on a panel is drawn at 1×, 2× or 3× and nothing between.
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
- **Do not shade a plane through a dithering picker.** A "subtle" grain on a
  flat face scatters single pixels of the neighbouring step across it and the
  plane break — the thing the whole construction is built to show — stops being
  a break. A face is one step unless the recipe asks for texture.

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
- **Planes are two steps apart, never one.** One step is a shading nuance; two
  is a plane change, and the plane change is the entire read on a face-on solid.
- The terminator follows form curvature — never a straight cut on organic mass.
- **No bounce light** on the shade side, except a single 1px rim at the base of
  round masses.
- No gradients, no soft falloff, no additive glow (emissive material aside, §14).

## 8. Light direction

- One key light. Azimuth **135° (upper-left)**, elevation **~60°**.
- Identical across every asset in the world. Never re-light per object.
- No fill light, no opposite-side rim.
- Ambient exists only as ramp step 2 — it is the "unlit" reference, not black.
- The key is what fixes the depth axis (§1). Change one and the other is wrong.

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
- Ramps are **derived from the law above, not typed by hand.** Five typed hex
  values are five chances to break one of these rules silently.
- Ramps share endpoints across materials where possible — palette economy is
  what makes a world look authored rather than assembled.
- Canvas / background: desaturated neutral. Never white, never pure black.

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

**Grain runs along its own plane's axis.** On a vertical wall the boards are
horizontal, so seams are measured up from the contact. On a sheared top plane
they run back along the depth axis — a seam measured against the screen instead
puts the planks across the boards.

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
2. **A visible hole** (§2b) — the one cue that cannot be read as flat paint.
3. **Shadow offset** — the constant down-right offset fixes the ground plane.
4. **Top-plane brightness** — anything facing up is brighter; that alone conveys
   pitch.
5. **Value compression with distance** — background elements lose steps 0 and 4,
   sitting entirely in the middle of the ramp.
6. **Vertical position** — lower on the canvas reads as nearer. Sorting is by
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

> Chunky, cel-banded props on a neutral field, architecture face-on and organic
> mass corner-on. Warm single key from the upper-left, cool hue-shifted shadows,
> one accent hue per object, a tinted 1px outline that gives way where the light
> hits, and a soft offset ground shadow that plants everything. Readable in
> silhouette at 1× before any colour lands.

Three things make it cohere and any one of them broken kills the set: **one light
direction**, **one shared palette with hue-shifted ramps**, **one ground-shadow
convention**.

## 21. Icon sub-mode

For inventory/UI items and skill tiles, not world props:

- Camera drops to **flat side elevation**, orthographic, no ground plane.
- Framing: item presented at a slight down-right diagonal, long axis roughly
  15–20° off horizontal. An icon is centred in its cell; it does not stand on
  the bottom edge, because it is a mark on a panel rather than a prop on a tile.
- Outline becomes **fully closed and higher contrast** than world props.
- The palette, the 5-step ramps, the hue-shift rule and the cluster rules all
  carry over unchanged. Icon ramps sit a step or two brighter than the world's:
  they are read against a dark inset panel, not against soil.
- Keying: an item's variant/tier is signalled by the accent hue only. Geometry
  stays close across a tier family.

### 21a. Mass before identity

At 16px an icon gets **one** idea, and it must arrive as a filled shape.

- **An outline with an empty middle is not an icon.** On a dark panel it reads
  as a frame around nothing — indistinguishable from a tile whose art failed to
  load. Draw the mass, then put the identity ON it (stitches, a seam, a strap).
- **A line is not a mass.** A 1px diagonal beside seventeen solid tiles reads as
  a scratch on the panel. Give a blade a spine and a grip; keep the lit edge to
  the one pixel that earns it.
- Test the sheet as a CONTACT SHEET on the panel colour, never one icon at a
  time. Anything that disappears in that grid is broken, whatever it looks like
  on its own.

### 21b. One size per meaning

A sprite's on-screen size is part of the language, so two things that mean the
same thing are drawn the same size. A skill canister and a rifle are both
PICKUPS: they fly the same path into the same corner and they are drawn at the
same zoom. A payout that arrives bigger than everything else the player collects
reads as a different system announcing itself — and the smaller sprite blown up
larger is the one that looks like the bigger prize, which is exactly backwards.

## 22. Light is art direction, not a lighting pass

Every light in this game is drawn ADDITIVELY over the art, and additive pools
SUM with nothing clamping the total. That single fact is behind every
blown-out frame this project has shipped.

- **Judge a light as part of its STACK, never on its own.** A torch is a flame
  sprite plus a floor pool plus whatever bloom finds; a beacon is four lamps
  plus a halo plus a grade layer. Every pass that tuned one of those in
  isolation put the sum straight back. Tune against the WORST case — eleven
  torches in a ring, four lamps on one deck — not against the single one.
- **A glow with no shape carries no information.** A radial gradient cannot say
  where light comes from; all it does is flatten the banding of whatever is
  under it. If a layer's only contribution is brightness, DELETE it — halving a
  useless layer twice just makes it a cheaper useless layer.
- **What says "this is lit" is the lit OBJECT.** Bake the lamp into the sheet at
  the housing, where the eye can see the source. A wash over everything near the
  source is a wash, not a lamp.
- **Never light an arrival brighter than the place it arrives at.** A ceremony
  that spikes exposure and bloom and then releases makes the destination look
  dimmer for the rest of the visit, and the player remembers the flare rather
  than the room.
- Colour and contrast carry the mood. Exposure and bloom only say it LOUDER.

---

## Checklist before an asset ships

1. Silhouette in solid black, at 1×, on the canvas colour — is it identifiable?
2. Correct yaw for the class — does this object have a front (§1)?
3. Face-on solids: flat base, rectangular front, top plane sheared up-RIGHT,
   shade sliver on the right, terminator as a value step?
4. Top plane between 35–45% of the silhouette, never dominant?
5. Light from 135°/60° — no exceptions, no second source?
6. Exactly 5 ramp steps, each with a hue shift, planes two steps apart?
7. Step 2 the largest area, step 4 under 5%? One accent hue, under 8% of pixels?
8. Ground shadow present, offset down-right, correct ellipse ratio?
9. 1–2px contact AO inside the sprite, above the shadow?
10. No orphan pixels beyond the 3 allowed, no jaggies, no doubles, no dithered
    plane?
11. Outline 1px, hue-tinted, broken on the lit crest? No pure black or white?
12. Height:footprint within 1.1–1.6?
13. Drawn at an integer zoom, and at the same size as everything that means the
    same thing (§21b)?
14. Sits next to two existing assets without either looking foreign?
