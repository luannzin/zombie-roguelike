# STATE

Current project state. Short-lived by design — **this file is meant to be
edited often and never to become history.** Durable rules belong in
`AGENTS.md`; durable design belongs in [`docs/design/`](docs/design/).

**Ambient context, not a required read.** Consult it when the task touches a
recently changed system, when something looks like a regression, before
modifying anything under *Do not touch*, or when the task asks what to work on
next. Skip it for a self-contained change to a stable system.

_Last verified: 2026-08-20 against `main` @ `869e36c` + the fix pass below._

## Current phase

The full expedition loop runs end to end: camp -> forest -> extraction -> exit
-> store -> next night. The last few weeks have been **depth on the beats that
already exist** rather than new systems — the shop became a round clearing, the
knife got a real swing, the shotgun got its own dynamics, the machine got its
ceremony.

## Currently working on

- **The visual refactor toward depth / 3D-ish volume** (`PIXEL-ART-DIRECTION-V2.md`).
  The art half is moving asset by asset; the RENDER half landed as a whole (see
  below), so new art is authored against a frame that has bloom, shafts, fog and
  a grade on it.
  **Done so far:** terrain and scenery, the object sheets, the held weapons, the
  LOOT atlas (all 46 items plus the 12 gun icons), the skill payout TIN, the
  extraction PLATFORM and its drones, the PLAYER (plus a holding pose), and the
  THREE CREATURES. **Still on the old shading:** the console and threshold kit
  (`make_rift.py`), the merchant's own kit (`make_store.py`), the upgrade
  cabinet (`make_machine.py`), and the skill ICONS (flat HUD marks by contract
  — read `make_skills.py`'s header before "fixing" them).
- **The SHOP is a building again** (`store.py` offsets are still moving). The
  zone is now an outdoor APRON — platforms land, the cart is parked, the
  payout happens — and a brick SHOP at the north end of it, entered through a
  door, with the exit corridor coming off its back wall. Two new mirrored tile
  kinds carry it (`BRICK` / `TILEFLOOR`), and `GROUNDS` / `CLEAR` in
  `world.py` + `world.ts` are the pair to keep in step.
- **THE FIRST BOSS — art is done, mechanics are not.** `make_sawyer.py` and
  `assets/processed/sawyer/` are finished and verified: 390 frames on a
  128x120 rig, eight clips (idle, walk, chop, rip, rev, death in four facings;
  a facing-less sweep; the arrive cinematic) plus the thrown crescent in eight
  baked headings. **Nothing in `server/app/` or `client/` references him yet** —
  no `EnemyType`, no spawn, no loader, no wire shape. The design reasoning is
  in [`docs/design/enemies.md`](docs/design/enemies.md) § THE SAWYER, including
  the list of what is still undecided (where he is fought, what starts him,
  whether the crescent rides the existing damage path). Read that before
  writing the fight; the art's event frames on the manifest are meant to drive
  the timings rather than the other way round.
- Weapon feel: shotgun cone and melee swing landed; the catalog's derivation from CS2 stats is stable.

## Recently completed

| | |
| --- | --- |
| **the dead were redrawn** | three creatures, three ANATOMIES: the walker keeps the player's build, the husk became a real skeleton (skull, a gap of neck, ribs with gaps you can see through), the brute became a mass with fungus growing out of it. Every ramp is derived through `material_ramp` instead of typed hex, and every creature carries an EYE — one saturated pixel in a dark socket, the sheet's single accent. The S15 test (all three in solid black) is in `make_zombie.py`'s header and passes |
| **the player has a HOLDING pose** | the sheet grew a second block of rows (`hold-down` / `hold-left` / `hold-right` / `hold-up`, APPENDED — walk rows keep their indices) with the weapon arm raised on the right-handed side and the off hand tucked. `process_sprites.py` now carries a second pose block generically (`POSE_PREFIXES`), mirroring each block on its own. `render/guns.ts`'s `GUN_GRIP_SIDE` and `arms.ts`'s `WRIST_OUT` are the client half of that pose and move with it |
| **held weapons are drawn at 3/4** | `make_guns.DRAW_SCALE` — the art is authored at one pixel scale so it can say "AK", and drawn smaller so it stops out-measuring the body. In the manifest, so sprite / muzzle / port / support hand all shrink together |
| **the weapon is HELD** | the gun was a sprite floating at chin height with nobody holding it, and the same sprite for every state of every weapon. Now: the grip is measured off the FEET and off the centreline (`GUN_GRIP_ABOVE_FEET` / `GUN_GRIP_SIDE`), arms are PLOTTED from the shoulder to it (`render/arms.ts`), the atlas carries an OPEN action frame per firearm derived from the closed art (`make_guns._cycled`), brass leaves the ejection port when the action opens, a swap is a DRAW, the weapon breathes and bobs and braces, and a hot barrel smokes. What each class does is derived from its catalog row in `client/src/game/weapon-feel.ts` — no per-weapon table. `bun tests/weapon-pose.ts` covers the pose and the atlas |
| **the mechanism is audible** | `gun-cycle` (three weights) and `gun-draw` in `make_audio.py`. Only the shotgun's forend and the AWP's bolt play the cycle: anything faster is inside its own gunshot |
| **ground contact** | six hard ellipses in six files became one `render/shadows.ts`: an ambient CONTACT pool plus a CAST thrown away from the frame's lights, lengthening with distance from them and breathing on the fire's own flicker. Bodies, scenery props, loot, coins and the pads are on it; trees and rocks stay baked into the ground cache on purpose. `bun tests/shadows.ts` covers the field's arithmetic |
| **the lamp is a shadow source** | `RenderState.lamp` says where the lantern IS (ahead of the body, down the aim), so the shadow field has something to point away from. It is deliberately NOT in the shaft ranking — see the known problem below |
| **the dark is a silhouette level** | `UNSEEN_ALPHA` 0.9 -> 0.78, `FOG_ALPHA` 0.66 -> 0.62. A tenth of the art surviving made the unlit half one flat value; a fifth makes a trunk, a rock and a crate three readable shapes and none of them a readable object. Creatures are untouched — that gate is `applyVisibility`, off the fov's light |
| loot, the tin, the pad | the loot atlas is banded volume out of `make_loot.paint_form` — sub-blobs, edge-test planes, a material-tinted keyline that breaks on the lit crest, and an offset ground shadow on every frame; the payout tin is a five-band cylinder; and the extraction skid is a HEIGHT FIELD rasterised on `make_objects`' own dimetric with the drones rebuilt out of its volume toolkit. The ropes are plotted pixel by pixel instead of stroked. `material_ramp` in `make_textures.py` is now where S11's ramp law lives for the whole pipeline |
| **the finish** | the renderer no longer draws on the visible canvas. Every layer draws into an offscreen 2D surface; `client/src/render/post/` finishes it in WebGL2 — bright pass, three-level bloom, radial light shafts, defocus, chromatic aberration, fog, a full grade (exposure / shoulder / contrast / saturation / temperature / tint / lift / gamma / gain), wash, vignette and grain. Driven by a `GradeStack`: a base LOOK per place plus named event layers on their own envelopes. The old 2D danger vignette is now one of those layers, and survives as the no-WebGL2 fallback |
| camera feel | breath and sway on two slow sines, a directional spring IMPULSE (recoil goes back down the barrel), and the shake moved off `Math.random()` onto summed detuned sines |
| ground fog | a fourth atmosphere field: low banks drifting on the wind, drawn smooth (one baked blob, stamped), under the darkness so it only exists where there is light |
| skill payout | the tin is a canned good at 16x18 (was a 16x24 aerosol tube), it no longer drops onto the machine's tray — it appears over the winner's head and flies to the HUD like any collect |
| loot frames | a frame now comes from the atlas manifest, not from catalog position — the knife and the condensed core had been drawing ammunition boxes, and every gun was drawing another gun. `test_loot_frames.py` guards it |
| dark gold | the purple coin is an ANOMALY SHARD, painted from the rift's prism at both sizes, and both drop taps cut hard so it is a rare find |
| the level-up | it used to be silent: now a summon column on the body plus an `Announce` card, the small mid-run sibling of the arrival title |
| shop | clearing -> APRON plus a brick BUILDING: L counter in the corner, shelves behind him, six tables, cabinet on the west wall, oil lamps on stands, cart parked outside |
| the payout | the landed platforms STAY parked in the yard for the visit (they used to vanish with the ceremony); the day-complete card carries the take and the canvas `+N` that duplicated it is gone |
| store art | every sheet rebuilt: brick wall + paved floor, tiling L counter, wall shelves, decoration crates, table lamps, tables, torches, mats, the cart and his kit |
| melee | three-beat combo with the blade following its own arc |
| shotgun | one shell, six rays, its own muzzle/impact art and audio |
| stamina | SHIFT sprint on a bar, prediction-replayable, `winded` latch |
| currency | GROUP gold (`Room.balance`) split from PLAYER dark gold (`Player.gold`) |
| skills | levels as spins, the slot cabinet, `Mods` read at every consumer site |
| extraction | cargo platform, the pour, drone pickup, siren + `hunt_all`, carved exit |
| the skid, square to the screen | the platform was rasterised corner-on like a crate and read as a lozenge with no front to walk into. Same camera slope, same key, same painter, footprint yawed onto the screen axes: full-width front face, a deck you can see the load on, three walls and an open front with a hazard ramp. `pad-cargo.ts`'s floor fractions moved with it |
| the pour is a commitment | movement no longer cancels it and there is no ceiling — the press tips the WHOLE bag, on either side of the quota. Damage still ends it. The `over` prompt mode is gone with the rule that needed it |
| undergrowth is cover | bushes were drawn over the player and ignored by `ai.look`. The server re-derives the client's bush tiles from the map seed (`world.tile_hash`, bit-exact with `render/terrain.ts`) and cuts a creature's reach over them |
| the exit arrow routes | it was a compass pointing through trees; `game/exit-path.ts` floods the map from the corridor mouth and the chevron follows the walkable route |
| container density | scenes rolled openables in independent loops that summed, and nothing stopped two landing on one tile. `scenery._thin_containers` caps a scene at five and drops collisions |

## Known problems

- **The "darker grade" request is still unanswered.** A darker `forestLook` was
  tried and reverted by hand; the dark now comes from `UNSEEN_ALPHA` instead,
  which is a different lever (how much of the unlit world survives, not what
  the whole frame is graded to). Nothing in the game picks a grade at random,
  so whatever was seen has not been identified.
- **The lantern has no god rays and three routes are closed.** Lowering the
  bloom threshold blooms the lit grass; a hot core drawn into the scene comes
  back through bloom as a circle on the player (shipped for one round, removed);
  a synthetic emitter inside the shaft march hides that circle but smears
  evenly, because occlusion in that pass is the trunk really being dark in the
  bright buffer and nothing fake inherits it. The open route is dust: the motes
  in `layers/atmosphere.ts` are dimmed by the darkness pass, so a beam made of
  them respects the shadowcast for free. Nobody has tried it yet.
- **The post chain has no automated check and cannot have one.** `bun tests/grade.ts` covers the stack's envelopes and composition — the arithmetic — and nothing covers the shader. Judge it by looking: a bonfire should bloom and the grass beside it should not.
- **The lobby is not graded.** `LobbyScene` / `CampfireCanvas` own their own 2D canvases and do not go through the post chain, so the title screen and the arena are finished differently. Nobody sees them side by side today, but the seam is real and it is where a "the camp looks flatter than the game" report will come from.
- **`texImage2D` from the scene canvas every frame** is the one unavoidable cost of the hybrid, and it scales with window size rather than with what is on screen. Marked `ponytail:` in `post/chain.ts`; the upgrade is drawing the world into a GL target directly, which is a renderer rewrite.
- **`make_objects.box` is corner-on and slopes the CONTACT.** It is right for
  what it was written for (a crate seen corner-on) and wrong for small standing
  props: the bottom comes out a V, so the object reads as a losange floating
  over the floor. `make_store._block` is the front-facing alternative — flat
  base, rectangular front, top sheared right — and the store's kit and crates
  are on it. Anything new in that folder should be too. The extraction skid was
  the last big thing on the corner-on axes and has been turned square to the
  screen; the rule that came out of it is in `docs/design/extraction.md` —
  **architecture is axis-aligned, props are corner-on.**
- **Generated frames can clip their own cells and nothing notices.** A packed
  sheet with clipped frames is a valid PNG. `make_store._check_margins` guards
  the three sheets it has bitten (kit, crate, lamp); no other generator has an
  equivalent.
- **Additive light does not clamp.** The store's flat-white bug was fixed by spending one budget across four places (`STORE_AMBIENT`, `RING_TORCHES`, `TORCH_LIGHT_TILES`, `layers/payout` alphas), and it came back twice. Second pass: the torch FLAME sheet and the scene-light pools were each tuned against one lamp alone in a black wood, and the shop has eleven overlapping. Third pass (this one): the floor itself was doing part of the torches' job, so the room was bright everywhere and lit nowhere — `STORE_AMBIENT` 0.45 -> 0.36, `TORCH_FIRE_ALPHA` / `LAMP_FIRE_ALPHA` 0.55 / 0.42, `drawSceneLights` stops 0.135 / 0.045, and the pad's four overlapping lamp sheets held at 0.72 with the halo at 0.085. The underlying renderer still has no clamp, so the next zone with many lights will hit it a fourth time.
- **Naming drift is permanent and deliberate.** `rift.py` / wire `rifts` mean the extraction platform; `crates.py` / wire `crates` mean all interactive objects. Do not rename either — the cost is twenty client files for nothing.
- **Two giant files** (`server/app/room.py` 2.8k lines, `client/src/game/game.ts` 4.4k lines) — see below. Their section banners were rewritten to be honest (5 → 16 and 5 → 21); the files themselves are unchanged and still unsplit.
- Dark gold currently buys nothing. Intentional, but it means its drop taps are untested against real demand — and they were just cut hard for the shard art, so the first thing it can buy has to be priced against the NEW rate, not the old one.
- **The skill tray was empty for every run until now.** `skills.catalog_payload` shipped a list while the client declared `Record<string, SkillConfig>`, so `config.skills[key]` was `undefined` for all eighteen: no tray row, no hover card, and the payout tin always wore frame 0. Fixed, and `test_config_parity.py` now checks the SHAPE of all four catalogs, not just the top-level key set. The other three were already dicts.
- `Announce` has exactly one caller. It was built as a general mid-run card and that is what it is for; a second caller is welcome, a fork of it is not.

## Next priorities

1. Keep the shop layout stable long enough for `test_store_walk.py` to be a meaningful regression check rather than a per-commit fixture.
2. Something for dark gold to buy (per-player, never party-funded).
3. Ammunition tuning once more guns are routinely owned by day 5+.

## Do not touch

Unless the task is explicitly about them:

- `client/src/components/ui/**` — generated coss/shadcn components. Add with `bunx --bun shadcn@latest add @coss/<name>`, never hand-edit.
- `assets/processed/**` — generated output. Edit the generator in `server/tools/`.
- `assets/raw/**` and `assets/inspiration/**` — never served, never read at runtime.
- `server/.venv/`, `client/node_modules/`, `client/dist/`.
- The **eight** mirror pairs, one side alone. Three are line-for-line (`simulation.py`/`simulation.ts`, `protocol.py`/`protocol.ts`, `machine.py`/`machine.ts`); five are the same rule re-derived on the other side (`world.py`/`world.ts`, `Room.collect_loot`+`Inventory.add`/`game/interaction.ts`, `ai.look`/`render/fov.ts`, `world.tile_hash`/`render/terrain.ts`'s `tileHash`, `make_platform.py`'s deck/`game/pad-cargo.ts`). The full list with the reason for each is in the root `AGENTS.md`.
- `Room.enter_store`'s balance credit — the single settlement point.

## Known technical risks

| risk | why it bites |
| --- | --- |
| mirror drift | one side edited alone: rubber-banding, or a silently dropped wire field. Eight pairs, not three — the five undeclared ones (`world.ts`, `interaction.ts`, `fov.ts`, `tileHash`, `pad-cargo.ts`) are the ones a reader will not know to check. `tileHash` is the worst of them: it has a test now because nothing at runtime notices when the two sides put undergrowth in different tiles |
| generated-list insertion | inserting into `weapons.WEAPONS` / skills / loot icons shifts every frame index in already-committed sheets |
| `Mods` bypass | a site reading a raw `config.py` constant makes a skill silently do nothing, with no error |
| map generation | `mapgen`/`scenery` failures are seed-dependent; a bad edit ships and breaks one night in twenty |
| light budget | additive, unclamped; new lights saturate a zone rather than erroring |
| `Navigator.invalidate()` | forgetting it after freeing tiles leaves pathing walking into walls that are gone |
| grade knobs added halfway | a field on `Grade` that is not in `SCALARS`/`TRIPLES` is a knob that silently refuses to animate. The `satisfies` on both lists is what turns that into a type error |
| no automated client tests | `bun run typecheck` and `bun tests/grade.ts` are the only gates; everything else is two browser tabs. It is a stronger gate than it was: the always-sent half of `GameConfig` is now required, so a hedged constant is a type error rather than a silent stale value |
