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
| wounds | `server/tools/make_gore.py`, `client/src/render/gore.ts` |
| darkness / vision | `client/src/render/fov.ts`, `layers/darkness.ts` — note `fov.ts` mirrors `ai.py`'s view scales |
| colours, type | `client/src/styles/index.css` only |

**Do not touch from here:** anything under `server/app/`. A presentation change
that needs a server change is a sign the boundary is in the wrong place — say
so rather than reaching across it.

---

## Design law

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
