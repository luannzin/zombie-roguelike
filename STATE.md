# STATE

Current project state. Short-lived by design — **this file is meant to be
edited often and never to become history.** Durable rules belong in
`AGENTS.md`; durable design belongs in [`docs/design/`](docs/design/).

**Ambient context, not a required read.** Consult it when the task touches a
recently changed system, when something looks like a regression, before
modifying anything under *Do not touch*, or when the task asks what to work on
next. Skip it for a self-contained change to a stable system.

_Last verified: 2026-08-23 against `main` @ `844686a` + the DIFFICULTY pass below._

## Current phase

The full expedition loop runs end to end: camp -> forest -> extraction -> exit
-> store -> next night. The last few weeks have been **depth on the beats that
already exist** rather than new systems — the shop became a round clearing, the
knife got a real swing, the shotgun got its own dynamics, the machine got its
ceremony.

## Currently working on

- **THE DIFFICULTY PASS JUST LANDED. The loop was complete and had no
  pressure in it; this is the pass that gave it some.** Five changes, all with
  their reasoning written into the owning design docs. The short version of the
  diagnosis: the game had no failure state, so nothing else could feel
  dangerous.
  - **A CROWD CAN KILL YOU NOW** ([`docs/design/enemies.md`](docs/design/enemies.md)
    § The crowd). Melee was rate-limited per PLAYER, so thirty-two zombies did
    exactly as much damage as one and a body survived 6.7s inside the whole
    map's population. `Room.resolve_attack` no longer touches
    `hurt_immunity`; each creature's own `attack_cooldown` is the only limit,
    and `spawn_enemy` scatters attack phase so a pack streams damage rather
    than volleying it. 1 zombie ~13s, 3 ~4.4s, 5 ~2.8s, 8 ~1.7s. The client
    counts bodies in contact (`Game.stepPressure`) and drives the vignette and
    the heartbeat off it, so being surrounded is legible before it is lethal.
  - **BEING HIT COSTS YOU YOUR SPEED**
    ([`docs/design/player.md`](docs/design/player.md) § Being hit).
    `Player.stagger`, a clock on the tick row, mirrored in `simulation.ts`.
    Staggered walking (2.73 tiles/s) barely beats a zombie's 2.6; staggered
    sprinting still escapes. Stamina is now what decides whether you get out.
  - **THE FOREST SCALES WITH THE DAY** (same doc as the crowd, § The night gets
    bigger). Population, refill rate and wave size all walk with `day`.
    Deliberately NOT health or damage.
  - **THE SHELF AND THE CURVE** — the shop draws distinct-first so six tables
    show six things (it was routinely showing two), and `XP_BASE` went 40 ->
    110 (growth 1.4 -> 1.28) so the first level is a night's fighting rather
    than the first minute's.
  - **TWO PIECES OF THAT PASS WERE BUILT AND THEN REVERTED**, both on the
    user's call after reading them, and both reversals are written up as design
    law rather than deleted quietly:
    - **A NIGHT CLOCK** — rolled countdown, HUD timer, closed extraction at
      zero. Out because it made every decision a scheduling decision: the
      player reads the corner of the screen instead of the forest, and the
      pressure it creates is administrative rather than frightening. The hole
      it aimed at (waiting costs nothing) is now the population curve's job.
      See [`docs/design/extraction.md`](docs/design/extraction.md) § No clock.
    - **XP FOR EXTRACTION** — paid per point of value poured into a pad. Out
      because it made the level bar a second quota meter: one act was already
      paying money, a quest row and the night's objective, and the number over
      a dying body stopped being the only reason to fight. Killing is the sole
      source of xp. See [`docs/design/skills.md`](docs/design/skills.md)
      § What a level costs.

- **GEAR LANDED BEFORE IT: LÂMINAS, WORN ARMOUR AND THE SHIELD.** Three systems in
  one pass, all documented in the new [`docs/design/gear.md`](docs/design/gear.md).
  Headlines:
  - **The belt's last cell is a BLADE CELL now, not "the knife".** It is still
    never empty — that was always the promise, and the fixed knife was one
    implementation of it — but what it holds changes. `axe` and `katana` are
    real rows, found in the world AND sold, and every lâmina is the knife's
    own three beats through seven multipliers (`weapons.BladeProfile`). The
    knife's profile is all ones and `test_gear.py` pins that the generator
    reproduces it exactly. The knife itself is NOT AN OBJECT: replace it and
    nothing hits the floor; replace an axe and the axe does.
  - **Armour is the fourth container** (`server/app/armor.py`): three slots,
    four materials, per-piece durability, visible on the body through the
    `gear` overlay system that already carried the backpack. Everything is
    derived from the zombie's CLAW the way the guns are derived from its
    health — once, at build time: the rating that comes out is FLAT damage
    points, so nothing on a card or the wire has to name a creature to explain
    it. The ladder is 2 / 3 / 5 / 7 armour over 8 / 24 / 60 / 112 durability,
    which is 4 / 8 / 12 / 16 blows exactly. One blow lands on ONE part, rolled
    against coverage taken off the player sprite's own row bands — so on this chibi figure the HELMET is the
    piece that matters most, which is what the silhouette says rather than a
    balance call.
  - **The riot shield** eats a gun cell, goes up on RIGHT MOUSE, blocks
    completely inside a 140-degree arc, slows the walk, and comes apart in
    fourteen claws. It is the only thing in the game that takes a blow to
    zero.
  - **The shop is three ladders now** and the day walks all of them; the
    eleven-gun ladder comes out byte-for-byte what it was.
  **VERIFIED HEADLESSLY, NOT PLAYED.** `test_gear.py` (8 groups) plus the
  whole existing suite and `bun run typecheck` are green, and the live wire
  was checked from a browser console — the config, the catalogs and the belt
  all arrive correctly. Nobody has yet worn a set, watched a plate break
  mid-fight, or stood behind the shield. First playthrough should watch for:
  whether the three HUD bars read at a glance or are just noise beside the
  health bar; whether a steel set at 2.7 kg is a real movement cost or is
  ignored; whether losing the chestplate mid-fight lands as an EVENT (it has
  no sound of its own yet — see below); and whether the shield's 0.55x walk
  makes raising it a decision or just makes it annoying.


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
- **THE FIRST BOSS IS IN.** THE SAWYER — the logging crew's foreman — is the
  end of `BOSS_DAY` (**2**, in `config.py` — one constant, read in one place).
  The staging: a normal night, and the exit corridor opens onto
  a round yard instead of onto the shop, whose own way out opens straight
  across from the way in, and only once he is down. Four moves on four range
  bands, an animated telegraph on every one, an enrage at half health, and a
  thrown crescent. His timings come out of the art's own manifest — see the mirrors list in [`AGENTS.md`](AGENTS.md).
  **Verified headlessly, not in a live browser**: `test_boss_fight.py` drives a
  whole boss night and `bun tests/boss-clock.ts` pins the animation contract,
  but nobody has yet stood in the yard and fought him. First playthrough should
  watch for: whether 900 HP solo is the right length, whether the chop's 0.64s
  windup is readable, and whether the ring at 21 tiles is too big to corner him
  in or too small to kite in.
  The HUD bar is a struck gold plate with five segments, and the yard is LIT —
  a ring of drums, four burning heaps and a real ambient floor. That floor is
  the second exception in the game to "ambient is zero where you can die"; the
  argument is in `zones.ARENA_AMBIENT`.
- Weapon feel: shotgun cone and melee swing landed; the catalog's derivation from CS2 stats is stable.

## Recently completed

| | |
| --- | --- |
| **the belt lost its knife and kept its promise** | `KNIFE_SLOT` is `BLADE_SLOT`, `Hotbar.add` routes on `is_blade`, and `Room.swap_blade` is the one way steel changes hands. Every rule about that cell follows from it having no empty state, which is the one shape the rest of the belt does not have |
| **the shop sells AMMUNITION** | a row of open crates against the south wall, one per calibre somebody in the room is carrying — so a party of knives sees an empty wall, and buying the first shotgun DROPS a crate of shells in (a fall, a hard landing, two bounces, on the client's own clock off a row it has not drawn before). A crate never sells out, and a box costs its own share of a full reserve at half the price of the cheapest gun that eats it — derived, no price list. New art: `make_store.make_ammobox`, five frames, the only boxes in the room drawn OPEN. **Not yet played in a browser** — worth watching whether the crates read as buyable next to the six tables, and whether pistol rounds at 4 gold are too close to free |
| **eighteen more skills, and armour** | the catalog is 36 rows (9/8/8/6/5) because a ten-day run was seeing the same three commons; legendary odds doubled (2 -> 4 in `PULL_WEIGHTS`) because at one in fifty most runs never saw the colour the machine dramatises. `Mods.armor` is the one new axis — damage TAKEN, applied in `Room.damage_player`, floored at 0.35 so a stacked run cannot reach zero. `make_skills._check_order` now fails the build if the icon sheet and the catalog disagree, which nothing at runtime would notice |
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

- **Gear has no sound of its own.** A plate soaking is silent (the blow it
  came with is not) and a piece breaking borrows `crate-break` pitched up. The
  three that are missing are a steel tick, a leather scuff and a
  polycarbonate crack — three recipes in `make_audio.py` and one call site
  each. Losing a chestplate is currently an event with no audio, which is the
  weakest part of the whole system.
- **The shield has no impact art.** A blow stopping dead on it looks the same
  as a blow missing. It belongs in `weapon-vfx` and wants the hit point, which
  `snapshot.armorHits` already carries.
- **The twelve armour overlays have not been watched at speed.**
  `make_armor._check` fails the build if a piece leaves the 16x16 grid and the
  bands were measured off the real player sheet, so they are ON the body — but
  nobody has watched a full steel set walk across a clearing to see whether it
  reads as worn or as painted on. The head piece is the one to look at: it
  covers the top four rows of a head that is nearly half the figure.

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
4. Play a night in a full set and a night behind the shield, then tune
   `armor.HITS_BASE`, `CEILING_SHARE` and `SHIELD_HITS` against what actually
   happened rather than against the arithmetic.
5. The three missing gear sounds, and the shield's block spark.

## Do not touch

Unless the task is explicitly about them:

- `client/src/components/ui/**` — generated coss/shadcn components. Add with `bunx --bun shadcn@latest add @coss/<name>`, never hand-edit.
- `assets/processed/**` — generated output. Edit the generator in `server/tools/`.
- `assets/raw/**` and `assets/inspiration/**` — never served, never read at runtime.
- `server/.venv/`, `client/node_modules/`, `client/dist/`.
- `Room.damage_player` — the ONE door every damaging thing in the game comes
  through, and now the only place the shield, worn armour and `Mods.armor` are
  applied. A `return` added above the plate is armour that silently stops
  working.
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
