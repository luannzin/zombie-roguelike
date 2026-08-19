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
| `world.ts` | client tile map, collision + sight queries, fires, hearth mask, placed scenery, live interactive objects, the extraction rift |
| `objects.ts` | the client's copy of `welcome.config.objects`: which sheet, verb, prompt, footprint and hit box each object kind has. No table of its own |
| `combat.ts` | client-side shot feel: capsules, tile DDA, per-object sprite boxes (BREAKABLE only) |
| `effects.ts` | tracers, blade paths, dust, blood, floating text, event lights, boot prints, object one-shots, the loot pop, wind, death burst |
| `entity-visuals.ts` | per-entity flash, recoil, gun kick/pump, hit-stun tilt, anim, worn wounds; `HIT_FLASH_LIFE` is also the object one-shot blink |
| `lantern.ts` | four-cell battery, produces `output` 0..1 |
| `hud-store.ts` | the only seam to React; `HUD_INTERVAL` = 0.2 s |
| `tooltip-anchors.ts` | screen-space points for world `Tooltip`s, written every frame |
| `exit-guide.ts` | the way-out chevron: where on screen it belongs, and the smoothing between the raw target and what is drawn. It BLINKS — see the exit contract below |
| `inventory-anchors.ts` | screen-space centres for the HUD bag (pack + slots) |
| `inventory-actions.ts` | bag → socket: `Game` binds `drop`; React never owns the connection |
| `loot-flies.ts` | collect flies: hold over the head, then travel; membership is a store, pose is per-frame |
| `pad-cargo.ts` | the POUR's other half: items in the air out of a backpack, and the pile they become on a platform's deck. Deck-relative, so the load leaves with the skid |
| `machine.ts` | the upgrade machine's CEREMONY: one lever pull as beats, the BAND's scroll position per reel, the arm, and where the canister is. Timing comes from `config.machine` — a mirror of `server/app/machine.py` |
| `payout.ts` | the night's platforms being lowered into the shop, and the gold coming off them. Presentation only; the balance was credited server-side |

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
  waist-high cover (barrel, box, fence, log, sign): solid to bodies and bullets,
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
  number and a number is not damage. Only flesh bleeds — a barrel hit is an
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
  powers the deck and the corner lamps go GREEN. Feeding an open one spends
  bag catalog value toward its quota. Paying the quota does not call anything:
  it makes the pad `ready`, and a player CALLS THE PICKUP by hand. Calling
  the LAST pad carves `world.egress`, kills the lantern (`Lantern.kill`), and
  offers `exit`. Reaching the mouth is another welcome — at the STORE, not at
  camp. Leaving the store is another welcome again, at the NEXT night's
  forest: after the first expedition the run is a two-zone cycle and never
  comes back to the camp.
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
  - **The pad's whole feed state is on the wire** — `fed`, `need`, `ready` on
    `RiftStateRow` — and the client re-derives none of it. There is no `level`:
    overfeed tiers used to pick a colour bank and a drone count, and neither
    exists any more. Green lamps vs red sirens is the whole vocabulary.
  - Overfeeding is REPEATABLE and the pocket is what says so. E on a ready pad
    feeds while the bag has value and CALLS THE PICKUP when the bag is empty
    (`riftPrompt` modes `over` / `close`, mirroring `Room.activate_rift`). The
    quota landing chimes `rarity` variant 4. It fires off a state row where
    the state STRING did not change, which is exactly why it is checked
    separately from `onRiftState`'s string compare.
  - `over` is NOT offered on the last pad — the overpayment is only paid back
    while there is another console to carry a core to, so on the final rift
    paid means call. The prompt checks that the same way the server does (is
    any pad still `dormant`), because a mode the server would ignore is worse
    than no prompt at all.
  - A `busy` prompt (another pad already awake) buzzes locally instead of
    sending a packet the server would drop.
  Two snapshot rows a pad — pressed, and open — and the seconds between them
  (and the whole thirteen-second pickup) run on this client's own render clock
  (`Game.stepRift`), because a ceremony resolved at 6 Hz would step rather than
  play. The server's `t` is adopted on every row, so somebody joining
  mid-sequence picks it up in progress instead of watching it replay from zero.
  - **THE CALL IS THE SET PIECE.** `closeAt` is the press. Sirens start
    immediately (`playSfx('siren')` once per `siren.png` sweep) and
    `Room.sirening` has already put the pack on hunt. Four drones leave the
    treeline staggered, each arrival and each tie is a beat, the strain grows
    a shove rather than a hit, and the ground letting go is the only beat that
    earns a real camera slam. Those beats fire on the frame `elapsed` CROSSES
    them, which is what makes each happen exactly once when a frame runs long.
    No point-light disc — a `ctx.arc` gradient in world pixels becomes a hard
    circle at arena zoom; the light belongs to the sheets.
  - Timing is ONE clock: `config.rift`, straight out of `server/app/rift.py`.
    Three files, one set of numbers, the same discipline `SUMMON_TIME` already
    follows. There is nothing about the aircraft on the wire: `closeAt` plus
    the constants is the whole flight plan.
  - E offers a pad BEFORE an object and before the fire: if you are standing at
    the console with a box at your elbow, you did not walk there for the box.
    Dormant shows "ligar a plataforma" (or "outra plataforma está ligada");
    under quota shows "carregar a plataforma"; past it shows "sobrecarregar a
    plataforma"; with an empty pocket it shows "chamar a extração · o barulho
    atrai tudo" in the danger tone. All but the first carry the coin badge and
    the pad's own `have/need`. An empty bag at a hungry pad refuses audibly and
    does not send. Spent, charging and a pad already calling show nothing — a
    prompt on a structure that is already answering reads as the first press
    not having registered.
  - Activation is one-way. There is no packet to switch a pad back off, and
    the pickup is a player's second press, never a timer.
  - The way-out chevron (`hud/ExitGuide`, `/hud/chevron.png` — a TRIANGLE, not
    the thin dart on `arrow.png`) is generated HUD chrome, not a sprite in the
    forest. It sits outside `HudScreen` — the fish-eye would pull it off the
    glass — and it rides HALFWAY between the player and the screen edge rather
    than on the bezel: on the bezel it is furthest from the thing it is about,
    it fights the hotbar and the minimap for the corner, and it is where the
    jitter is worst because the ray is longest there. The ray leaves the
    player's UPPER half, so it rides above the action instead of over the
    ground they are walking onto.
  - **The chevron's target is not smooth and cannot be made smooth upstream.**
    `projectionFor` rounds the camera offset to a whole screen pixel, so the
    projected player position twitches every frame, and a ray cast from it
    multiplies the twitch by the distance to the edge. `game.ts` writes a
    TARGET; `exit-guide.ts` owns a second, smoothed pose (`stepExitGuide`,
    exponential in `exp(-dt/tau)` so it is frame-rate independent, shortest-arc
    on the angle so it never spins the long way round the ±pi seam) and
    `ExitGuide` applies it as a sub-pixel `translate3d`. Do not round that
    transform — it puts the jitter straight back. `snapExitGuide` drops the
    drawn pose without dropping the target, so the first painted frame of a
    night's chevron is ON the bearing rather than sweeping onto it from
    wherever the previous night left it.
- `Game.lights` is bonfires read off the tiles PLUS whatever the map's scenes
  are still burning (`world.scenery.lights`), on one list. The lighting has no
  concept of a camp light versus a forest light and must not grow one. Rebuild
  it when that list changes: an open rift pushes a beacon onto it and a spent
  one takes it off, and the exit's torches join it when `egress` arrives
  (`rebuildLights`). A snapshot taken only at welcome leaves
  the pad dark after it powers up. The torches matter most of all here — the exit
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
- **A LEVER PULL IS THE MACHINE'S OWN CEREMONY, and the split is the rift's.**
  The server resolves the roll in one frame and ships one `spins` row; this
  side flies four seconds off it plus `config.machine` on the RENDER clock
  (`Game.stepMachine`). Beats fire on the frame `elapsed` CROSSES them, so each
  happens exactly once when a frame runs long. Every client in the glade runs
  it — a slot machine going off is the loudest thing in the shop and the party
  should be able to look over at somebody else's legendary — and only the
  PULLER's client claims the canister into its HUD tray.
  - THE THIRD REEL IS THE DESIGN. Two stop on a fixed rhythm; the third holds
    for `reelHold[rarity]`, longer the better the pull was. Because the roll
    already happened the wait is honest — the machine is taking its time
    telling them, not deciding late.
  - **A REEL IS A BAND, NOT A FRAME INDEX.** `reelScroll` returns where a
    window sits on one tall strip of ten cells (`/machine/strip.png`), and the
    layer blits one or two source rects out of it — so a spin is a strip going
    past, the TEASE is the band decelerating through six or seven faces with
    the answer already decided, and the NEAR MISS is free, because the strip's
    fixed order puts a legendary next to a common. It is modelled BACKWARD from
    the stop (`landing - remaining(timeLeft)`), never integrated forward, so
    the reel arrives exactly on its face on exactly the frame it is due; a slot
    machine that stops between two symbols is broken in the one way everybody
    can see. Motion blur is the same blit again, offset and faded by the band's
    own speed. The two reel gaps in `server/app/machine.py` must stay longer
    than `REEL_DECEL`, or nothing in the middle of a pull is ever a blur.
  - The PAY LINE flashes across all three windows on the frame the last reel
    lands (`payLineFlash`), scaled by `pullGain` like everything else. The
    burst fires at the TRAY, which is where the prize comes out; the pay line
    is where it was decided, and the machine reacting to its own result has to
    come before the consequence of it.
  - RARITY IS A MULTIPLIER, NOT A SECOND ANIMATION. `pullGain` scales the
    burst, the marquee and the canister's glow off ONE curve, and the sounds
    ladder the same way (`reel` pitched with the tier, `rarity` behind it,
    `jackpot` only at epic and up). Five hand-authored ceremonies would be five
    things to learn instead of one.
- **THE PAYOUT IS AN ARRIVAL, NOT A TRANSACTION** (`payout.ts`). The balance is
  already credited when the party crosses the corridor; this owns the two
  seconds between the number being true and the player believing it. It starts
  in `onWelcome` off `world.store.payout`, and `Game.balanceShown` is what the
  HUD is allowed to SAY while gold is still in the air — driven off the
  ceremony's own clock rather than off however many coin sprites got drawn, so
  the number is exactly right when it stops.
- **THE EXIT IS FOUND, NOT FOLLOWED, AND THE CHEVRON BLINKS.** It used to be
  permanent, which made every other channel the exit has into decoration; then
  it faded out after ten seconds, which left a party that turned the wrong way
  at second twelve with nothing to ask. It now PULSES — a long solid burst on
  the frame the exit is carved, then dark, then a couple of seconds every few,
  for as long as the way out is uncrossed. `hud-store.exitGuide` is ONE BIT
  (there is an uncrossed exit) and the envelope lives in `hud/ExitGuide` on the
  render clock, because its ramps are shorter than the store's 200 ms
  republish. The other two channels carry the dark beats: the four torches at
  the threshold, and a slow spatial PING from the mouth (`Game.stepBeacon`) —
  which is the one that still works while the player is looking the other way.
  THERE IS NO COLUMN OF LIGHT ANY MORE. `drawEgressBeacon` threw one straight
  up over the treeline in world space, which was the best of the four channels
  right up until somebody noticed it was drawn off `world.egress` — and the
  SHOP has an egress (its north corridor). A party who walked into the
  merchant's clearing soon after calling the pickup got a flaring pillar
  standing in the exit of the one zone with nothing to navigate. It was deleted
  rather than special-cased: a marker that has to ask which map it is on is a
  marker that belongs to the map, and the exit already had three channels. The
  quest row is an ORDER
  now rather than a task (`quests.EXIT_LABEL`): the night is over and they are
  still in it.
- **A SNARL IS QUEUED, NOT PLAYED** (`Game.drainAlertQueue`). One creature
  noticing you is one snarl; the extraction alarm commits everything in earshot
  on the same frame, and stacking those is a wall of noise that says nothing
  about how many there are or where. Draining nearest-first at
  `ALERT_SNARL_GAP` turns it into heads turning one after another around you,
  and it is tuned against the server's own startle wave (`ai.STARTLE_*`).
- **AN EMPTY CONTAINER SAYS SO, ON EVERY VERB.** It used to be a gust on a
  break and silence on an open, so an opened chest that paid nothing was
  indistinguishable from a press the server dropped — and those are opposite
  feelings. `onCrateBreak` now plays `empty` and puffs on both, which closes
  the interaction: I opened this, it worked, there was nothing inside.
- `dispose()` releases every timer, listener, observer and rAF handle created in
  this folder.
- **Sound is driven from two places and the split is deliberate.** EVENTS (a
  shot, a hit, an object, a pickup) are played by the handler that already knows
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
- **SHIFT IS PREDICTED LIKE MOVEMENT IS, because it IS movement.** The key
  rides the packet as `sprint` and means "I want to run", nothing more:
  `simulation.isRunning` / `stepStamina` are line-for-line mirrors of
  `server/app/simulation.py`, so the bar drains on the frame the key goes down
  and lands on the server's number a round trip later. `reconcile` snaps `st` /
  `wind` off the tick row before it replays the pending inputs — breath is
  authoritative exactly like position, and the replay is only correct because
  the step is a pure function of (running, moving). Two masks, both in
  `liveInput` for the reason written there: a cutscene and a POUR both puppet
  the body server-side, so the key is dropped there rather than predicted
  against a run that never happened. While `locked` there is no prediction at
  all, so the snapshot path snaps the breath with the position.
- **The run bar is drawn twice, it is YELLOW in both places, and it is the
  LESSER bar in both.** Over the body it is the second row of ONE plate
  (`render/layers/entities.ts` `drawHealthBar`): same backdrop as the health
  bar, a pixel of it as the separator, inset a pixel each side. The plate is
  anchored by its bottom edge and a player's is always two rows tall, full or
  not — geometry that tracked the number would jog the health bar up and down
  the head on every sprint, which is what makes a world-space meter read as
  pasted on rather than worn. Enemies have no second row at all. In the corner
  it sits directly under HP in `Vitals`. Neither one ramps with its own number:
  green-to-red is a wound reading, and breath is not a wound. `winded` is a
  STATE rather than a low number, so it drains the colour and says so in a
  word.
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
  `Game.locked` is departing OR arriving — interact, loot, objects, the rift
  prompt and prediction all key off that, not off `departing` alone.
- Entering a zone is announced ONCE, through `hud-store.arrival`, keyed by the
  zone key; `introducing` says whether the hold is still running. INTRO_TIME,
  `CARD_MS` in `hud/ZoneTitle` and the `zone-*` keyframes are one timeline. The
  card must clear BEFORE the hold ends, or the HUD rises under the title.
  Forest names the night over the march (`introducing` is false; `cinematic`
  covers the letterbox).

- **A POUR IS TWO CLOCKS AND THE SPLIT IS DELIBERATE.** The server owns the
  BEAT — one integer on the player row (`pour`: walk / lift / dump / stow) plus
  one `pours` event per item — because it owns when the pocket actually empties.
  This side owns the POSE: `Game.pourPose` eases the backpack between worn and
  held-out-upside-down on the render clock, and `pad-cargo.ts` flies each item
  from the bag's mouth onto the deck and leaves it there. Nothing here may
  decide that an item left the bag; nothing on the wire may decide where the
  pack is on this frame.
  The local body is the only one that needs help: it faces the MOUSE, so
  `Game.pourAim` turns it at the awake pad for the length of the ceremony, and
  the walk up to the mark is server-driven so `moving` has to be forced — there
  is no predicted velocity to read it off. Piles are keyed by pad id and pad ids
  repeat across nights: `clearPadCargo()` on every `welcome`, or tonight's haul
  stacks on top of last night's.

## Work Guidance

- New per-frame state stays here or in `render/`; it must not reach React.
- New HUD data means a field on the `hud-store` snapshot, published at 5 Hz —
  not a subscription from a component to the game. Camp ready uses `ready` and
  `prompt`; a nearby drop uses `lootPrompt`; the pocket uses `inventory`;
  the walk-out and the forest emerge use `cinematic`; an object in reach uses
  `cratePrompt`, which carries the object's own VERB as a string rather than a
  flag — a barrel says destruir, a chest abrir, a car boot vasculhar, and the
  wording is authored server-side beside the drop table; a pad uses `riftPrompt`
  (`open` / `busy` / `feed` / `over` / `close`); a shop table in reach uses
  `buyPrompt` and the party's purse uses `balance`; the
  extraction exit arrow uses `exitGuide`. Run
  objectives use `quests` — announced at top-centre,
  then flown into the card under the minimap the way a collect flies into
  the bag. Completed rows rise and leave; the HUD dismisses them after
  that beat.
  A world `Tooltip` also needs an `anchor` id written in `syncTooltipAnchors`
  each frame — show/hide is the store, the pixels are the camera. E is
  interact: collect on a drop, use an object, open or feed a rift, buy off a
  shop table, ready at the fire. The server validates range.
  TAB toggles `inventory.open` locally and is patched immediately so the
  drawer does not wait for the 5 Hz tick. A collect fly is
  `loot-flies` + `inventory-anchors`, not a React render: hold over the
  head, open the bag, then travel into the slot. Travel waits until
  `slot-N` has a live anchor (drawer open, cell on screen) and aims
  through `warpHudPoint` so the sprite lands on the glass-warped cell.
  The pocket snapshot carries `gold` — the GROUP's metal — as the sum of catalog values in
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
