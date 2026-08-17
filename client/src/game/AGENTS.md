# client/src/game/ — game core

## Purpose

Everything between the socket and the renderer: the loop, the predicted local
player, interpolated remotes, world state, transient effects, and the single
seam React is allowed to read.

## Ownership

| file | owns |
| --- | --- |
| `game.ts` | orchestrator: two clocks, render loop, `start()`/`dispose()`, hunt-diamond latch |
| `lobby-scene.ts` | the camp, drawn before the simulation is allowed to run |
| `simulation.ts` | movement — mirror of `server/app/simulation.py` |
| `prediction.ts` | apply-locally, replay-on-ack reconciliation |
| `interpolation.ts` | remote entity smoothing |
| `input.ts` | keyboard/mouse sampling into an `InputPacket` (1/2/3 is the hotbar) |
| `world.ts` | client tile map, collision + sight queries, fires, hearth mask, placed scenery, live crates, the extraction rift |
| `combat.ts` | client-side shot feel: capsules, tile DDA, crate sprite boxes |
| `effects.ts` | tracers, blade paths, dust, blood, floating text, event lights, boot prints, crate smash, wind, death burst |
| `entity-visuals.ts` | per-entity flash, recoil, gun kick/pump, hit-stun tilt, anim, worn wounds; `HIT_FLASH_LIFE` is also the crate smash blink |
| `lantern.ts` | four-cell battery, produces `output` 0..1 |
| `hud-store.ts` | the only seam to React; `HUD_INTERVAL` = 0.2 s |
| `tooltip-anchors.ts` | screen-space points for world `Tooltip`s, written every frame |
| `exit-guide.ts` | extraction-exit arrow: where on screen it belongs, and the smoothing between the raw target and what is drawn |
| `inventory-anchors.ts` | screen-space centres for the HUD bag (pack + slots) |
| `inventory-actions.ts` | bag → socket: `Game` binds `drop`; React never owns the connection |
| `loot-flies.ts` | collect flies: hold over the head, then travel; membership is a store, pose is per-frame |

## Local Contracts

- Two clocks: a fixed 30 Hz tick samples input, predicts and sends; `rAF`
  interpolates, smooths and renders. Do not move prediction into `rAF`.
- `simulation.ts` is the **only** place the local player may be moved, and it
  must stay a line-for-line mirror of the Python version. Carried weight
  scales `moveSpeed` (`carryScale`); prediction reads `LocalPlayer.carryWeight`,
  which is `Game.moveWeight` — **the bag plus only the weapon in hand**, a
  mirror of `Player.carry_weight`. It is NOT roster `inv.w`: that field is
  the pocket alone and is what the bag's `current / maxkg` bar shows, since
  guns must not eat a budget that means "how much loot fits". The sum is
  rebuilt here rather than sent because `heldSlot` is client-authored — a
  server-computed number would be stale for exactly the frames the player is
  watching their own speed change, so every path that can move it (welcome,
  roster, a bag toss, `selectHotbar`) reassigns `carryWeight` on the spot.
- `hud-store.ts` is the only channel to the UI for state. World tooltip
  positions travel through `tooltip-anchors.ts` (written every frame, never
  subscribed). The exit arrow pose travels through `exit-guide.ts` the same
  way. Nothing here may touch the DOM beyond the two canvases
  `game.ts` owns.
- **`Game` does not own its socket.** The connection is created by
  `hooks/useRoomSession` and has been carrying the lobby since before the game
  existed; `Game` subscribes in `start()` and unsubscribes in `dispose()`, and
  must never close it. The `welcome` it was built from is replayed in `start()`
  because it arrived first. A later welcome (forest after camp) is handled by
  `onWelcome` on the same instance: it rebuilds the map and holds the intro,
  but it must resume the input sequence from `max(local.sequence, welcome.ack)`.
  Starting at 0 while the server still holds the camp's `last_processed_seq`
  drops every later packet as a replay, and you cannot walk off the spawn tile.
- **A snapshot row is only what moves.** Identity and the score board arrive on
  `snapshot.roster` a few times a second; `game.ts` caches it by id and every
  name, colour and HUD number is read from that cache. Never expect a name on a
  snapshot player, and reconcile against the row's own `seq` — the snapshot has
  no `ack`.
- `lobby-scene.ts` is decoration only: no input, no prediction, no socket. It
  draws through the arena's own `TerrainLayer`, so the lobby and the game
  cannot drift apart.
- **The lobby draws the real camp.** `setCamp` takes the map from `hello` and
  `setMembers` takes the server's own coordinates; the scene never decides
  where anybody stands. It used to force the local player into the front seat,
  which meant every client saw a different party and everyone's characters
  jumped the instant the run started. The local player is marked by the ring
  under their feet instead. The one caller with no server — the title screen —
  falls back to a locally generated clearing, which only has to LOOK like the
  place because nobody is standing in it. Its map is the same size as the real
  camp (`CAMP_WIDTH_TILES` × `CAMP_HEIGHT_TILES`): a smaller one makes the
  camera clamp and pulls the fire off the rest anchor, so entering a room jumps
  it. The rest anchor itself is `campFireAnchor` in `render/framing.ts`, shared
  with the title screen.
- Positions arrive as the CENTRE of a collision box, the way a snapshot carries
  them; the scene converts to a contact point with `config.playerHalfHeight`.
  Getting that wrong is a party floating above their own shadows.
- **The lobby performs the transition, not the arena.** `beginLaunch` drifts the
  camera from the fire onto the local player, takes the anchor back to centre
  and pushes from `campZoom` to `ARENA_ZOOM`, all on one smootherstep — so the
  last frame this scene draws is pixel-for-pixel the first frame the arena
  draws, and `Camera` has no arrival code at all. The screen swap waits for the
  move to land (see `screens/RoomScreen`), never for the `welcome`.
- The lobby's canvas is FULL SCREEN with the chrome floating over it, for the
  same reason: the arena's canvas is the whole window, so a lobby canvas in a
  column beside a sidebar would shift the world sideways at the handover no
  matter how well the camera matched.
- The lobby runs the arena's `FovField` and `DarknessLayer` over the same
  bonfire light, in the arena's pass order. Nothing here may draw its own
  version of the night — the camp has to be lit identically before and after
  the run starts, and it is, by being lit by the same code.
- The **hearth** is the fire plus the seat ring, and nothing decorative stands
  in it: the map generator refuses trees and rocks there, and a `TerrainLayer`
  decoration mask (`world.hearthMask`) refuses grass and ferns. Both measure on
  the same ellipse the seats use. A plant in front of a player hides the
  character the roster is pointing at. The arena sets the same mask, because
  `preparation` is that same ground.
- A **bonfire is a tile** (`FIRE`), and everything reads it off the map:
  collision, the animated sprite, and the light. It blocks bodies but not sight
  (`blocksSight`) — left as an occluder it would shadow the half of the party
  sitting behind it, which is the one place in the camp that must be lit.
- **`TileMap.scenery` is the placed half of the world and it is not derivable.**
  Everything else the client draws comes off `world.seed` hashed with a tile
  coordinate, because one rock is as good as another. The scenes on the map
  payload (`server/app/scenery.py`) cannot work that way — their meaning is the
  relationship between pieces — so they arrive as rows and are unpacked once,
  split into `flat` (baked into the ground canvas) and `standing` (sorted by
  `y` at parse time, because the renderer MERGES it into the entity depth order
  every frame and that merge walks two ascending lists). `PROP` is the tile kind
  a building's footprint claims: solid, sight-blocking, painted as ground, and
  drawn by nothing — the sprite in `scenery.standing` covers it. `LOW` is
  waist-high cover (crate, fence, log, sign): solid to bodies and bullets,
  transparent to light, painted as ground the same way. A log that blocked
  sight would throw a hard shadow; one that was walkable would not be cover.
  Standing collision is one tile tall at the contact — a tree's canopy and a
  sign's board are drawn on the tiles above and are not walls.
- **The hunt diamond is the one tell that may outlive the light, and only
  after you earned it.** `Game.latchAlertMarks` records an enemy the team
  can already see while its `aw` is past `NOTICE_AT`. That latch is what
  lets the mark sit on the night after the lamp goes out. A hunter that
  committed in the dark, never seen, is not latched — painting its diamond
  would be a free tracker. The latch dies when the creature calms down,
  despawns, or the map is replaced.
- **A hit answers in two timescales and it needs both.** The IMPACT is the
  frame it landed on — white flash, debris kicking back along the ray, a spray
  of blood carrying forward out the far side (`Effects.spawnBlood`), a number,
  and — if the round was heavy — a knockback along the shot with a tilt
  around the feet (`EntityVisuals.takeHit`). `hitPower(damage)` is the
  scale: a Glock flinches, a Deagle plants them, an AWP still hits harder
  than either — the shove itself stays small. Blood volume and impact
  debris use the same number. The freeze stacks so a burst keeps the
  sprite planted; the walk slow/stop is authoritative (`Enemy.stagger`),
  not a client freeze over a body that keeps walking.
  The WOUND is what is still there ten seconds later: one frame of the gore
  sheet pinned to the sprite by `EntityVisuals.splatter`, riding the body
  through its walk cycle and its facings until it dries. Without the second a
  zombie at 1 HP looks exactly like one at full, because the health bar is a
  number and a number is not damage. Only flesh bleeds — a crate hit is an
  impact and a blocked swing is neither, so `spawnShot` takes `flesh`
  separately from `hit` and `onAttack` splatters only when the swing got
  through. Wounds are normalised to the sprite (`u`/`v`), never world pixels:
  this folder does not know how big anything is, and the renderer scales them
  by whatever sheet it is drawing. It also MASKS them to the silhouette, which
  makes `splatter`'s ranges a contract rather than taste — a mark aimed past
  the body is deleted, not clipped, so it aims at the trunk and stays inside
  it. Widening those ranges quietly costs hits their wound.
- **Footprints are the one effect that is not short-lived, and the exception is
  the feature.** `Game.trackFootsteps` lays one per stride for every body on
  visible ground, with the depth coming from the SOIL under it (`soilAt`), and
  they last long enough to be navigation rather than flavour — on an extraction
  run the trail you left walking out is how you find the way back. They are
  laid AFTER `applyVisibility`, so nothing unlit ever marks the ground: a trail
  appearing out of the dark would be a free tracker. Enemies leave them too,
  and that is the interesting half — fresh prints crossing yours that you did
  not make. The compass frame mirrors `track_frame` in `server/app/scenery.py`,
  so the map's abandoned trails and the player's own prints are the same mark.
  Stepping in a corpse's pool tints the next prints red (`Footprint.blood`),
  decaying each stride — a trail of what you walked through, drying out behind
  you.
- **Corpses stay.** `spawnDeath` is the juice (dirt, a wind puff, the death
  VFX sheet); the body is a persistent row (`welcome.corpses` / dirty
  snapshot), drawn from `<sheet>-death` (a one-shot timeline that holds the
  last prone frame) with a growing pool from scenery `blood.png`. Never
  rotate the walk sprite. Hidden in the dark. Embark clears them.
  `DEATH_TIME` / `DEATH_IMPACT` mirror `make_vfx.py`; the thud in
  `zombie-death` sits on that impact. The body sheet's own `frames / fps`
  is the collapse clock.
- **The extraction pads are the objects on the map with a STATE MACHINE, and
  the split is: the server says WHAT, the client says what that FEELS like.**
  Count scales with the day (`rift.count_for_day`), but only ONE may be awake
  at a time. Finding them is a quest
  (`hud-store.quests`, id `extract`, `0/N`). The console press is the tick,
  not standing nearby — that is when `feed` appears (catalog gold, coin
  badge on the HUD), carrying THAT pad's quota. Pressing a dormant console
  starts the ceremony; feeding an open one spends bag catalog value toward
  its quota. Paying the quota does not close anything: it makes the pad
  `ready`, and a player shuts it by hand. Shutting the LAST pad
  carves `world.egress`, kills the lantern
  (`Lantern.kill`), and offers `exit`. Reaching the mouth is another
  welcome — at the STORE, not at camp. Leaving the store is another welcome
  again, at the NEXT night's forest: after the first expedition the run is a
  two-zone cycle and never comes back to the camp.
- **The store is an arrival like the forest is, and an ordinary forest map.**
  Same corridor, same seal, so `arriving` is true for both zone kinds and the
  camp is the only place you simply appear in — and only ever once, at the
  start of the run. It takes the darkness, the
  decoration mask and the terrain bake exactly as a forest does — there is no
  zone branch for any of it, and adding one back is how it became an interior
  the first time. The only client-side special case is the merchant's clip
  player, stepped on the render clock exactly like the rift's ceremony,
  because neither has ever been on the wire.
  `nearStand` mirrors `Room._stand_in_reach` feet-to-table, and it drives all
  three of the lift, the pool and the prompt — a layer working it out for
  itself would be a second opinion about what "close enough" means.
  - **The pad's whole feed state is on the wire** — `fed`, `need`, `level`,
    `ready` on `RiftStateRow` — and the client re-derives none of it. `level`
    especially: the overfeed tiers live in `server/app/rift.py` and picking
    which colour bank to draw from is a lookup, not arithmetic, for the same
    reason the ceremony timings are.
  - Overfeeding is REPEATABLE and the pocket is what says so. E on a ready pad
    feeds while the bag has value and shuts it when the bag is empty
    (`riftPrompt` modes `over` / `close`, mirroring `Room.activate_rift`). A
    tier bump chimes `rarity` at the tier's own variant; the quota landing
    chimes variant 4. Both fire off a state row where the state STRING did not
    change, which is exactly why they are checked separately.
  - `over` is NOT offered on the last pad — the overpayment is only paid back
    while there is another console to carry a core to, so on the final rift
    paid means shut. The prompt checks that the same way the server does (is
    any pad still `dormant`), because a mode the server would ignore is worse
    than no prompt at all.
  - A `busy` prompt (another pad already awake) buzzes locally instead of
    sending a packet the server would drop.
  Two snapshot rows a pad — pressed, and open — and the four seconds between
  them run on this client's own render clock (`Game.stepRift`), because a
  ceremony resolved at 6 Hz would step rather than play. The server's `t` is
  adopted on every row, so somebody joining mid-sequence picks it up in
  progress instead of watching it replay from zero.
  - **The stagger IS the effect.** The four stones catch one at a time
    (`rift.PILLAR_STAGGER`), so the light visibly runs around the ring. Firing
    them together costs nothing and reads as a light switch. Each catch is a
    small trauma and a chime; the tear is a bigger shove. No point-light disc
    — a `ctx.arc` gradient in world pixels becomes a hard circle at arena zoom.
    Those beats fire on the frame `elapsed` CROSSES them, which is what makes
    each happen exactly once when a frame runs long.
  - Timing is ONE clock: `config.rift`, straight out of `server/app/rift.py`,
    whose sheet durations are `frames / fps` from `make_rift.py`. Three files,
    one set of numbers, the same discipline `SUMMON_TIME` already follows.
  - E offers a pad BEFORE a crate and before the fire: if you are standing at
    the console with a box at your elbow, you did not walk there for the box.
    Dormant shows "abrir" (or "outra fenda está aberta"); under quota shows
    "alimentar a fenda"; past it shows "saturar a fenda" with the tier; with an
    empty pocket it shows "fechar a fenda". All four carry the coin badge and
    the pad's own `have/need`. An empty bag at a hungry pad refuses audibly and
    does not send. Spent, charging and collapsing show nothing — a prompt on a
    structure that is already answering reads as the first press not having
    registered.
  - Activation is one-way. There is no packet to switch a pad back off, and
    collapse is a player's second press, never a timer.
  - The exit arrow (`hud/ExitGuide`, `/hud/arrow.png`) is generated HUD
    chrome, not a sprite in the forest. It sits outside `HudScreen` — the
    fish-eye would pull it off the glass — and it rides HALFWAY between the
    player and the screen edge rather than on the bezel: on the bezel it is
    furthest from the thing it is about, it fights the hotbar and the minimap
    for the corner, and it is where the jitter is worst because the ray is
    longest there. The ray leaves the player's UPPER half, so the arrow rides
    above the action instead of over the ground they are walking onto.
  - **The arrow's target is not smooth and cannot be made smooth upstream.**
    `projectionFor` rounds the camera offset to a whole screen pixel, so the
    projected player position twitches every frame, and a ray cast from it
    multiplies the twitch by the distance to the edge. `game.ts` writes a
    TARGET; `exit-guide.ts` owns a second, smoothed pose (`stepExitGuide`,
    exponential in `exp(-dt/tau)` so it is frame-rate independent, shortest-arc
    on the angle so it never spins the long way round the ±pi seam) and
    `ExitGuide` applies it as a sub-pixel `translate3d`. Do not round that
    transform — it puts the jitter straight back.
- `Game.lights` is bonfires read off the tiles PLUS whatever the map's scenes
  are still burning (`world.scenery.lights`), on one list. The lighting has no
  concept of a camp light versus a forest light and must not grow one. Rebuild
  it when that list changes: an open rift pushes a beacon onto it and a spent
  one takes it off, and the exit's torches join it when `egress` arrives
  (`rebuildLights`). A snapshot taken only at welcome leaves
  the pad dark after the tear. The torches matter most of all here — the exit
  opens during the blackout, so for the rest of that night they are the only
  thing burning on the map, and a torch that only glowed in the additive pass
  would light nothing and reveal nothing. `TileMap` lights them in BOTH
  `setEgress` and its constructor, or a client that reconnects after the exit
  opened is the one player walking home in the dark.
- VOID is a winding gap in the treeline, not a missing floor and not a
  rectangle: painted as ground, crushed by a darkness falloff.
  `blocksSight` lets light fall into it so the trees do not close into a
  wall; the darkness pass then kills the warmth along the path so leaked
  firelight never turns the mouth into a hallway. It is solid at camp and
  on the forest arrival; once `world.egress` is set it is the walkable
  extraction corridor — the same dark gap the party already walked out of
  the camp through. Forest `world.entrance`
  is the same shape on a random edge: after the emerge, `tilePatches`
  turn those tiles to TREE. `Renderer.stampTiles` paints the new trunks
  into the prop bake and `DarknessLayer.invalidatePath` lets the crush
  recede; the minimap rebuilds so the corridor filling in is visible.
  Soil under VOID was already forest floor — do not rebuild the ground
  canvas for a slam. Egress opening is the inverse: VOID appears in the
  treeline and `stampTiles` plus `invalidatePath` bring the crush back.
- **The summon sheet is the clock.** `SUMMON_TIME` is the sheet's
  `frames / fps` and `SUMMON_IMPACT` mirrors `IMPACT_AT` in
  `server/tools/make_vfx.py`; the body must finish resolving on the frame the
  sprite flashes, or the arrival lands twice. The sheet owns the flash and the
  shockwaves — the code only adds what it cannot know, which is whose arrival
  it is: the sheet is greyscale and tinted with the arriving player's colour,
  plus one ring and a spray of sparks in the same colour.
- **The kindle sheet is the fire's clock.** `KINDLE_TIME` is the sheet's
  `frames / fps` and `KINDLE_IMPACT` mirrors `KINDLE_IMPACT` in
  `make_vfx.py`. It plays on the start-match launch, on the bonfire — not
  when a player is summoned, and not when the lobby first appears. The
  code only adds what the sheet cannot know: live embers past the frame
  and a surge on the same `flicker` every lit thing reads. No expanding
  ring; the column is the tell. The sheet is greyscale and tinted with
  `fire.core`, so the roar belongs to the hearth rather than to a player.
- Lobby names are drawn in SCREEN space, on a card ABOVE the head. Above,
  because the seat ring is elliptical and a label under a player's feet lands
  on whoever is sitting closer to the camera. The card is the roster row in
  pixels — inset fill, hairline border, 2px colour bar — and every measurement
  is a whole multiple of one design pixel so it stays on the font's grid.
- `dispose()` releases every timer, listener, observer and rAF handle created in
  this folder.
- **Sound is driven from two places and the split is deliberate.** EVENTS (a
  shot, a hit, a crate, a pickup) are played by the handler that already knows
  the event happened, next to the visual effect they belong with. STATE (which
  ambience is playing, how fast the heart is going, whether anything is growling
  out there) is reconciled every frame in `updateAudio`, called from `render`
  after `applyVisibility` and `latchAlertMarks` so it reads the same resolved
  entities the renderer is about to draw. The listener is the PLAYER, not the
  camera — during the walk-out the camera looks ahead at the VOID mouth, and a
  party marching away from a fire that got louder would be wrong.
- **The zone says what the place sounds like**, exactly as it already says the
  title card, whether guns fire and whether the lamp works. `applyZoneAmbience`
  runs on arrival and nothing reads the map to infer it. Forest weather
  (`zone.weather`) picks the mix: rain fades in the `rain` bed, fog quiets
  the wind, clear is wind + night as before. Camp is always the fire.
- **Ambience is declared by the SCREEN, and `lobby-scene` declares none.** The
  scene is decoration and draws the title screen's backdrop as well as a room's,
  so it cannot know whether it is a place you are standing in — the menu's fire
  is a picture and must stay silent. `LobbyScreen` states `{ fire: 1 }` on
  mount, `HomeScreen` states `{}`, and `Game` states the zone's on arrival.
  None of them clear on unmount: whoever mounts next declares the mix, which is
  what lets lobby → arena hand over with no gap while lobby → menu still goes
  quiet. `Game.dispose()` is the only release (`stopBeds`).
- **Footsteps are played from `trackFootsteps`**, because that loop is already
  the one place that fires exactly once per stride, for every body, with the
  soil in hand — a separate timer keyed off velocity would drift out of sync
  with the print. It inherits that loop's visibility gate, so the unlit half of
  the forest speaks through GROWLS instead of footsteps and the two channels say
  different things.
- **The ambient growl is NOT gated on visibility, and that is the point.** The
  sound is what tells you something is there; the lantern is what tells you
  where. The alert snarl is latched per enemy id so a hunt announces itself once
  and then shuts up, and it re-arms when the creature calms — same lifetime as
  the hunt diamond.
- Sounds timed against a sprite sheet are aligned in the GENERATOR, not here:
  `kindle` and `summon` put their impact on the frame the sheet flashes. Moving
  a sheet's `frames / fps` means re-timing its sound in `make_audio.py`.
- **Every player wears the backpack.** `toDrawablePlayer` sets `gear` to
  `[welcome.config.backpackSprite]` and the lobby draws the same overlay on
  every seat. It is always on for now — unequip is a later field, not a
  missing sprite. The sheet is greyscale and tinted with the player's colour.
- **A gun is in the hand, selected locally.** `held` rides the input packet
  the way the lantern switch does (slot index, or -1 holstered). The belt
  itself is roster `guns`; a collect with `dest: "hotbar"` flies to
  `hotbar-N`. Prediction fires with that weapon's cadence / damage / range
  from `welcome.config.weapons`. AWP `aimDelay` waits on the held trigger
  (`adsHold`); `stepScope` eases `Camera.zoom` toward `scopeZoom`. Predicted
  tracers start at `gunMuzzle` so the streak leaves the barrel. Holstered
  draws nothing — no white line. The belt is 3 cells: two gun slots, both
  EMPTY at the start of a run, and the knife last
  (`server/app/weapons.py`); 3 selects it.
- **The knife swings, and the split with prediction is different from a
  gun's.** `Game.tick` branches on `weapon.melee`, not on `kind`, and
  `predictSwing` runs the same chain arithmetic the server does off the
  same `ComboStep` numbers (`comboStep` / `comboLeft` mirror
  `Player.combo_step` / `combo_left`). What it predicts is the ARC, the
  lunge, the trauma and the sound — everything the click bought. What it
  deliberately does NOT predict is who got opened: `predictShot` runs a
  local hitscan because it has to know where to stop a tracer, but a swing
  has no length to resolve, so blood, damage numbers and wounds all come
  back on the authoritative `swings` row. Guessing victims would stamp a
  WOUND on a body the server says was outside the arc, and a wound is the
  one effect here that lasts long enough to be a lie.
- **A blade path is drawn from the HAND, a claw arc is drawn on the
  VICTIM.** `Effects.swings` and `Effects.slashes` are two objects for that
  reason and must not be merged. A player has to read their own reach
  whether or not the swing landed — so a whiff still draws, and it draws
  from the body centre the server actually swept from. An enemy's claw is
  the opposite question ("that one got me") and belongs on the thing it
  hit. `onSwing` therefore skips the arc for the local player, who has been
  looking at their own since the frame they clicked, and applies the bodies
  for everybody.
- **A zombie is dressed at spawn.** `toDrawableEnemy` picks the body sheet
  from `enemyTypes[t].variants[v]` and builds `gear` as clothes then hat
  from the optional snapshot indices. The look is identity, not motion —
  interpolation copies the indices, it does not blend them. Sheets are
  loaded from the type's `variants` / `hats` / `clothes` lists on welcome.
- Tuning comes from `welcome.config`; the lantern's drain/recharge constants
  are the exception, because the battery is client-local. The switch is not:
  `on` is on the input packet and every player snapshot so remotes go dark.
- `lantern.output` is the local lamp the lighting system reads — fov beam gain
  and reach, hearth warmth, the HUD cells, and how far every enemy on screen
  can see you (`sightReach`). Remotes contribute 0 or 1 from their snapshot
  `lantern` flag.
- **The lamp is a two-way switch and `sightReach` is where that is answered.**
  Enemy stat blocks carry two reaches; the local battery's output picks between
  them. The server decides the real thing on the boolean switch — including
  while a creature hunts, so killing the lamp shortens a hunter too. The
  few frames of fade where they disagree cost nothing. The tell is the hunt
  diamond (`layers/vision.ts`), not a floor cone, and only after this client
  has seen the body while it was already alerting (`alertSeen` / `alertKnown`).
- `lantern.allowed` comes from `welcome.zone.lantern` and is a property of the
  LAMP, not a check at the call site, so every route to switching on goes
  through one refusal. A refused press is COUNTED, not ignored: the HUD reads
  at 5 Hz and has to be able to answer each keypress, because a control that
  silently does nothing reads as a broken keybind rather than as a rule.
  Paying the feed quota is `Lantern.kill`: charge is zero and will not
  trickle back until the next welcome. The server also strips `lantern` on
  every input for the rest of the night, so remotes go dark with you.
- The zone also masks `shoot` on the outgoing packet. The server drops it too,
  and the mask has to be on the packet or prediction draws a tracer that was
  never fired.
- Entering a zone HOLDS the player for `INTRO_TIME` **except the forest
  emerge**: movement and aim are masked on the outgoing packet (not at the
  input layer, or prediction would move them locally and yank them back),
  the character faces the camera, and the HUD keeps its corners off the
  glass. Forest skips that posed hold — `snapshot.arriving` is the camp
  walk-out in reverse, letterboxed (`cinematic`), looking into the trees,
  and `introLeft` stays 0. After every living body is on floor the woods
  slam the corridor (`tilePatches`); the player has the controls for that
  beat so they can look back. Then `hud-store.quests` fills.
- The camp walk-out (`snapshot.departing`) is the same mask plus no local
  prediction: the server puppets every body, and the local player is
  interpolated with the remotes so they cannot fight the march. Camera follows
  the party, looking ahead at the VOID mouth. E at the fire sends
  `{type:"ready"}`; the server is what decides whether it counted.
  `Game.locked` is departing OR arriving — interact, loot, crates, the rift
  prompt and prediction all key off that, not off `departing` alone.
- Entering a zone is announced ONCE, through `hud-store.arrival`, keyed by the
  zone key; `introducing` says whether the hold is still running. INTRO_TIME,
  `CARD_MS` in `hud/ZoneTitle` and the `zone-*` keyframes are one timeline. The
  card must clear BEFORE the hold ends, or the HUD rises under the title.
  Forest names the night over the march (`introducing` is false; `cinematic`
  covers the letterbox).

## Work Guidance

- New per-frame state stays here or in `render/`; it must not reach React.
- New HUD data means a field on the `hud-store` snapshot, published at 5 Hz —
  not a subscription from a component to the game. Camp ready uses `ready` and
  `prompt`; a nearby drop uses `lootPrompt`; the pocket uses `inventory`;
  the walk-out and the forest emerge use `cinematic`; a crate in reach uses
  `cratePrompt`; a pad in reach uses `riftPrompt`
  (`open` / `busy` / `feed` / `over` / `close`); a shop table in reach uses
  `buyPrompt` and the party's purse uses `balance`; the
  extraction exit arrow uses `exitGuide`. Run
  objectives use `quests` — announced at top-centre,
  then flown into the card under the minimap the way a collect flies into
  the bag. Completed rows rise and leave; the HUD dismisses them after
  that beat.
  A world `Tooltip` also needs an `anchor` id written in `syncTooltipAnchors`
  each frame — show/hide is the store, the pixels are the camera. E is
  interact: collect on a drop, smash a crate, open or feed a rift, buy off a
  shop table, ready at the fire. The server validates range.
  TAB toggles `inventory.open` locally and is patched immediately so the
  drawer does not wait for the 5 Hz tick. A collect fly is
  `loot-flies` + `inventory-anchors`, not a React render: hold over the
  head, open the bag, then travel into the slot. Travel waits until
  `slot-N` has a live anchor (drawer open, cell on screen) and aims
  through `warpHudPoint` so the sprite lands on the glass-warped cell.
  The pocket snapshot carries `gold` as the sum of catalog values in
  the bag (`value × qty`). The cell, the weight bar and that total
  stay at their pre-collect state while a fly is in the air.
  Dragging a cell off the panel calls `requestInventoryDrop`; `Game`
  sends `{type:"drop","slot"}` and clears the cell until the roster
  confirms. `lootPrompt.full` is a bag that cannot take the nearby drop;
  `lootPrompt.swap` is a full BELT that would trade instead, and it carries
  the name of the gun in hand so the tooltip can say what you are putting
  down as well as what you are picking up.
  The hotbar is `hotbar` on the same snapshot: two gun slots and the
  knife, above the lantern, always visible. 1/2/3 selects (same key
  holsters) and is patched immediately, like TAB. A gun fly uses dest
  `hotbar` and anchor `hotbar-N`. `held` rides the input packet. AWP
  hold-to-aim zooms the camera toward `scopeZoom`; ammo is named and unused.
- Anything long-lived created here gets a matching release in `Game.dispose()`
  in the same change.

## Verification

- `bun run typecheck` from `client/`.
- Rubber-banding on the local player means `simulation.ts` has drifted from the
  server; compare the two files directly.
