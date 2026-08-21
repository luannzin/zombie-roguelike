# Presentation: audio, VFX, light — design law

Nearest contracts: [`client/AGENTS.md`](../../client/AGENTS.md),
[`client/src/render/AGENTS.md`](../../client/src/render/AGENTS.md),
[`server/tools/AGENTS.md`](../../server/tools/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the sound catalog and its mix, effect sheets, the light budget, gore, and every purely visual reaction to a server event |
| **Inputs** | server events (`shots`, `swings`, `kills`, `pours`, `spin`, `crateBreaks`, `riftStates`), zone declarations, the generated manifests |
| **Outputs** | pixels and audio. **Nothing.** No gameplay state leaves this layer |
| **Depends on** | `assets/processed/*/manifest.json`, `welcome.config`, `client/src/styles/index.css` tokens |
| **Consumers** | nobody — this is a leaf |
| **Authoritative** | nothing at all |

## Invariants

- **The client is presentation.** A visual layer may never settle economy, spend inventory, or decide a gameplay outcome.
- **A SOUND IS PER EVENT, NEVER PER CATEGORY.** Reaching for an existing sound because it is roughly the right shape is how the loudest channel in the game ends up saying every object is the same object.
- **Sound is generated art.** `server/tools/make_audio.py` is the source; gain and bus travel on the manifest, so the mix is generated output rather than numbers in the client.
- **Four buses** (`ui`, `ambient`, `sfx` — guns and zombies only — `misc`) and **no per-bus trim**: everything is loudness-normalized at generation time. Balance problems move a `level_db` in the generator.
- **Ambience is declarative** — a screen states what the world sounds like; nothing starts or stops a bed.
- **A page may not make noise until it has been touched.**
- **React never renders per frame.** `hud-store.ts` publishes at 5 Hz through `useSyncExternalStore`.
- **All colours and type live in `client/src/styles/index.css`**, read by the canvas through `client/src/theme/`. Never hardcode a colour.
- **Additive light does not clamp.** Every light in a zone plus `zone.ambient` is ONE budget — see [`store.md`](store.md) for the bug this rule came from.
- **Rendering knows nothing about the network; networking knows nothing about rendering.**
- **`assets/processed/` is generated output.** Edit the generator in `server/tools/`, never the PNG.
- **Rarity is one five-colour ladder** across loot auras, skill canisters, machine reels and HUD borders. The generators duplicate the hex values from `index.css` by hand — keep the lists identical.

## Change surface

| intent | touch |
| --- | --- |
| add a sound | a recipe in `server/tools/make_audio.py` + one call site in `client/src/audio/sfx.ts` |
| add/retune an effect sheet | the matching `server/tools/make_*.py`, then rerun and commit script + output |
| how an effect plays | `client/src/game/effects.ts`, `client/src/render/layers/effects.ts` |
| muzzle / impact art | `server/tools/make_weapon_vfx.py`, `client/src/render/weapon-vfx.ts` |
| gunsmoke, barrel heat, brass | `Effects.spawnMuzzleSmoke` / `spawnCasings` + `drawBarrelHeat` in `layers/entities.ts`; how hot a shot leaves the barrel is `game/weapon-feel.ts` |
| the sound a mechanism makes | `sfx_gun_cycle` / `sfx_gun_draw` in `make_audio.py`; whether a weapon is slow enough to be heard is `WeaponFeel.audible` |
| wounds | `server/tools/make_gore.py`, `client/src/render/gore.ts` |
| how dark the unlit world is | `UNSEEN_ALPHA` / `FOG_ALPHA` in `layers/darkness.ts`. NOT whether creatures are drawn — that is `Game.applyVisibility` |
| darkness / vision | `client/src/render/fov.ts`, `layers/darkness.ts` — `fov.ts` draws vision at the reaches `ai.py` tests against, both read off `config.enemyViewDarkScale` / `enemyViewLitScale` |
| how a thing sits on the ground | `client/src/render/shadows.ts` — the contact pool and the cast, for every caller. Never a new ellipse at a call site |
| which lights move a shadow | `Renderer.collectShadowLights` — the same four sources the shaft pass ranks |
| colours, type | `client/src/styles/index.css` only |
| how a place looks | one of the three PLACE functions in `client/src/render/post/looks.ts` |
| how an event changes the picture | an EVENT partial in `post/looks.ts` + one `hold`/`release` in `Game.stepGrade`, or one `pulse` at the event |
| a new grade knob | `Grade` + its `SCALARS`/`TRIPLES` row in `post/grade.ts`, one uniform, its use in the composite shader in `post/chain.ts` |
| bloom / shafts / fog / lens maths | `post/chain.ts` only |
| camera feel | `client/src/render/camera.ts` |

**Do not touch from here:** anything under `server/app/`. A presentation change
that needs a server change is a sign the boundary is in the wrong place — say
so rather than reaching across it.

---

## Design law

- **A GUN THAT HAS BEEN WORKING LOOKS LIKE IT.** Heat accumulates per pull
  (sized off the muzzle flash the catalog already scales per round) and decays
  over a couple of seconds, so one shot leaves nothing and a magazine leaves a
  plume: smoke that RISES — the only thing this class throws that does not
  fall — and a single additive world pixel at the bore. One pixel is not
  timidity, it is the light budget: the additive chain does not clamp, and a
  glow big enough to be pretty at the muzzle washes out the ground under two
  players firing. Brass is thrown from the EJECTION PORT when the action opens,
  not from the muzzle on the frame of the trigger, and only the two mechanisms
  slow enough to be heard over their own gunshot — the shotgun's forend, the
  AWP's bolt — get a sound.

- **A SOUND IS PER EVENT, NEVER PER CATEGORY.** The object vocabulary was
  undone once already by three different containers all playing the inventory
  panel's UI tick, and the same trap caught the upgrade machine (built out of
  `object-heavy` and `object-open` first, and reading as a car boot). A lever,
  a reel detent, a canister landing in a steel tray and a container that turned
  out to be empty are four events and they have four recipes. Reaching for an
  existing sound because it is roughly the right shape is how the loudest
  channel in the game ends up saying every object is the same object.
- **Sound is generated art, like every pixel.** `server/tools/make_audio.py`
  synthesises the whole catalog into `assets/processed/audio/` — deterministic,
  stdlib only, one DSP vocabulary at the top that every recipe is written in —
  and the manifest carries each sound's gain and bus, so the mix is generated
  output rather than numbers scattered through the client. The client half is
  `client/src/audio/`: it knows about a listener at a point and sounds at other
  points, and nothing about players, zombies or zones. Sounds are SPATIAL,
  which is what makes the lantern pay off — a creature you cannot see but can
  place is the difference between tension and ambush. Ambience is stated, never
  started: a zone declares what it sounds like and the beds crossfade to it.

- **TWENTY SMALL THINGS, NONE OF THEM VISIBLE.** The frame is finished on the
  GPU (`client/src/render/post/`) and every term in it is deliberately below
  the threshold where a player could name it. The base looks sit within a few
  percent of neutral; the events rarely go a third of the way to their own
  extreme; the grain is 2-3%; the aberration is under half a pixel until
  something is wrong. The test for any number in `looks.ts` is not "can I see
  it" — it is "can I see it MISSING". A grade the player can point at is a
  filter, and a filter is the one thing this is not.

- **THE CAMP IS THE FOREST, AND THE TITLE SCREEN IS THE CAMP.** `campLook`
  used to be its own softer grade — warmer, a touch brighter, the frame opened
  up — on the argument that the clearing is the safe beat of the loop and
  should not wear the night the run does. What it actually did was make the
  first thing a player ever sees a different GAME to the one they are about to
  play: the fire, the trunks and the grass in that clearing are the same art
  the forest is drawn from, and grading them warm put a visible cut in colour
  on the exact frame the camera push out of the lobby exists to hide. It
  returns `forestLook()` now. What says "safe" at the camp is the fire and the
  absence of anything walking toward it, not two percent of exposure. The SHOP
  keeps its own look, because that one is indoors and the walk into it is
  meant to read as a change of place.
  And the lobby is no longer the one ungraded picture in the game.
  `game/lobby-scene.ts` paints into an offscreen surface and finishes through
  its own `PostChain`, exactly as the arena does — so the title card has the
  bloom on its fire, the fog, the vignette and the grain that used to all
  arrive at once the moment the run started. No shaft lights: the scene has one
  candidate source, parked mid-frame behind a menu, and a beam raking the title
  card is the one thing in this look a player could point at.

- **PIXEL ART IS THE WORLD. IT IS NOT THE LIGHT, THE AIR OR THE LENS.** This
  is the split the whole finish rests on, and it is structural rather than a
  preference: every `layers/` pass draws into an offscreen 2D surface at one
  pixel per pixel, and that surface is handed to a WebGL2 chain that is never
  nearest-filtered. Bloom, shafts, fog, defocus and grain are smooth; the
  forest under them is not. The alternative — pixelating the effects to
  "match" — was rejected because it makes the effects look like more world
  instead of like light, and the contrast between a hard sprite and soft light
  is most of what reads as production value. The same rule is why
  `layers/atmosphere.ts` turns image smoothing ON for its ground fog and off
  again after: fog is air, and air has no pixel grid.

- **THE GRADE IS A STACK, NOT A SETTING, BECAUSE EVENTS OVERLAP.** The
  interesting looks in this game are momentary — a pad lighting up, a round
  landing, the merchant's clearing, a critical wound — and they do not take
  turns. One shared grade means whichever event fires last wins and whichever
  finishes last clears it, so a hit taken during an extraction ends by
  resetting the extraction back to the forest. So: a base LOOK per place, and
  every event a named PARTIAL layer with its own attack/hold/release, fading in
  over whatever the current answer is. A layer only names the fields it has an
  opinion about, which is what lets "the anomaly" say *colder shadows, more
  aberration* without also having an opinion about the shop's bloom.
  The envelope is also the CHOREOGRAPHY: a ceremony does not need seven clocks
  for its light and its exposure and its bloom and its shafts, it needs one
  layer with a long attack. The extraction's grade takes over a second to
  arrive, and that alone is the difference between "the numbers changed" and a
  machine coming down through the trees.

- **BLOOM BELONGS TO LIGHTS, NOT TO BRIGHT THINGS.** The threshold sits high
  (0.72 at rest) with a soft knee, so a lit patch of grass does not glow and a
  campfire does. Three blur levels are summed at falling weights rather than
  one wide blur, because a single radius has one shape and real spill has a
  hot core and a wide skirt. The tone curve rolls highlights off instead of
  clipping them, which is the only reason bloom can be pushed at all — without
  a shoulder, every added photon lands on a pixel that is already white.

- **LIGHT SHAFTS ARE A RADIAL BLUR OF THE BRIGHT BUFFER, AND THAT IS WHY THEY
  NEED NO GEOMETRY.** The bright pass has already thrown away everything that
  is not a light. Smearing what is left toward a source produces a beam that
  only survives where nothing occludes the line back to it — so a trunk
  between the player and a burning rig punches a real gap in the shaft, for
  free, because the trunk is dark in that buffer. Four sources at most, ranked
  by brightness AND by nearness to the middle of the frame: a light at the very
  edge rakes the screen at a glancing angle and reads as a smudge on the lens
  rather than as light coming through trees.

- **A SHADOW IS LIGHT, SO IT ANSWERS TO THE LIGHTS.** Every standing thing in
  the game used to draw its own hard ellipse at a fixed alpha — six call sites,
  one shape, pointing nowhere. That is enough to say a silhouette is not
  floating and it is the end of what it can say: a crate two tiles from a
  bonfire and a crate alone in the black wood wore the identical mark, so
  nothing on the floor ever reacted to a light moving past it, and the whole
  world read as sprites laid on a picture of ground. `render/shadows.ts` splits
  it into the two things that were being conflated. The CONTACT pool is ambient
  occlusion: always there, unlit or not, the crease where an object stops the
  sky reaching the floor, and it is what actually does the grounding. The CAST
  is the shadow proper — thrown away from whatever is lighting the object,
  lengthening the further it stands from that light, gone where nothing is
  burning. The lights are the SAME four the shaft pass ranks, and that is the
  rule rather than a convenience: two different answers to "what is lighting
  this place" is how a frame stops agreeing with itself. Fire flicker rides the
  cast, because a body standing at the hearth with a still shadow is a body in
  front of a poster. The mark is a soft stamped blob and never a hard ellipse:
  the same split that keeps bloom and fog smooth applies to it, since a shadow
  is light and not world. Trees and rocks stay OUT of it — their contact is
  baked into a ground cache that is rebuilt when the map changes, and a trunk
  that swung its shadow around the player would cost that rebake every frame
  for a thing nobody looks at to find the fire.

- **THE LANTERN CANNOT HAVE SHAFTS, AND THE TWO ATTEMPTS SAY WHY.** A shaft is
  a radial blur of the BRIGHT buffer, so a source has to have bright pixels of
  its own — a bonfire clears the threshold on its flame sprite and the pass
  gets a beam for free. The lantern has nothing: it is a wash on the ground and
  the thing making it is not drawn. First attempt was to draw it — a hot core
  at the player's hand — and bloom immediately turned that into a lamp-sized
  DISC stuck to the player, which is a HUD element with a light's excuse.
  Second attempt moved the core into the shaft march alone, where bloom could
  not see it. That hid the disc and kept the beam, and it was still wrong: the
  smear radiated EVENLY, because a synthetic emitter is added near the source
  whether or not a trunk stands in the way. The occlusion in this pass is not
  a trick — it is the trunk genuinely being dark IN the buffer, and nothing
  synthetic can inherit that. So the lantern stays out of the shaft ranking.
  Its beam is already occluded correctly, by the shadowcast, and its VOLUME
  belongs to the motes drifting in it (`layers/atmosphere.ts`) — dust in the
  beam is dimmed by the darkness pass and therefore respects the same shadows.
  That is the lever for a volumetric lantern; the shaft pass is not.
  `RenderState.lamp` survives because the SHADOW field needs it: a shadow has
  to know where the light is, and that has nothing to do with bloom.

- **THE DARK IS A SILHOUETTE LEVEL, NOT A BLACKOUT.** The night wash is
  `source-over`, so what survives in the unlit half is `(1 - alpha)` of the art
  plus the tone. At 0.9 that is a tenth of the picture: every value out there
  landed within a few levels of every other, and the forest stopped being a
  place and became a black rectangle with a torch hole cut in it — which is
  not the same thing as darkness, and reads as missing rather than as night.
  A fifth of the art gets through now, which is the level where a trunk, a rock
  and a crate are three readable SHAPES and none of them is a readable OBJECT:
  you can see that something is there and roughly what it is, and nothing
  about its colour, its detail or its condition. That is the cinematic version
  of a dark wood, and the loud version — everything crushed to one value — was
  costing the game its own set dressing.
  **It does not reveal creatures**, and the separation is deliberate: the
  creature gate is `Game.applyVisibility` reading the fov's LIGHT, not this
  alpha, so a zombie in the dark is still genuinely not on screen. The world
  being legible and the threat being hidden are two different statements and
  they are made by two different systems.

- **THE DANGER VIGNETTE IS NOW A LAYER LIKE EVERYTHING ELSE.** It used to be a
  2D pass painted over the finished frame, which meant it was the one reaction
  in the game that could not compose with another — it sat on top of an
  extraction instead of being part of the same picture. Same heartbeat, same
  crush, same blood tone; it is simply in the stack now, and the corner falloff
  is a smooth gradient in a shader rather than four rectangles. The old pass
  survives only as the no-WebGL2 fallback, and that fallback is deliberately
  NOT a 2D imitation of the chain: bloom by repeated `drawImage` is slow and
  banded, and a half-done look is worse than the look's absence.

- **A CAMERA, NOT A VIEWPORT.** Three things ride on top of the follow and none
  of them is meant to be noticed. A permanent sub-pixel BREATH on two slow
  incommensurate sines, because a frame that is perfectly still between two
  footsteps reads as a screenshot. A directional IMPULSE with a spring under it
  — recoil goes back down the barrel — because trauma says *how violent* and
  only a direction says *which way*, and a shot to the left and a shot to the
  right should not be the same event. And the SHAKE itself moved off
  `Math.random()` onto summed detuned sines: white noise at 60 Hz is television
  static, two sines that never quite repeat are a hand that got hit.

- **DEPTH OF FIELD IS FOR THE SCOPE AND FOR DEATH, AND ESSENTIALLY NOWHERE
  ELSE.** During play it is zero. Down the scope the forest goes soft around
  what the gun is pointed at, which is the same statement the zoom is already
  making; on death the picture stops being a place and becomes a photograph of
  one. Any other use is a phone in portrait mode.

- **A hit shows on the body, and it keeps showing.** A landed shot throws
  debris BACK along the ray and blood FORWARD out the far side, so the two
  read as a round passing through something rather than stopping on it, and
  it leaves a WOUND — one frame of `assets/processed/gore/` pinned to the
  sprite and masked to its silhouette, so the mark is ON the creature and
  carried through the walk cycle until it dries. Damage the player
  can only read off a health bar is a number; damage they can see on the
  creature is damage. Volume of spray and debris follows the gun's damage.
  A landed round knocks the body a little BACK along the shot with a tilt
  around the feet. Stacked hits slow then stop the walk on the server
  (`Enemy.stagger`); the sprite freeze is the visual of that plant. Only
  flesh bleeds: wood takes splinters and a swing the i-frames ate takes
  nothing.
- **THE FIRE AT THE BARREL IS PIXEL ART, NOT A CIRCLE**
  (`server/tools/make_weapon_vfx.py`, `client/src/render/weapon-vfx.ts`). The
  shot was the last important event in the game still drawn entirely out of
  canvas primitives, which made the loudest thing on screen the only thing
  that did not look like it was made of the same stuff as the forest. What is
  drawn now comes off
  `assets/inspiration/pixel-art-new-style/weapon-vfx.png` and follows what
  that sheet actually teaches: a muzzle flash is a hot core with PETALS and a
  LANCE thrown down the barrel, never a disc; the RING a beat later is what
  makes it read as pressure leaving a gun rather than a lamp switching on;
  white is the middle and deep red is the edge; and it ends in SMOKE, because
  a flash that simply faded is an effect stopping rather than finishing. The
  shotgun gets a different SHAPE and not a bigger flash — a cone that reaches,
  holds, breaks up and drifts — which is most of what makes the two weapons
  feel like different objects. Three sheets, all pointing right and rotated
  onto the aim, all drawn ADDITIVELY after the darkness pass, and all with the
  ramp BAKED IN: unlike `make_vfx.py`'s greyscale sheets, fire is not
  anybody's colour and a muzzle flash tinted to the shooter would be the one
  effect in the game that lied about what it was. One flash per TRIGGER PULL
  however many pellets came out of it, one damage number per BODY however many
  pellets reached it, and the atlas is null-safe — a client that could not
  load it falls back to the primitives it replaced.
