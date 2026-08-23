"""Authoritative tuning constants.

These values are shipped to the client inside the `welcome` message so that
client-side prediction runs the exact same numbers as the server simulation.
Never hardcode a gameplay constant on the client: read it from the welcome
payload instead.

==========================================================================
SCALE
==========================================================================
`TILE_SIZE` is THE scale of the game. Every size, speed and distance below is
authored in TILES and multiplied by it, so changing this one number rescales
the whole game consistently — art, collision, movement speed, weapon range.

    TILE_SIZE = 16   ->  sprite 16x16, box 9.6x7.2, speed 70 px/s, range 128
    TILE_SIZE = 32   ->  sprite 32x32, box 19.2x14.4, speed 141 px/s, range 256

Canonical shape:
    tile           1   x 1     tiles   (16 x 16 px)
    sprite frame   1   x 1     tiles   (16 x 16 px)
    collision box  0.6 x 0.45  tiles   (9.6 x 7.2 px, feet footprint)
    hit capsule    r 0.3, full sprite height (stadium from feet to head)

Taller characters (bosses, zombie variants) only need SPRITE_TILES_H raised
for that entity's asset — the renderer anchors any frame height by its bottom
edge, and the hit capsule grows with sprite height, so nothing else changes.

Movement is continuous, not tile-by-tile: position is a float in world pixels
and the grid is only used for collision and (later) pathfinding. That is
cheaper than it sounds — a move costs a handful of float ops plus an overlap
test against at most 4 tiles, so a tick is O(entities), never O(map).

The collision box is deliberately much smaller than the sprite. A full 1-tile
box cannot fit through a 1-tile gap, and a character whose feet collide on its
own shoulders feels awful. Position = CENTRE of the collision box; the sprite
is drawn with its bottom edge at `y + PLAYER_HALF_HEIGHT`.
"""

import math

# --- scale ------------------------------------------------------------------
TILE_SIZE = 16

# --- simulation -------------------------------------------------------------
TICK_RATE = 30
DT = 1.0 / TICK_RATE

# How many queued inputs a single player may consume in one server tick.
# 1 is the normal case; a small burst allowance absorbs network jitter without
# letting a client trivially speed-hack by flooding input packets.
MAX_INPUTS_PER_TICK = 2
MAX_INPUT_QUEUE = 10

# --- player (authored in tiles) ---------------------------------------------
SPRITE_TILES_W = 1.0
SPRITE_TILES_H = 1.0
PLAYER_BOX_TILES_W = 0.6
PLAYER_BOX_TILES_H = 0.45
# Capsule radius ≈ collision half-width; vertical span = full sprite.
PLAYER_HIT_TILES_R = 0.3
MOVE_TILES_PER_SEC = 4.4

SPRITE_WIDTH = round(TILE_SIZE * SPRITE_TILES_W)        # 16
SPRITE_HEIGHT = round(TILE_SIZE * SPRITE_TILES_H)       # 16
PLAYER_HALF_WIDTH = TILE_SIZE * PLAYER_BOX_TILES_W / 2  # 4.8
PLAYER_HALF_HEIGHT = TILE_SIZE * PLAYER_BOX_TILES_H / 2 # 3.6
PLAYER_HIT_RADIUS = TILE_SIZE * PLAYER_HIT_TILES_R      # 4.8
MOVE_SPEED = TILE_SIZE * MOVE_TILES_PER_SEC             # 70.4 px/s

MAX_HP = 100
RESPAWN_DELAY = 2.0          # seconds

# --- running (authored as multipliers and points per second) ----------------
# SHIFT IS A DECISION, NOT A SECOND WALK SPEED. Sprinting is how a party
# crosses ground it has already read — the walk back to a console, the last
# stretch to the exit while the pack is coming — and stamina is what stops it
# being the only speed anybody ever uses. The whole system is four numbers:
#
#   * the run is worth taking (SPRINT_SPEED), and it is bounded well under a
#     zombie's charge, so it outruns a shamble and never outruns a hunt;
#   * it costs more than standing still pays back, so a night cannot be
#     sprinted end to end;
#   * catching your breath is FASTER STANDING STILL than walking, which is the
#     one place the bar asks the player to stop and look at the dark;
#   * spending it to zero locks the key until a THIRD of the bar is back
#     (`STAMINA_RECOVER`). Without that lockout an empty bar stutters between
#     one frame of run and one frame of walk for as long as SHIFT is held.
#
# It multiplies the walk, so a skill's speed bonus and the carry penalty both
# still apply underneath — a body hauling a full bag runs at a full bag's pace.
SPRINT_SPEED = 1.55
STAMINA_MAX = 100.0
STAMINA_DRAIN = 26.0         # points/s while actually running
STAMINA_REGEN_WALK = 12.0    # points/s while still on your feet and moving
STAMINA_REGEN_REST = 24.0    # points/s standing still
STAMINA_RECOVER = 0.33       # fraction back before SHIFT answers again

# --- spawning (authored in tiles) -------------------------------------------
# After the camp walk-out the party emerges from a VOID corridor on a random
# map edge, then that path seals. Respawn (and a late join) uses a ring around
# that mouth so a death does not throw someone into the middle of the woods.
SPAWN_RING_TILES = 2.5
SPAWN_SEPARATION_TILES = 1.2

SPAWN_RING = TILE_SIZE * SPAWN_RING_TILES
SPAWN_SEPARATION = TILE_SIZE * SPAWN_SEPARATION_TILES

# --- the camp (authored in tiles) -------------------------------------------
# The clearing the party gathers in. It is ONE place shown twice: the lobby
# draws it while people trickle in, and `preparation` is the same map, walkable,
# once the host starts. Every number below is therefore read by both — the seat
# a player was standing on at the campfire is the tile they wake up on.
# Sized so the WIDE shot never frames the edge of the world. The lobby holds the
# camp at `ARENA_ZOOM - 1` (see client/src/render/framing.ts), which on a very
# wide monitor is a lot of forest — the map has to be bigger than that view or
# the camera clamps and the treeline stops looking like it goes on.
CAMP_WIDTH_TILES = 76
CAMP_HEIGHT_TILES = 48
# Open ground around the fire before the treeline starts.
CAMP_CLEARING_TILES = 8.2
# The hearth: the fire plus the ring of players around it. Nothing grows here —
# the map generator refuses trees and rocks, and the client refuses grass and
# ferns on the same ellipse. A bush in front of a seated player hides the
# character the roster is pointing at.
CAMP_HEARTH_TILES = 5.6
# The seat ring. Elliptical: a circle reads as a flat disc from this angle, and
# it is squashed by exactly the ratio the clearing and the decoration mask use.
CAMP_RING_TILES_X = 3.5
CAMP_RING_TILES_Y = 2.0
# How far the bonfire throws light, in tiles. In the camp this is the ONLY light
# — lanterns are off (see zones.py), so this number decides whether the party
# can see each other.
CAMPFIRE_LIGHT_TILES = 10.0

CAMP_RING_X = TILE_SIZE * CAMP_RING_TILES_X
CAMP_RING_Y = TILE_SIZE * CAMP_RING_TILES_Y

# The camp exit: a winding VOID path through the trees on the RIGHT of the
# clearing. This is the typical half-width at the mouth, not a stamped
# rectangle — `camp._carve_exit` wanders, narrows, and frays around it.
# Wide enough for two staggered files, narrow enough to read as a gap in
# the woods. The mouth sits in the treeline, where the party can walk up
# to it and bounce. Forest floor under extreme shadow, not a missing texture.
CAMP_EXIT_HALF_TILES = 2
# How close to the fire (in tiles, from the flame's base to the player's feet)
# you must stand to ready up. Matches the hearth so anyone in the seat ring
# can press E, and nobody out in the scrub can.
CAMP_READY_RANGE_TILES = CAMP_HEARTH_TILES
# Walk-out: a touch slower than a run, so the files read as a departure
# rather than as a race to the trees.
MARCH_TILES_PER_SEC = 3.6
MARCH_SPEED = TILE_SIZE * MARCH_TILES_PER_SEC

# Forest entrance: the camp's black corridor, continued. A winding VOID path
# through a random edge, deep enough to read as the same walk, then a mouth
# clearing the party is marched onto before the woods swallow the way back.
ENTRANCE_DEPTH_TILES = 12
ENTRANCE_MOUTH_TILES = 4.6
# THE EXIT IS SHALLOW, AND THE ARRIVAL IS DEEP, AND THEY ARE READ FROM
# OPPOSITE ENDS — the same asymmetry `entrance.EDGE_PINCH` / `EDGE_FLARE`
# already encodes for how the border ranks are cut.
#
# An arrival corridor is walked from the world's edge INWARD: its depth is the
# length of the dark walk out of it, and twelve tiles of that is the point.
# An exit is walked toward the edge, and what the party sees "appear" is not
# its far end — that end is off in the dark — but its MOUTH: the floor
# threshold with the torches and the paving. At the arrival's depth that
# threshold lands twelve tiles inland, which on a 64-tall map reads as the way
# out having opened in the middle of the woods rather than at the border.
# Short, so the mouth is right against the treeline and the hole in it is the
# thing you walk to.
EXIT_DEPTH_TILES = 5

# --- the store (authored in tiles) ------------------------------------------
# The night's takings, spent. The zone is ONE WALK, SOUTH TO NORTH: the party
# arrives through a corridor at the bottom of the map, the corridor opens into
# a round CLEARING with everything worth stopping for around its rim, and a
# second corridor leaves from the top. Come in, go round, go on.
#
# WHY A CIRCLE AND NOT A LANE. It was a long east-west glade first, with the
# tables strung along it, and the shape was doing exactly one thing: making
# sure nobody could walk past the stock. That is a corridor's whole argument,
# and it is a weak one, because the party has to walk the same straight line
# every night whether or not they have anything to spend. A ROOM is different:
# it is somewhere you STAND. The two corridors on the ends keep the entrance
# and the exit as separate events, which is the part of the lane that was
# worth keeping.
#
# AND IT IS A SMALL ROOM. The first circle was sixteen tiles of radius on a
# 52x62 map, on the argument that the wagon, the stalls and the apron should
# read as three separate places. What that actually bought was a field: the
# stock was a long walk from the trader, the cabinet was across a clearing
# from both, and the party spent the whole visit crossing ground rather than
# looking at prices. A SHOP IS A COUNTER YOU STAND AT. Everything in it now
# fits in one screen from the door — the trader in the middle, his stock in
# front of him, the machine on the west arc — and the map is only as big as it
# has to be for the treeline to have depth and the two necks to have somewhere
# to run.
#
# IT IS TALLER AGAIN, AND THE EXTRA ROWS ARE THE APRON. The zone is two places
# now, read south to north: an outdoor APRON where the night's platforms come
# down, and the SHOP itself — a brick building standing at the north end of it,
# the first and only structure in the game. Making them one room was the older
# mistake in the other direction: a party walked into a clearing and got paid,
# priced and levelled in the same twenty tiles, and every beat landed on top of
# the last one. Two places, one walk.
STORE_WIDTH_TILES = 38
#: SHORTER, AND THE ROWS THAT WENT WERE WALKING. The zone reads as four beats
#: south to north — the throat in, the apron the platforms come down on, the
#: shop, the way out — and the first and last of those are THRESHOLDS, not
#: journeys. At fifty-four rows the party crossed nine tiles of empty yard
#: before the first skid and five more of corridor before that, which is time
#: spent walking through a place that has already said what it is.
STORE_HEIGHT_TILES = 48
#: Radius of the APRON, in tiles. `store._circle_half` breathes around it so
#: the rim reads as woods rather than as a stamped disc. It is the outdoor half
#: of the zone and nothing is sold in it.
STORE_CIRCLE_TILES = 10.0
#: Typical width of the two NECKS — the walkable throat between a corridor
#: mouth and the apron. Narrow, so arriving and leaving are both a squeeze
#: that opens out; the apron does the breathing. At eight it was not a squeeze:
#: eight tiles is most of the apron's own diameter, so the throat and the yard
#: read as one tapering space and the arrival had no threshold in it. The
#: corridor's own VOID is derived off this (`store._carve_ends`), so narrowing
#: the neck narrows the way in with it — four tiles, which is two files of
#: players with a shoulder either side and nothing to spare.
STORE_LANE_TILES = 5.5
#: VOID at each end: the way in at the bottom (which seals) and the way out at
#: the top (which does not). The NORTH one is inside the building — see
#: `store.SHOP_ROWS`.
STORE_CORRIDOR_TILES = 4
STORE_BUY_TILES = 1.9
STORE_BUY_DIST = TILE_SIZE * STORE_BUY_TILES
#: How far the goods FLOAT off a table when somebody is in range, in tiles.
#: The client bobs them through this rather than parking them at it — a lift
#: that stopped would be a levitating sprite, and a lift that breathes is the
#: table saying it is offering something. Authored here so the bob and the
#: reach cannot drift.
STORE_LIFT_TILES = 0.4
#: How close the feet have to be for E to pull the machine's lever, in tiles.
#: Wider than a table, narrower than a rift console: the cabinet is a big
#: object and standing at it should be unambiguous, but the nearest stall must
#: never be offering itself at the same time as the lever.
STORE_SPIN_TILES = 2.2
STORE_SPIN_DIST = TILE_SIZE * STORE_SPIN_TILES
#: What the FIRST bought pull costs once nobody has a level left to spend, in
#: party gold. The ladder doubles from here with every pull the party buys and
#: it resets when they walk into the next night's shop — see `Room.spin_price`.
#:
#: A LEVEL IS STILL THE CURRENCY; THIS IS THE OVERDRAFT. The number is a little
#: under the cheapest gun on a table on purpose: the first extra pull is an
#: easy yes, the second is a real trade against a weapon, and the fourth is
#: never worth it. That curve is the whole point — the machine keeps saying yes
#: and the party is the one who has to stop.
STORE_SPIN_PRICE = 50
#: How far the machine's own marquee throws, in tiles. It is a LIT OBJECT — the
#: only electrical thing in the game — and it stands alone on the west arc of
#: the clearing, so its pool is what pulls a party across to it. Kept SHORT: it
#: is a marquee on a small cabinet in a small room, and every one of these
#: pools is drawn additively on top of the zone's ambient floor — see
#: `zones.STORE_AMBIENT` and `store.TORCH_LIGHT_TILES` for what happens when
#: they are allowed to pile up.
STORE_MACHINE_LIGHT_TILES = 4.5

#: What the merchant charges, as a multiple of the item's catalog value. He is
#: the only place to buy a gun and he knows it.
#:
#: KEPT LOW ON PURPOSE, and the number is pinned to the first night rather than
#: to a feeling about margins. Day one has a single pad, a single pad is always
#: the LAST pad, and the last pad never offers to keep loading — so a first
#: night banks its quota (`rift.night_need`, 40) plus whatever the final item
#: overshot by, and nothing else. At this markup the cheapest gun on the
#: cheapest table is 46, which the first night clears. Push the markup up and
#: that shop becomes a room of things nobody can buy, which is the worst
#: possible first impression for a zone whose whole job is to make the night's
#: take feel like it bought something — and, now that guns are ONLY sold here
#: and never found, a first shop nobody can buy from is a second night with a
#: knife.
STORE_MARKUP = 1.15
#: How far one stall's price may wander off that markup, either way.
#:
#: THIS IS WHAT MAKES SIX STALLS SIX DECISIONS. The stock is rolled WITH
#: REPLACEMENT — he can be holding three Glocks — and six tables carrying the
#: same number is a shelf, not a shop. A spread turns a duplicate into the one
#: question a trader's stall is actually about: this one or the cheaper one
#: over there. It is small enough that it never reorders the catalog (a
#: haggled AK never undercuts a full-price FAMAS), because the price ladder is
#: teaching the value of the guns and a spread that shuffled it would be
#: teaching noise.
STORE_PRICE_SPREAD = 0.16

# --- vision (authored in tiles) ---------------------------------------------
# The client draws the darkness; these numbers decide its shape. They live here
# for the same reason every other constant does — one source of truth — and are
# shipped in `welcome.config` so the client never invents its own.
#
# Sight is blocked by solid tiles, so a thicket casts a real shadow. Two lights
# stack: a small glow you always carry, and a directional lantern along your aim.
# Vision is SHARED: the team sees the union of what its members see.
VISION_AMBIENT_TILES = 3.5   # omnidirectional glow around a player
VISION_LANTERN_TILES = 11.0  # how far the lantern cone reaches
VISION_CONE_DEGREES = 75.0   # full width of the cone

VISION_AMBIENT_DIST = TILE_SIZE * VISION_AMBIENT_TILES
VISION_LANTERN_DIST = TILE_SIZE * VISION_LANTERN_TILES

# --- enemies -----------------------------------------------------------------
# Per-creature stat blocks (health, damage, xp, gold, speed…) are NOT here:
# they are `EnemyType` entries in enemies.py, authored in the same tiles/seconds
# units and shipped to the client in `welcome.config.enemyTypes`. Only the rules
# that apply to *every* enemy live below.

# THE I-FRAME IS A FLOOR, NOT A SHIELD, and that is the whole difference
# between a horde and a crowd.
#
# It used to be 0.6s, which was sized to make a pack survivable: one hit opened
# a window every other zombie whiffed into, so the ceiling was
# `max(enemy damage) / MELEE_IMMUNITY` dps REGARDLESS OF HOW MANY WERE ON YOU.
# Thirty-two zombies did exactly as much damage as one. That number is the
# reason the game had no horror in it — the crowd on screen was decoration,
# because arithmetically it was a single body wearing thirty-two sprites, and
# no amount of spawning, lighting or sound design can make a threat out of
# something that cannot hurt you faster than its smallest unit.
#
# A pack is now rate-limited PER ATTACKER, and it always was: every creature
# carries its own `EnemyType.attack_cooldown` (1.1s on a zombie), so a body
# already swings at its own cadence and the shared window was a SECOND limiter
# stacked on top of the real one. What is left here is only the floor that
# stops two of them landing on the same tick — enough that the hurt flash, the
# shove and the sound each get a frame to read, and nothing more. Damage now
# scales with how many things are actually touching you, which is what makes
# being surrounded a thing that happens to you rather than a picture of one.
#
#     1 zombie      8 dps   ~12s     a chore, exactly as before
#     3 zombies    25 dps    ~4s     a fight you are losing
#     5 zombies    41 dps    ~2.4s   the moment you have to leave
#     8           65 dps    ~1.5s    surrounded is fatal
#
# AND SHRINKING IT WAS NOT ENOUGH — IT HAD TO STOP GATING MELEE ALTOGETHER.
# A blocked swing still spends the swinger's cooldown, so ANY shared window
# makes a pack that swings together pay for one hit between them. A pack that
# walked to you together is synchronised by construction, so the window was
# still collapsing the exact case it existed for, at any size. `resolve_attack`
# no longer sets it; `Room.spawn_enemy` scatters each body's attack phase so
# the pack's damage arrives as a stream rather than a volley.
#
# WHAT STILL USES IT are the two things a shared window was always right for,
# and neither is a rate limit: the boss's chop (something enormous just hit
# you — the small things do not get to pile onto that frame) and the grace
# below. Both SET it; regular melee only reads it.
MELEE_IMMUNITY = 0.14        # the boss's suppression window, not a melee gate
RESPAWN_IMMUNITY = 1.5       # longer window on respawn, so you can walk away

# BEING HIT COSTS YOU THE ONE THING THAT ALWAYS WORKED: LEAVING.
#
# A player walks at 4.4 tiles/s and sprints at 6.8 against a zombie's 2.6, so
# disengaging was free, instant and always correct — every situation in the
# game had the same answer and it was "walk away". Horror needs the exit to
# close sometimes, and this is the cheapest honest way to close it: a blow that
# lands puts a brief drag on the body, and the drag REFRESHES, so a crowd that
# is landing hits keeps you at walking pace inside it.
#
# THE NUMBER IS PICKED AGAINST THE ZOMBIE'S OWN SPEED, not by feel. Staggered
# walking is 4.4 * 0.62 = 2.7 tiles/s — a hair over their 2.6, so walking out of
# a pack that is connecting is *technically* possible and practically hopeless.
# Staggered sprinting is 4.2, which still outruns them: the escape is real, it
# just costs the bar. That is the trade the whole system now turns on — you get
# out on stamina, and stamina is the resource you spent getting into it.
HIT_STAGGER_TIME = 0.5       # seconds of drag one connecting blow leaves
HIT_STAGGER_SCALE = 0.62     # what the walk is multiplied by while it lasts

# Gun hits slow then pin. Damage adds to a 0..1 meter; at STOP they plant.
# A Glock (~7) is a hitch; a burst stacks into a stop. A Deagle (~24) almost
# pins in one; an AWP (~55) plants on the first round. The hold is how long
# the meter stays before it decays — a pause in fire lets them walk again.
# Never on the wire: the snapshot already carries the slowed vx/vy.
ENEMY_STAGGER_PER_DAMAGE = 1 / 32
ENEMY_STAGGER_MIN = 0.16
ENEMY_STAGGER_MAX_ADD = 0.92
ENEMY_STAGGER_STOP = 0.82
ENEMY_STAGGER_HOLD = 0.22
ENEMY_STAGGER_HOLD_SCALE = 0.35
ENEMY_STAGGER_HOLD_MAX = 1.05
ENEMY_STAGGER_DECAY = 1.6

# Population. The cap scales with the number of living players so a solo run is
# not a swarm and a full room is not empty — and WITH THE DAY, which it did not
# used to, and which was the second reason the game got easier as it went on.
#
# The forest triples between night one and night five (4 028 tiles -> 12 144,
# see `mapgen.size_for_pads`) and the night's quota sextuples, but nothing in
# `ai.py` or `enemies.py` had ever heard of the day. So the density fell off a
# cliff exactly as the party was asked to spend longer out there:
#
#     night 1   76x53    6 enemies per player   1.49 per 1000 tiles
#     night 3  108x75    6                      0.74
#     night 5+ 132x92    6                      0.49
#
# Night five was three times EMPTIER than night one. The walk got longer, the
# quota got bigger, and the forest got quieter — which reads to a player as
# padding, because that is what it is.
ENEMY_MAX_PER_PLAYER = 6
ENEMY_MAX_TOTAL = 32
ENEMY_SPAWN_INTERVAL = 2.5   # seconds between spawn attempts
ENEMY_FIRST_SPAWN_DELAY = 4.0

#: What each night adds to the population ceiling, as a fraction of the first
#: night's. Linear rather than exponential: this multiplies a cap that already
#: multiplies by the party, and two compounding curves is how a day-nine forest
#: becomes a slideshow.
#:
#: A THIRD A NIGHT IS WHAT HOLDS DENSITY ROUGHLY FLAT ACROSS THE MAP GROWTH,
#: and holding it flat is the FLOOR of this fix, not the goal. The map triples
#: by night five, so +33%/night lands night five at 2.3x the bodies on 3x the
#: ground — still slightly thinner per tile, but the party is stronger by then
#: and a crowd is now genuinely dangerous (see `MELEE_IMMUNITY`), so the same
#: number of zombies is a harder night than it was.
ENEMY_DAY_POPULATION = 0.33
#: And they arrive FASTER. The cap says how many the forest holds; this says
#: how quickly it refills after a fight, which is what decides whether a party
#: can clear a pocket and then work in peace. By night five a wave lands every
#: 1.5s rather than every 2.5, so standing and fighting stops being a way to
#: make the map safe and becomes a way to be surrounded.
ENEMY_DAY_RATE = 0.11
#: The floor under the interval however long a run goes. Below this the
#: director is spawning faster than a group can walk out of its landing spot,
#: which stacks bodies on the anchor tile instead of making a wave.
ENEMY_SPAWN_INTERVAL_MIN = 1.1

# Spawns land in a ring around a random living player: far enough not to appear
# in your face, close enough that they actually reach you.
ENEMY_SPAWN_MIN_TILES = 7.0
ENEMY_SPAWN_MAX_TILES = 15.0
# How hard packed enemies push each other apart (see ai.separation).
ENEMY_SEPARATION_TILES = 0.75

# Enemies arrive as a GROUP, not one at a time. A lone shambler is a chore; two
# to four sharing a patch of forest is an encounter you have to decide about
# before it decides about you. Weights are relative, matched index for index.
ENEMY_GROUP_SIZES = (1, 2, 3, 4)
ENEMY_GROUP_WEIGHTS = (4.0, 3.0, 2.0, 1.5)
#: How much the day tilts those weights toward the BIG end. The size of the
#: group you meet is the difference between an obstacle and an encounter now
#: that a crowd can kill — one shambler is a chore at any point in a run, and
#: four arriving together on night eight is the game asking a question. Applied
#: as a multiplier on each weight raised to its own index, so night one is
#: untouched and later nights bend the same curve rather than switching to a
#: different table.
ENEMY_DAY_GROUP_TILT = 0.16
# How far apart a group's members land, in tiles. They wander around their OWN
# landing spot afterwards, so this is also roughly how loose the pack stays.
ENEMY_GROUP_SPREAD_TILES = 2.5

# --- enemy senses (authored in tiles/seconds) --------------------------------
# An enemy that has not noticed anybody does not chase: it patrols the ground it
# spawned on. Being seen is a real event with a real cost, which is what makes
# the lantern a decision instead of a light switch.
#
# The cone itself is per-creature (`EnemyType.view_tiles` / `view_degrees`), for
# the same reason speed and damage are. Everything below applies to all of them.

# SIGHT IS SYMMETRIC. It is one dark forest and everybody is standing in it: if
# you can make a shape out at that distance, it can make you out at the same
# distance — provided it happens to be facing you. So an enemy's reach is not a
# number of its own, it is a fraction of the LANTERN's, and it is the SAME
# fraction the client's two sight models use: the naked eye with the lamp off,
# and the full wash the lamp opens up with it on.
# Changing the lantern rescales the danger along with the visibility.
#
# BOTH SCALES SHIP IN `welcome.config` (`enemyViewDarkScale` /
# `enemyViewLitScale`) and `client/src/render/fov.ts` reads them. They used to
# be hand-copied there as `EYE_REACH` / `SIGHT_REACH`, which made the symmetry
# rule a comment two files apart could break silently — a player seeing a
# radius the creatures do not respect is invisible to every test we have.
#
# Which of the two applies is decided PER TARGET, by that player's own switch.
# Switching on does not merely let you see further — it lets you BE seen
# further, by everything already looking your way.
ENEMY_VIEW_DARK_SCALE = 0.62
ENEMY_VIEW_LIT_SCALE = 1.0
ENEMY_VIEW_DARK_TILES = VISION_LANTERN_TILES * ENEMY_VIEW_DARK_SCALE
ENEMY_VIEW_LIT_TILES = VISION_LANTERN_TILES * ENEMY_VIEW_LIT_SCALE

# UNDERGROWTH IS COVER, and until now it was scenery pretending to be. The
# client has always drawn bushes over the top of a body — you stand in a
# thicket and the picture says you are hidden — while `look` tested a clean
# ray at full reach and every creature on the map saw straight through the
# thing that was covering you. A picture that lies about the rules is worse
# than no picture: the player takes cover, is seen anyway, and concludes the
# senses are broken.
#
# There is no bush TILE. Undergrowth is placed by hashing the tile coordinate
# against the map seed, which is why the map payload is a seed and not a
# decoration layer, so the server re-derives the same bushes the client draws
# (`world.bush_at`) instead of anybody shipping a mask.
#
# WHY A REACH SCALE AND NOT AN OCCLUDER. Making a bush block the sight ray
# would be the stronger rule and the wrong one: a ray is all-or-nothing, so a
# single bush anywhere on the line would hide a player standing in the open
# ten tiles past it, and a thicket would become a wall creatures cannot see
# over from any range. Concealment belongs to the tile the target is STANDING
# in — crouch in the bush and things have to come close, break the line and
# they see you as before.
#
# Tuned against the notice cone, not against a number: at this scale a dark
# player in undergrowth is invisible past ~4 tiles, which is inside the reach
# a shambler closes in a second. Cover buys a beat, never safety.
BUSH_CONCEAL_SCALE = 0.55
#: Share of floor tiles carrying a bush. Was a client-side constant in
#: `layers/terrain.ts`; it decides how much cover a forest has, so it is a
#: gameplay number and lives here. The client reads it off `welcome.config`.
BUSH_CHANCE = 0.055

# GLARE: the beam falling on something that is not looking at you.
#
# A lantern pointed at a thing is a thing that can notice the lantern, whichever
# way its head happens to be turned. Being in the beam does NOT spot the player
# — it makes the enemy turn around, and the turn is what puts the player inside
# its own cone. That indirection is the whole mechanic: the lamp is not what
# gets you seen, it is what gets you looked at.
ENEMY_GLARE_RATE = 0.55       # awareness per second in the brightest part
# Fraction of the beam's reach that is bright enough to be noticed. Past this
# the light is a wash on the trees and nothing turns around for it.
ENEMY_GLARE_REACH = 0.7
# Ceiling the glare alone may reach. It can make something look; it can never
# make it commit — committing is the sight cone's job, and an enemy that
# charged a light it had not identified would make the lamp unusable rather
# than expensive.
ENEMY_GLARE_CAP = 0.75
# How fast a glared enemy swings round, in degrees per second. Slow enough to
# watch the head come about, fast enough that it is coming about.
ENEMY_TURN_DEGREES = 200.0
# How fast a creature turns while it is only patrolling. Nothing in this game
# ever snaps its head: a body that changes facing between two frames reads as a
# turret, and half of what makes a shambling thing unsettling is that it takes
# its time. Every facing change goes through `ai.turn_towards` at one of these
# two rates — never by assignment.
ENEMY_IDLE_TURN_DEGREES = 70.0

# How long a player has to stand in the cone before the enemy commits. Scales
# with distance: right in its face is nearly instant, the far edge of the cone
# takes its time. Both are short enough that walking through a cone is a
# mistake, long enough that clipping the edge is survivable.
ENEMY_NOTICE_NEAR = 0.45     # seconds to be spotted at touching distance
ENEMY_NOTICE_FAR = 2.0       # seconds to be spotted at the edge of the cone
# How fast suspicion drains once nobody is in the cone any more.
ENEMY_FORGET_RATE = 0.5      # awareness per second
# Above this, an enemy with nothing in its cone stops patrolling and just
# LOOKS. It is what makes a glare or a distant shot visible from across the
# clearing — the pack stops shambling and holds still, facing you — and it is
# also what keeps a turn from being undone by the next leg of its rounds.
ENEMY_SUSPICIOUS = 0.12

# A hunter that has not had eyes on its target for this long goes home. It keeps
# walking to where it last saw them for the whole window, which is what stops a
# corner from being a hard off-switch.
ENEMY_LOSE_DELAY = 4.0
# How far from HOME an enemy will chase before it turns around. Past this it
# stops being a patrol that got interrupted and starts being a conga line.
ENEMY_LEASH_TILES = 22.0
# The patrol: how far from its spawn point an idle enemy will drift, and how
# long it stands still between legs.
ENEMY_HOME_TILES = 3.5
ENEMY_WANDER_PAUSE_MIN = 1.0
ENEMY_WANDER_PAUSE_MAX = 3.5
# Patrol pace, as a fraction of the creature's own speed. A shamble, not a jog —
# the difference between a wandering enemy and a hunting one has to be legible
# from across the clearing.
ENEMY_WANDER_SPEED_SCALE = 0.42
# Close enough to a patrol waypoint (or to home) to call it arrived. It has to
# comfortably exceed the creature's TURN RADIUS (patrol speed over
# ENEMY_IDLE_TURN_DEGREES, about 0.9 tiles for a zombie) — a body that turns in
# a wider circle than its own arrival radius orbits a waypoint it can never
# reach, and the patrol becomes a carousel.
ENEMY_ARRIVE_TILES = 1.3

# One enemy spotting you is every enemy near it spotting you. The shout is a
# single hop on purpose: a chain would walk across the whole map from one
# careless step, and a fight you cannot disengage from is not a fight.
ENEMY_ALERT_SHARE_TILES = 8.0

# --- noise (authored in tiles) ----------------------------------------------
# Anything the player does that an enemy can HEAR emits one of these. Only the
# gunshot exists so far; footsteps, doors and thrown objects are the same shape
# (`ai.Noise`) with a different radius, which is the whole reason this is a list
# on the room and not a flag on the shot event.
#
# A noise fills awareness by `1 + spare` at its centre and tapers to nothing at
# the rim, so the middle of the blast is an instant hunt and the outer band only
# makes heads turn.
SHOT_NOISE_TILES = 16.0
NOISE_ALERT_GAIN = 1.45

# Navigation. An enemy walks straight at its target while it has a clear
# body-width corridor within this range, and follows the flow field otherwise
# (see pathing.py). The cap bounds how far the clearance rays are traced.
ENEMY_DIRECT_SIGHT_TILES = 12.0
# How long an enemy may make no headway before it stops trusting its eyes and
# commits to the field route. Short enough to be invisible, long enough that
# brushing a wall does not send it onto tile centres.
ENEMY_STUCK_DELAY = 0.25

# An enemy nobody is near stops being content and starts being budget: after
# this long with every living player beyond the distance, it is recycled so the
# director can spawn a fresh one where the fight actually is. Players outrun
# zombies by design, so without this the map slowly fills with statues.
ENEMY_DESPAWN_TILES = 34.0
ENEMY_DESPAWN_DELAY = 8.0    # seconds abandoned before recycling

ENEMY_SPAWN_MIN_DIST = TILE_SIZE * ENEMY_SPAWN_MIN_TILES
ENEMY_SPAWN_MAX_DIST = TILE_SIZE * ENEMY_SPAWN_MAX_TILES
ENEMY_SEPARATION = TILE_SIZE * ENEMY_SEPARATION_TILES
ENEMY_DESPAWN_DIST = TILE_SIZE * ENEMY_DESPAWN_TILES
ENEMY_DIRECT_SIGHT_DIST = TILE_SIZE * ENEMY_DIRECT_SIGHT_TILES
ENEMY_GROUP_SPREAD = TILE_SIZE * ENEMY_GROUP_SPREAD_TILES
ENEMY_LEASH_DIST = TILE_SIZE * ENEMY_LEASH_TILES
ENEMY_HOME_DIST = TILE_SIZE * ENEMY_HOME_TILES
ENEMY_ARRIVE_DIST = TILE_SIZE * ENEMY_ARRIVE_TILES
ENEMY_ALERT_SHARE_DIST = TILE_SIZE * ENEMY_ALERT_SHARE_TILES
ENEMY_GLARE_DIST = VISION_LANTERN_DIST * ENEMY_GLARE_REACH
SHOT_NOISE_DIST = TILE_SIZE * SHOT_NOISE_TILES

# --- progression -------------------------------------------------------------
# Levels are derived from total xp by the server and sent already split into
# (level, xp into level, xp needed) so the client never re-implements the curve.
#
# THE OPENING WAS FREE AND IT PAID FOR THE WRONG THING.
#
# At XP_BASE 40 against a zombie's 12 xp, level 2 cost 3.3 zombies and level 5
# cost 24 of them CUMULATIVELY — one night-one forest, with its 32-body cap and
# its 2.5s respawns, handed out four or five levels before the party had met
# anything. Four spins on night one is the machine's whole ceremony spent on a
# player who has not yet learned what a skill is for.
#
# KILLING IS THE ONLY SOURCE AND THAT IS THE DECISION, not an omission. A pass
# that paid xp per point of loot extracted was tried and taken back out: it made
# the level bar a second quota meter, so the pad was already paying money AND
# progression AND a quest row for the same act, and the number over a body
# stopped being the only reason to fight anything. Fixing the pace belongs in
# the price of a level, which is the line below, and not in a second source.
#
# 110 is a night's work at the opening — roughly nine zombies against the old
# 3.3. The growth is GENTLER than it was (1.4 -> 1.28) because the base carries
# the weight now: 1.4 off a bigger base put level ten out of reach of a
# ten-night run, which is the opposite mistake and just as bad.
XP_BASE = 110                # xp required for level 2
XP_GROWTH = 1.28             # each level costs this much more than the last
MAX_LEVEL = 30

# --- dark gold (authored in tiles) ------------------------------------------
# The purple coin, and the PLAYER's own currency — see `coins.py`. A creature's
# gold is how many coins it CAN drop, not how many it does: each point is
# rolled on its own at COIN_DROP_CHANCE, so a 3-gold zombie pays 0..3. A fixed
# payout makes every corpse the same corpse; a roll makes a good one worth
# noticing.
#
# THIS NUMBER IS THE FAUCET, and it is now set for a RARE DROP rather than a
# quiet one. Dark gold is not the resource a night is scored on — that is group
# gold, and the party earns it by carrying loot to a platform — so a shard off
# every second corpse would make the currency the party is actually playing for
# the quieter of the two.
#
# IT WENT FROM 0.22 TO 0.07 WHEN THE COIN BECAME AN ANOMALY SHARD, and the art
# is the argument. A struck purple coin can fall out of anything; a fragment of
# the thing the whole night is spent feeding cannot fall out of a third of the
# corpses in the forest without becoming litter. At 0.07 a 3-gold zombie pays
# nothing four times in five, one shard most of the rest, and three about twice
# in ten thousand — so finding one is an event, which is what the sprite now
# promises. Move this and `crates.DROP_COIN` together: they are the two taps,
# and turning one alone just changes where the same money comes from.
COIN_DROP_CHANCE = 0.07
COIN_MAGNET_TILES = 2.4
COIN_COLLECT_TILES = 0.4
COIN_BURST_TILES_PER_SEC = 5.5    # pop off the corpse
COIN_REPULSE_TILES_PER_SEC = 3.2  # kick away when magnet starts
COIN_ATTRACT_ACCEL_TILES = 70.0   # px/s² toward the locked player
COIN_ATTRACT_MAX_TILES_PER_SEC = 16.0
COIN_REPULSE_DURATION = 0.1       # seconds of outward kick before attract
COIN_DRAG = 5.5                   # loose / repulse air drag
# How fast attract kills tangential velocity (higher = less orbit).
COIN_ORBIT_DAMP = 18.0

COIN_MAGNET_DIST = TILE_SIZE * COIN_MAGNET_TILES
COIN_COLLECT_DIST = TILE_SIZE * COIN_COLLECT_TILES
COIN_BURST_SPEED = TILE_SIZE * COIN_BURST_TILES_PER_SEC
COIN_REPULSE_SPEED = TILE_SIZE * COIN_REPULSE_TILES_PER_SEC
COIN_ATTRACT_ACCEL = TILE_SIZE * COIN_ATTRACT_ACCEL_TILES
COIN_ATTRACT_MAX_SPEED = TILE_SIZE * COIN_ATTRACT_MAX_TILES_PER_SEC

# --- loot (authored in tiles) -----------------------------------------------
# How close the feet have to be for E to collect. A reach, not a magnet.
LOOT_COLLECT_TILES = 2.25
LOOT_COLLECT_DIST = TILE_SIZE * LOOT_COLLECT_TILES

# How close the feet have to be for E to use an object. Same reach as loot.
# Measured to the nearest point of the FOOTPRINT rather than to the contact
# point (`crates.nearest`), because a bus is four tiles long and a
# centre-to-centre reach would refuse the prompt at exactly the rear doors the
# art is telling you to press.
CRATE_BREAK_TILES = 2.25
CRATE_BREAK_DIST = TILE_SIZE * CRATE_BREAK_TILES

# How close to the extraction console E answers. Wider than a crate: the
# console is the one interactive thing on the map you are meant to be able to
# find while something is chasing you, and a tight radius turns that into
# pixel-hunting at the worst possible moment.
RIFT_ACTIVATE_TILES = 2.75
RIFT_ACTIVATE_DIST = TILE_SIZE * RIFT_ACTIVATE_TILES
# How far into the extraction VOID a living player must walk, past the
# FLOOR mouth toward the map edge, before "Encontre a saída" ticks.
# Standing at the threshold is finding it; crossing the dark is leaving.
EXIT_CROSS_TILES = 1.75
# Quieter than a gunshot — wood giving way, not a muzzle. This is only the
# FALLBACK: how far each object carries is `ObjectType.noise_tiles`, because a
# mailbox and a lorry bonnet are not the same event.
CRATE_NOISE_TILES = 5.5
CRATE_NOISE_DIST = TILE_SIZE * CRATE_NOISE_TILES
# Shot box, for anything that does not name its own. Walking still uses the
# foot tiles; a bullet has to hit the wood you aim at, and the real box comes
# off `ObjectType.hit_w_tiles` / `hit_h_tiles` and rides `welcome.config.objects`
# — a car is four tiles wide and a toolbox is one, and one number for both
# would mean either shooting past the car or shooting the toolbox from the
# next tile over.
CRATE_HIT_W_TILES = 1.0
CRATE_HIT_H_TILES = 2.0
CRATE_HIT_W = TILE_SIZE * CRATE_HIT_W_TILES
CRATE_HIT_H = TILE_SIZE * CRATE_HIT_H_TILES

# --- inventory / carry ------------------------------------------------------
# Starting pocket. A later upgrade grows the slot count; weight is independent
# of that and can go PAST the max — the bag never refuses for being heavy.
#
# FIVE, NOT THREE, AND IT MOVED WITH THE MAP. The forest is twice the size and
# carries about twice the loot, and at three slots a party filled the bag at
# the second scene and spent the rest of the night walking past things. That
# is not scarcity, it is the game refusing its own content. Five is still
# short of a night's find — the bag is meant to be the reason you make two
# trips to a platform — and the WEIGHT bar, not the slot count, is still what
# decides whether the last thing was worth picking up.
INVENTORY_SLOTS = 5
CARRY_MAX_WEIGHT = 14.0
# Fraction of max weight where the walk is still full speed. Past this the
# body starts to feel it; at 1.0 the multiplier is CARRY_SLOW_AT_MAX, and it
# keeps falling if they go over, floored at CARRY_SLOW_FLOOR so they can
# still limp out.
CARRY_SLOW_START = 0.2
CARRY_SLOW_AT_MAX = 0.55
CARRY_SLOW_FLOOR = 0.35

# --- combat (authored in tiles) ---------------------------------------------
SHOT_RANGE_TILES = 8.0
MUZZLE_OFFSET_TILES = 0.25

FIRE_COOLDOWN = 0.5         # seconds between shots (~2 shots/s)
SHOT_RANGE = TILE_SIZE * SHOT_RANGE_TILES       # 128 px @ TILE_SIZE=16
MUZZLE_OFFSET = TILE_SIZE * MUZZLE_OFFSET_TILES # 4 px
SHOT_DAMAGE = 8

# --- the boss (authored in tiles/seconds) ------------------------------------
# THE SAWYER. One night in a run ends in a fight instead of a walk, and which
# night that is lives here — the only knob anybody should need to move it.
#
# EVERY TIMING HE HAS IS SOMEWHERE ELSE ON PURPOSE. His windups, his recoveries
# and the length of his arrival are read out of
# `assets/processed/sawyer/manifest.json` by `boss.py`, because the telegraph a
# player learns the fight from is the animation, and a duration typed here
# would be a second opinion about it. What lives in this file is what the ART
# cannot know: how hard he hits, how far he reaches, how long he waits.

#: The day the arena replaces the walk to the shop. `None` disables the fight
#: entirely; 1 puts it on the very first night, which is the quickest way to
#: test it.
#:
#: It is a DAY NUMBER rather than a flag because the fight is a milestone in a
#: run, and a run's shape is measured in nights. `Room` tests it once, on the
#: crossing, so changing it mid-session takes effect on the next night.
BOSS_DAY: int | None = 2

#: His health, and how much a second, third and fourth gun add. See
#: `boss.hp_for` — the first player is worth more than the rest.
BOSS_HP_BASE = 900
BOSS_HP_PER_EXTRA = 520

#: Slower than a player runs (4.4 t/s), and that is the contract the whole
#: fight rests on: he is always outrunnable, so every hit he lands is a hit
#: somebody chose to stand still for.
BOSS_SPEED_TILES = 2.9
#: Degrees per second he may turn while free. Low enough that circling him
#: WORKS, which is the fight's answer to the chop.
BOSS_TURN_DEGREES = 190.0

#: Seconds between moves, before the roll in `boss._wait` spreads it.
BOSS_ATTACK_COOLDOWN = 1.35

#: Under this fraction of his health he roars and speeds up.
BOSS_ENRAGE_AT = 0.5
#: What the enrage multiplies. Under one for the wait, over one for the walk.
BOSS_ENRAGE_RATE = 0.62
BOSS_ENRAGE_SPEED = 1.18

#: The overhead chop: narrow, long, and the biggest number in the fight.
BOSS_CHOP_DAMAGE = 34
BOSS_CHOP_REACH_TILES = 3.6
#: The spin: everything within reach, for a second and a half.
BOSS_SWEEP_DAMAGE = 26
BOSS_SWEEP_REACH_TILES = 3.4
#: The landing, in the cinematic and on nothing else.
BOSS_STOMP_DAMAGE = 22
BOSS_STOMP_REACH_TILES = 4.0

#: The thrown crescent. Slow enough to walk out of BY DESIGN — it is the
#: answer to standing still at range, so a moving player must never be hit by
#: one they saw leave the bar.
BOSS_CREST_DAMAGE = 22
BOSS_CREST_SPEED_TILES = 7.2
BOSS_CREST_LIFE = 1.9
BOSS_CREST_RADIUS_TILES = 0.85
#: How far out he will still choose to throw one.
BOSS_RIP_RANGE_TILES = 11.0

#: THE FAN — what the throw becomes once he is enraged. THREE crescents on a
#: spread instead of one, and that is the whole variant: same clip, same
#: windup, same tell, a different thing leaving the bar. A single crescent is
#: dodged by taking one step sideways, which is correct while he still has
#: half his health and is exactly why a player who never closes the distance
#: cannot lose the second half of the fight. Three of them make the sidestep a
#: DIRECTION rather than a reflex — you have to go somewhere the fan is not.
BOSS_FAN_CRESCENTS = 3
BOSS_FAN_SPREAD_DEGREES = 25.0

#: THE ROVING SWEEP — the spin, enraged, walks. Rooted, the answer to it is to
#: back off one tile and wait a second and a half; walking, backing off has to
#: be a retreat. It moves at a FRACTION of his walk because a spin that
#: tracked at full speed would be unloseable, and this move is already the one
#: with no blind side.
BOSS_SWEEP_DRIFT = 0.62

#: THE DOUBLE CHOP — enraged, the chop has this chance of coming straight back
#: with no cooldown between them. The chop's recovery is the longest window in
#: the fight and the whole fight is built on it being reliable; taking it away
#: half the time is the variant, because a punish window you have to CHECK is
#: a different window from one you can count on.
BOSS_DOUBLE_CHOP_CHANCE = 0.5

#: THE CHARGE — the answer to a gun, and the one move that is not a swing.
#:
#: Everything else he does is authored around a player who came close: the
#: chop punishes standing in the line, the sweep punishes crowding him, and
#: the crescent punishes standing STILL at range — which a player with a
#: rifle simply does not do. Kiting a body that walks slower than you run has
#: no counter in a move list made entirely of swings, so the counter is a move
#: that closes the distance instead of reaching across it.
#:
#: HE IS STILL FAIR, and the fairness is the same fairness the chop has: he
#: commits. The heading is locked when the roar lands and he cannot steer
#: after it, so the charge is beaten by moving SIDEWAYS — the same lesson the
#: chop teaches, asked at a range where the player thought they were safe.
BOSS_CHARGE_SPEED_TILES = 10.5
#: Seconds of run before he pulls up on his own. Times the speed, this is how
#: far he crosses: a little over the arena's radius, so nowhere in the yard is
#: out of his reach and no single charge crosses the whole of it.
BOSS_CHARGE_TIME = 1.05
BOSS_CHARGE_DAMAGE = 30
#: Half-width of the body that is running, in tiles. Wider than his hit
#: capsule: it is a shoulder, not a blade, and a charge that missed by a pixel
#: would read as a bug rather than as a dodge.
BOSS_CHARGE_WIDTH_TILES = 1.5
#: The band he will pick it from. It starts inside the chop's range because a
#: charge from four tiles is a legitimate surprise, and it reaches most of the
#: yard because that is the distance it exists to punish.
BOSS_CHARGE_MIN_TILES = 4.0
BOSS_CHARGE_MAX_TILES = 16.0
#: Seconds rooted after a clean run. His shortest recovery — he pulled up on
#: his own feet.
BOSS_CHARGE_RECOVER = 0.7
#: …and after he buries the bar in the treeline, which is the biggest free
#: window in the fight and the reward for dodging correctly.
BOSS_SLAM_RECOVER = 1.55

#: HOW MUCH THE PICKER IS ALLOWED TO REPEAT ITSELF.
#:
#: `boss._choose` used to be a hard alternation: never the same move twice
#: running, uniform among whatever else the range allowed. At close quarters
#: that is chop, sweep, chop, sweep forever, and past four tiles the crescent
#: was the ONLY legal move, so the second half of every fight was one attack
#: on a metronome. Both halves read as a script because both halves were one.
#:
#: A repeat is now cheap rather than forbidden, and three in a row is the only
#: thing actually banned — one that never repeats is as legible as one that
#: always does, just in the other direction.
BOSS_REPEAT_PENALTY = 0.34
#: Weight a move keeps at the very edge of its band, as a fraction of the
#: weight it has in the middle. Above zero so the bands genuinely OVERLAP: at
#: four tiles the chop, the throw and the charge are all on the table and
#: which one arrives is not something the player can read off a tape measure.
BOSS_BAND_EDGE = 0.3

#: His own melee i-frames, per victim. Longer than `MELEE_IMMUNITY` because
#: his sweep's hitbox is open for a second and a half and would otherwise bill
#: the same body every tick of it.
BOSS_MELEE_IMMUNITY = 0.85

#: Hit capsule and sprite height, in tiles. He is three and a half tiles tall
#: and his capsule is over two wide — a body this size wants a hitbox that
#: matches what the player can see, or shots that visibly connect will miss.
BOSS_HIT_TILES_R = 1.05
BOSS_SPRITE_TILES_H = 3.44

#: What he is worth. Coins hit the FLOOR like any other kill — after two
#: minutes of dodging a chainsaw, walking round picking up his takings is the
#: exhale the beat wants, and a number that appeared in the bank would have
#: nothing to do with the fight that earned it.
BOSS_COINS = 34
#: xp, and it is paid to EVERYBODY. He is not a kill somebody stole; a party
#: that stood in that ring together levels together.
BOSS_XP = 420

# --- the arena (authored in tiles) -------------------------------------------
#: The ring they fight in, and it is sized against the VIEWPORT rather than
#: against a feeling.
#:
#: The camera sits at `ARENA_ZOOM` = 4, so a 1280x720 canvas shows twenty
#: tiles across and eleven down. A ring wider than that is a ring the player
#: is fighting inside without being able to see — they lose the boss off the
#: edge of the screen while kiting him, which turns the one fight in the game
#: built around reading a telegraph into a fight about guessing where he went.
#: Thirty tiles across is half again the view: enough to run, never enough to
#: lose him.
#:
#: The first cut was 21 (forty-two across) on the argument that a boss arena
#: should feel big. It felt empty, and at that size the ring of fires — which
#: is the whole light and the whole edge of the place — was never on screen
#: with him.
ARENA_RADIUS_TILES = 15.0
#: Burning fuel drums around the rim. `world.FIRE` tiles: they light, they
#: cast, they animate and they block, all for free.
ARENA_FIRES = 9
#: Wreckage still burning INSIDE the ring, as scene lights with no collision.
#:
#: The floor (`zones.ARENA_AMBIENT`) is what makes the middle of the yard
#: legible; these are what stop it being FLAT. A uniform floor with a bright
#: rim reads as a lit stage with nothing on it — S22 is explicit that a glow
#: carrying no shape carries no information, and that what says "this is lit"
#: is the lit object. So the interior gets four burning heaps, each with a
#: mark on the ground under it, and the light in the middle of the room has
#: somewhere it is coming from.
#:
#: They are LIGHTS AND DECALS, never tiles. A `FIRE` tile is solid, and four
#: solid tiles in the middle of a boss arena is four places a two-tile body
#: can wedge itself while the party shoots it from behind them.
ARENA_EMBERS = 4
ARENA_FIRE_LIGHT_TILES = 7.5
#: How far into the ring the party has to walk before he comes down.
ARENA_TRIGGER_TILES = 7.0
#: How far IN FRONT of whoever tripped it he lands, in tiles.
#:
#: He does not land where he was standing. The camera follows the player and
#: shows five and a half tiles above them; his entrance starts seven and a
#: half tiles up and falls, so unless the landing point is close, the whole
#: cinematic — the shadow, the drop, the impact — happens off the top of
#: somebody's screen. Landing him a fixed distance ahead of the trigger, along
#: the line they are already walking, puts it in the middle of the frame every
#: time and reads as the better story anyway: he comes down in front of you,
#: not somewhere over there.
ARENA_LAND_AHEAD_TILES = 4.5

# --- networking -------------------------------------------------------------
SNAPSHOT_EVERY_N_TICKS = 1   # broadcast rate = TICK_RATE / this
# A snapshot row carries only what MOVES. Names, colours and the score board
# ride a roster attached every N ticks (and on any membership change) — they
# are read by a HUD that republishes at 5 Hz, so paying for them thirty times a
# second bought nothing. 6 ticks = 5 Hz, the same cadence.
ROSTER_EVERY_N_TICKS = 6


def xp_to_next(level: int) -> int:
    """Total xp required to go from `level` to `level + 1`."""
    return round(XP_BASE * XP_GROWTH ** (level - 1))


def level_progress(xp: int) -> tuple[int, int, int]:
    """Split lifetime xp into (level, xp into this level, xp needed to level)."""
    level = 1
    remaining = max(0, xp)
    while level < MAX_LEVEL:
        need = xp_to_next(level)
        if remaining < need:
            return level, remaining, need
        remaining -= need
        level += 1
    return MAX_LEVEL, remaining, xp_to_next(MAX_LEVEL)


def _finite(value: float) -> float | None:
    """`None` for an infinite deadline, so the payload stays valid JSON."""
    return value if math.isfinite(value) else None


def _boss_name() -> str:
    """His name, from the module that owns him. Imported late — `boss.py`
    reads TILE_SIZE out of this one, so a module-scope import is a cycle."""
    from .boss import NAME
    return NAME


def _boss_title() -> str:
    from .boss import TITLE
    return TITLE


def _boss_moves() -> dict:
    from .boss import moves_payload
    return moves_payload()


def _boss_crescent() -> dict:
    from .boss import crescent_payload
    return crescent_payload()


def client_config() -> dict:
    """Gameplay constants mirrored by the client's prediction code."""
    # Local import: enemies.py reads TILE_SIZE from this module, so importing it
    # at module scope would be a cycle. Enemy stat blocks still reach the client
    # through this one function, which stays the single client-config contract.
    from . import ammo, rift, skills
    from .machine import client_payload as machine_payload
    from .crates import catalog_payload as objects_payload
    from .enemies import enemy_types_payload
    from .loot import catalog_payload
    from . import armor
    from .weapons import (
        BLADE_SLOT,
        GUN_SLOTS,
        HOTBAR_SLOTS,
        STARTING_MELEE,
        catalog_payload as weapons_payload,
    )

    return {
        "tickRate": TICK_RATE,
        "dt": DT,
        "tileSize": TILE_SIZE,
        "spriteWidth": SPRITE_WIDTH,
        "spriteHeight": SPRITE_HEIGHT,
        "playerHalfWidth": PLAYER_HALF_WIDTH,
        "playerHalfHeight": PLAYER_HALF_HEIGHT,
        "playerHitRadius": PLAYER_HIT_RADIUS,
        "moveSpeed": MOVE_SPEED,
        "maxHp": MAX_HP,
        "fireCooldown": FIRE_COOLDOWN,
        "shotRange": SHOT_RANGE,
        "shotDamage": SHOT_DAMAGE,
        "muzzleOffset": MUZZLE_OFFSET,
        "enemyTypes": enemy_types_payload(),
        "coinSprite": "coin",
        "backpackSprite": "backpack",
        "visionAmbientTiles": VISION_AMBIENT_TILES,
        "visionLanternTiles": VISION_LANTERN_TILES,
        "visionConeDegrees": VISION_CONE_DEGREES,
        # SIGHT SYMMETRY, as the two fractions of the lantern's reach that both
        # sides must agree on. The client draws its naked-eye and lit washes at
        # exactly the reaches `ai.look` tests against — see the note above
        # `ENEMY_VIEW_DARK_SCALE`. Shipped rather than mirrored: the rule has no
        # runtime symptom when it breaks, only a wrong game.
        "enemyViewDarkScale": ENEMY_VIEW_DARK_SCALE,
        "enemyViewLitScale": ENEMY_VIEW_LIT_SCALE,
        # Undergrowth density. The client places bushes from this and the map
        # seed; `ai.look` re-derives the same tiles and shortens its reach over
        # them, so the cover the player can see is the cover the rules apply.
        # How much it shortens by (`BUSH_CONCEAL_SCALE`) stays here.
        "bushChance": BUSH_CHANCE,
        # Camp geometry. The client needs it to keep undergrowth out of the
        # hearth and to light the fire it can already see in the tiles.
        "campfireLightTiles": CAMPFIRE_LIGHT_TILES,
        # WHO THE PARTY IS FIGHTING, and it is shipped rather than hardcoded
        # in the HUD for the reason every other string is: the client renders
        # what the server says the world contains. A name kept in a React
        # component is a name that drifts from `boss.py` in silence, on the
        # one label an entire fight is announced with.
        "bossName": _boss_name(),
        "bossTitle": _boss_title(),
        # HIS MOVES' SHAPES AND CLOCKS. The client draws a telegraph on the
        # floor from these — see `boss.Move.client_payload`. Shipped rather
        # than mirrored because a marker that disagrees with the hitbox is
        # worse than no marker: it teaches a rule the simulation does not keep.
        "bossMoves": _boss_moves(),
        # The crescent's travel, for the lane `rip` telegraphs.
        "bossCrescent": _boss_crescent(),
        # HIS CAPSULE, so the client's own tracer stops on him.
        #
        # `predictShot` builds the local player's shot against players and
        # enemies and draws it the frame the trigger goes down; the boss was
        # missing from that list, so every round a player fired at the biggest
        # body in the game flew visibly THROUGH it. The damage was always
        # landing — the server had him in `targets` from the day he shipped —
        # but a shot with no hit marker, no number and no stop reads as a shot
        # that missed, and a player who thinks their gun does nothing to a
        # boss stops shooting him. These are the three numbers `combat.py`'s
        # capsule wants, in world px, exactly as `Boss` computes them.
        "bossHit": {
            "radius": round(TILE_SIZE * BOSS_HIT_TILES_R, 2),
            "halfHeight": round(TILE_SIZE * 0.5, 2),
            "spriteHeight": round(TILE_SIZE * BOSS_SPRITE_TILES_H, 2),
        },
        "hearthTiles": CAMP_HEARTH_TILES,
        "ringTilesX": CAMP_RING_TILES_X,
        "ringTilesY": CAMP_RING_TILES_Y,
        # How close to the fire the ready prompt answers, in tiles.
        "readyRangeTiles": CAMP_READY_RANGE_TILES,
        # How close to a drop E will collect, in tiles.
        "lootCollectTiles": LOOT_COLLECT_TILES,
        # How close to a crate E will smash, in tiles.
        "crateBreakTiles": CRATE_BREAK_TILES,
        # How close to the extraction console E will activate, in tiles.
        "riftActivateTiles": RIFT_ACTIVATE_TILES,
        # The shop. How close to a table E will buy, and how far the weapon on
        # it lifts when somebody is in that range — the lift is the visual half
        # of the same reach, so the two travel together or the gun rises at a
        # distance where the key does nothing.
        "storeBuyTiles": STORE_BUY_TILES,
        "storeLiftTiles": STORE_LIFT_TILES,
        # The upgrade machine: how close E answers, and the clock the whole
        # pull runs on. Same discipline as `rift` above — the client flies the
        # reels, the lamps, the eject and the settle off these plus the one
        # `pullAt` on the wire, and the server ends the sequence on them.
        "storeSpinTiles": STORE_SPIN_TILES,
        "machine": machine_payload(),
        # Skills: name, rarity, blurb, icon frame, stack cap. The tray above
        # the bag draws a tile the server only ever names by key.
        "skills": skills.catalog_payload(),
        # The extraction platform's clock, in seconds. ONE clock: the client
        # flies the whole pickup off these numbers plus the one `closeAt` on
        # the wire, and the server ends the sequence on them. See
        # server/app/rift.py.
        "rift": {
            "consoleLag": rift.CONSOLE_LAG,
            "openAt": rift.OPEN_AT,
            "lightTiles": rift.LIGHT_TILES,
            "drones": rift.DRONES,
            # THE PICKUP, and the client flies the whole thing off these plus
            # the one `closeAt` on the wire. Sirens alone first; then drone `i`
            # leaves the treeline at `liftAlarm + i * droneStagger`, crosses in
            # `droneInbound`, and spends `droneDrop` paying its line down to
            # its corner. `tiedAt` is when the last of them is on.
            "liftAlarm": rift.LIFT_ALARM,
            "droneStagger": rift.DRONE_STAGGER,
            "droneInbound": rift.DRONE_INBOUND,
            "droneDrop": rift.DRONE_DROP,
            "tiedAt": rift.TIED_AT,
            # Then the lift: straining against ground that will not let go, the
            # skid breaking free, and the flight out. `breakAt` is also when
            # the deck's tiles become walkable — the server patches them on
            # that tick — so it is shipped rather than re-derived.
            "liftStrain": rift.LIFT_STRAIN,
            "liftBreak": rift.LIFT_BREAK,
            "liftClimb": rift.LIFT_CLIMB,
            "breakAt": rift.BREAK_AT,
            # The window, and the way it ends. NULL means "never" — the
            # platform waits until a player launches it. It cannot be `inf`:
            # Python serialises that as the bare token `Infinity`, which is not
            # JSON and which `JSON.parse` throws on, taking the entire config
            # payload with it.
            "openTime": _finite(rift.OPEN_TIME),
            "collapseAt": _finite(rift.COLLAPSE_AT),
            "collapseTime": rift.COLLAPSE_TIME,
            "spentAt": _finite(rift.SPENT_AT),
        },
        # Fallback shot box on an object, in tiles. Bottom-anchored on the
        # contact. Per-object boxes ride `objects` below and win.
        "crateHitWTiles": CRATE_HIT_W_TILES,
        "crateHitHTiles": CRATE_HIT_H_TILES,
        # THE OBJECT VOCABULARY: which sheet each one draws from, which verb
        # E offers, what the prompt says, and how big a target it is. The
        # client has no table of its own — adding a barrel kind is a row in
        # `crates.TYPES` and a sheet in `make_objects.py`.
        "objects": objects_payload(),
        # Calibres, which catalog row is a box of each, and the reserve caps.
        "ammo": ammo.client_payload(),
        # Catalog: name, rarity, atlas frame, weight, value, pocket.
        # Guns also have a combat block in `weapons`.
        "loot": catalog_payload(),
        "weapons": weapons_payload(),
        # WHAT A BODY CAN WEAR: twelve pieces, three slots, four materials,
        # and every number on them derived from one claw. The client draws
        # the durability bars, the overlay sheets and the tooltip off this and
        # has no table of its own — adding a material is a row in
        # `armor.MATERIALS` and a ramp in `make_armor.py`.
        "armor": armor.catalog_payload(),
        # The slots in the order they are worn and drawn, top to bottom. The
        # HUD stacks its rows off this and a `LootPickup` with `dest:"worn"`
        # indexes it, so the order is a contract rather than a convenience.
        "armorSlots": list(armor.SLOTS),
        "armorSlotNames": dict(armor.SLOT_NAMES),
        # WHERE A BLOW LANDS, per slot. The client needs it for one honest
        # number — what a whole set actually stops, which is the
        # coverage-weighted sum of what each plate stops on its own part — and
        # a HUD that averaged the three instead would be quietly wrong about
        # every partial set. See `armor.COVERAGE`: it is the player sprite's
        # own anatomy, so it is a fact about the art rather than a tuning knob.
        "armorCoverage": {slot: round(share, 4) for slot, share in armor.COVERAGE.items()},
        "inventorySlots": INVENTORY_SLOTS,
        "hotbarSlots": HOTBAR_SLOTS,
        # WHICH CELLS ARE WHICH. The belt is `gunSlots` gun cells and then the
        # BLADE cell, and the client needs the split to know that key 3 is
        # never empty and that a lâmina replaces rather than stows.
        "gunSlots": GUN_SLOTS,
        "bladeSlot": BLADE_SLOT,
        # What the blade cell falls back to. The client needs it for exactly
        # one thing: knowing that a knife replaced by a better lâmina does not
        # land on the floor, so the pickup prompt must not offer it as
        # something you are giving up. See `Room.swap_blade`.
        "startingBlade": STARTING_MELEE,
        "carryMaxWeight": CARRY_MAX_WEIGHT,
        "carrySlowStart": CARRY_SLOW_START,
        "carrySlowAtMax": CARRY_SLOW_AT_MAX,
        "carrySlowFloor": CARRY_SLOW_FLOOR,
        # Running. The client predicts its own body, so every number the
        # sprint reads has to be here — see `simulation.step_stamina`.
        "sprintSpeed": SPRINT_SPEED,
        "staminaMax": STAMINA_MAX,
        "staminaDrain": STAMINA_DRAIN,
        "staminaRegenWalk": STAMINA_REGEN_WALK,
        "staminaRegenRest": STAMINA_REGEN_REST,
        "staminaRecover": STAMINA_RECOVER,
        # Prediction multiplies by the scale every frame it is set; the time is
        # for drawing only, because nothing client-side ever starts a stagger.
        "hitStaggerScale": HIT_STAGGER_SCALE,
        "hitStaggerTime": HIT_STAGGER_TIME,
    }
