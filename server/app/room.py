"""The game room: authoritative state + fixed-tick simulation loop.

A room has two phases and, separately, a ZONE.

The phases are `lobby` and `playing`. In `lobby` nothing ticks: players join,
take a colour and a seat at the fire, and state is pushed only when membership
changes. `begin()` flips it to `playing` and starts the 30 Hz loop. The socket
is the same one throughout.

The zone (see zones.py) is WHERE the room is, and it does not change when the
phase does. A room opens in the camp and stays there: the lobby is the camp seen
from a chair, `preparation` is the same camp with the simulation running. That
is why `begin()` does not respawn anybody — the seat you were standing on is the
tile you start on, and a party watching their characters teleport the instant
the host clicks start would learn that the lobby was only ever a picture.

Zone rules the loop obeys:
  * a non-hostile zone runs no enemy director and fires no weapons
  * seats are re-spaced around the fire while the room is in `lobby`, and never
    afterwards — position belongs to the simulation once it is running

Rooms are created and looked up by code in `rooms.py`; nothing in this class
assumes it is the only one.

NAVIGATING THIS FILE. It is ~2.9k lines and is not meant to be read whole.
Every handler sits under a `# --- <section> ---` banner; grep the banner, not
the line number. In order:

    lifecycle           start / stop
    membership          spawns, seats, join, leave, the lobby payloads, ready
    loot and the belt   collect, the gun trade
    interactive objects break / open / lift, nests, the ambush
    extraction          the console, the pour, the quota, the carved exit
    the shop            the six stalls, the upgrade machine's lever
    the bag             drop one slot back onto the ground
    zone transit        embark / enter_store / depart_store, all via _swap_map
    input               queue_input
    the tick            step(), the one ordered pass
    extraction clock    the pickup: siren, drones, the deck freeing
    bodies + corridors  the per-tick player update, and the walk-out /
                        arrival / seal that puppet it
    quests              offering and ticking the run's objectives
    enemies             the director's slice of the tick
    ultimates           R: whether the press is legal, what it does to the
                        world, what fills the bar, and how long it lasts
    the boss            the Sawyer: waking him, his tick, hurting him, and the
                        exit his death carves
    combat              attacks both ways, the swing, the shot, damage, death
    networking          broadcast, the snapshot assembly, the 30 Hz loop

The banners used to be five, one of which spanned 1374 lines across eight of
the sections above. That is worth keeping honest: `AGENTS.md` tells a reader
to jump to the section rather than open the file, and a banner that lies turns
that instruction into a full scan.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
import uuid

from . import (
    ai, ammo, arena, armor, boss, camp, coins, combat, crates, entrance, events, loot,
    mapgen, medical, projectiles, protocol, quests, rift, skills, store,
    ultimates, weapons, zones,
)
from . import machine
from .ai import EnemyDirector
from .coins import Coin
from .config import (
    ARENA_LAND_AHEAD_TILES,
    ARENA_TRIGGER_TILES,
    BOSS_COINS,
    BOSS_DAY,
    BOSS_XP,
    CRATE_BREAK_DIST,
    CRATE_NOISE_DIST,
    DT,
    LOOT_COLLECT_DIST,
    MARCH_SPEED,
    RIFT_ACTIVATE_DIST,
    EXIT_CROSS_TILES,
    INVENTORY_SLOTS,
    STORE_BUY_DIST,
    STORE_SPIN_DIST,
    STORE_REROLL_PRICE,
    STORE_SPIN_PRICE,
    MAX_HP,
    MAX_INPUT_QUEUE,
    MAX_INPUTS_PER_TICK,
    HIT_STAGGER_TIME,
    MELEE_IMMUNITY,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    MOVE_SPEED,
    RESPAWN_DELAY,
    RESPAWN_IMMUNITY,
    WIPE_HOLD,
    HORDE_TELEGRAPH,
    SHOT_NOISE_DIST,
    ENEMY_HARD_CAP,
    ROSTER_EVERY_N_TICKS,
    SNAPSHOT_EVERY_N_TICKS,
    SPAWN_RING,
    SPAWN_SEPARATION,
    STAMINA_MAX,
    TILE_SIZE,
    client_config,
    level_progress,
)
from .corpses import Corpse
from .crates import VERB_BREAK, Crate
from .entrance import Entrance
from .rift import Rift
from .store import Stand
from .loot import Drop
from .quests import Quest
from .enemies import ENEMY_TYPES, Enemy, EnemyType, dress
from .world import FLOOR, VOID
from .entities import (
    USE_CRATE,
    USE_HEAL,
    POUR_DUMP, POUR_LIFT, POUR_STOW, POUR_WALK,
    InputCmd, Player, Pour, UltState, clean_name, pick_color, random_name,
    Use,
)
from .pathing import Navigator
from .simulation import apply_input, carry_scale, step_stamina

#: How many creatures stand on a nest, and how far from its middle they are
#: scattered, in tiles.
#:
#: The pack is sized to be OBVIOUSLY too many for a knife and obviously
#: possible with a gun, because that is the sentence the shrine is trying to
#: say from across the clearing: come back when you have bought something.
#: `NEST_INNER` keeps them off the altar itself — a creature standing on the
#: prize would make the fight about a pixel rather than about the ground.
NEST_PACK = (5, 8)
NEST_INNER = 2.0
NEST_SPREAD = 5.0

#: How far a shotgun pellet may wander off its slot in the pattern, as a
#: fraction of the gap between slots.
#:
#: Small, and that is the design of the weapon rather than a tuning value.
#: At 0 two shells are the same photograph; at 1 the pattern stops being a
#: pattern and the shotgun becomes a dice roll you cannot plan around. A
#: quarter of a slot is enough that no two shells look alike and never
#: enough to change what a shell does at a given range — which is the only
#: thing the player is allowed to be reading when they decide to step in.
PELLET_WOBBLE = 0.25


class Room:
    def __init__(self, code: str = "LOCAL", seed: int | None = None):
        self.code = code
        self.phase = protocol.PHASE_LOBBY
        #: First player in wins the start button; promoted on departure.
        self.host_id: str | None = None
        #: Which day the run is on. Day 1 opens in the camp.
        self.day = 1
        self.zone = zones.camp(self.day)
        # The camp IS the lobby's backdrop and `preparation`'s ground. One map,
        # generated once, sent in `hello` before anybody may walk on it.
        self.world = camp.build_camp(seed if seed is not None else random.randrange(1, 2**31))
        #: Join order. It decides who sits where, and every client agrees on it
        #: because it is only ever computed here.
        self.seating: list[str] = []
        self.spawn_points: list[tuple[float, float]] = []
        self.spawn_ring: list[tuple[float, float]] = []
        self.players: dict[str, Player] = {}
        self.enemies: dict[str, Enemy] = {}
        self.coins: dict[str, Coin] = {}
        self.drops: dict[str, Drop] = {}
        self.crates: dict[str, Crate] = {}
        #: Extraction points, empty on a map without any (every camp, and any
        #: forest the generator could not fit a plot into).
        self.rifts: list[Rift] = []
        #: Forest arrival corridor. None in the camp.
        self.gate: Entrance | None = None
        #: Extraction exit, carved when the feed quota is paid. None until then.
        self.egress: Entrance | None = None
        #: Run objectives. Empty until the entrance seals.
        self.quests: list[Quest] = []
        #: What ONE pad asks for tonight. Each rift carries its own `fed`
        #: against this; the night's bill is this times however many landed.
        self.pad_need = 0
        #: Lamps are dead and the pack does not give up. Latched until return.
        self.blackout = False
        self.panic = False
        #: THE PARTY'S MONEY, and it is the party's rather than a player's on
        #: purpose. Everything else a run produces is personal — your kills,
        #: your xp, the gun in your hands — but what comes back from a night is
        #: what the whole group fed into the anomalies, and there is no honest
        #: way to split a shared bill four ways after the fact. One balance,
        #: one shop, and who spends it is a conversation the party has.
        #:
        #: `Player.gold` is a different number and stays one: coins picked up
        #: off corpses, which nobody pooled.
        self.balance = 0
        #: How many pulls the party has BOUGHT at this night's cabinet. A level
        #: is still the only free spin; once nobody is owed one the lever will
        #: still take gold, and every purchase doubles what the next one costs
        #: (`spin_price`). Reset on the walk into each shop, so the ladder is a
        #: decision the party makes fresh every night rather than a tax that
        #: compounds across a whole run.
        #:
        #: PARTY-WIDE, LIKE THE MONEY IT SPENDS. It is one machine and one
        #: purse, so four players cannot each buy a 50-gold pull — the second
        #: one costs 100 whoever is standing at the lever.
        self._spins_bought = 0
        self._spin_price_dirty = False
        #: Rerolls bought THIS VISIT. Resets with the shop, like the spins,
        #: because both ladders are about one merchant on one night.
        self._rerolls_bought = 0
        self._reroll_price_dirty = False
        #: Rerolls this tick. The lever's own ceremony — one row, for the
        #: sound and the shelf visibly turning over.
        self.reroll_events: list[dict] = []
        #: The shop's tables. Empty on every map that is not the store.
        self.stands: list[Stand] = []
        self._stands_dirty = False
        #: The shop's ammunition crates — one per calibre SOMEBODY IN THE ROOM
        #: IS CARRYING, and nothing else. Rebuilt from the belts every tick of
        #: a store visit (`_sync_ammo_boxes`), so buying the first shotgun in
        #: the party is what puts shells on the wall.
        self.ammo_boxes: list[store.AmmoBox] = []
        self._boxes_dirty = False
        #: Calibres that have ALREADY been stocked this visit. A crate that
        #: landed stays landed: without this a player swapping their rifle away
        #: for one step would watch the rifle crate blink out and back, and a
        #: shop whose shelves flicker reads as broken rather than as responsive.
        self._boxes_seen: set[str] = set()
        self._balance_dirty = False
        self.corpses: dict[str, Corpse] = {}
        self.sockets: dict[str, object] = {}
        self.director = EnemyDirector(self.spawn_points, self.day)
        self.navigator = Navigator(self.world)
        self.tick = 0
        self.shot_events: list[dict] = []
        #: Melee arcs thrown this tick. A separate list from `shot_events`
        #: because a swing is not a tracer: no distance, no single victim, and
        #: a combo step the client draws a different shape for.
        self.swing_events: list[dict] = []
        #: Things enemies can HEAR, made this tick and consumed by the next
        #: `ai.update`. A gunshot is the only source so far; anything else the
        #: player does loudly is one more append (see `ai.Noise`).
        self.noises: list[ai.Noise] = []
        self.attack_events: list[dict] = []
        self.kill_events: list[dict] = []
        self.pickup_events: list[dict] = []
        self.loot_pickup_events: list[dict] = []
        #: Items tipped out of a backpack onto a platform this tick. The juice:
        #: every client draws the sprite leaving the bag and landing on the
        #: deck, and `n` is the pile index so they all stack it the same way.
        self.pour_events: list[dict] = []
        self.crate_break_events: list[dict] = []
        #: Blows that landed on GEAR this tick: a plate soaking one, a shield
        #: eating one whole, and the frame either of them came apart on. The
        #: juice — a spark off steel, a crack, and the one moment the player
        #: has to be told in the world rather than on a bar that a piece is
        #: gone. The roster carries the durability; this carries the EVENT,
        #: the same split every other ceremony in this file keeps.
        self.armor_events: list[dict] = []
        #: Purchases made this tick. The juice: the client flies the gun onto
        #: the belt cell and counts the balance down.
        self.buy_events: list[dict] = []
        #: Lever pulls made this tick. One row is a whole four-second ceremony:
        #: the roll is already decided, and every client in the glade flies the
        #: reels, the eject and the settle off it plus `config.machine`.
        self.spin_events: list[dict] = []
        #: Seconds left on the cabinet's own ceremony. ONE machine, one lever:
        #: a second player pulling into somebody else's spin would have to
        #: interrupt an animation everybody in the glade is already watching.
        #: A countdown rather than a deadline because the room has no wall
        #: clock — every other timer here is `-= dt` too.
        self._machine_busy = 0.0
        self._shot_id = 0
        self._swing_id = 0
        self._enemy_id = 0
        self._coin_id = 0
        self._task: asyncio.Task | None = None
        #: Walk-out cinematic. The camp is still the map; input is ignored and
        #: bodies are slid toward formation slots, then into the black exit.
        self.departing = False
        self._depart_phase: str | None = None
        self._depart_hold = 0.0
        self._slots: dict[str, tuple[float, float]] = {}
        self._pending_embark = False
        self._pending_return = False
        #: Forest emerge cinematic. Same lock as the camp walk-out: input is
        #: acked and dropped, bodies are slid out of the VOID corridor.
        self.arriving = False
        self._arrive_phase: str | None = None
        self._arrive_hold = 0.0
        self._seal_left = 0.0
        self._tile_patches: list[tuple[int, int, int]] = []
        self._entrance_dirty = False
        self._quests_dirty = False
        #: Someone joined or left: attach the roster to the next snapshot
        #: instead of making the party wait out the interval for a name.
        self._roster_dirty = True
        #: A drop was collected or tossed: attach the remaining loot list next tick.
        self._loot_dirty = True
        self._loot_seq = 0
        self._crates_dirty = True
        self._corpses_dirty = True
        #: Set when any rift changes state, not every tick — the four seconds
        #: in between are the client's own clock.
        self._rift_dirty = False
        self._egress_dirty = False
        self._blackout_dirty = False
        #: THE SAWYER, on the one night there is one. None everywhere else,
        #: and that is the whole gate — every boss branch in this file is a
        #: `self.boss is None` test rather than a zone check, so a room that
        #: never builds one never pays for one.
        self.boss: boss.Boss | None = None
        #: What he did this tick, for the client's shake, dust, sound and
        #: gore. Cleared every broadcast like `shot_events`.
        self.boss_events: list[dict] = []
        #: Set when he changes state, when his health moves, or when a
        #: crescent is in the air. The row is small and the bar has to be
        #: exact, so in practice this is on for the whole fight — it exists
        #: so the row is absent on every OTHER map rather than absent between
        #: his frames.
        self._boss_dirty = False
        #: The night's takings, carried across the arena. THE MONEY IS STILL
        #: CREATED IN `enter_store` AND NOWHERE ELSE (see AGENTS.md) — this is
        #: the receipt travelling with the party, because the pads that earned
        #: it belong to a map they have already left.
        self._night_takes: list[int] | None = None
        #: THE RUN IS OVER AND THE SCREEN IS BLACK. Counts down while the
        #: death card holds; the reset itself happens when it reaches zero
        #: (`run`). A hold rather than a keypress because the last thing
        #: anybody wants on that frame is another decision to make.
        self._wipe_hold = 0.0
        #: Which night it ended on. The card says so, and it is captured when
        #: the party goes down rather than read at reset time — by then the day
        #: is already back to one.
        #: Non-zero means A WIPE IS IN PROGRESS — it is the latch as well as
        #: the number the card shows. `_wipe_hold` alone cannot be one: it
        #: reaches zero on the tick before the reset runs, and a check that
        #: read it would fire the wipe a second time on that frame.
        self._wipe_day = 0
        #: A wave that has been ROLLED and announced but not yet arrived, as
        #: `(x, y, bearing, size)`, plus the seconds left before it does. Held
        #: on the room rather than in the director because the gap between the
        #: howl and the bodies is a beat of the ROOM's night — see `_step_horde`.
        self._horde: tuple[float, float, float, int] | None = None
        self._horde_left = 0.0
        #: Waves announced this tick. One row is a howl at a bearing; the
        #: client plays it spatially and puts a card up. Cleared every
        #: broadcast like every other event list.
        self.horde_events: list[dict] = []
        #: Kits spent this tick. The juice: a green wash on the body, the
        #: number floating off it, and the sound. Cleared every broadcast.
        self.heal_events: list[dict] = []
        #: THE NIGHT'S SCRIPT. One per map, like the population director and
        #: for the same reason: a night is a fresh script rather than a
        #: continuation, so every clock in it restarts at an entrance.
        self.events = events.EventDirector(self.day)
        #: Rows fired this tick, drained into the snapshot.
        self.event_rows: list[dict] = []
        #: EVERY CREATURE PROJECTILE IN THE AIR, and the id counter that names
        #: them. On the ROOM rather than on the creature that threw it, because
        #: a spit outlives its thrower — shooting a bloater mid-flight must not
        #: delete the thing already coming at you, or killing it would be a way
        #: to un-fire a shot.
        self.shots: list[projectiles.Projectile] = []
        self._shot_id = 0
        #: Shots that LEFT something this tick — the launch, for the sound and
        #: the burst of bile. An event; the live rows carry the flight.
        self.spit_events: list[dict] = []
        #: Where shots ENDED this tick. Also an event.
        self.shot_bursts: list[dict] = []
        #: EVERYTHING A PLAYER'S ULTIMATE PUT IN THE AIR, and its own id
        #: counter. A separate list from `self.shots` rather than a `team`
        #: field on the projectile, and the split is about what they are
        #: tested AGAINST: a creature's spit bills players and a crescent
        #: bills creatures, so one list would mean a per-projectile branch
        #: inside `projectiles.advance` — which is the one function in that
        #: module that must stay a loop over one body list.
        self.ult_shots: list[projectiles.Projectile] = []
        self._ult_shot_id = 0
        #: Ultimates that FIRED this tick. The one-shot every client draws the
        #: burst, the shake and the sound off — an event, never state, so a
        #: dropped packet cannot replay somebody's ultimate.
        self.ult_events: list[dict] = []
        #: Where an ultimate projectile ended. Same contract as `shot_bursts`.
        self.ult_bursts: list[dict] = []
        #: Seconds left of an event dark, or 0. Suppresses every lantern on the
        #: map through the SAME branch the extraction blackout uses — see
        #: `begin_dark` for why there is deliberately only one such branch.
        self.dark_left = 0.0
        self._dark_dirty = False
        self._load_drops()
        self._load_crates()
        self._load_rifts()
        self._load_stands()
        self._load_entrance()
        self._rebuild_spawns()

    def _load_stands(self) -> None:
        """Hydrate the shop's tables from the map the builder left behind."""
        rows = (self.world.store or {}).get("stands")
        self.stands = store.stands_from_payloads(rows)
        self._stands_dirty = bool(self.stands)
        rows = (self.world.store or {}).get("boxes")
        self.ammo_boxes = store.ammo_boxes_from_payloads(rows)
        self._boxes_seen = {box.calibre for box in self.ammo_boxes}
        self._boxes_dirty = bool(self.ammo_boxes)

    def _load_drops(self) -> None:
        """Hydrate live drops from the map the generator left behind."""
        self.drops = loot.from_payloads(self.world.loot)
        seq = 0
        for drop_id in self.drops:
            if drop_id.startswith("l"):
                try:
                    seq = max(seq, int(drop_id[1:]))
                except ValueError:
                    pass
        self._loot_seq = seq
        self._loot_dirty = True

    def _next_drop_id(self) -> str:
        self._loot_seq += 1
        return f"l{self._loot_seq}"

    def _load_crates(self) -> None:
        """Hydrate live crates from the map the generator left behind."""
        self.crates = crates.from_payloads(self.world.crates)
        self._crates_dirty = True

    def _load_rifts(self) -> None:
        """Hydrate extraction points from the map the generator left behind."""
        self.rifts = rift.from_payloads(self.world.rifts)
        self.pad_need = rift.pad_need(self.day, len(self.rifts)) if self.rifts else 0
        for row in self.rifts:
            # A hydrated map may already carry a quota (the room stores the
            # geometry payload back after every state change). Only a pad that
            # has never been priced takes tonight's number.
            if row.need <= 0:
                row.need = self.pad_need
        self.egress = entrance.from_payload(self.world.egress)
        self.blackout = False
        self.panic = False
        self._rift_dirty = False
        self._egress_dirty = False
        self._blackout_dirty = False

    def _load_entrance(self) -> None:
        """Hydrate the forest corridor from the map the generator left behind."""
        self.gate = entrance.hydrate(self.world.tiles, self.world.entrance)
        self._entrance_dirty = False
        self._tile_patches = []
        self.arriving = False
        self._arrive_phase = None
        self.quests = []
        self._quests_dirty = False

    # --- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # --- membership ---------------------------------------------------------
    def pick_spawn(self) -> tuple[float, float]:
        """A tile on the ring around the arrival mouth, clear of teammates.

        Co-op: everyone lands together where they walked in. The separation
        test only stops players from spawning inside each other — it does not
        push them apart, so a full room still starts as one group.
        """
        living = [p for p in self.players.values() if p.alive]
        minimum = SPAWN_SEPARATION * SPAWN_SEPARATION
        for x, y in self.spawn_ring:
            if all((p.x - x) ** 2 + (p.y - y) ** 2 >= minimum for p in living):
                return x, y
        return self.spawn_ring[0] if self.spawn_ring else random.choice(self.spawn_points)

    def _rebuild_spawns(self) -> None:
        """Floor tiles, nearest the arrival mouth (or the map centre in camp)."""
        self.spawn_points = self.world.free_spawn_points(
            PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT
        )
        if self.gate is not None:
            self.spawn_ring = entrance.mouth_spawns(self.gate, self.spawn_points)
            return
        centre_x = self.world.pixel_width / 2
        centre_y = self.world.pixel_height / 2
        self.spawn_ring = sorted(
            self.spawn_points,
            key=lambda p: (
                abs(math.hypot(p[0] - centre_x, p[1] - centre_y) - SPAWN_RING)
                + random.uniform(0.0, SPAWN_SEPARATION)
            ),
        )

    def reseat(self) -> None:
        """Space the party evenly around the fire, in join order.

        Only legal while the room is in `lobby`. Once the simulation is running,
        position is the simulation's — shoving a player two tiles sideways
        because somebody else joined would fight their own prediction.
        """
        if self.phase != protocol.PHASE_LOBBY:
            return
        total = len(self.seating)
        for index, pid in enumerate(self.seating):
            player = self.players.get(pid)
            if player is None:
                continue
            player.x, player.y = camp.seat_position(self.world, index, total)
            player.vx = player.vy = 0.0

    def add_player(self, socket, name: str | None = None) -> Player:
        pid = uuid.uuid4().hex[:8]
        taken_names = {p.name for p in self.players.values()}
        player = Player(
            id=pid,
            name=clean_name(name, taken_names) or random_name(taken_names),
            # Colour is the lobby's identity — two players sharing one makes the
            # roster unreadable, so an unused swatch is picked rather than a
            # random one.
            color=pick_color({p.color for p in self.players.values()}),
        )
        self.players[pid] = player
        self.sockets[pid] = socket
        self.seating.append(pid)
        self._roster_dirty = True
        if self.host_id is None:
            self.host_id = pid
        if self.phase == protocol.PHASE_LOBBY:
            # Everyone shuffles round to make room, which is what the client
            # animates. Someone joining a run in progress takes a spawn instead.
            self.reseat()
        else:
            player.x, player.y = self.pick_spawn()
            if self.departing:
                self._slots = camp.formation_slots(
                    self.world, self.seating, set(self.players)
                )
            elif self.arriving and self.gate is not None:
                self._slots = entrance.formation_slots(
                    self.gate, self.seating, set(self.players)
                )
                slot = self._slots.get(pid)
                if slot is not None:
                    player.x, player.y = slot
                    player.aim_x = self.gate.dx
                    player.aim_y = self.gate.dy
        return player

    def remove_player(self, pid: str) -> None:
        self.players.pop(pid, None)
        self.sockets.pop(pid, None)
        self._roster_dirty = True
        if pid in self.seating:
            self.seating.remove(pid)
        # The host leaving must not lock the room out of ever starting.
        if pid == self.host_id:
            self.host_id = next(iter(self.players), None)
        self.reseat()

    def welcome_payload(self, player: Player) -> dict:
        return protocol.welcome(
            player.to_payload(),
            client_config(),
            self.world.to_payload(),
            self.zone.to_payload(),
            ack=player.last_processed_seq,
            loot=[drop.to_payload() for drop in self.drops.values()],
            corpses=[row.to_payload() for row in self.corpses.values()],
            quests=[q.payload() for q in self.quests] or None,
            blackout=self.blackout,
            balance=self.balance,
            spin_price=self.spin_price,
        )

    def hello_payload(self, player: Player) -> dict:
        return protocol.hello(
            player.id,
            self.code,
            client_config(),
            self.world.to_payload(),
            self.zone.to_payload(),
        )

    def lobby_payload(self) -> dict:
        return protocol.lobby(
            self.code,
            self.host_id,
            self.phase,
            self.zone.to_payload(),
            [
                {
                    "id": p.id,
                    "name": p.name,
                    "color": p.color,
                    # Where they actually are. The lobby draws this, so the
                    # scene and the simulation cannot disagree about the party.
                    "x": round(p.x, 4),
                    "y": round(p.y, 4),
                }
                for p in self.players.values()
            ],
        )

    async def begin(self) -> None:
        """Leave the chairs: hand out the map and start ticking.

        Nobody moves. The zone is already the camp, everyone is already standing
        on their seat, and the only thing that changes is that the world starts
        answering their input.
        """
        if self.phase == protocol.PHASE_PLAYING:
            return
        self.phase = protocol.PHASE_PLAYING

        await self.broadcast(self.lobby_payload())
        for pid, socket in list(self.sockets.items()):
            player = self.players.get(pid)
            if player is not None:
                await self._safe_send(pid, socket, protocol.dumps(self.welcome_payload(player)))
        self.start()

    def toggle_ready(self, pid: str) -> None:
        """Flip ready if this player is standing at the fire in the camp.

        When every living player is ready, the walk-out starts. Too late to
        unready once it has: the camera has already left.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind != zones.KIND_CAMP:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        if not camp.near_fire(player.x, player.y, self.world):
            return
        player.ready = not player.ready
        living = [p for p in self.players.values() if p.alive]
        if living and all(p.ready for p in living):
            self.begin_depart()

    # --- loot and the belt --------------------------------------------------
    def collect_loot(self, pid: str, drop_id: str) -> None:
        """Pick up a drop if this player is standing on it.

        Camp has none. Too late once the walk-out has started. Distance is
        measured from the feet, the same way the ready prompt is. A full bag
        (no empty slot and no stack of this key) leaves the drop where it is.
        Overweight is not a refuse.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind == zones.KIND_CAMP:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        drop = self.drops.get(drop_id)
        if drop is None:
            return
        feet_y = player.y + PLAYER_HALF_HEIGHT
        if (drop.x - player.x) ** 2 + (drop.y - feet_y) ** 2 > LOOT_COLLECT_DIST * LOOT_COLLECT_DIST:
            return
        item = loot.BY_KEY.get(drop.key)
        dest = "bag"
        if item is not None and item.pocket == "ammo":
            # AMMUNITION, and it answers to the collecting player's own belt.
            # Not the party's: in a four-player room the rifle rounds belong
            # to whoever is carrying the rifle, and a teammate who cannot fire
            # the calibre may not scoop them up "for later". A player who
            # already holds all they can carry of it leaves the box on the
            # ground — `Reserve.add` returning zero is the refusal.
            calibre = ammo.calibre_for_key(drop.key)
            if calibre is None or calibre not in ammo.carried_by(player.hotbar):
                return
            if player.ammo.add(calibre, ammo.rounds_in(drop.key)) <= 0:
                return
            # No slot, because rounds do not take one. The pickup event still
            # needs an index for the fly-to-slot animation, so it names the
            # hotbar cell the matching gun is in — the sprite flies to the
            # weapon it just fed, which is exactly what happened.
            dest = "ammo"
            slot = next(
                (
                    index
                    for index, key in enumerate(player.hotbar.slots)
                    if ammo.calibre_of(key) == calibre
                ),
                0,
            )
            del self.drops[drop_id]
            self.loot_pickup_events.append(
                loot.LootPickup(
                    drop.id, player.id, drop.key, drop.x, drop.y, slot, dest
                ).to_payload()
            )
            self._loot_dirty = True
            self._roster_dirty = True
            return
        if item is not None and item.pocket == medical.POCKET:
            # MEDICINE, into its own two cells. It REFUSES when both are full
            # rather than swapping, unlike a gun cell: two kits are a QUANTITY
            # and not alternatives, so silently dropping one to pick up another
            # would be the game throwing away the exact resource the player was
            # bending down to stockpile. The drop stays on the ground, which is
            # the same answer a full ammunition reserve gives.
            if not player.medical.add(drop.key):
                return
            dest = "med"
            slot = next(
                (i for i, key in enumerate(player.medical.slots) if key == drop.key), 0
            )
        elif item is not None and item.pocket == "worn":
            dest = "worn"
            slot = self.wear_armor(player, drop.key, drop.hp)
        elif item is not None and item.pocket == "hotbar":
            dest = "hotbar"
            slot = self.take_weapon(player, drop.key, drop.hp)
        else:
            # A condensed core carries its own value, weight and drawn size —
            # they came off the rift that made it, not off the catalog — so
            # they go into the slot with it. Everything else passes None and
            # reads its row.
            slot = player.inventory.add(
                drop.key, value=drop.value, weight=drop.weight, scale=drop.scale
            )
        if slot is None:
            return
        del self.drops[drop_id]
        self.loot_pickup_events.append(
            loot.LootPickup(
                drop.id, player.id, drop.key, drop.x, drop.y, slot, dest
            ).to_payload()
        )
        self._loot_dirty = True
        self._roster_dirty = True

    def wear_armor(self, player: Player, key: str, hp: int | None = None) -> int | None:
        """Put a plate on. Returns its slot INDEX, or None if it was refused.

        ONE REFUSAL, AND IT IS THE ONLY ONE THIS CATEGORY NEEDS: the piece
        you are already wearing, in the same or better condition. Everything
        else goes on, including a piece that is WORSE than what is there —
        because "worse" is not something the server gets to decide. A fresh
        cloth vest over a steel one with four points left is a real choice a
        player might make on purpose, and a game that quietly refused it
        would be answering a question the player was in the middle of asking.

        The piece that comes off keeps whatever life it had and lands at the
        feet, so the swap is reversible one step later — the same promise
        `swap_weapon` makes about a traded gun.

        The index rather than the slot name because it is going onto a
        `LootPickup`, which carries an int for every other destination: the
        client flies the sprite at the armour row it landed on.
        """
        piece = armor.BY_KEY.get(key)
        if piece is None:
            return None
        worn = player.armor.get(piece.slot)
        incoming = piece.max_hp if hp is None else hp
        if worn is not None and worn.key == key and worn.hp >= incoming:
            return None
        old = player.armor.equip(key, hp)
        if old is not None:
            self._drop_at_feet(player, old.key, old.hp)
        self._roster_dirty = True
        return armor.SLOTS.index(piece.slot)

    def take_gear(self, player: Player, key: str) -> tuple[int | None, str]:
        """Route one bought or found thing to the container it belongs in.

        THE SHOP AND THE FOREST HAND OVER THE SAME OBJECTS THROUGH THE SAME
        RULES. `loot.ItemDef.pocket` is the only thing that decides where
        something lands, so a table selling a helmet and a cabin dropping one
        cannot disagree about what happens when you already have one.
        """
        item = loot.BY_KEY.get(key)
        if item is not None and item.pocket == "worn":
            return self.wear_armor(player, key), "worn"
        if item is not None and item.pocket == medical.POCKET:
            # THE SAME REFUSAL THE FOREST GIVES: a full belt does not swap a
            # kit away, so `add` returning False is `None` here and `buy`
            # refuses the trade before the balance moves. Without this branch
            # medicine fell through to the belt and the merchant sold a
            # bandage into a GUN CELL — the one route where "the shop is the
            # same rules with a price on them" was not true.
            if not player.medical.add(key):
                return None, medical.POCKET
            slot = next(
                (i for i, held in enumerate(player.medical.slots) if held == key), 0
            )
            return slot, medical.POCKET
        return self.take_weapon(player, key), "hotbar"

    def take_weapon(self, player: Player, key: str, hp: int | None = None) -> int | None:
        """Put a found or bought weapon on the belt. Returns the cell, or None.

        THE ONE DOOR, and it exists because a pickup and a purchase have to
        answer the belt's rules identically — the shop is not a second set of
        rules about what fits where, it is the same belt with a price on it.
        A gun looks for an empty cell and trades if there is none; a lâmina
        goes into the blade cell and displaces whatever was in it.
        """
        if weapons.is_blade(key):
            return self.swap_blade(player, key)
        # A gun goes straight to the hand when there was no gun in it. A
        # BLADE counts as no gun for this: a run opens holding steel, so
        # testing "is the hand empty" would mean nobody's FIRST pickup ever
        # equipped itself, which is the one time this matters most. A second
        # gun does not steal the hand.
        held = player.hotbar.equipped()
        unarmed = held is None or held.melee is not None
        slot = player.hotbar.add(key)
        if slot is None:
            # Belt full: trade whatever is in the hand for this. See
            # `swap_weapon` — refuses unless a GUN is held.
            slot = self.swap_weapon(player, key)
            if slot is None:
                return None
        elif unarmed:
            player.hotbar.held = slot
        # A SHIELD BRINGS ITS DURABILITY WITH IT. The belt cell holds a key
        # and the body holds what is left of the thing — see `Player.shield`
        # — so this is the one join where the two have to be made at the same
        # moment. `hp` carries a second-hand shield's wear through a trade.
        if weapons.is_shield(key):
            player.shield = armor.fresh_shield(key, hp)
        return slot

    def swap_blade(self, player: Player, key: str) -> int | None:
        """Put `key` in the blade cell and leave the old lâmina at the feet.

        THE CELL IS NEVER EMPTY, SO THIS IS NEVER A REFUSAL — it is always a
        trade, and the only thing that can refuse it is picking up the blade
        you are already carrying. That is the whole difference between this
        and a gun cell: a belt with two guns has to be asked which one you
        want to lose, and a belt with one blade does not.

        THE KNIFE IS NOT AN OBJECT AND DOES NOT FALL ON THE FLOOR. It is the
        promise that the cell is full, not a thing the party owns — leaving a
        knife in the grass every time somebody found an axe would litter the
        map with pickups nobody would ever want, and `loot.py` marks it
        `droppable=False` precisely so no pool can produce one. Every other
        lâmina lands at the feet, where its owner can change their mind one
        step later, exactly like a traded gun.
        """
        bar = player.hotbar
        old = bar.blade
        slot = bar.add(key)
        if slot is None:
            return None
        if old != weapons.STARTING_MELEE:
            self._drop_at_feet(player, old)
        # Steel that replaces the steel in your hand stays in your hand. The
        # cell did not move, so neither did the selection — but a player who
        # was holding a GUN keeps holding it, because a pickup that yanked
        # the rifle out of somebody's hands mid-fight to show them a knife is
        # the worst moment this system could produce.
        return slot

    def _drop_at_feet(self, player: Player, key: str, hp: int | None = None) -> str:
        """Put one `key` on walkable ground near `player`. Returns the drop id.

        The tail of every trade: the weapon you gave up lands where you are
        standing rather than in the void, so a trade is reversible one step
        later and experimenting is not punished by eating the loser.
        """
        feet_y = player.y + PLAYER_HALF_HEIGHT
        occupied = [
            (d.x / TILE_SIZE - 0.5, d.y / TILE_SIZE - 0.5) for d in self.drops.values()
        ]
        pos = loot.place_near(self.world.tiles, player.x, feet_y, occupied, random.Random())
        if pos is None:
            pos = (player.x, feet_y)
        drop_id = self._next_drop_id()
        self.drops[drop_id] = Drop(id=drop_id, key=key, x=pos[0], y=pos[1], hp=hp)
        self._loot_dirty = True
        return drop_id

    def swap_weapon(self, player: Player, key: str) -> int | None:
        """Trade the gun in hand for `key`, dropping the old one at the feet.

        The way OUT of a full belt, and it is deliberately narrow: the hand
        has to be holding a GUN. Holding a BLADE refuses — not because the
        lâmina is precious, but because it is not in a gun cell and trading
        it for a rifle would empty the one cell that is never empty. Steel is
        traded for steel, through `swap_blade`. Holstered refuses for the
        same reason it cannot fire: an empty hand is not a choice about which
        gun to keep.

        Returns the slot the new gun landed in, or None if no trade was legal.
        """
        bar = player.hotbar
        held = bar.held
        if held < 0 or held >= weapons.GUN_SLOTS:
            return None
        old = bar.slots[held]
        if old is None or weapons.is_blade(old):
            return None
        # AT MOST ONE SHIELD, EVER, and this is the door that was letting a
        # second one through. `Hotbar.add` refuses them and every pickup goes
        # via it — but a full belt falls through to here, which writes the cell
        # DIRECTLY, so trading a gun away was the one route that bypassed the
        # rule. The durability lives on the body (`Player.shield`, one field),
        # so the second one would have arrived holding the first one's damage.
        # Trading a shield FOR a shield is still fine: the belt count does not
        # change.
        if weapons.is_shield(key) and bar.holds_shield() and not weapons.is_shield(old):
            return None

        bar.slots[held] = key
        # A SHIELD TRADED AWAY TAKES ITS DAMAGE WITH IT. Its durability lives
        # on the body, so handing the object over means handing the number
        # over too — and the wreck of a shield somebody spent half of is
        # exactly what a teammate should find on the floor when they pick it
        # up, not a fresh one.
        worn = player.shield
        if weapons.is_shield(old) and worn is not None and worn.key == old:
            player.shield = None
            self._drop_at_feet(player, old, worn.hp)
        else:
            self._drop_at_feet(player, old)
        return held

    # --- interactive objects: using one, and what falls out -----------------
    def break_crate(self, pid: str, crate_id: str) -> None:
        """Use the object in front of this player — break it, or open it.

        ONE MESSAGE FOR BOTH VERBS. From the input's point of view "use the
        thing I am standing at" is a single intent, and which verb that turns
        out to be is a property of the object rather than of the key: the
        prompt on screen already told the player whether they were about to
        destroy a barrel or open a boot, and a second keybind for the second
        half of that would be a rule the fiction does not have.

        Walk-out is too late. Distance is measured feet to FOOTPRINT — see
        `crates.nearest` — so the rear of a bus is in reach of the rear of a
        bus. Camp maps have no objects. A shot that lands on a BREAK object's
        sprite box does the same work through `smash_crate`.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        crate = self.crates.get(crate_id)
        if crate is None:
            return
        feet_y = player.y + PLAYER_HALF_HEIGHT
        half = crate.type.tiles_w * TILE_SIZE * 0.5
        dx = max(0.0, abs(crate.x - player.x) - half)
        dy = crate.y - feet_y
        if dx * dx + dy * dy > CRATE_BREAK_DIST * CRATE_BREAK_DIST:
            return
        # A TIMED OBJECT OPENS A CHANNEL INSTEAD OF OPENING. Everything else in
        # the game resolves on this frame; the vault asks the player to stand
        # here first — see `crates.ObjectType.open_time`.
        if crate.type.open_time > 0.0:
            self._begin_force(player, crate)
            return
        self.smash_crate(crate, player)

    def _begin_force(self, player: Player, crate: Crate) -> None:
        """Start working on a timed object. Nothing opens on this frame.

        THE NOISE GOES OUT NOW, AND THAT IS THE MECHANIC RATHER THAN A DETAIL.
        A slow open whose noise fired on completion would be a gamble with no
        stake in it — you would hear whether it was worth it before anything
        heard you. Announcing first means the risk is committed before the
        payoff is known, which is the only arrangement under which "do I open
        this now or come back later" is a real question.

        An interrupted force therefore costs the seconds AND the attention of
        everything in earshot, and leaves the object shut. That is the price of
        trying, and it is payable more than once.
        """
        if player.pour is not None or player.using is not None:
            return
        # ONE PAIR OF HANDS PER OBJECT. Two players forcing the same vault
        # would both finish and it would pay twice — the second channel is
        # refused rather than queued, because a player standing next to
        # somebody else's four seconds should go and do something useful.
        if any(
            other.using is not None
            and other.using.kind == USE_CRATE
            and other.using.target == crate.id
            for other in self.players.values()
        ):
            return
        player.using = Use(
            kind=USE_CRATE,
            target=crate.id,
            left=crate.type.open_time,
            total=crate.type.open_time,
        )
        player.vx = player.vy = 0.0
        # `Mãos de Veludo` (`skills.Mods.quiet_hands`) takes the whole stake
        # away. Not a smaller radius — silence — because a quieter announcement
        # is still an announcement, and what the row is buying is the ability to
        # open the loudest object in the game without telling the forest.
        if not player.skills.mods.quiet_hands:
            self.noises.append(
                ai.Noise(
                    x=crate.x, y=crate.y, radius=crate.type.noise, source_id=player.id
                )
            )

    def cancel_force(self, pid: str) -> None:
        """E CAME BACK UP. The vault shuts, and the seconds are spent.

        THE HOLD IS THE POINT. A timed open used to be a press: you committed
        the noise and the seconds and then watched, unable to change your mind
        about a decision the forest had already answered. Holding the key means
        the player can let go the moment something walks into the clearing —
        the stake is still paid (the noise went out at the start, which is the
        whole gamble; see `_begin_force`) and the object is still shut, so
        nothing about the cost changed. What changed is that leaving is now
        something they DO rather than something they wait for.

        ONLY A CRATE. A heal is not a hold — see `_step_use` — and being able
        to abort one on the key that started it would make holding 4 free.
        """
        player = self.players.get(pid)
        if player is None or player.using is None:
            return
        if player.using.kind != USE_CRATE:
            return
        player.using = None

    def _finish_force(self, player: Player, crate_id: str) -> None:
        """The channel completed. Open it exactly as a keypress would have.

        THE SAME DOOR, deliberately: `smash_crate` owns the roll, the ambush,
        the wire row and the noise, and a timed object that resolved through
        its own copy of that would be the place the two drift. What the
        channel changed is WHEN this is called, and nothing else.

        The object is re-read off the room rather than held, because four
        seconds is long enough for the map to have moved on — and an opened
        vault is refused by `smash_crate` anyway, so a race resolves to a miss
        rather than to a double payout.
        """
        crate = self.crates.get(crate_id)
        if crate is None or crate.opened:
            return
        self.smash_crate(crate, player)

    def smash_crate(self, crate: Crate, source: Player | None) -> None:
        """Use an object once: mark it open, roll what was in it, make noise.

        The same path for both verbs, because everything downstream of the
        animation is identical: the object is spent, something or nothing
        falls out, and whatever heard it comes looking. The verb decides two
        things — which sheet the client plays and how loud it was — plus
        whether the ground goes back to floor, because a barrel that came
        apart leaves splinters and an opened car is still parked there.
        """
        if crate.id not in self.crates or crate.opened:
            return
        kind = crate.type
        # IT STAYS ON THE MAP. An opened car is still a car and a searched
        # mailbox is still a mailbox: the object flips to `opened`, holds its
        # last animation frame and refuses every later press. Deleting it was
        # the old behaviour and it read as the forest eating its own scenery
        # one press at a time.
        crate.opened = True
        # Only a BREAK frees its ground. A barrel that came apart leaves
        # splinters you can walk over; a boot that was opened is still a car
        # sitting there, and handing its four tiles back to the floor would
        # let the party walk through the bodywork. Every tile, not one: a
        # vehicle is four wide.
        if kind.verb == VERB_BREAK:
            for tx, ty in crate.cells():
                self.world.set_tile(tx, ty, FLOOR)
            self.navigator.invalidate()
        self.world.crates = [row.to_payload() for row in self.crates.values()]
        self._crates_dirty = True

        # ONE ANNOUNCEMENT PER OBJECT. A timed one already made it, at the
        # START of the channel — that is the whole gamble (see `_begin_force`),
        # and shouting again on completion would both double a very large
        # radius and quietly undo the arrangement: the point is that the risk
        # is committed before the payoff is known.
        if source is not None and kind.open_time <= 0.0:
            self.noises.append(
                ai.Noise(x=crate.x, y=crate.y, radius=kind.noise, source_id=source.id)
            )

        rng = random.Random()
        # `blackout` is the run home: lanterns dead, exit open, ground already
        # swept. An object rolls COINS ONLY from here — putting a fresh bottle
        # back on a map that was just cleared of them would undo `_clear_loot`
        # one boot at a time.
        outcome, item_key, coin_count = crates.roll_drop(
            kind, rng, items=not self.blackout
        )
        # Military-flavoured objects pay ROUNDS instead of an item, and only
        # for a calibre somebody in the room is carrying. Rolled here rather
        # than in `crates.roll_drop` because that module has no idea who is in
        # the room, and "is this box useful to anybody" is the only question
        # ammunition ever asks.
        if outcome == crates.DROP_ITEM and not self.blackout:
            box = ammo.roll_from_object(
                kind.tags, rng, ammo.party_calibres(self.players.values())
            )
            if box is not None:
                item_key = box

        if outcome == crates.DROP_COIN:
            self.drop_coins(crate.x, crate.y, coin_count)
        elif outcome == crates.DROP_ITEM and item_key:
            drop_id = self._next_drop_id()
            self.drops[drop_id] = Drop(
                id=drop_id,
                key=item_key,
                x=(crate.tx + 0.5) * TILE_SIZE,
                y=(crate.ty + 0.5) * TILE_SIZE,
            )
            self._loot_dirty = True

        # AND SOMETIMES SOMEBODY IS STILL IN THE CAR. Rolled after the loot
        # and independent of it, so a boot can hold a medical kit AND a
        # passenger — the two are not alternatives, and the run where both
        # happen is the one the player retells.
        ambushed = False
        if (
            kind.ambush > 0.0
            and self.zone.hostile
            and source is not None
            and rng.random() < kind.ambush
        ):
            ambushed = self._ambush(crate, source)

        self.crate_break_events.append(
            crates.CrateBreak(
                crate.id, crate.kind, crate.x, crate.y, crate.variant, crate.flip,
                outcome, item_key, ambushed,
            ).to_payload()
        )

    def _seed_nests(self) -> None:
        """Stand a pack on every nest the map asked for, before anybody arrives.

        THE ONLY CREATURES IN THE GAME THAT ARE PLACED RATHER THAN SPAWNED.
        Everything else comes out of `EnemyDirector`, which puts groups in a
        ring around a living player — good for pressure, useless for making a
        PLACE dangerous, because the ring follows the party around. A shrine
        has to be guarded whether or not anyone has walked to it yet, or the
        bargain it offers (better loot, worse odds) is a bargain the player
        only finds out about after they have already committed.

        They are dropped in loose and left ALONE: no commit, no alarm. A nest
        that started hunting would walk off its own ground and turn the
        landmark back into an empty clearing before the party ever saw it.

        TWO SIZES, AND THE MAP SAYS WHICH. A count of 0 means "the landmark's
        guard", which is `NEST_PACK` and is the only real fight the map places;
        anything else is a scene that simply kept one or two of its dead
        standing in it (see `mapgen.HAUNT_SCENES`). Those are not a difficulty
        change — they are the answer to "why is this wreck dangerous", and the
        loot inside it stops being a chore the moment there is one.

        AND A FOURTH COLUMN SAYS WHAT. Everything above takes whatever the
        director is already spawning, because the story those scenes tell is
        about people and the people are interchangeable. A DEN is not: the
        scene exists because of the animal in it, so `mapgen.DEN_SCENES` names
        the type key and this is the only place in the game that spawns a
        creature the spawn table has never heard of. It arrives ASLEEP — see
        `spawn_enemy`.
        """
        nests = getattr(self.world, "nests", None)
        if not nests or not self.zone.hostile:
            return
        types = [entry for entry, _ in ai.SPAWN_TABLE]
        if not types:
            return
        rng = random.Random(self.world.seed ^ 0x4E57)
        for row in nests:
            x, y = row[0], row[1]
            asked = row[2] if len(row) > 2 else 0
            named = ENEMY_TYPES.get(row[3]) if len(row) > 3 and row[3] else None
            count = rng.randint(*NEST_PACK) if asked <= 0 else asked
            # A pair standing in a wreck belongs IN the wreck; a shrine's guard
            # has to stay off the altar. Same two numbers, scaled to the group.
            spread = NEST_SPREAD if asked <= 0 else NEST_SPREAD * 0.55
            inner = NEST_INNER if asked <= 0 else 0.6
            if named is not None:
                # A DEN'S OCCUPANT IS THE MIDDLE OF ITS OWN SCENE. Everything
                # else here is scattered because a group standing on one tile
                # is a stack of sprites; there is one of these, the bones are
                # laid denser toward the spot it is lying on, and a miniboss
                # rolled two tiles off centre would be a miniboss asleep in
                # the treeline next to a hollow with nothing in it.
                spread = inner = 0.0

            for _ in range(count):
                angle = rng.uniform(0, math.tau)
                radius = rng.uniform(inner, spread) * TILE_SIZE
                spot = loot.place_near(
                    self.world.tiles,
                    x + math.cos(angle) * radius,
                    y + math.sin(angle) * radius * 0.7,
                    [],
                    rng,
                )
                if spot is None:
                    continue
                self.spawn_enemy(named or rng.choice(types), spot[0], spot[1])

    def _ambush(self, crate: Crate, victim: Player) -> bool:
        """Put one creature on the tile the object was standing on.

        It arrives ALREADY HUNTING the player who opened it. A passenger that
        spawned confused and had to notice them would be a spawn; one that
        comes out of the door swinging is the door being opened.
        """
        types = [entry for entry, _ in ai.SPAWN_TABLE]
        if not types:
            return False
        spot = loot.place_near(
            self.world.tiles, crate.x, crate.y, [], random.Random()
        )
        if spot is None:
            return False
        enemy = self.spawn_enemy(random.choice(types), spot[0], spot[1])
        ai.commit(enemy, victim)
        return True

    # --- extraction: the console, the pour, the quota, the exit -------------
    def activate_rift(self, pid: str, rift_id: str | None = None) -> None:
        """Wake a platform, load a running one, or call the pickup.

        FOUR PRESSES, ONE BUTTON, and which one you get is the pad's state
        and what is in your pocket:

          dormant, nothing else awake   wake it (once only, not reversible).
                                        Green lamps, lit clearing, nothing in
                                        the air and nothing has heard anything.
          dormant, another pad awake    nothing. One at a time.
          open, quota not yet paid      load the pocket toward the quota
          open, quota paid, pads left,
            bag has something           KEEP loading. Everything past the quota
                                        grows the core waiting at the far end.
          open, quota paid, otherwise   CALL THE PICKUP. The lamps go red, the
                                        siren starts, and the whole map comes.

        THE BAG IS WHAT DISAMBIGUATES THE LAST TWO, and it has to be something
        rather than a second key: "carregar além do limite" is only a real
        choice if it is repeatable, and a press that called the pickup the
        instant the quota landed would leave no window to spend at all.
        Reading the pocket gives both: the pad takes everything you have, and
        when you have nothing left to give it, the same press calls it in.

        THE LAST PAD TAKES OVERPAYMENT TOO. It does not hand a core back —
        `_drop_excess` needs a console to carry one to — but it does not need
        to: payout at the end of the night is `sum(fed)`, so everything loaded
        past the quota is banked as gold either way. What the last pad costs
        you is the chance to re-feed the core, not the value.

        Measured from the FEET, the same way collect and smash are, so the
        prompt and the check agree.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        target = self._rift_in_reach(player, rift_id)
        if target is None:
            return
        if target.state == rift.DORMANT:
            if self._awake_rift() is None:
                self._press_console(player, target)
            return
        if target.state == rift.OPEN and target.close_at is None:
            if player.pour is not None:
                return
            if target.ready and player.inventory.bag_value() <= 0:
                self._shut_rift(target)
            else:
                self._begin_pour(player, target)

    def _awake_rift(self) -> Rift | None:
        """The pad currently answering, if any.

        ONE AT A TIME is the rule the whole night hangs off. Three platforms
        awake at once turns a night into an errand list the party splits up and
        does in parallel; one at a time makes it a route, and makes the
        overpayment you carry forward worth carrying.
        """
        for row in self.rifts:
            if row.state in (rift.CHARGING, rift.OPEN):
                return row
        return None

    def _rift_in_reach(self, player: Player, rift_id: str | None) -> Rift | None:
        feet_y = player.y + PLAYER_HALF_HEIGHT
        reach = RIFT_ACTIVATE_DIST * RIFT_ACTIVATE_DIST
        if rift_id:
            for row in self.rifts:
                if row.id != rift_id:
                    continue
                dx = row.console_x - player.x
                dy = row.console_y - feet_y
                if dx * dx + dy * dy <= reach:
                    return row
            return None
        nearest: Rift | None = None
        nearest_d = reach
        for row in self.rifts:
            dx = row.console_x - player.x
            dy = row.console_y - feet_y
            dist = dx * dx + dy * dy
            if dist <= nearest_d:
                nearest = row
                nearest_d = dist
        return nearest

    def _press_console(self, player: Player, target: Rift) -> None:
        target.press()
        self._rift_dirty = True
        # It is LOUD. A lift rotor spinning up in the dark is the largest thing
        # that has happened on this map, and every creature that could hear a
        # crate come apart can hear this — which is the cost of calling for a
        # ride, and the reason the walk to the console is a decision.
        self.noises.append(
            ai.Noise(
                x=target.x,
                y=target.y,
                radius=RIFT_ACTIVATE_DIST * 6.0,
                source_id=player.id,
            )
        )
        self._note_rift_opened(target)

    def _note_rift_opened(self, target: Rift) -> None:
        """Extract ticks on the console press, not on walking nearby.

        That is when the load row appears: the platform is turning, and its
        quota is now the job. Standing in the clearing is not enough.
        """
        if not target.found:
            target.found = True
        quest = next((q for q in self.quests if q.id == quests.EXTRACT), None)
        if quest is None:
            self.offer_extract_quest()
        else:
            quest.have = min(quest.need, sum(1 for row in self.rifts if row.found))
            quest.done = quest.have >= quest.need
            self._quests_dirty = True
        self.offer_feed_quest(target)

    def _begin_pour(self, player: Player, target: Rift) -> None:
        """Start the ceremony. Nothing is spent on this frame.

        THE PRESS NO LONGER PAYS THE PAD — it sends the body to do it. What
        used to be one call that emptied the pocket into a counter is now a few
        seconds of somebody walking up to a machine, taking their pack off,
        turning it over and tipping a night's work into it. The value moves one
        item at a time in `_tip_item`, so the number on the HUD and the sprites
        on the deck are the same event and cannot disagree.

        THERE IS NO CEILING. The press empties the bag, every time, whether
        that lands under the quota, exactly on it, or a long way past it. A
        pour that stopped on the bill was the one interaction in the game that
        did less than the player asked for: you walked a night's haul to the
        machine, pressed the one button there is, and were left standing at it
        still carrying half of it. Overshoot is not a mistake to be protected
        from — it is the only way to grow the core waiting at the far end.
        """
        if player.inventory.bag_value() <= 0:
            return
        player.pour = Pour(
            rift_id=target.id,
            phase=POUR_WALK,
            left=rift.POUR_WALK_MAX,
            x=target.deck_x,
            y=target.deck_y + rift.POUR_STAND * TILE_SIZE,
        )
        # One noise for the whole pour, thrown when it starts. A pad being
        # loaded is a crate being emptied into an iron box and it carries; one
        # per item would be the same event reported twenty times.
        self.noises.append(
            ai.Noise(
                x=target.x,
                y=target.y,
                radius=RIFT_ACTIVATE_DIST * 3.0,
                source_id=player.id,
            )
        )

    # --- medicine: the only way health comes back ---------------------------
    def use_medical(self, pid: str, slot: int) -> None:
        """Start spending one medical cell. Nothing is consumed on this frame.

        THE COST OF A HEAL IS WHERE YOU ARE STANDING, NOT WHAT IT COSTS. Every
        other resource in this game is spent by pressing a key; medicine is
        spent by being still, in the open, for seconds, unable to answer
        anything that walks up. That is the entire design of the verb — a
        medkit resolved on the keypress would be a second health bar, and a
        player would top up mid-fight and never think about it again.

        REFUSED AT FULL HEALTH. Not out of tidiness: with a handful of cells,
        a kit spent for nothing is a large slice of the night's medicine gone
        to a mis-key, and on a permanent run that is a real loss to hand somebody
        for pressing 4 while distracted.
        """
        player = self.players.get(pid)
        if player is None or not player.alive or player.downed:
            return
        if player.pour is not None or player.using is not None:
            return
        # NOT MID-ARRIVAL AND NOT MID-DEPARTURE. Both puppet the body already,
        # and a channel started under a cinematic would resolve into a zone the
        # player has left.
        if self.departing or self.arriving:
            return
        key = player.medical.peek(slot)
        if key is None:
            return
        kit = medical.BY_KEY.get(key)
        if kit is None:
            return
        if player.hp >= player.max_hp:
            return
        player.using = Use(kind=USE_HEAL, slot=slot, left=kit.use_time, total=kit.use_time)
        player.vx = player.vy = 0.0

    def heal_player(
        self,
        target: Player,
        amount: int,
        source: Player | None = None,
        key: str | None = None,
    ) -> int:
        """Put health back into a body. THE ONE DOOR, exactly as damage has one.

        There used to be no door because there was only one caller: a medical
        channel finishing, in `_step_use`, which wrote `player.hp` directly.
        `AGENTS.md` recorded that as a rule — *health comes back in exactly one
        place, once* — and the rule was always about the DOOR rather than about
        medicine. There are two sources now (a kit, and the field gun) and
        there will be a third the moment somebody adds a shrine, so the door is
        a method instead of a coincidence.

        WHAT DID NOT CHANGE, and it is the important half: there is still no
        regeneration, still no heal on extraction, and still nothing that
        happens to a body on its own. Every point of health in this game is
        something a person spent something to give it.

        A DOWNED BODY IS NOT HEALED. Nothing brings one back but the party
        reaching the next zone (`_check_wipe` is built on that), and a heal
        that stood somebody up would quietly delete permadeath — which is the
        thing every other system in this game is balanced against.

        Returns what actually landed, which is what the charge is billed on:
        topping somebody up from 99 must not be worth the same as catching
        them at 10.
        """
        if amount <= 0 or not target.alive or target.downed:
            return 0
        before = target.hp
        target.hp = min(target.max_hp, target.hp + amount)
        healed = target.hp - before
        if healed <= 0:
            return 0
        self._roster_dirty = True
        # THE JUICE, and it is an event rather than a state for the same reason
        # every other ceremony here is: the bar moving is a fact anybody can
        # read off the roster, and the flash, the sound and the number floating
        # off the body are a thing that HAPPENED and must never be replayed by
        # a client that missed a packet.
        self.heal_events.append(
            {
                "id": target.id,
                "k": key,
                "hp": healed,
                "x": round(target.x, 1),
                "y": round(target.y, 1),
            }
        )
        if source is not None:
            held = source.hotbar.equipped()
            if held is not None:
                self._charge_ult(source, held, ultimates.CHARGE_HEAL, healed)
        return healed

    def _step_use(self, player: Player, dt: float) -> None:
        """Run the clock, and spend the cell on the LAST frame and only there.

        THIS IS THE ONE PLACE A USE DIFFERS FROM A POUR AND IT IS THE
        IMPORTANT ONE. A pour spends as it goes, so being interrupted still
        costs you what already left the bag — that is fair, because the only
        thing that interrupts a pour is being hit while standing at a machine
        you chose to stand at. A heal is different: what interrupts it is the
        thing you were healing because of. Taking the kit AND the health for
        that would be punishing the player twice for one mistake, so an
        interrupted heal costs the seconds and keeps the item.

        `damage_player` clears `using` outright, so there is no cancellation
        branch here — being hit is the only interruption there is.
        """
        use = player.using
        if use is None:
            return
        player.vx = player.vy = 0.0
        use.left -= dt
        if use.left > 0.0:
            return
        player.using = None
        # THE ONLY THING THE KIND DECIDES IS WHAT THE LAST FRAME DOES. Every
        # other rule about a channel — the puppet, the clock, the cancel, the
        # ring on the client — is the same for both and is written once above.
        if use.kind == USE_CRATE:
            self._finish_force(player, use.target)
            return
        key = player.medical.take(use.slot)
        kit = medical.BY_KEY.get(key or "")
        if kit is None:
            return
        # THROUGH THE ONE DOOR. A kit does not get to write `hp` itself any
        # more — see `heal_player` — because it is no longer the only source.
        # `source` is None: healing yourself must not charge anybody's
        # ultimate, or the medic build would be "stand still and press 4".
        self.heal_player(player, kit.heal, source=None, key=key)

    def _puppet_inputs(self, player: Player) -> bool:
        """Ack everything, obey nothing — and report a MOVEMENT key.

        The body is a puppet for the length of a channel, but the queue still
        has to drain and the sequence still has to be acked, or the client's
        prediction never hears back and walks off on its own.

        THE RETURN VALUE IS ONLY MEANINGFUL TO A POUR. Walking away ends a
        pour and nothing ends a heal but being hit (see `_step_use`), so the
        two callers read this differently and the difference is deliberate:
        what a heal costs you is the seconds, and a heal you could abort for
        free the instant something appeared would have no cost at all.

        A POUR IS INTERRUPTIBLE AND THIS IS WHERE IT BECOMES SO. It was not,
        and the argument for that was real — a load undone by somebody leaning
        on W while watching the deck is the most expensive verb in the game
        lost to the key held down more than any other. What that argument
        missed is the FOREST. The pour is several seconds standing at a lit
        machine with a siren's worth of noise already thrown, which is exactly
        when something arrives; a player who could see it coming and could not
        step off the mark was not making a decision, they were watching one be
        made for them. The commitment is still real because the pour SPENDS AS
        IT GOES — walking away costs you nothing you have not already banked,
        and it does not give the bag back either.
        """
        walked = False
        for cmd in player.inputs:
            if cmd.up or cmd.down or cmd.left or cmd.right:
                walked = True
            player.last_processed_seq = cmd.sequence
            player.last_input = cmd
        player.inputs.clear()
        return walked

    def _step_pour(self, player: Player, dt: float) -> None:
        """Run one body's pour a tick further.

        Four beats, and each one hands to the next: WALK up to the mark in
        front of the deck, LIFT the pack off the back and turn it over, DUMP
        one item every `POUR_BEAT` until the BAG runs out — there is no bill to
        stop on — then STOW the pack again. The client draws all four off
        `Player.pour.phase` and runs its own clock inside whichever it is in.
        """
        pour = player.pour
        if pour is None:
            return
        target = next((row for row in self.rifts if row.id == pour.rift_id), None)
        # The pad launched, or went out from under them. Nothing to pour into.
        if target is None or target.state != rift.OPEN or target.close_at is not None:
            player.pour = None
            return

        player.vx = 0.0
        player.vy = 0.0
        # `apply_input` is skipped for a puppet, and it is what normally ticks
        # the breath — so the pour refills it here. Three seconds standing at a
        # skid is exactly the moment a bar that only refills in the simulation
        # loop would visibly freeze.
        step_stamina(player, False, False, dt)
        # Face the deck for the whole ceremony. A body tipping a bag out over
        # its own shoulder is the one thing that would make this read as a bug.
        dx = target.deck_x - player.x
        dy = target.deck_y - (player.y + PLAYER_HALF_HEIGHT)
        span = math.hypot(dx, dy)
        if span > 1e-3:
            player.aim_x = dx / span
            player.aim_y = dy / span
        pour.left -= dt

        if pour.phase == POUR_WALK:
            if self._walk_to_mark(player, pour, dt) or pour.left <= 0.0:
                pour.phase = POUR_LIFT
                pour.left = rift.POUR_LIFT
            return
        if pour.phase == POUR_LIFT:
            if pour.left > 0.0:
                return
            pour.phase = POUR_DUMP
            pour.left = 0.0
            # Falls THROUGH to the dump on the same tick: the first item leaves
            # on the frame the bag finishes turning over, not a beat after it.
        if pour.phase == POUR_DUMP:
            while pour.left <= 0.0:
                if not self._tip_item(player, target):
                    pour.phase = POUR_STOW
                    pour.left = rift.POUR_STOW
                    return
                pour.left += rift.POUR_BEAT
            return
        if pour.left <= 0.0:
            player.pour = None

    def _walk_to_mark(self, player: Player, pour: Pour, dt: float) -> bool:
        """Step toward the drop mark. True once standing on it.

        Driven through `world.move_axis` like every other body in the game, so
        the walk cannot post the player through the skid's own tiles if the
        mark ends up on the far side of something.
        """
        feet_y = player.y + PLAYER_HALF_HEIGHT
        dx = pour.x - player.x
        dy = pour.y - feet_y
        span = math.hypot(dx, dy)
        if span <= 1.0:
            return True
        mods = player.skills.mods
        speed = MOVE_SPEED * mods.speed * carry_scale(player.carry_weight, mods.carry)
        step = min(span, speed * dt)
        player.vx = dx / span * speed
        player.vy = dy / span * speed
        player.x = self.world.move_axis(
            player.x, player.y, PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT,
            dx / span * step, 0,
        )
        player.y = self.world.move_axis(
            player.x, player.y, PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT,
            dy / span * step, 1,
        )
        return False

    def _tip_item(self, player: Player, target: Rift) -> bool:
        """One item out of the bag and onto the deck. False when the bag is out.

        This is the whole transaction, one unit at a time: the pocket loses it,
        the pad gains its value, the deck's pile grows by one, and the event
        goes out so every client can watch the same sprite fall into the same
        place. `n` is the pile index and it is the server's, because two
        players watching one pour have to see one pile.
        """
        slot = player.inventory.tip_one()
        if slot is None:
            return False
        # THE HAUL SKILLS PAY HERE AND NOWHERE ELSE. What a scavenger's eye is
        # worth is what the platform credits for the thing he loaded, not what
        # the catalog says it is: the bag, the tooltip and the drop on the
        # ground all keep saying the honest number, and the bonus shows up as
        # the quota filling faster than the pocket emptied. A skill that
        # rewrote the item's value would have to rewrite it in five places and
        # would make two players carrying the same ring disagree about it.
        value = round(slot.unit_value() * player.skills.mods.haul)
        target.feed(value)
        row = {
            "by": player.id,
            "r": target.id,
            "k": slot.key,
            "v": value,
            "n": target.cargo,
            "x": round(player.x, 1),
            "y": round(player.y + PLAYER_HALF_HEIGHT, 1),
        }
        # A condensed core carries its own drawn size, and it has to land on
        # the deck at the size it was lying in the grass at.
        if slot.scale is not None:
            row["s"] = round(slot.scale, 2)
        self.pour_events.append(row)
        target.cargo += 1
        self._rift_dirty = True
        self._roster_dirty = True
        self._sync_feed_quest(target)
        return True

    def _shut_rift(self, target: Rift) -> None:
        """A paid pad, launched by hand. Starts the lift; banks the overpayment.

        The DROP is not made here — it is made when the skid is actually gone
        (`step_rift`), because the core is what did not fit aboard and it has
        to land on ground the party can see it land on.
        """
        if not target.begin_collapse():
            return
        self._rift_dirty = True
        self.world.rifts = [row.geometry_payload() for row in self.rifts]
        self._drop_feed_quest()
        if self._all_pads_shut():
            self._close_extraction()

    def _all_pads_shut(self) -> bool:
        """Every pad on the map either gone or already climbing away."""
        return all(
            row.state == rift.SPENT or row.close_at is not None
            for row in self.rifts
        )

    def _pads_left(self) -> bool:
        """Another console still waiting to be found — "faltam extrações".

        DORMANT is the test, not "not spent": a pad that is awake is the one
        being worked on and a pad that is lifting is finished with. What this
        answers is whether there is anywhere left to carry a core to, which is
        the only thing the core exists for.
        """
        return any(row.state == rift.DORMANT for row in self.rifts)

    def _sync_feed_quest(self, target: Rift) -> None:
        """Mirror one pad's meter onto the HUD row.

        `have` is allowed PAST `need` and the row stays done — that overshoot
        is the whole reason to keep feeding, and clamping it would hide the
        only number that says how big the core is going to be.
        """
        quest = next((q for q in self.quests if q.id == quests.FEED), None)
        if quest is None:
            return
        quest.have = target.fed
        quest.need = target.need
        quest.done = target.fed >= target.need
        self._quests_dirty = True

    def _drop_feed_quest(self) -> None:
        """Take the feed row off the HUD. The next pad puts a fresh one up."""
        before = len(self.quests)
        self.quests = [q for q in self.quests if q.id != quests.FEED]
        if len(self.quests) != before:
            self._quests_dirty = True

    def _drop_excess(self, target: Rift) -> None:
        """Pay the overpayment back as ONE object, on the ground by the console.

        Four slots of loot condensed into one you carry to the NEXT console, at
        a weight that makes carrying it a real cost. That is the whole of what
        it is for, which is why it only exists while there is a next console:
        with no pad left to explore the party is walking out, and a core would
        be a souvenir rather than a decision.

        `Room.activate_rift` is the other half of that rule. On the last pad it
        stops offering to keep loading at all, because saturating a platform
        that cannot pay you back is a way to lose a full bag to a keypress.
        """
        value = target.excess
        target.excess = 0
        if value <= 0 or not self._pads_left():
            return
        worth, kg, scale = loot.shard_stats(value)
        # IN THE MIDDLE OF THE IMPRINT, on the ground the platform was sitting
        # on. This is the thing that did not fit aboard, so it lands in the
        # hole the skid left rather than being scattered onto some walkable
        # tile near the console like a dropped bag. Those tiles were handed
        # back to the floor by `_free_deck` seconds ago, so the exact point is
        # legal; `place_near` is only the fallback for a map that somehow is
        # not.
        pos: tuple[float, float] | None = (target.x, target.y)
        tx = int(target.x // TILE_SIZE)
        ty = int(target.y // TILE_SIZE)
        tiles = self.world.tiles
        if not (0 <= ty < len(tiles) and 0 <= tx < len(tiles[0]) and tiles[ty][tx] == FLOOR):
            occupied = [
                (drop.x / TILE_SIZE - 0.5, drop.y / TILE_SIZE - 0.5)
                for drop in self.drops.values()
            ]
            pos = loot.place_near(tiles, target.x, target.y, occupied, random.Random())
        if pos is None:
            pos = (target.x, target.y)
        drop_id = self._next_drop_id()
        self.drops[drop_id] = Drop(
            id=drop_id, key=loot.SHARD_KEY, x=pos[0], y=pos[1],
            value=worth, weight=kg, scale=scale,
        )
        self._loot_dirty = True

    def _close_extraction(self) -> None:
        """Every pad gone: the exit opens and the night hunts.

        The pads are already climbing away on their own clocks — this does not
        touch them. What it does is the map-level consequence, and it is the
        one moment in a run where the world changes shape around the party.
        """
        for row in self.rifts:
            if row.state == rift.DORMANT and row.begin_collapse():
                self._rift_dirty = True
        self.world.rifts = [row.geometry_payload() for row in self.rifts]
        self._open_egress()
        self._begin_blackout()
        self._clear_loot()
        self.offer_exit_quest()

    def _clear_loot(self) -> None:
        """Sweep every drop still lying on this map. The run home is a RUN.

        Extraction is what loot was FOR. Once the last pad is shut there is no
        console left to feed and nothing to spend a find on, so a bottle in the
        grass on the way out is a reason to stop moving with the whole pack
        hunting — a decision the game is offering the player where the honest
        answer is always "no". Taking them off the map turns the last leg into
        the one thing it should be, which is a sprint.

        This runs BEFORE the last pad reaches SPENT, and that is safe rather
        than lucky: a pad only pays out a condensed core while another console
        is still waiting (`_drop_excess`), so the final platform never drops
        one into a map that was just cleared.
        """
        if not self.drops:
            return
        self.drops.clear()
        self._loot_dirty = True

    def _open_egress(self) -> None:
        if self.egress is not None:
            return
        avoid = self.gate.side if self.gate is not None else None
        if self.zone.kind == zones.KIND_ARENA:
            # THE YARD'S WAY OUT IS OPPOSITE ITS WAY IN, and it has to be
            # joined to the ring by hand — see `arena.open_far_exit`. Every
            # other map is happy with a random edge.
            opened = arena.open_far_exit(self.world, self.gate)
        else:
            opened = entrance.open_exit(self.world.tiles, self.world.seed, avoid)
        if opened is None:
            return
        gate, patches = opened
        self.egress = gate
        self.world.egress = gate.geometry_payload()
        self._tile_patches.extend(patches)
        self._egress_dirty = True
        self.navigator.invalidate()

    def _begin_blackout(self) -> None:
        if self.blackout:
            return
        self.blackout = True
        self.panic = True
        self._blackout_dirty = True
        for player in self.players.values():
            player.last_input.lantern = False

    # --- the shop: the stalls and the upgrade machine -----------------------
    def buy(self, pid: str, stand_id: str | None = None) -> None:
        """Take the gun off a table and the price off the party's balance.

        The mirror of `collect_loot`, and deliberately so: a bought weapon
        lands on the belt through the same two rules a found one does — it
        arms an empty hand, and a full belt TRADES rather than refuses,
        leaving the old gun on the floor of the shop where its owner can
        pick it back up if they change their mind one step later.

        THE STAND SELLS ONCE. It is a specific weapon lying on a specific
        table, not a shelf with stock behind it, so the table is empty
        afterwards and the party can see at a glance what they have already
        taken. Two players cannot both buy it: `sold` is checked and set on
        the same tick, and the tick is the server's.

        Measured from the FEET, like every other E in the game.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind != zones.KIND_STORE:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        box = self._box_in_reach(player, stand_id)
        if box is not None:
            self._buy_ammo(player, box)
            return
        target = self._stand_in_reach(player, stand_id)
        if target is None or target.sold:
            return
        if target.price > self.balance:
            return

        # THE SAME DOOR A PICKUP USES. A refused trade must not charge for a
        # thing that was never handed over, which is why this is tested
        # before the balance moves.
        slot, dest = self.take_gear(player, target.key)
        if slot is None:
            return

        self.balance -= target.price
        # A GUN COMES LOADED. The merchant is the only source of firearms in
        # the game, so a purchase that handed over an empty weapon would ask
        # the party to survive a night before the thing they just spent the
        # last night earning does anything at all. A lâmina eats nothing and
        # `grant_for` knows it.
        player.ammo.grant_for(target.key)
        target.sold = True
        self._balance_dirty = True
        self._stands_dirty = True
        self._roster_dirty = True
        self._sync_store_payload()
        row = {
            "id": target.id,
            "by": player.id,
            "k": target.key,
            "price": target.price,
            "slot": slot,
            "x": round(target.x, 2),
            "y": round(target.y, 2),
        }
        # Omitted for the belt, which is what most tables sell — the same
        # trade `LootPickup` makes with the pocket.
        if dest != "hotbar":
            row["dest"] = dest
        self.buy_events.append(row)

    def _sync_spins(self, player: Player) -> int:
        """Pay out any levels this player has crossed. Returns how many.

        Called wherever xp moves rather than once a tick, because a level is a
        thing the player should hear land — the client reads the count off the
        roster and the level-up chime is what tells somebody in the middle of a
        fight that there is a pull waiting for them at the shop.
        """
        level, _, _ = level_progress(player.xp)
        gained = player.skills.sync_level(level)
        if gained:
            self._roster_dirty = True
        return gained

    @property
    def spin_price(self) -> int:
        """What the next BOUGHT pull costs, in party gold.

        `STORE_SPIN_PRICE` doubled once per purchase already made tonight. It
        is derived rather than stored so there is one number and one place it
        can be wrong, and it is exponential rather than linear because the
        thing being sold has no ceiling: a flat price would make the last hour
        of a rich night a queue at the lever until the balance ran out, which
        turns a roll into a vending machine. Doubling means the party always
        gets to buy one more and never gets to buy five.
        """
        return STORE_SPIN_PRICE << self._spins_bought

    @property
    def reroll_price(self) -> int:
        """What the next reroll of the merchant's tables costs, in party gold.

        `spin_price`'s shape, copied on purpose rather than re-derived: the two
        are the same argument about the same kind of purchase — something with
        no ceiling, sold repeatedly, inside one visit — and having one of them
        be linear would be an accident nobody could defend afterwards.

        Doubling means the party always gets to reroll one more time and never
        gets to reroll five. A flat price would make a rich night a queue at
        the merchant until the balance ran out, which turns a shelf into a
        vending machine — the exact failure `spin_price` names.
        """
        return STORE_REROLL_PRICE << self._rerolls_bought

    def reroll(self, pid: str) -> None:
        """Buy a new shelf. The tables stay; what is on them changes.

        THE MIRROR OF `spin`, down to the refusals being silent. Standing too
        far away, being broke, being on the wrong map — the client already
        knows all three and says so locally, and a server that answered them
        would be answering a question it cannot see the player asking.

        A SOLD TABLE STAYS SOLD (`store.reroll_stands`). Without that, the
        correct play is to buy the cheapest thing on the shelf and reroll until
        the shop has paid for itself, which makes the merchant a machine for
        turning gold into more gold.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind != zones.KIND_STORE:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        if not self.stands:
            return
        # NOTHING LEFT TO REROLL IS A REFUSAL, not a purchase. A party who
        # bought the whole shelf pressing this would pay for a shuffle of
        # nothing, and the one thing a price ladder must never do is charge for
        # an outcome the game already knows is empty.
        if all(stand.sold for stand in self.stands):
            return
        price = self.reroll_price
        if self.balance < price:
            return
        # AT THE MERCHANT, not at the cabinet. It is HIS stock — the machine
        # sells skills and he sells objects, and a party pressing one lever for
        # both would have no idea which of the two they were bargaining with.
        # It also puts the reroll where the party is already standing when they
        # decide they do not like the shelf.
        spot = self._merchant_spot()
        if spot is None:
            return
        # Measured from the FEET, like every other press in this room.
        feet_y = player.y + PLAYER_HALF_HEIGHT
        if math.hypot(player.x - spot[0], feet_y - spot[1]) > STORE_SPIN_DIST:
            return

        self.balance -= price
        self._balance_dirty = True
        self._rerolls_bought += 1
        self._reroll_price_dirty = True
        store.reroll_stands(self.stands, self.day, random.Random())
        self._stands_dirty = True
        self.reroll_events.append(
            {"by": pid, "cost": price, "x": round(spot[0], 1), "y": round(spot[1], 1)}
        )

    def _merchant_spot(self) -> tuple[float, float] | None:
        """Where the trader is standing, or None off the shop map."""
        row = (self.world.store or {}).get("merchant")
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return None
        return float(row[0]), float(row[1])

    def _machine_spot(self) -> tuple[float, float] | None:
        """Where the cabinet is standing, or None off the shop map."""
        row = (self.world.store or {}).get("machine")
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return None
        return float(row[0]), float(row[1])

    def spin(self, pid: str) -> None:
        """Pull the lever. Spend one level, take one skill.

        THE ROLL HAPPENS NOW AND THE SHOW HAPPENS AFTER. Everything the client
        is about to spend four seconds on — the arm, the reels, which one stops
        late, the colour of the canister — is decided on this frame and shipped
        as one row. The alternative is a machine whose result arrives at
        snapshot rate somewhere in the middle of its own animation, which is
        how a reel ends up visibly changing its mind.

        REFUSALS ARE SILENT HERE AND LOUD ON THE CLIENT. Standing too far away,
        having no spin left, or arriving while somebody else's pull is still
        running are all things the HUD already knows — the prompt says which —
        so a packet that would be dropped is not sent, and one that slips
        through a race simply does nothing.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind != zones.KIND_STORE:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        # A LEVEL FIRST, GOLD ONLY WHEN THERE IS NO LEVEL LEFT. The banked
        # pull is never skipped in favour of a paid one — nobody would ever
        # choose to pay while holding a free spin, so making them press twice
        # to say so would be a menu.
        price = 0 if player.skills.spins > 0 else self.spin_price
        if price > self.balance:
            return
        spot = self._machine_spot()
        if spot is None:
            return
        feet_y = player.y + PLAYER_HALF_HEIGHT
        dx = spot[0] - player.x
        dy = spot[1] - feet_y
        if dx * dx + dy * dy > STORE_SPIN_DIST * STORE_SPIN_DIST:
            return
        if self._machine_busy > 0.0:
            return

        rolled = skills.roll(random.Random(), player.skills.stacks)
        # CHARGED AFTER THE LAST REFUSAL, like every other purchase in the
        # shop: a pull that does not happen must not cost anything, and the
        # ladder must not climb for it either.
        if price:
            self.balance -= price
            self._spins_bought += 1
            self._balance_dirty = True
            self._spin_price_dirty = True
        else:
            player.skills.spins -= 1
        held = player.skills.add(rolled.key)
        # A slot skill has to actually widen the bag, and it has to do it here
        # rather than in `flatten`: `Mods` is a value and the pocket is state.
        player.inventory.grow(INVENTORY_SLOTS + player.skills.mods.slots)
        # More health means more health NOW, not after the next respawn — a
        # ceiling that only applied tomorrow would make the tile lie for a
        # whole night. Only the ceiling moves; a hurt player stays hurt.
        player.hp = min(player.hp + max(0, player.skills.mods.max_hp - MAX_HP), player.max_hp)
        self._machine_busy = machine.duration(rolled.rarity)
        self._roster_dirty = True
        row = {
            "by": player.id,
            "k": rolled.key,
            "r": rolled.rarity,
            # Copies held AFTER this one. The HUD tile counts to it, and a
            # pull past the cap still counts — see `skills.Loadout.add`.
            "n": held,
            "left": player.skills.spins,
            "x": round(spot[0], 1),
            "y": round(spot[1], 1),
        }
        # Present only on a BOUGHT pull, the same way `dest` is only on a buy
        # that missed the belt: it is what the party paid, and it is what lets
        # the cabinet read as a till rather than as a reward.
        if price:
            row["cost"] = price
        self.spin_events.append(row)

    def _sync_ammo_boxes(self) -> None:
        """Put a crate on the wall for every calibre the party is carrying.

        RUN EVERY TICK OF A STORE VISIT, and it is five set lookups over a
        handful of belts — cheaper than the alternative, which is remembering
        to call it from every place a weapon can change hands. A gun is bought,
        traded at a full belt, dropped, picked back up off the floor or walked
        in by somebody who joined late, and all five have to put shells on the
        wall; a hook on `buy` alone would have covered exactly one of them.

        MONOTONIC WITHIN A VISIT — see `_boxes_seen`. The set only ever grows
        while the party is in the shop, because a purchase that trades away the
        gun you were holding briefly removes its calibre from the room, and a
        crate that blinked out on the frame you bought something reads as the
        shop taking it back.
        """
        if self.zone.kind != zones.KIND_STORE:
            return
        carried = ammo.party_calibres(self.players.values())
        fresh = carried - self._boxes_seen
        if not fresh:
            return
        self._boxes_seen |= fresh
        self.ammo_boxes = store.ammo_boxes(self.world.width, self._boxes_seen)
        self._boxes_dirty = True
        self._sync_store_payload()

    def _buy_ammo(self, player: Player, box: store.AmmoBox) -> None:
        """Buy one crate-load of rounds. The crate stays; the reserve fills.

        THREE REFUSALS AND THEY ARE THE SAME THREE A BOX ON THE FOREST FLOOR
        HAS, plus the price. You must be carrying a gun that eats the calibre
        (`ammo.carried_by`, the collecting player's OWN belt — the rifle rounds
        belong to whoever brought the rifle, and that rule does not stop being
        true because there is a merchant standing there); a reserve already at
        its cap refuses, because `Reserve.add` returning zero is what a full
        player looks like everywhere else in this game; and the party has to be
        able to cover it.

        A PARTIAL FILL IS A FULL PRICE. Buying a box with four rounds of room
        left hands over four rounds and charges for the crate — the same trade
        as picking a box up off the floor at 236 of 240, which also throws the
        rest away. Pro-rating it would mean a price that changed depending on
        how empty you were, which is a second price on the same wall.
        """
        if box.price > self.balance:
            return
        if box.calibre not in ammo.carried_by(player.hotbar):
            return
        if player.ammo.add(box.calibre, box.rounds) <= 0:
            return
        self.balance -= box.price
        self._balance_dirty = True
        self._roster_dirty = True
        # The cell holding the gun this just fed. No slot is spent — rounds
        # take none — but the client flies the box at the weapon it topped up,
        # exactly as it does for a box collected off the ground.
        slot = next(
            (
                index
                for index, key in enumerate(player.hotbar.slots)
                if ammo.calibre_of(key) == box.calibre
            ),
            0,
        )
        self.buy_events.append(
            {
                "id": box.id,
                "by": player.id,
                "k": box.key,
                "price": box.price,
                "slot": slot,
                "dest": "ammo",
                "n": box.rounds,
                "x": round(box.x, 2),
                "y": round(box.y, 2),
            }
        )

    def _box_in_reach(self, player: Player, stand_id: str | None) -> store.AmmoBox | None:
        """The crate this press named, if the player is standing at it.

        BY ID ONLY. Every other fixture in the shop resolves the nearest thing
        in range when the client names nothing, and a crate deliberately does
        not: the client always sends the id of the prompt it is showing, and
        falling through to "the nearest crate" would let a press meant for a
        table spend money on rounds.
        """
        if stand_id is None:
            return None
        feet_y = player.y + PLAYER_HALF_HEIGHT
        for box in self.ammo_boxes:
            if box.id != stand_id:
                continue
            dx = box.x - player.x
            dy = box.y - feet_y
            if dx * dx + dy * dy <= STORE_BUY_DIST * STORE_BUY_DIST:
                return box
            return None
        return None

    def _stand_in_reach(self, player: Player, stand_id: str | None) -> Stand | None:
        feet_y = player.y + PLAYER_HALF_HEIGHT
        reach = STORE_BUY_DIST * STORE_BUY_DIST
        nearest: Stand | None = None
        nearest_d = reach
        for row in self.stands:
            if stand_id is not None and row.id != stand_id:
                continue
            dx = row.x - player.x
            dy = row.y - feet_y
            dist = dx * dx + dy * dy
            if dist <= nearest_d:
                nearest = row
                nearest_d = dist
        return nearest

    def _sync_store_payload(self) -> None:
        """Write the tables back onto the map, so a late join sees the gaps."""
        if not self.world.store:
            return
        self.world.store["stands"] = [row.to_payload() for row in self.stands]
        # The crates go back on the map for the same reason the tables do: a
        # player who joins mid-visit gets the room as it stands, wall included.
        self.world.store["boxes"] = [box.to_payload() for box in self.ammo_boxes]

    # --- the bag back onto the ground ---------------------------------------
    def drop_loot(self, pid: str, slot: int) -> None:
        """Toss a bag slot onto the ground near this player's feet.

        Camp has none, and the walk-out is too late. A stack becomes one
        world drop per unit — the ground list has no quantity. Placement
        is walkable floor around the feet; the server picks the tiles.

        The SHOP refuses too, and for a different reason than the camp: there
        is nothing to pick a dropped relic back up for. The corridor is one
        walk in one direction and the map is gone at the end of it, so a bag
        emptied onto the boards is a bag deleted with a ceremony. Note this
        does not cover a GUN traded out from under the hand at a table — that
        one lands on the floor on purpose, so a purchase stays reversible for
        as long as the party is still standing there.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing or self.arriving:
            return
        if self.zone.kind in (zones.KIND_CAMP, zones.KIND_STORE):
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        taken = player.inventory.take(slot)
        if taken is None:
            return
        feet_y = player.y + PLAYER_HALF_HEIGHT
        occupied = [
            (drop.x / TILE_SIZE - 0.5, drop.y / TILE_SIZE - 0.5)
            for drop in self.drops.values()
        ]
        rng = random.Random()
        for _ in range(taken.qty):
            pos = loot.place_near(self.world.tiles, player.x, feet_y, occupied, rng)
            if pos is None:
                pos = (player.x, feet_y)
            px, py = pos
            occupied.append((px / TILE_SIZE - 0.5, py / TILE_SIZE - 0.5))
            drop_id = self._next_drop_id()
            # Whatever the slot was carrying goes back on the ground with it.
            # A core tossed out of the bag has to still be worth what it was
            # worth, or dropping one would launder it into a catalog default.
            self.drops[drop_id] = Drop(
                id=drop_id, key=taken.key, x=px, y=py,
                value=taken.value, weight=taken.weight, scale=taken.scale,
            )
        self._loot_dirty = True
        self._roster_dirty = True

    # --- the wipe: the one way a run ends -----------------------------------
    def _check_wipe(self) -> None:
        """Is anybody still standing? If not, the run is over.

        ONE RULE FOR SOLO AND CO-OP, and that is the whole reason it is written
        as a count rather than as two branches. A death DOWNS a body; a run
        ends when the party has nobody left up. Alone, those are the same
        frame — you are the whole party, so going down is wiping. With company,
        a body on the floor is a clock on everyone still walking: they can
        finish the night and carry it out, and the pressure that creates is the
        kind a co-op game should get from its own players rather than from a
        number in the corner of the screen.

        NON-HOSTILE ZONES CANNOT WIPE A PARTY. Nothing in the camp or the shop
        downs anybody in the first place (`damage_player` respawns there), so
        the guard is belt-and-braces — but it also means a room sitting in the
        lobby with no players cannot trip this on an empty `values()`.

        A DISCONNECT IS NOT A RESCUE AND DOES NOT NEED TO BE SPECIAL-CASED.
        `remove_player` drops the row entirely, so a party whose last standing
        member's socket dies is a party with nobody left up — which is exactly
        what this counts, and exactly what it should mean.
        """
        if not self.zone.hostile or self._wipe_day:
            return
        players = list(self.players.values())
        if not players:
            return
        if any(not p.downed for p in players):
            return
        self._wipe_hold = WIPE_HOLD
        self._wipe_day = self.day

    async def wipe(self) -> None:
        """The run is over. Everything goes back to the first night.

        TRUE PERMADEATH, AND THE LIST IS DELIBERATELY TOTAL: day one, a knife,
        no skills, no plate, no rounds, no balance, a fresh camp. A partial
        reset is a tax, and a player learns to pay a tax — what makes a run
        worth protecting is that losing it costs the whole thing.

        THE CAMP COMES BACK FOR THIS AND ONLY THIS. `advance_zone`'s contract
        is that the loop never returns to the fire, because the shop already
        resets a party between nights and routing them home made them ready up
        twice for one decision. That argument is about a run CONTINUING. A run
        that has ended has to begin again, and beginning is the one thing the
        camp has always been for — so this is the reason the door was left
        open for, not an exception to the rule.

        It goes through `_swap_map` like every other map change, so the second
        `welcome` and the socket hand-off are the ones every transition uses.
        The players are stripped BEFORE the swap, because `_swap_map`'s whole
        promise is that what a body is carrying survives it.
        """
        self._wipe_hold = 0.0
        self._wipe_day = 0
        self.day = 1
        self.balance = 0
        self._balance_dirty = True
        self._spins_bought = 0
        self._spin_price_dirty = True
        self._rerolls_bought = 0
        self._reroll_price_dirty = True
        self.reroll_events = []
        self._night_takes = None
        for player in self.players.values():
            player.reset_for_new_run()
        # Seats are the camp's, and the camp is where a run begins. Reseating
        # before the swap means `_slots` is already the formation the fire
        # expects when `_swap_map` places bodies.
        self.reseat()
        await self._swap_map(
            zones.camp(self.day),
            camp.build_camp(random.randrange(1, 2**31)),
        )
        # A fresh camp is a fresh readiness check. `_swap_map` already clears
        # `ready`; what it cannot know is that the party should be standing on
        # their seats rather than on a spawn ring, because there is no arrival
        # corridor here to be marched out of.
        for index, pid in enumerate(self.seating):
            player = self.players.get(pid)
            if player is not None:
                player.x, player.y = camp.seat_position(
                    self.world, index, len(self.seating)
                )

    # --- zone transit: the three legal map swaps, all via _swap_map ---------
    def begin_depart(self) -> None:
        """Lock input and line the party up for the exit."""
        if self.departing or self.zone.kind != zones.KIND_CAMP:
            return
        self.departing = True
        self._depart_phase = "hold"
        self._depart_hold = 0.45
        self._slots = camp.formation_slots(
            self.world, self.seating, set(self.players)
        )
        for player in self.players.values():
            player.vx = player.vy = 0.0
            player.aim_x = 1.0
            player.aim_y = 0.0
            player.inputs.clear()

    async def embark(self) -> None:
        """They have crossed. Swap the camp for the forest and welcome again.

        The FIRST expedition only. Every later one leaves from the shop
        (`depart_store`) rather than from the fire, and both go through the
        same `_swap_map` — this one exists separately because it is the end of
        the walk-out cinematic and has to clear that state.
        """
        if self.zone.kind != zones.KIND_CAMP:
            self._pending_embark = False
            return
        self._pending_embark = False
        await self._swap_map(
            zones.forest(self.day),
            mapgen.build_forest(
                day=self.day, calibres=ammo.party_calibres(self.players.values())
            ),
        )

    async def advance_zone(self) -> None:
        """Whatever comes after the map they just walked out of.

        ONE crossing, two destinations, and the dispatch lives here rather than
        in `_tick_exit_quest` because the quest is the same mechanic both times:
        a living body walking into the VOID at the end of the map. What is on
        the far side of it is a property of the zone being left, not of the
        walk.

        forest -> store   the night's takings become the party's balance
        forest -> ARENA   on a boss night, and only on the way OUT. See
                          `is_boss_night`: the fight is what was at the end of
                          the exit corridor, not a place the party chose to go
        arena  -> store   same crossing, same banking, one map later
        store  -> forest  the day rolls over and the next night starts

        THE LOOP DOES NOT COME BACK TO THE CAMP. `preparation` is where a run
        BEGINS and nothing more: the party gathers at the fire once, readies
        once, and walks out once. After that the shop is the place between
        nights — it is already the beat that resets the party (spend, re-arm,
        catch a breath by a fire), and routing them through an empty camp
        afterwards made them ready up a second time to do a thing they had
        just decided to do.
        """
        if self.zone.kind == zones.KIND_FOREST:
            if self.is_boss_night():
                await self.enter_arena()
                return
            await self.enter_store()
            return
        if self.zone.kind == zones.KIND_ARENA:
            await self.enter_store()
            return
        await self.depart_store()

    def is_boss_night(self) -> bool:
        """Does the way out of this forest lead into the yard?

        `BOSS_DAY` is a DAY NUMBER in `config.py` and this is the only place
        that reads it — set it to 5 and nothing else in the codebase changes.
        `None` turns the fight off entirely.

        The second half of the test is what stops a party fighting him twice:
        `boss` survives on the room until the arena is swapped out, so the
        check is "have I already built one", not a flag somebody has to
        remember to clear.
        """
        return BOSS_DAY is not None and self.day == BOSS_DAY

    async def enter_arena(self) -> None:
        """They walked into the exit corridor and it opened onto the landing.

        THE TAKINGS TRAVEL WITH THEM. `enter_store` is still the one place
        money is created, so what happens here is the receipt being kept: the
        pads that earned it are on a map that is about to stop existing, and
        a party that dies in the arena has still earned it (they respawn; the
        night is not lost). Reading `self.rifts` after the swap would bank
        zero, which is the same bug as not banking at all.
        """
        self._night_takes = [max(0, row.fed) for row in self.rifts]
        await self._swap_map(zones.arena(self.day), arena.build_arena(self.day))

    async def enter_store(self) -> None:
        """Out of the woods and into the shop. BANK THE NIGHT ON THE WAY IN.

        This is where the currency is actually created, and it is deliberately
        the only place. Gold does not accumulate during a run — what a party
        has at the end of a night is what they FED INTO THE ANOMALIES, because
        that is the one number that measures the thing the night was about.
        Loot still in the bag is not money: it is loot they failed to extract,
        and the sweep at the blackout already said so.

        The day does NOT increment here. This corridor is the end of the night
        they just survived, not the start of the next one — see `zones.store`.
        """
        if self.zone.kind not in (zones.KIND_FOREST, zones.KIND_ARENA):
            self._pending_return = False
            return
        takes = self._night_takes
        if takes is None:
            takes = [max(0, row.fed) for row in self.rifts]
        self._night_takes = None
        earned = sum(takes)
        self.balance += earned
        self._balance_dirty = True
        # A NEW NIGHT'S CABINET SELLS AT THE BOTTOM OF THE LADDER AGAIN. The
        # doubling is meant to make the party stop buying WITHIN a visit; if it
        # carried across the run, the price by night six would be a number
        # nobody could reach and the mechanic would quietly stop existing.
        self._spins_bought = 0
        self._spin_price_dirty = True
        # Same argument, same reset: a reroll ladder that carried across the
        # run would be a number nobody could reach by night six, and the
        # mechanic would quietly stop existing.
        self._rerolls_bought = 0
        self._reroll_price_dirty = True
        self.reroll_events = []
        # The night's platforms come home with the party. `takes` only decides
        # what lands on the shop's apron and what each skid is worth on screen
        # — the balance above is the transaction, and the ceremony the client
        # runs off this is presentation. Keeping the two apart is what stops a
        # reconnect halfway through the animation paying anybody twice.
        await self._swap_map(
            zones.store(self.day),
            store.build_store(self.day, random.randrange(1, 2**31), takes),
        )

    async def _swap_map(self, zone: zones.Zone, world) -> None:
        """Move the whole room onto a new map that is entered through a corridor.

        The shape `embark` walks for the forest, factored out for the second
        arrival that wanted it. Everything a player is CARRYING survives —
        pocket, belt, xp — because this is one continuous run; everything the
        MAP was holding does not.

        Sequence is not reset, for the same reason it is not reset on embark:
        the client has been numbering packets since the camp and `queue_input`
        drops anything at or below the ack.
        """
        self._pending_return = False
        self.departing = False
        self._depart_phase = None
        self._slots = {}
        self.zone = zone
        self.world = world
        self.navigator = Navigator(self.world)
        self.enemies.clear()
        self.coins.clear()
        self.noises.clear()
        self.corpses.clear()
        self._corpses_dirty = True
        self.crate_break_events = []
        self.pour_events = []
        self.spin_events = []
        self.horde_events = []
        self.heal_events = []
        self._horde = None
        self._horde_left = 0.0
        # A NEW NIGHT IS A NEW SCRIPT. Every clock, every cooldown and every
        # per-night allowance restarts here, which is what makes "this night"
        # mean anything at all.
        self.events = events.EventDirector(self.day)
        self.event_rows = []
        # Nothing crosses an entrance. A disc still in the air when the party
        # walks out would arrive on a forest it was never thrown in.
        self.shots = []
        self.spit_events = []
        self.shot_bursts = []
        self.ult_shots = []
        self.ult_events = []
        self.ult_bursts = []
        self.dark_left = 0.0
        self._dark_dirty = True
        self.boss = None
        self.boss_events = []
        self._boss_dirty = False
        self._machine_busy = 0.0
        for player in self.players.values():
            player.pour = None
            player.using = None
        self._load_drops()
        self._load_crates()
        self._load_rifts()
        self._load_stands()
        # THE WALL IS STOCKED BEFORE THE MAP GOES OUT. It would be filled a
        # tick later anyway — `step` runs this every frame of a store visit —
        # but a tick later is a SNAPSHOT, and a crate the client meets on a
        # snapshot is a crate it drops in. The party would walk into the shop
        # through a hail of boxes for calibres they have been carrying all
        # night. Landing them on the map payload makes the drop-in mean the one
        # thing it is for: a calibre that is new.
        self._sync_ammo_boxes()
        self._load_entrance()
        self._rebuild_spawns()
        self.director = EnemyDirector(self.spawn_points, self.day)
        self._seed_nests()
        self._load_boss()
        self.begin_arrive()
        for player in self.players.values():
            player.ready = False
            # Anybody who was down on the way out comes back up here. The
            # crossing does not tick respawn timers, so a body that fell in the
            # last seconds of the run would otherwise arrive dead somewhere
            # with nothing that could have killed it.
            player.hp = player.max_hp
            player.alive = True
            # THE CROSSING IS THE RESCUE. A downed body cannot walk, so it got
            # here because somebody else finished the night — which is the
            # whole of the co-op contract, and it costs nothing here because
            # arriving already stands everybody up.
            player.downed = False
            player.using = None
            player.respawn_timer = 0.0
            player.hurt_immunity = 0.0
            player.stagger = 0.0
            slot = self._slots.get(player.id)
            if slot is not None:
                player.x, player.y = slot
            else:
                player.x, player.y = self.pick_spawn()
            player.vx = player.vy = 0.0
            if self.gate is not None:
                player.aim_x = self.gate.dx
                player.aim_y = self.gate.dy
            else:
                player.aim_x = 0.0
                player.aim_y = 1.0
            player.inputs.clear()
            player.idle_ticks = 0
            player.combo_step = 0
            player.combo_left = 0.0
            player.last_input = InputCmd(sequence=player.last_processed_seq)
        for pid, socket in list(self.sockets.items()):
            player = self.players.get(pid)
            if player is not None:
                await self._safe_send(
                    pid, socket, protocol.dumps(self.welcome_payload(player))
                )

    async def depart_store(self) -> None:
        """They walked out of the shop. Straight into the next night.

        THE RUN DOES NOT GO HOME. `preparation` is the beginning of a run and
        nothing else — see `advance_zone`. The shop is what sits between
        nights, so leaving it is leaving for the next expedition, and the day
        rolls over here rather than at a camp nobody visits any more.

        The hand-off is the walk-out's, deliberately: same `_swap_map`, so the
        party arrives in the new forest inside an edge corridor, is marched out
        of it, and the woods seal behind them exactly as they do on the first
        expedition. Leaving the merchant should feel like leaving the fire.

        Everything they are CARRYING survives — the belt they just bought from,
        whatever the fenda left in the pocket, their xp, and the party balance.
        """
        if self.zone.kind != zones.KIND_STORE:
            self._pending_return = False
            return
        self.day += 1
        await self._swap_map(
            zones.forest(self.day),
            mapgen.build_forest(
                day=self.day, calibres=ammo.party_calibres(self.players.values())
            ),
        )

    # --- input --------------------------------------------------------------
    def queue_input(self, pid: str, msg: dict) -> None:
        player = self.players.get(pid)
        if player is None:
            return
        cmd = InputCmd.from_message(msg)
        # ONE BRANCH, TWO REASONS. The run for the exit and an event dark are
        # different things that mean the same thing to a lamp, and giving them
        # separate suppression paths is how a light the player can see and the
        # server cannot eventually happens.
        #
        # AND ONE EXEMPTION, and only from the DARK. `Filamento Frio` is a rule
        # about the night's script, not about the run home: the blackout is the
        # last beat of a map and the whole party is meant to be running in it,
        # so a skill that lit one of them would be rewriting the ending rather
        # than the weather.
        if self.blackout or (
            self.dark_left > 0.0 and not player.skills.mods.lamp_immune
        ):
            cmd.lantern = False
        # Ignore out-of-order / replayed inputs.
        if cmd.sequence <= player.last_processed_seq:
            return
        if player.inputs and cmd.sequence <= player.inputs[-1].sequence:
            return
        player.inputs.append(cmd)
        while len(player.inputs) > MAX_INPUT_QUEUE:
            player.inputs.popleft()

    # --- the tick: one pass, in order ---------------------------------------
    def step(self, dt: float) -> None:
        # The cabinet's lockout. Off the shop map it is already zero and this
        # is one float subtraction a tick, which is cheaper than branching on
        # the zone to find out whether to do it.
        if self._machine_busy > 0.0:
            self._machine_busy = max(0.0, self._machine_busy - dt)
        self.step_players(dt)
        self.step_seal(dt)
        self.step_quests()
        self.step_enemies(dt)
        # AFTER the pack, because that is the tick something is thrown ON: a
        # disc launched this frame should not also move this frame, or the
        # first thing a player sees of it is a body-length down its own flight
        # path — which is exactly the beat the windup bought them.
        self.step_shots(dt)
        self.step_ult_shots(dt)
        self.step_boss(dt)
        self.step_coins(dt)
        self.step_rift(dt)
        self._sync_ammo_boxes()
        self._step_dark(dt)
        # THE NIGHT'S SCRIPT, AFTER THE NIGHT'S OWN SYSTEMS.
        #
        # Ordered here on purpose: `step_rift` and `step_quests` are what turn
        # the siren on and the blackout over, and the director's gate reads
        # both. Ticking it earlier would let an event fire on the same frame a
        # pickup opened — inside the one beat the whole guard exists to keep
        # clear — because the flags it checks would still be a tick stale.
        self.events.update(dt, self)
        # LAST, because everything above can be what puts the final body down
        # — a claw, a crescent, a charge. Asking before them would miss a wipe
        # by a tick, and a tick is a whole snapshot of the party standing dead.
        self._check_wipe()
        if self._wipe_hold > 0.0:
            self._wipe_hold = max(0.0, self._wipe_hold - dt)

    # --- extraction: the pickup's clock -------------------------------------
    def step_rift(self, dt: float) -> None:
        """Run every pad's sequence. Marks dirty only on a transition.

        TWO THINGS HAPPEN OFF THIS CLOCK and they are half a second apart.
        `_free_deck` is the platform breaking ground: the tiles it was standing
        on stop being a wall the instant it is no longer standing on them, and
        that has to be a tile patch on the wire because the map physically
        changed shape. SPENT is later — the skid is out of sight, and that is
        where an overpayment turns into an object, on ground the party is
        standing next to watching it land.
        """
        for row in self.rifts:
            changed = row.step(dt)
            self._siren(row)
            if self._free_deck(row):
                changed = True
            if not changed:
                continue
            self._rift_dirty = True
            if row.state == rift.SPENT:
                self._drop_excess(row)
            self.world.rifts = [item.geometry_payload() for item in self.rifts]

    @property
    def _weather(self) -> zones.WeatherRule:
        """What tonight's coat does. Falls back to clear for an unknown one."""
        return zones.rule_for(self.zone.weather)

    @property
    def sirening(self) -> bool:
        """Any pad has called for a pickup and the aircraft are still working."""
        return any(row.alarm for row in self.rifts)

    @property
    def alarm_point(self) -> tuple[float, float] | None:
        """The pad whose pickup is sounding, or None.

        It is what the pack turns to LOOK at when the alarm reaches it (see
        `ai.startle`). Facing the noise rather than the party is the whole
        difference between "everything switched to hunt" and "everything heard
        the platform" — and the party is standing at that platform, so it costs
        them nothing in fairness and buys the beat its entire meaning.
        """
        for row in self.rifts:
            if row.alarm:
                return row.x, row.y
        return None

    def _siren(self, target: Rift) -> None:
        """The pickup, heard from anywhere on the map.

        THIS IS THE COST OF CALLING FOR EXTRACTION and it is the only thing in
        the game that makes a noise on a repeating clock. A gunshot is a local
        problem somebody nearby investigates; this is a red light sweeping a
        black forest for thirteen seconds with a `SIREN_TILES` radius on every
        pulse, which in practice is the whole map. The party chose to press
        that button, they cannot un-press it, and everything out there is now
        walking toward the one clearing they are standing in.

        `source_id` is None on purpose. A noise belongs to whoever made it so
        the pack chases the person who fired — but nobody made this one, the
        machine did. What actually sends the horde is `hunt_all` (see
        `step_enemies`); this is what turns the heads of everything that was
        facing the other way, including whatever is already on top of the pad.
        """
        if not target.alarm:
            return
        since = target.elapsed - (target.close_at or 0.0)
        pulse = int(since / rift.SIREN_PULSE)
        if pulse <= target.siren_pulse:
            return
        target.siren_pulse = pulse
        self.noises.append(
            ai.Noise(
                x=target.x,
                y=target.y,
                radius=rift.SIREN_TILES * TILE_SIZE,
            )
        )

    def _free_deck(self, target: Rift) -> bool:
        """Hand the platform's tiles back to the floor. True the tick it fires.

        The deck is solid the whole time the skid is on it and walkable the
        moment it is not — a party that watches a platform fly away and then
        walks into the hole it left is the only version of this that is not a
        lie. The patches ride the next snapshot; the navigator is rebuilt
        because a hole opening in the middle of a clearing is exactly the sort
        of thing the pack's routes were avoiding.
        """
        if target.freed or not target.lifted:
            return False
        target.freed = True
        for tx, ty in target.deck_tiles():
            self.world.set_tile(tx, ty, FLOOR)
            self._tile_patches.append((tx, ty, FLOOR))
        self.navigator.invalidate()
        return True

    # --- bodies, and the corridors that puppet them -------------------------
    def begin_arrive(self) -> None:
        """Lock input and line the party up inside the arrival corridor.

        The formation is the ZONE's, because the two arrivals are different
        pictures: a party coming out of a hole in a treeline should not look
        arranged, and a party walking into a shop is walking into somewhere
        that was arranged for them. See `store.formation_slots`.
        """
        if self.gate is None:
            self.arriving = False
            return
        self.arriving = True
        self._arrive_phase = "hold"
        self._arrive_hold = 0.35
        formation = (
            store.formation_slots
            if self.zone.kind == zones.KIND_STORE
            else entrance.formation_slots
        )
        self._slots = formation(self.gate, self.seating, set(self.players))
        self._entrance_dirty = True

    def step_players(self, dt: float) -> None:
        if self.departing:
            self.step_depart(dt)
            return
        if self.arriving:
            self.step_arrive(dt)
            return
        if self.boss is not None and self.boss.state == boss.ARRIVE:
            # THE ARRIVAL IS ON RAILS, and the party is in it. Input is
            # dropped rather than queued for exactly the same reason the
            # walk-out drops it (`step_depart`): two seconds of buffered
            # movement replayed the instant the cinematic ends would teleport
            # everybody, and the one thing this beat must not do is take the
            # party's footing away and then give it back somewhere else.
            #
            # Timers still run — i-frames, respawns, cooldowns — because the
            # fight starts the frame this returns and a player who arrived
            # mid-reload should not have the clock paused for them.
            for player in self.players.values():
                player.inputs.clear()
                player.vx = player.vy = 0.0
                if player.hurt_immunity > 0.0:
                    player.hurt_immunity = max(0.0, player.hurt_immunity - dt)
                if player.fire_cooldown > 0.0:
                    player.fire_cooldown = max(0.0, player.fire_cooldown - dt)
            return
        for player in self.players.values():
            if player.fire_cooldown > 0.0:
                player.fire_cooldown = max(0.0, player.fire_cooldown - dt)
            # AN ULTIMATE'S WINDOW BURNS IN REAL TIME. Ticked up here with the
            # other clocks rather than inside `handle_attack`, because it has
            # to run out for somebody who stopped shooting — which is exactly
            # the frame that handler does nothing — and because a window that
            # only advanced while the trigger was down would be a window you
            # could pause by letting go.
            if player.ult is not None:
                player.ult.left -= dt
                if player.ult.left <= 0.0:
                    player.ult = None
            # The chain closes on its own. Ticked here rather than in
            # `handle_melee`, because it has to run out for a player who
            # stopped swinging — which is exactly the frame that handler is
            # not doing anything.
            if player.combo_left > 0.0:
                player.combo_left = max(0.0, player.combo_left - dt)
                if player.combo_left == 0.0:
                    player.combo_step = 0
            if player.hurt_immunity > 0.0:
                player.hurt_immunity = max(0.0, player.hurt_immunity - dt)

            if not player.alive:
                player.inputs.clear()
                # DOWN IS NOT A TIMER, and this guard is the whole difference.
                # A downed body has no `respawn_timer` at all, so without the
                # test below it would tick straight past zero and stand back
                # up on the next frame — permadeath undone by a subtraction.
                # Nothing brings it back but the party reaching the next zone.
                if player.downed:
                    continue
                player.respawn_timer -= dt
                if player.respawn_timer <= 0.0:
                    self.respawn(player)
                continue

            # Mid-pour the body is a puppet: input is acked and dropped, the
            # walk is driven from here, and the one key that still does
            # anything is a movement key, which ENDS it. What already left the
            # bag stays on the pad — the ceremony spends as it goes — so
            # stepping off the mark costs the rest of the load and nothing
            # that was banked.
            if player.pour is not None:
                if self._puppet_inputs(player):
                    player.pour = None
                else:
                    self._step_pour(player, dt)
                    continue

            # Mid-heal, the puppet with no way out: the queue drains and the
            # sequence is acked so prediction hears back, and nothing else
            # happens. Only `damage_player` ends this one — see `_step_use`.
            if player.using is not None:
                self._puppet_inputs(player)
                self._step_use(player, dt)
                continue

            budget = MAX_INPUTS_PER_TICK if len(player.inputs) > 3 else 1
            consumed = 0
            while player.inputs and consumed < budget:
                cmd = player.inputs.popleft()
                player.hotbar.apply_held(cmd.held)
                self.sync_block(player, cmd)
                apply_input(player, cmd, self.world, dt)
                self.handle_attack(player, cmd, dt)
                player.last_processed_seq = cmd.sequence
                player.last_input = cmd
                consumed += 1

            if consumed == 0:
                # Network jitter: briefly extrapolate the last known input so
                # remote viewers do not see a stutter.
                if player.idle_ticks < 3:
                    player.hotbar.apply_held(player.last_input.held)
                    self.sync_block(player, player.last_input)
                    apply_input(player, player.last_input, self.world, dt)
                    self.handle_attack(player, player.last_input, dt)
                else:
                    # Past the extrapolation window nothing calls `apply_input`
                    # any more, and that is what normally ticks the breath. A
                    # body standing still on a quiet socket is RESTING, not
                    # holding its bar wherever the last packet left it.
                    step_stamina(player, False, False, dt)
                player.idle_ticks += 1
            else:
                player.idle_ticks = 0

    def step_depart(self, dt: float) -> None:
        """Puppet every body through the walk-out. Input is acked and dropped."""
        for player in self.players.values():
            while player.inputs:
                cmd = player.inputs.popleft()
                player.last_processed_seq = cmd.sequence
                player.last_input = cmd
            player.idle_ticks = 0
            # Nobody is holding SHIFT through a cutscene, and the march is not
            # the party's walk — the breath comes back over it.
            step_stamina(player, False, False, dt)

        if self._depart_phase == "hold":
            self._depart_hold -= dt
            for player in self.players.values():
                player.vx = player.vy = 0.0
                player.aim_x = 1.0
                player.aim_y = 0.0
            if self._depart_hold <= 0.0:
                self._depart_phase = "align"
            return

        if self._depart_phase == "align":
            arrived = True
            for pid, player in self.players.items():
                slot = self._slots.get(pid)
                if slot is None:
                    continue
                (
                    player.x,
                    player.y,
                    player.vx,
                    player.vy,
                    player.aim_x,
                    player.aim_y,
                    done,
                ) = camp.march_towards(
                    player.x, player.y, slot[0], slot[1], MARCH_SPEED, dt
                )
                if not done:
                    arrived = False
            if arrived:
                self._depart_phase = "walk"
            return

        if self._depart_phase != "walk":
            return

        mouth_x, _, east_x = camp.exit_corridor(self.world)
        dest_x = east_x + TILE_SIZE * 2
        for pid, player in self.players.items():
            slot = self._slots.get(pid)
            ty = slot[1] if slot is not None else player.y
            (
                player.x,
                player.y,
                player.vx,
                player.vy,
                player.aim_x,
                player.aim_y,
                _,
            ) = camp.march_towards(
                player.x, player.y, dest_x, ty, MARCH_SPEED, dt
            )
        crossed = mouth_x + TILE_SIZE * 3.5
        if self.players and all(p.x >= crossed for p in self.players.values()):
            self._pending_embark = True

    def step_arrive(self, dt: float) -> None:
        """Puppet every body out of the forest corridor. Input is acked and dropped."""
        gate = self.gate
        if gate is None:
            self.arriving = False
            return
        for player in self.players.values():
            while player.inputs:
                cmd = player.inputs.popleft()
                player.last_processed_seq = cmd.sequence
                player.last_input = cmd
            player.idle_ticks = 0
            step_stamina(player, False, False, dt)

        if self._arrive_phase == "hold":
            self._arrive_hold -= dt
            for player in self.players.values():
                player.vx = player.vy = 0.0
                player.aim_x = gate.dx
                player.aim_y = gate.dy
            if self._arrive_hold <= 0.0:
                self._arrive_phase = "walk"
            return

        if self._arrive_phase != "walk":
            return

        arrived = True
        for pid, player in self.players.items():
            slot = self._slots.get(pid)
            sx = slot[0] if slot is not None else player.x
            sy = slot[1] if slot is not None else player.y
            dest_x, dest_y = entrance.emerge_point(gate, sx, sy)
            (
                player.x,
                player.y,
                player.vx,
                player.vy,
                player.aim_x,
                player.aim_y,
                done,
            ) = camp.march_towards(
                player.x, player.y, dest_x, dest_y, MARCH_SPEED, dt
            )
            if not done:
                arrived = False
        living = [p for p in self.players.values() if p.alive]
        if living and arrived and all(gate.past_mouth(p.x, p.y) for p in living):
            self.arriving = False
            self._arrive_phase = None
            self._slots = {}
            self.begin_seal()

    def begin_seal(self) -> None:
        """The woods take the corridor back, edge first."""
        gate = self.gate
        if gate is None or gate.state != entrance.OPEN:
            return
        gate.state = entrance.SEALING
        gate.elapsed = 0.0
        gate.rank = 0
        if not gate.ranks:
            gate.ranks = entrance._ranks(self.world.tiles, gate.side)
        self._seal_left = 0.0
        self._entrance_dirty = True
        self._sync_entrance_payload()

    def step_seal(self, dt: float) -> None:
        gate = self.gate
        if gate is None or gate.state != entrance.SEALING:
            return
        gate.elapsed += dt
        self._seal_left -= dt
        if self._seal_left > 0.0:
            return
        self._seal_left = entrance.SEAL_RANK_TIME
        patches = entrance.seal_rank(self.world.tiles, gate)
        if patches:
            self._tile_patches.extend(patches)
            self.navigator.invalidate()
        if gate.rank >= len(gate.ranks):
            gate.state = entrance.GONE
            gate.ranks = []
            self._entrance_dirty = True
            self._sync_entrance_payload()
            self._rebuild_spawns()
            self.director = EnemyDirector(self.spawn_points, self.day)
            # The way back closing is the moment either zone gets a job. In the
            # forest that is finding the pads; in the shop it is the doorway at
            # the far end, which has been standing open the whole time and now
            # has a row on the HUD saying so.
            if self.zone.kind == zones.KIND_STORE:
                self.offer_store_quest()
            else:
                self.offer_extract_quest()

    def _sync_entrance_payload(self) -> None:
        if self.gate is None:
            self.world.entrance = None
            return
        self.world.entrance = self.gate.geometry_payload()

    # --- quests -------------------------------------------------------------
    def offer_extract_quest(self) -> None:
        if not self.rifts:
            return
        if any(q.id == quests.EXTRACT for q in self.quests):
            return
        quest = quests.extract(need=len(self.rifts))
        quest.have = min(quest.need, sum(1 for row in self.rifts if row.found))
        quest.done = quest.have >= quest.need
        self.quests.append(quest)
        self._quests_dirty = True
        awake = self._awake_rift()
        if awake is not None:
            self.offer_feed_quest(awake)

    def offer_feed_quest(self, target: Rift) -> None:
        """Put the feed row up for the pad that just woke.

        ONE ROW AT A TIME, matching the one pad. It carries THAT pad's quota
        and is dropped when the pad is shut, so walking to the next console
        puts a fresh 0/need on the HUD rather than continuing somebody else's
        meter.
        """
        if target.need <= 0:
            return
        if any(q.id == quests.FEED for q in self.quests):
            self._sync_feed_quest(target)
            return
        self.quests.append(quests.feed(target.need))
        self._sync_feed_quest(target)

    def offer_exit_quest(self) -> None:
        if any(q.id == quests.EXIT for q in self.quests):
            return
        self.quests.append(quests.exit_quest())
        self._quests_dirty = True

    def offer_store_quest(self) -> None:
        """The shop's only row: the doorway at the other end of the corridor."""
        if any(q.id == quests.EXIT for q in self.quests):
            return
        self.quests.append(quests.store_exit_quest())
        self._quests_dirty = True

    def step_quests(self) -> None:
        """Tick progress. The exit is crossing the VOID; extract ticks on the console."""
        if self.quests:
            self._tick_exit_quest()
        if self.zone.kind == zones.KIND_ARENA:
            self._tick_arena_exit()

    def _tick_exit_quest(self) -> None:
        if self.egress is None or self._pending_return:
            return
        quest = next((q for q in self.quests if q.id == quests.EXIT), None)
        if quest is None or quest.done:
            return
        ts = TILE_SIZE
        hh = PLAYER_HALF_HEIGHT
        crossed = False
        for player in self.players.values():
            if not player.alive:
                continue
            feet_y = player.y + hh
            tx = int(player.x // ts)
            ty = int(feet_y // ts)
            if ty < 0 or tx < 0 or ty >= self.world.height or tx >= self.world.width:
                continue
            if self.world.tiles[ty][tx] != VOID:
                continue
            if self.egress.into_corridor(player.x, feet_y, EXIT_CROSS_TILES):
                crossed = True
                break
        if not crossed:
            return
        quest.have = quest.need
        quest.done = True
        self._quests_dirty = True
        self._pending_return = True

    # --- enemies ------------------------------------------------------------
    def step_enemies(self, dt: float) -> None:
        """Advance the pack, resolve its swings, then top the population up."""
        # A safe zone has no director and, having never spawned anything, no
        # pack to advance. Checked here rather than in `step` so a zone that
        # turns hostile mid-run still finishes whatever is already on the map.
        # The forest also stays quiet until the entrance is GONE — the slam is
        # the moment the night starts hunting, not the walk out of the dark.
        sealed = self.gate is None or self.gate.state == entrance.GONE
        if (not self.zone.hostile or self.arriving or not sealed) and not self.enemies:
            self.noises.clear()
            return
        outcome = ai.update(
            self.enemies.values(),
            self.players.values(),
            self.world,
            self.navigator,
            dt,
            self.noises,
            # THE SIREN IS A PANIC ON ITS OWN. `self.panic` is the permanent
            # one the last pad's blackout sets; a pickup adds a temporary one
            # for exactly as long as the lamps are red. Calling for extraction
            # is the loudest thing anybody does on a night and it has to cost
            # what that sounds like: every creature on the map commits to the
            # nearest living player and starts walking, and the party has to
            # stand next to the pad for thirteen seconds while they arrive.
            hunt_all=self.panic or self.sirening,
            alarm_at=self.alarm_point,
            # THE WEATHER, AS TWO SCALARS. Read off the zone every tick rather
            # than cached: a coat belongs to the map, and the map can change
            # under a room mid-run. See `zones.WeatherRule` for why they are an
            # inverted pair rather than a difficulty knob.
            sight_scale=self._weather.sight,
            noise_scale=self._weather.noise,
        )
        # Heard once. A noise that survived the tick would keep waking whatever
        # walked into its radius long after the sound was over.
        self.noises.clear()
        for attack in outcome.attacks:
            self.resolve_attack(attack)
        for stranded in outcome.despawned:
            self.enemies.pop(stranded.id, None)

        if not self.zone.hostile:
            return
        # NOBODY ELSE IS INVITED TO THE BOSS FIGHT. The arena is `hostile` —
        # weapons fire, players die — but the director does not run in it.
        #
        # It is the one place in the game where adding pressure would REMOVE
        # tension: the whole fight is a conversation between a party and one
        # readable body, and a stream of zombies walking into it turns every
        # telegraph into something happening in a crowd. It would also quietly
        # break the arithmetic — his health is scaled to the guns pointed at
        # him, and guns pointed somewhere else are guns he does not have to
        # survive.
        if self.zone.kind == zones.KIND_ARENA:
            return
        for enemy_type, x, y in self.director.update(dt, self.players.values(), len(self.enemies)):
            self.spawn_enemy(enemy_type, x, y)
        self._step_horde(dt)

    # --- the horde ----------------------------------------------------------
    def _step_horde(self, dt: float) -> None:
        """Roll for a wave, warn about it, then send it.

        THE POPULATION RAMP IS A SLOPE AND A SLOPE HAS NO MOMENTS IN IT.
        `EnemyDirector.night_scale` is the right pressure and it is completely
        unreadable in the second it changes — nobody notices a ceiling move. So
        the slope has EVENTS on it: every so often the forest sends a wave from
        one bearing, and the party has to decide whether to answer it or leave.

        THE WARNING IS NOT A COURTESY, IT IS THE MECHANIC. A horde that
        materialises behind somebody at twenty hit points ends a permanent run
        with no story attached to it, and "I got jumped" is not a lesson. The
        howl goes up first, from the direction they are coming from, and the
        gap between it and the bodies is the only part of this the player
        actually plays.

        THREE CHANNELS, because the one that works depends on where they are
        looking: a spatial HOWL at the bearing (which works with your back
        turned), a map-wide NOISE the pack itself reacts to, and a card. The
        noise is not decoration — it means the wave wakes what is already out
        there on its way in, so a horde arriving through a quiet pocket brings
        that pocket with it.
        """
        if self._horde_left > 0.0:
            self._horde_left = max(0.0, self._horde_left - dt)
            if self._horde_left > 0.0 or self._horde is None:
                return
            x, y, bearing, size = self._horde
            self._horde = None
            # AGAINST THE BUDGET, NOT THE STANDING CEILING, and the
            # difference is the whole mechanic. `director.cap` is how full the
            # forest is KEPT — an ambient number the trickle refills toward. A
            # horde is a deliberate spike ON TOP of that, so measuring it
            # against the same ceiling would mean the wave only ever arrives
            # when the map happens to be quiet, which is exactly backwards:
            # the moment a horde is worth having is when things are already
            # busy. `ENEMY_HARD_CAP` is what it may not exceed, because that
            # one is a tick budget rather than a difficulty knob.
            room = ENEMY_HARD_CAP - len(self.enemies)
            if room <= 0:
                return
            places = self.director.horde_places(x, y, bearing, min(size, room))
            for enemy_type, px, py in places:
                self.spawn_enemy(enemy_type, px, py)

    def send_horde(self) -> dict | None:
        """Announce a wave. The bodies follow `HORDE_TELEGRAPH` seconds later.

        THE EFFECT SIDE OF `events.horde`, and it is only the announcement —
        `_step_horde` runs the telegraph down and does the spawning. The split
        is what the warning IS: the howl has to be in the air before anything
        walks out of the treeline, and the gap between them is the only part of
        this the player actually plays.

        Returns False when nothing was sent — a wave already pending, or a map
        with nobody living on it — so the director does not spend a cooldown on
        a horde that never happened.
        """
        if self._horde is not None or self._horde_left > 0.0:
            return None
        planned = self.director.plan_horde(self.players.values())
        if planned is None:
            return None
        self._horde = planned
        self._horde_left = HORDE_TELEGRAPH
        x, y, _bearing, _size = planned
        # The howl comes from WHERE THEY ARE, so the sound itself is the
        # bearing. `voice` resolves the audio by prefix on the client; this is
        # the same channel the wolf pack's call already uses.
        self.horde_events.append({"x": round(x, 1), "y": round(y, 1)})
        # And it wakes the woods on the way in.
        # SOURCE-LESS ON PURPOSE. `ai.hear` turns a creature to FACE a noise
        # and raises its awareness, but only COMMITS it to a hunt when the
        # noise came from a player it can be pointed at. A howl out of the
        # treeline should stir the woods and swing every head toward it — it
        # should not tell forty creatures where the party is standing.
        self.noises.append(ai.Noise(x=x, y=y, radius=SHOT_NOISE_DIST * 1.6))
        # NO PLACE ON THE EVENT ROW, because the horde already has a wire of
        # its own — `horde_events` carries the bearing the howl plays at. This
        # row is only "a horde happened", for the card and the log.
        return {}

    def step_coins(self, dt: float) -> None:
        outcome = coins.step(self.coins, self.players.values(), dt)
        for pickup in outcome.collected:
            self.pickup_events.append(pickup.to_payload())

    # --- the night's script: what an event is allowed to do -----------------
    #
    # `events.py` schedules; these are the doors it opens. Every one of them is
    # a thin wrapper over machinery that already existed for some other reason,
    # and every one returns whether it ACTUALLY happened — an effect that
    # swallowed its own failure would spend a rare event's whole night
    # allowance on nothing.

    def begin_dark(self, seconds: float) -> dict | None:
        """Kill every lantern on the map for `seconds`.

        THE SAME RULE THE EXTRACTION BLACKOUT USES, deliberately: `queue_input`
        already drops the lantern bit while `blackout` is on, so this adds a
        second reason for that same branch rather than a second way for a lamp
        to be off. Two independent lantern-suppression paths would eventually
        disagree, and the symptom would be a light the player can see and the
        server cannot.

        Refused while the real blackout is running. The run for the exit
        already has the lights out, and firing here would let the dark's timer
        outlive it and take the lamps away again on the far side.
        """
        if self.blackout or self.dark_left > 0.0:
            return None
        self.dark_left = seconds
        self._dark_dirty = True
        for player in self.players.values():
            # `Filamento Frio` — see `skills.Mods.lamp_immune`. One of the two
            # halves; the other is in `queue_input`, which is what stops the
            # lamp being switched back off on the next packet.
            if player.skills.mods.lamp_immune:
                continue
            player.last_input.lantern = False
        # NO PLACE. The dark is everywhere, and a cue with a bearing on it
        # would send the party looking in a direction for something that is
        # not in one.
        return {}

    def _step_dark(self, dt: float) -> None:
        """Run the dark down, and tell the client on the frame it lifts.

        The client needs BOTH edges. It predicts its own lamp, so a dark that
        ended without saying so would leave a player pressing F at a lantern
        the server had already re-enabled — which reads as the key being
        broken rather than as the night being over.
        """
        if self.dark_left <= 0.0:
            return
        self.dark_left = max(0.0, self.dark_left - dt)
        if self.dark_left <= 0.0:
            self._dark_dirty = True

    def drop_supplies(self, count: int, tiles: float) -> dict | None:
        """Put a cache of loot on the ground, `tiles` away from the party.

        AWAY IS THE WHOLE EVENT. A crate at your feet is a reward; a crate two
        clearings out is a decision — the forest is fuller than it was an hour
        ago, the bag is already worth something, and the walk has to be paid
        for. So the placement is anchored on a living player and pushed out
        past the lantern, not scattered near one.

        It is marked with a BEACON. An opportunity nobody can find is a threat
        with extra steps: the light is what makes the trade legible from where
        the party is standing, rather than something they have to be told.
        """
        living = [p for p in self.players.values() if p.alive]
        if not living:
            return None
        anchor = random.choice(living)
        rng = random.Random()
        reach = tiles * TILE_SIZE
        bearing = rng.uniform(0.0, math.tau)
        want_x = anchor.x + math.cos(bearing) * reach
        want_y = anchor.y + math.sin(bearing) * reach
        occupied = [
            (d.x / TILE_SIZE - 0.5, d.y / TILE_SIZE - 0.5) for d in self.drops.values()
        ]
        spot = loot.free_tile_near(
            self.world.tiles,
            want_x / TILE_SIZE - 0.5,
            want_y / TILE_SIZE - 0.5,
            occupied,
            rng,
        )
        if spot is None:
            return None
        cx = (spot[0] + 0.5) * TILE_SIZE
        cy = (spot[1] + 0.5) * TILE_SIZE

        # MILITARY AND SUPPLIES, because that is what falls out of an aircraft
        # — and because it is the one loot roll in the game that can be BIASED
        # without lying: everything else on the map is what happened to be
        # there, and this was packed.
        dropped = 0
        for _ in range(count):
            item = loot.roll_item(rng, tags=("military", "supplies"))
            if item is None:
                continue
            pos = loot.place_near(self.world.tiles, cx, cy, occupied, rng)
            if pos is None:
                pos = (cx, cy)
            occupied.append((pos[0] / TILE_SIZE - 0.5, pos[1] / TILE_SIZE - 0.5))
            drop_id = self._next_drop_id()
            self.drops[drop_id] = Drop(id=drop_id, key=item.key, x=pos[0], y=pos[1])
            dropped += 1
        if not dropped:
            return False
        self._loot_dirty = True
        # WHERE, for the wire. The beacon that marks it is pushed CLIENT-side
        # off this position — the same way the extraction pad's lamp is (see
        # `scenery.SceneLight`) — so the server ships a place and not a light.
        return {"x": round(cx, 1), "y": round(cy, 1)}

    def stir_at_downed(self, tiles: float) -> dict | None:
        """The woods turn toward the body that just fell.

        A NOISE AND NOT A HUNT, and the difference is the whole design.
        `ai.hear` with no source raises awareness and swings heads toward a
        sound without committing anything to a target — so the forest stirs
        toward the fall rather than every creature on the map walking at the
        survivors. A blanket hunt here would make one player going down
        equivalent to pressing the extraction siren, which is a far larger
        event than a fall should be.

        Anchored on the body rather than on the party, because that is where
        the sound came from — and because it is what makes the rescue the
        hard part rather than the retreat.
        """
        fallen = [p for p in self.players.values() if p.downed]
        if not fallen:
            return None
        body = fallen[-1]
        self.noises.append(
            ai.Noise(x=body.x, y=body.y, radius=tiles * TILE_SIZE)
        )
        return {"x": round(body.x, 1), "y": round(body.y, 1)}

    def spawn_enemy(self, enemy_type: EnemyType, x: float, y: float) -> Enemy:
        self._enemy_id += 1
        enemy = Enemy(id=f"e{self._enemy_id}", type=enemy_type, x=x, y=y)
        # A PACK MUST NOT SWING IN LOCKSTEP, and without this it does.
        #
        # Creatures arrive as a GROUP, walk to you together and come into reach
        # on the same tick, so their cooldowns run in phase for the rest of
        # their lives. Now that every one of those swings lands (see
        # `resolve_attack`), a synchronised six delivers 54 damage in one frame
        # and then nothing at all for a second — which is a slot machine, not a
        # fight: you either survive the volley untouched or you are deleted by
        # it, and no play in between changes the outcome.
        #
        # One random offset at birth turns that volley into a STREAM. Same
        # total damage per second, spread across the second, so being surrounded
        # is a rising cost you can feel accumulating and pull out of — and the
        # bites, the flinches and the hurt sound become a rhythm instead of one
        # stacked frame of noise.
        enemy.attack_cooldown = random.uniform(0.0, enemy_type.attack_cooldown)
        dress(enemy)
        # A CREATURE THAT SLEEPS ALWAYS ARRIVES ASLEEP, and it is decided here
        # rather than at the one call site that places one. There is exactly
        # one such creature today and it is only ever placed by `_seed_nests`,
        # but "sometimes it spawns awake" is a state nothing in `ai.py` is
        # written for — its whole encounter is the beat before it stands up —
        # so the stat block is what decides, once, for every path in.
        if enemy_type.sleeps:
            enemy.mode = ai.MODE_SLEEP
        self.enemies[enemy.id] = enemy
        if self.panic and not enemy.asleep:
            living = [p for p in self.players.values() if p.alive]
            if living:
                target = min(
                    living,
                    key=lambda p: (p.x - enemy.x) ** 2 + (p.y - enemy.y) ** 2,
                )
                ai.commit(enemy, target)
        return enemy

    # --- the boss -----------------------------------------------------------
    def _load_boss(self) -> None:
        """Stand him in the middle of the yard, asleep. Arena maps only.

        He exists from the moment the map does — hitbox, health and all —
        because the alternative is spawning him when the trigger fires, and a
        body that appears on the frame its own cinematic starts is a body that
        cannot cast the shadow the cinematic opens on.
        """
        if self.zone.kind != zones.KIND_ARENA:
            return
        x, y = arena.boss_spawn(self.world)
        self.boss = boss.Boss(
            id="sawyer",
            x=x,
            y=y,
            max_hp=boss.hp_for(max(1, len(self.players))),
        )
        self._boss_dirty = True

    def step_boss(self, dt: float) -> None:
        """His whole slice of the tick. Everything he can do to a player.

        Ordered after `step_enemies` on purpose: he is the last word in the
        room, and a crescent that lands on the same frame as a zombie's swing
        should be the thing that finished the job.
        """
        row = self.boss
        if row is None:
            return

        if row.state == boss.SLEEP:
            self._maybe_wake_boss()
            return

        living = [p for p in self.players.values() if p.alive]
        outcome = boss.update(row, living, self.world, dt)

        for player, damage, sx, sy, _owner in outcome.hits:
            if not player.alive:
                continue
            # HIS OWN I-FRAMES, NOT THE ZOMBIES'. `MELEE_IMMUNITY` is a shared
            # window sized for a crowd of 9-damage swings; a 34-damage chop
            # that lands inside somebody else's window would be free. So the
            # boss keeps his own per-victim clock (`boss.BOSS_MELEE_IMMUNITY`,
            # already applied) and this path only refreshes the shared one so
            # the party is not chopped and bitten on the same frame.
            player.hurt_immunity = max(player.hurt_immunity, MELEE_IMMUNITY)
            # HIS BLOWS DRAG TOO. A bar that size connecting and leaving the
            # body's footwork untouched would make him the one thing in the
            # game you can walk away from mid-combo — and his whole fight is
            # built on committing to a dodge before the swing lands.
            player.stagger = HIT_STAGGER_TIME
            self.damage_player(player, damage, None, sx, sy)
            self.boss_events.append({
                "kind": "hurt",
                "target": player.id,
                "x": round(player.x, 1),
                "y": round(player.y, 1),
                "dmg": damage,
            })

        if outcome.events:
            self.boss_events.extend(outcome.events)
        if row.just_enraged:
            row.just_enraged = False
            self.boss_events.append({
                "kind": "enrage", "x": round(row.x, 1), "y": round(row.y, 1),
            })
        if outcome.engaged:
            self.boss_events.append({
                "kind": "engage", "x": round(row.x, 1), "y": round(row.y, 1),
            })
        self._boss_dirty = True

        if row.state == boss.DEAD and self.egress is None and row.timer >= 0.0:
            self._boss_down()

    def _maybe_wake_boss(self) -> None:
        """Somebody has walked far enough into the ring. Drop him on them.

        The trigger is DISTANCE TO THE MIDDLE rather than a tripwire across
        the lane, because a party does not arrive together — one player runs
        ahead, and a line drawn across the corridor would start the cinematic
        while three of them were still in the dark. The middle is the one
        place everybody is walking toward.
        """
        row = self.boss
        if row is None or self.arriving:
            return
        cx, cy = arena.centre(self.world)
        for player in self.players.values():
            if not player.alive:
                continue
            if math.hypot(player.x - cx, player.y - cy) > TILE_SIZE * ARENA_TRIGGER_TILES:
                continue
            # HE LANDS IN FRONT OF WHOEVER WALKED IN, not on the spot he was
            # parked on. See `ARENA_LAND_AHEAD_TILES`: the camera is the
            # player's, and a cinematic that plays above the top edge of their
            # screen is a cinematic nobody watched. Toward the middle of the
            # ring rather than down their aim, because the middle is where
            # they were already going and it keeps him off the rim.
            dx = cx - player.x
            dy = cy - player.y
            length = math.hypot(dx, dy)
            if length > 1.0:
                reach = min(length, TILE_SIZE * ARENA_LAND_AHEAD_TILES)
                row.x = player.x + dx / length * reach
                row.y = player.y + dy / length * reach
            else:
                row.x, row.y = cx, cy
            # And he faces the person he is landing on.
            back = math.hypot(player.x - row.x, player.y - row.y)
            if back > 1.0:
                row.aim_x = (player.x - row.x) / back
                row.aim_y = (player.y - row.y) / back
            boss.wake(row)
            self._boss_dirty = True
            self.boss_events.append({
                "kind": "arrive", "x": round(row.x, 1), "y": round(row.y, 1),
            })
            return

    def damage_boss(
        self,
        amount: int,
        source: Player | None,
        dx: float = 0.0,
        dy: float = 0.0,
    ) -> None:
        """A landed shot or a landed swing. The only way his health moves.

        Every hit is broadcast even when it changes nothing, because a boss
        with two thousand health is a boss the player cannot see themselves
        hurting — the bar moves a pixel a shot. What sells it is the HIT: the
        flash, the wound, the number, and the fact that all three arrive on
        the frame the trigger was pulled.
        """
        row = self.boss
        if row is None or not row.vulnerable:
            return
        died = boss.hurt(row, amount)
        self._boss_dirty = True
        self.boss_events.append({
            "kind": "hit",
            "x": round(row.x, 1),
            "y": round(row.y, 1),
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            "dmg": amount,
            "hp": row.hp,
        })
        if died:
            self.boss_events.append({
                "kind": "slain", "x": round(row.x, 1), "y": round(row.y, 1),
            })
            self._boss_down(source)

    def _boss_down(self, source: Player | None = None) -> None:
        """He fell. Pay the party, open the treeline, and stop hunting them.

        THE EXIT IS CARVED HERE AND NOWHERE ELSE, which is what makes the
        yard a fight rather than a room with a fight in it: until this runs
        there is no gap in the rim, so the only way out of the arena is
        through him.
        """
        row = self.boss
        if row is None or self.egress is not None:
            return
        # Gold on the floor, not in the bank. Same contract as every other
        # kill in the game — somebody has to walk over it — and after two
        # minutes of dodging a chainsaw, walking around picking up his
        # takings is the exhale the beat wants.
        self.drop_coins(row.x, row.y, BOSS_COINS)
        for player in self.players.values():
            player.xp += BOSS_XP
            self._sync_spins(player)
        if source is not None:
            source.kills += 1
        self._open_egress()
        # Whatever else is on the map stops caring. Nothing should be chewing
        # on a player while they watch him go down.
        for enemy in self.enemies.values():
            ai.give_up(enemy)

    def _tick_arena_exit(self) -> None:
        """The crossing, for a map with no quest log to hang it on.

        `_tick_exit_quest` is the forest's version and it is driven by the
        EXIT objective; the arena has no quests, because a run's objectives
        are what a night asks of a party and this map asks one thing that no
        row of text improves. Same geometry, same `_pending_return`.
        """
        if self.egress is None or self._pending_return:
            return
        ts = TILE_SIZE
        hh = PLAYER_HALF_HEIGHT
        for player in self.players.values():
            if not player.alive:
                continue
            feet_y = player.y + hh
            tx = int(player.x // ts)
            ty = int(feet_y // ts)
            if ty < 0 or tx < 0 or ty >= self.world.height or tx >= self.world.width:
                continue
            if self.world.tiles[ty][tx] != VOID:
                continue
            if self.egress.into_corridor(player.x, feet_y, EXIT_CROSS_TILES):
                self._pending_return = True
                return

    # --- ultimates: what a BUILD can do that a weapon cannot ----------------
    #
    # The catalog, the requirements and the effect blocks are `ultimates.py`.
    # What lives here is the four things only a room can answer: whether the
    # press is legal, what the effect does to the world, what the bar is billed
    # for, and how long the window lasts. Nothing below names an ultimate, a
    # weapon or a material — the dispatch is on which effect BLOCK the row
    # carries, exactly as `handle_attack` dispatches on `melee` / `shield`.

    def ultimate_for(self, player: Player):
        """The ultimate the weapon in this player's hands owns, or None.

        THE PANEL FOLLOWS THE HAND. There is no "selected ultimate" and no
        second belt: an ultimate belongs to a weapon, so what R does is
        entirely decided by what 1/2/3 last chose. That is the one rule the
        whole HUD rests on and it is stated here rather than in four callers.
        """
        weapon = player.hotbar.equipped()
        if weapon is None:
            return None
        return ultimates.BY_WEAPON.get(weapon.key)

    def _empower(self, player: Player, weapon: weapons.WeaponDef):
        """The `Empower` running on `weapon` right now, or None.

        IT CHECKS THE WEAPON, not just the window. Holstering the minigun
        mid-storm and drawing a pistol must not hand the pistol six seconds of
        free ammunition — the window belongs to the weapon that opened it, and
        the seconds keep burning while it is put away. Swapping back inside
        the window gets the rest of it, which is correct: what was spent was
        time, and the player spent it.
        """
        state = player.ult
        if state is None:
            return None
        row = ultimates.BY_KEY.get(state.key)
        if row is None or row.weapon != weapon.key:
            return None
        return row.empower

    def _charge_ult(
        self, player: Player, weapon: weapons.WeaponDef, source: str, amount: float
    ) -> None:
        """Bill the bar for something the player just did with this weapon.

        THREE GUARDS AND EACH ONE IS A RULE:

          * the weapon has to OWN the ultimate being charged, so a night spent
            shooting cannot fill a katana's bar;
          * the SOURCE has to match the row's — a medic's bar fills on healing
            and cannot be filled by shooting something, which is what stops
            "carry the support gun and play normally";
          * the ultimate has to be UNLOCKED. A locked bar does not fill at
            all, which is what makes the state machine the player is shown —
            locked, then charging, then ready — the state machine the server
            actually runs. A full bar behind a padlock would be a HUD saying
            two things at once.
        """
        row = ultimates.BY_WEAPON.get(weapon.key)
        if row is None or row.charge_on != source or amount <= 0:
            return
        if ultimates.missing_tags(row, weapon.tags, player.armor.tag_pieces()):
            return
        have = player.ult_charge.get(row.key, 0.0)
        if have >= row.charge_full:
            return
        player.ult_charge[row.key] = min(row.charge_full, have + amount)
        self._roster_dirty = True

    def use_ultimate(self, pid: str) -> None:
        """R. Spend a full bar, if there is one and it is allowed to be spent.

        SILENT ON EVERY REFUSAL, like the shield's button and unlike a
        purchase. The HUD panel is on screen the whole time saying which of
        these is true — locked, charging, ready — so a buzzer here would be
        the game telling the player something they are already looking at.
        """
        player = self.players.get(pid)
        if player is None or not player.alive or player.downed:
            return
        # Not while the body is a puppet, and not in a zone where weapons do
        # not work. The camp is a place, not a firing range.
        if player.pour is not None or player.using is not None:
            return
        if not self.zone.hostile or self.arriving or self.departing:
            return
        if player.ult is not None:
            return
        weapon = player.hotbar.equipped()
        if weapon is None:
            return
        row = ultimates.BY_WEAPON.get(weapon.key)
        if row is None:
            return
        if ultimates.missing_tags(row, weapon.tags, player.armor.tag_pieces()):
            return
        if player.ult_charge.get(row.key, 0.0) < row.charge_full:
            return

        # SPENT FIRST. Everything below can fail to find a target and none of
        # it may leave the bar full — an ultimate that did nothing because
        # nobody was standing near it is still an ultimate that was fired.
        player.ult_charge[row.key] = 0.0
        self._roster_dirty = True

        if row.volley is not None:
            self._ult_volley(player, row)
        if row.empower is not None:
            player.ult = UltState(
                key=row.key,
                left=row.empower.duration,
                shots=row.empower.shots if row.empower.shots > 0 else -1,
            )
        if row.aura is not None:
            self._ult_aura(player, row)

        # THE ANNOUNCEMENT, and it is one event for every ultimate in the
        # catalog rather than one per effect. What a client does with it —
        # the flash, the ring, the shake, the sound — is chosen off `k`, and
        # the ROOM has no opinion about any of it.
        self.ult_events.append(
            {
                "by": player.id,
                "k": row.key,
                "x": round(player.x, 2),
                "y": round(player.y, 2),
                "dx": round(player.aim_x, 3),
                "dy": round(player.aim_y, 3),
            }
        )

    def _ult_volley(self, player: Player, row) -> None:
        """Put `row.volley` in the air, laid across the aim.

        AIMED, AND THEREFORE MISSABLE. Every projectile in this game is
        something a body can walk out of (`projectiles.py`) and an ultimate is
        not exempt: a crescent that homed would be a button that deletes what
        you point it at, which is a cutscene rather than a weapon.
        """
        volley = row.volley
        base = math.atan2(player.aim_y, player.aim_x)
        spread = math.radians(volley.spread_degrees)
        step = spread / max(1, volley.count - 1) if volley.count > 1 else 0.0
        centre = (volley.count - 1) / 2.0
        speed = volley.speed_tiles * TILE_SIZE
        for index in range(volley.count):
            angle = base + (index - centre) * step
            ux, uy = math.cos(angle), math.sin(angle)
            self._ult_shot_id += 1
            self.ult_shots.append(
                projectiles.Projectile(
                    id=self._ult_shot_id,
                    # Clear of the thrower's own tile, or it bursts on the wall
                    # they happen to be standing against.
                    x=player.x + ux * player.radius,
                    y=player.y + uy * player.radius,
                    dx=ux * speed,
                    dy=uy * speed,
                    life=volley.life,
                    radius=volley.radius_tiles * TILE_SIZE,
                    damage=volley.damage,
                    owner=player.id,
                    look=volley.look,
                )
            )

    def _ult_aura(self, player: Player, row) -> None:
        """One pulse centred on the body: heal the party, hurt the crowd.

        BOTH HALVES GO THROUGH THEIR OWN ONE DOOR — `heal_player` and
        `damage_enemy` — so an aura cannot become the one thing in the game
        that skips a plate or forgets to pay xp.
        """
        aura = row.aura
        reach = aura.radius_tiles * TILE_SIZE
        if aura.heal > 0:
            for other in list(self.players.values()):
                if math.hypot(other.x - player.x, other.y - player.y) > reach:
                    continue
                # `source=None`: an ultimate must not charge the bar that paid
                # for it, or a medic could hold R open forever.
                self.heal_player(other, aura.heal, source=None, key=row.key)
        if aura.damage > 0:
            for enemy in list(self.enemies.values()):
                if math.hypot(enemy.x - player.x, enemy.y - player.y) > reach:
                    continue
                self.damage_enemy(enemy, aura.damage, player, enemy.x - player.x, enemy.y - player.y)

    def _spend_ult_shot(self, player: Player) -> None:
        """One round out of a window budgeted in SHOTS. Closes it at zero."""
        state = player.ult
        if state is None or state.shots < 0:
            return
        state.shots -= 1
        if state.shots <= 0:
            player.ult = None

    def step_ult_shots(self, dt: float) -> None:
        """Fly every ultimate projectile one tick.

        THE MIRROR OF `step_shots`, against the other side of the room: a
        creature's spit is tested against players and this is tested against
        creatures. Same module, same order — moved, then the wall, then the
        bodies — so an ultimate cannot cut through a tree any more than a
        bloater's bile can.
        """
        if not self.ult_shots:
            return
        bodies = [e for e in self.enemies.values() if e.alive]
        if self.boss is not None and self.boss.vulnerable:
            bodies.append(self.boss)
        self.ult_shots, impact = projectiles.advance(self.ult_shots, bodies, self.world, dt)
        for body, damage, sx, sy, owner_id in impact.hits:
            # THE KILL IS CREDITED TO WHOEVER PRESSED R. Without the owner
            # column an ultimate would be the one way to clear a pack for no
            # xp and no level — a button that makes the run worse, which is
            # the exact opposite of what it is for.
            owner = self.players.get(owner_id)
            if isinstance(body, boss.Boss):
                self.damage_boss(damage, owner, sx - body.x, sy - body.y)
            else:
                self.damage_enemy(body, damage, owner, body.x - sx, body.y - sy)
        for bx, by in impact.bursts:
            self.ult_bursts.append({"x": round(bx, 1), "y": round(by, 1)})

    # --- combat -------------------------------------------------------------
    def resolve_attack(self, attack: ai.Attack) -> None:
        """Apply one melee swing, honouring the victim's i-frames.

        THE RATE LIMIT IS THE ATTACKER'S OWN, AND IT IS THE ONLY ONE. Every
        creature carries `EnemyType.attack_cooldown` (1.1s on a zombie) and
        `ai.step` spends it to produce exactly one `Attack` per creature per
        cycle — so the crowd is ALREADY rate-limited, per body, by the thing
        that should be doing it. This no longer touches `hurt_immunity`, and
        that one deletion is the whole of the fix.

        WHY SHRINKING THE SHARED WINDOW WAS NOT ENOUGH, because it is not
        obvious and it cost a rewrite to find out. A blocked swing still spends
        the swinger's cooldown up in `ai.step` — the enemy has committed either
        way. So any shared window at all makes a pack that swings TOGETHER pay
        for one hit: eight zombies arriving as a group land one blow between
        them, reset in lockstep, and land one blow again 1.1s later. At 0.6s
        that was catastrophic and at 0.14s it was still exactly as bad for the
        case that matters, because a pack that walked to you together IS
        synchronised. The window has to be gone, not small.

        WHAT STILL READS IT: the boss's chop and the respawn grace, both of
        which SET it and neither of which is a rate limit — one is "you were
        just hit by something enormous, the small things do not get to pile on
        top of that" and the other is "you have just stood up". Those are the
        two things a shared window was ever right for.

        A blocked swing is still broadcast: the player needs to see that the
        zombie hit them and it did nothing, otherwise the window reads as the
        server dropping hits.
        """
        enemy = attack.enemy
        target = attack.target
        # A THROW IS NOT A BLOW, and it leaves before any of the melee rules
        # below apply: there is no victim yet to have i-frames, no stagger to
        # apply, and nothing to broadcast as a landed hit. The damage arrives
        # later, from wherever the disc gets to, through the same one door.
        if attack.ranged:
            self._throw(enemy, target)
            return
        blocked = not target.alive or target.hurt_immunity > 0.0
        damage = 0 if blocked else enemy.type.damage

        if not blocked:
            # THE DRAG GOES ON BEFORE THE DAMAGE DOES, and it goes on whatever
            # the damage turns out to be. A blow stopped dead by a shield or
            # eaten by a plate still CONNECTED — something the size of a person
            # walked into you — and a player who could stand in a pack at full
            # speed because their armour was good would have found the way back
            # to the old game. Armour is meant to buy health, not momentum.
            target.stagger = HIT_STAGGER_TIME
            self.damage_player(target, damage, None, enemy.x, enemy.y)

        self.attack_events.append(
            {
                "by": enemy.id,
                "target": target.id,
                "x": round(target.x, 2),
                "y": round(target.y, 2),
                "dx": round(enemy.aim_x, 3),
                "dy": round(enemy.aim_y, 3),
                "dmg": damage,
                "blocked": blocked,
            }
        )

    def _throw(self, enemy: Enemy, target: Player) -> None:
        """One projectile leaves a creature. Nothing is resolved on this frame.

        AIMED WHERE THE TARGET IS, NOT WHERE IT WILL BE. No lead, deliberately:
        a shot that predicted the walk would be a shot you cannot dodge by
        walking, and outwalking it is the entire mechanic (`projectiles.py`).
        What the creature gets instead is the WINDUP — it has already committed
        to this direction three quarters of a second ago, so a player who
        changed direction during the telegraph has already won the exchange.
        That is the trade, and it is the one that makes the attack a skill
        check rather than a dice roll.
        """
        kind = enemy.type
        dx = target.x - enemy.x
        dy = target.y - enemy.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return
        ux, uy = dx / length, dy / length
        self._shot_id += 1
        self.shots.append(
            projectiles.Projectile(
                id=self._shot_id,
                # Launched clear of its own body, or it bursts on the tile the
                # creature is standing in when that tile happens to be solid.
                x=enemy.x + ux * kind.hit_radius,
                y=enemy.y + uy * kind.hit_radius,
                dx=ux * kind.shot_speed,
                dy=uy * kind.shot_speed,
                life=kind.shot_life,
                radius=kind.shot_radius,
                damage=kind.ranged_damage,
            )
        )
        self.spit_events.append(
            {
                "id": self._shot_id,
                "by": enemy.id,
                "x": round(enemy.x, 1),
                "y": round(enemy.y, 1),
                "dx": round(ux, 3),
                "dy": round(uy, 3),
            }
        )

    def step_shots(self, dt: float) -> None:
        """Fly every creature projectile one tick.

        THE SAME DOOR AS EVERYTHING ELSE. `projectiles.advance` returns the
        hits and `damage_player` applies them, so a spit goes through the
        shield, the worn plate and `Mods.armor` in exactly the order a claw
        does — which is the whole reason `damage_player` is one method.
        """
        if not self.shots:
            return
        living = [p for p in self.players.values() if p.alive and not p.downed]
        self.shots, impact = projectiles.advance(self.shots, living, self.world, dt)
        for player, damage, sx, sy, _owner in impact.hits:
            # THE DRAG GOES ON, for the same reason a claw's does: something
            # hit you, and a player who could stand in a firing line at full
            # walking speed would have no reason to leave it.
            player.stagger = HIT_STAGGER_TIME
            self.damage_player(player, damage, None, sx, sy)
        for bx, by in impact.bursts:
            self.shot_bursts.append({"x": round(bx, 1), "y": round(by, 1)})

    def sync_block(self, player: Player, cmd: InputCmd) -> None:
        """Decide whether the shield is up, BEFORE anything reads it.

        Called ahead of `apply_input` rather than inside `handle_attack`,
        because the walk is the first thing that asks: a block resolved after
        the body had already moved would make the shield a tick late every
        time it goes up, and a tick late on the frame you raise it is exactly
        the frame it was raised for.

        RIGHT MOUSE IS A REQUEST, the same way SHIFT is. What answers it is
        the belt: a shield in the hand, still in one piece. Anything else and
        the button does nothing at all — no error, no prompt. A control that
        is meaningless without the object is a control the player only ever
        presses while holding the object.
        """
        weapon = player.hotbar.equipped()
        up = (
            cmd.block
            and player.alive
            and player.pour is None
            and weapon is not None
            and weapon.shield is not None
            and player.shield is not None
            and player.shield.key == weapon.key
            and not player.shield.spent
        )
        player.blocking = up
        player.block_speed = weapon.shield.speed if up and weapon is not None and weapon.shield else 1.0

    def handle_attack(self, player: Player, cmd: InputCmd, dt: float) -> None:
        """One trigger, two weapons. A gun fires a ray; the knife swings an arc.

        Dispatched on the weapon's own `melee` block rather than on its `kind`
        string, so a second blade is a catalog row and nothing here changes.

        `zone.hostile` gates the GUN and not the swing. The rule it encodes is
        "weapons fire here", and a knife does not fire: it makes almost no
        noise, has no range, and cannot go off across a clearing by accident.
        Somebody messing about at the campfire with it is the camp behaving
        like a place rather than like a menu — and a player who dies to it
        walks back to their seat a couple of seconds later (`respawn`).
        """
        weapon = player.hotbar.equipped()
        if weapon is None or not player.alive:
            player.aim_hold = 0.0
            return
        if weapon.shield is not None:
            # A SHIELD HAS NO TRIGGER. Not "the attack is suppressed while
            # blocking" — there is nothing to suppress. The left button does
            # nothing at all with one in hand, which is the price of the cell
            # it is standing in and the reason a party with two of them is a
            # party that cannot kill anything.
            player.aim_hold = 0.0
            player.combo_step = 0
            player.combo_left = 0.0
            return
        if weapon.melee is not None:
            self.handle_melee(player, cmd, weapon)
            return
        if not self.zone.hostile:
            player.aim_hold = 0.0
            player.combo_step = 0
            player.combo_left = 0.0
            return
        # Holstering the blade mid-chain abandons it: coming back to the knife
        # starts at the first slash rather than resuming a finisher the player
        # has stopped thinking about.
        player.combo_step = 0
        player.combo_left = 0.0

        if weapon.fire_on_release:
            # THE AWP. Holding is aiming and never firing, however long it is
            # held; the shot is the frame the button comes UP. Everything
            # else in the game answers a press, so the one weapon that
            # answers a RELEASE is the one weapon whose input the player has
            # to think about — which is the same thing its price is saying.
            #
            # A tap under `aim_delay` is not a misfire and not an error: it
            # is somebody changing their mind, and it costs them nothing but
            # the time they spent scoped.
            if cmd.shoot:
                player.aim_hold += dt
                return
            held = player.aim_hold
            player.aim_hold = 0.0
            if held < weapon.aim_delay or player.fire_cooldown > 0.0:
                return
        else:
            if cmd.shoot:
                player.aim_hold += dt
            else:
                player.aim_hold = 0.0
                return
            if player.fire_cooldown > 0.0:
                return
            if player.aim_hold < weapon.aim_delay:
                return

        # THE ROUND IS SPENT BEFORE THE RAY IS CAST, and a dry trigger still
        # eats the cooldown. Both halves matter: a shot that resolved and then
        # discovered there was nothing to fire would credit a kill nobody
        # paid for, and a dry trigger that could be retried every tick would
        # spray `ui-error` thirty times a second the moment somebody ran out.
        # The client predicts the same thing off its own mirror of the
        # reserve, so an empty gun clicks on the frame it was pressed.
        #
        # ONE ROUND PER TRIGGER PULL, not per ray: a shotgun spends a SHELL
        # and gets six pellets out of it. See `fire`.
        # AN OPEN WINDOW PAYS FOR THE CADENCE AND, IF IT SAYS SO, FOR THE
        # ROUNDS. Read once, here, above both — a free-ammo window that still
        # spent the reserve would be an ultimate whose whole promise was
        # broken in a branch nobody would think to look at.
        boost = self._empower(player, weapon)
        cooldown = weapon.fire_cooldown * (boost.cadence_scale if boost is not None else 1.0)
        if boost is None or not boost.free_ammo:
            if not player.ammo.spend(ammo.calibre_of(weapon.key)):
                player.fire_cooldown = cooldown
                return
        player.fire_cooldown = cooldown
        self._roster_dirty = True
        self.fire(player, cmd.aim_x, cmd.aim_y, weapon)
        # AFTER the shot, so a one-shot window is spent by the round that used
        # it rather than by the press that opened it.
        self._spend_ult_shot(player)

    def handle_melee(self, player: Player, cmd: InputCmd, weapon: weapons.WeaponDef) -> None:
        """Advance the chain by one beat, if the trigger is down and the arm is free.

        Holding the button chains: slash, slash, cut, and then back to the
        first slash. The chain is not held open by the button, it is held open
        by `combo_left` — which is what lets a player break contact after two
        slashes and come back to a fresh one instead of an accidental finisher.
        """
        player.aim_hold = 0.0
        if not cmd.shoot or player.fire_cooldown > 0.0:
            return
        melee = weapon.melee
        if melee is None:
            return
        step_index = player.combo_step % len(melee.steps)
        step = melee.steps[step_index]
        player.fire_cooldown = step.cooldown
        # The window opens the moment the swing is thrown, and it is measured
        # from there rather than from when the cooldown ends, so the chain
        # gets tighter as the steps get slower.
        if step.window > 0.0:
            player.combo_step = step_index + 1
            player.combo_left = step.cooldown + step.window
        else:
            player.combo_step = 0
            player.combo_left = 0.0
        self.swing(player, cmd.aim_x, cmd.aim_y, weapon, step_index, step)

    def swing(
        self,
        attacker: Player,
        dx: float,
        dy: float,
        weapon: weapons.WeaponDef,
        step_index: int,
        step: weapons.ComboStep,
    ) -> None:
        """Resolve one arc: bodies first, then — only if it met none — a crate.

        Only if it met none, because a knife that carried through a zombie and
        also took the box behind it would clear a room the player never aimed
        at. A swing that landed on flesh has already done its job.

        A whiff is SILENT and is not broadcast. The client already drew its own
        arc when the local player threw it, and a remote player waving a blade
        at nothing is not information anybody needs at 30 Hz.
        """
        targets = [*self.players.values(), *self.enemies.values()]
        if self.boss is not None and self.boss.vulnerable:
            targets.append(self.boss)
        hits = combat.sweep(
            self.world,
            attacker.x,
            attacker.y,
            dx,
            dy,
            step.reach,
            step.arc_degrees,
            targets,
            ignore_id=attacker.id,
            limit=step.max_targets,
        )

        crate = None
        if not hits:
            crate, _ = crates.along_ray(self.crates, attacker.x, attacker.y, dx, dy, step.reach)

        # Same rule the gun keeps: fold the blade skills in once, above the
        # event and the resolution both.
        damage = max(1, round(step.damage * attacker.skills.mods.melee))
        self._swing_id += 1
        rows = []
        for hit in hits:
            rows.append({"id": hit.target.id, "dmg": damage})
        self.swing_events.append(
            {
                "id": self._swing_id,
                "by": attacker.id,
                "k": weapon.key,
                "step": step_index,
                "x": round(attacker.x, 2),
                "y": round(attacker.y, 2),
                "dx": round(dx, 3),
                "dy": round(dy, 3),
                "hits": rows,
            }
        )

        if hits or crate is not None:
            # Quiet, but not silent: steel going into a body still carries.
            # The whole chain is worth less than a quarter of a gunshot, which
            # is the entire argument for using it.
            self.noises.append(
                ai.Noise(
                    x=attacker.x, y=attacker.y, radius=step.noise, source_id=attacker.id
                )
            )

        if crate is not None:
            self.smash_crate(crate, attacker)
            return

        # Same billing rule the trigger keeps: what the arc actually opened,
        # once, so a whiff is worth nothing and a finisher through three
        # bodies is worth three.
        if hits:
            self._charge_ult(attacker, weapon, ultimates.CHARGE_DAMAGE, damage * len(hits))

        for hit in hits:
            victim = hit.target
            if isinstance(victim, boss.Boss):
                self.damage_boss(damage, attacker, hit.dx, hit.dy)
            elif isinstance(victim, Enemy):
                self.damage_enemy(victim, damage, attacker, hit.dx, hit.dy)
            else:
                self.damage_player(victim, damage, attacker, attacker.x, attacker.y)

    def _pellet_aim(
        self, dx: float, dy: float, weapon: weapons.WeaponDef
    ) -> list[tuple[float, float]]:
        """The directions one trigger pull actually casts.

        A single ray for everything but the shotgun, and for the shotgun a
        ROSETTE: `pellets` angles laid out evenly across `spread_degrees`,
        each nudged by a fraction of the gap between them.

        The layout is regular and the wobble is small ON PURPOSE. A cone of
        purely random angles is a slot machine — the same shot at the same
        range kills or tickles depending on a roll nobody can see — and the
        whole appeal of a shotgun is that walking one step closer is a plan.
        A fixed pattern with a little life in it keeps the geometry legible
        (six pellets, twenty degrees, so at four tiles they are wider apart
        than a body) while stopping two shells looking like a photocopy.
        """
        if weapon.pellets <= 1 or weapon.spread_degrees <= 0.0:
            return [(dx, dy)]
        spread = math.radians(weapon.spread_degrees)
        step = spread / max(1, weapon.pellets - 1)
        centre = (weapon.pellets - 1) / 2.0
        rays: list[tuple[float, float]] = []
        for index in range(weapon.pellets):
            angle = (index - centre) * step
            angle += random.uniform(-1.0, 1.0) * step * PELLET_WOBBLE
            cos = math.cos(angle)
            sin = math.sin(angle)
            rays.append((dx * cos - dy * sin, dy * cos + dx * sin))
        return rays

    def fire(self, shooter: Player, dx: float, dy: float, weapon: weapons.WeaponDef) -> None:
        """One trigger pull: one to `pellets` rays, one round, one event.

        The pellet loop is the shotgun's whole implementation and it is
        deliberately the SAME loop a pistol runs, once. Everything that made
        a shot a shot — the noise, the round, the event id, the crate test —
        happens per PULL; only the ray and what it hits happen per pellet.
        Anything that drifted out of that split would make a shell six
        gunshots: six bangs, six brass, six of everything the forest hears.

        Damage is tallied PER BODY across the pellets, so a zombie standing
        in the middle of the cone takes one number and the client floats one
        number, rather than six sixes stacking up over its head.
        """
        ox = shooter.x + dx * weapon.muzzle
        oy = shooter.y + dy * weapon.muzzle
        # A gun is loud. Everything in earshot that has not already noticed
        # somebody now has a direction to look in — and, close enough to the
        # muzzle, a person to walk at. See ai.Noise.
        self.noises.append(
            ai.Noise(x=shooter.x, y=shooter.y, radius=weapon.noise, source_id=shooter.id)
        )
        # Players and enemies share one target list: the capsule contract is
        # identical, so the ray does not care which kind it hits.
        targets = [*self.players.values(), *self.enemies.values()]
        if self.boss is not None and self.boss.vulnerable:
            targets.append(self.boss)
        # The shooter's skills are folded in ONCE, here, so the number the
        # client draws over the body (`dmg` on the shot event) and the number
        # the body actually loses are the same number. Rolling it a second time
        # at the damage call is how a hit marker starts lying.
        # THE WINDOW IS FOLDED IN HERE, with the skills, for the reason the
        # comment above gives: the number the client floats over the body and
        # the number the body loses have to be the same number, and rolling a
        # multiplier a second time at the damage call is how a hit marker
        # starts lying.
        boost = self._empower(shooter, weapon)
        # A HEALING WEAPON DEALS NOTHING, and it is a zero rather than a
        # `max(1, ...)` floor: the floor exists so a shot always costs the
        # thing it hits SOMETHING, and a dart that took a point off the ally it
        # was aimed at would be the single funniest bug in this game.
        damage = (
            0
            if weapon.heal > 0
            else max(
                1,
                round(
                    weapon.damage
                    * shooter.skills.mods.gun
                    * (boost.damage_scale if boost is not None else 1.0)
                ),
            )
        )
        reach = weapon.range * (boost.range_scale if boost is not None else 1.0)

        # Insertion order is the pattern's order, which is what lets the
        # client draw the cone in the shape it was actually cast.
        rays = self._pellet_aim(dx, dy, weapon)
        pellets: list[list[float]] = []
        # Bodies opened this pull, in the order they were first struck, with
        # the running total each one owes and the direction of the pellet
        # that reached it first (the knockback wants a direction, and the
        # last pellet's is as good a lie as the first's — the first is the
        # one that arrived).
        tally: dict[str, list] = {}
        struck: list = []
        longest = 0.0

        for px, py in rays:
            hit = combat.raycast(
                self.world, ox, oy, px, py, reach, targets, ignore_id=shooter.id
            )
            # The foot tile is only the contact. Aiming at the barrel has to
            # count, so the sprite box is tested against the same ray — closer
            # than the wall or the body the DDA already found.
            crate, crate_dist = crates.along_ray(self.crates, ox, oy, px, py, hit.distance)
            victim = None if crate is not None else hit.target
            dist = crate_dist if crate is not None else hit.distance
            longest = max(longest, dist)
            if weapon.pellets > 1:
                pellets.append(
                    [round(px, 3), round(py, 3), round(dist, 2), 1 if victim is not None else 0]
                )
            if crate is not None:
                # A shell that put three pellets through the same barrel
                # broke one barrel.
                if crate not in struck:
                    struck.append(crate)
                continue
            if victim is None:
                continue
            row = tally.get(victim.id)
            if row is None:
                tally[victim.id] = [victim, damage, px, py]
            else:
                row[1] += damage

        self._shot_id += 1
        # The PRIMARY victim: whoever the pull hurt most. It is what the
        # existing single-ray path already meant by `hit`, so a pistol's
        # event is byte-for-byte what it always was and a shell's names the
        # body a player would say they shot.
        rows = sorted(tally.values(), key=lambda row: -row[1])
        primary = rows[0] if rows else None
        event = {
            "id": self._shot_id,
            "by": shooter.id,
            "k": weapon.key,
            "x": round(ox, 2),
            "y": round(oy, 2),
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            # The DEEPEST ray, so a client with no pellet list still draws a
            # tracer that covers the pattern instead of stopping at whatever
            # the centre happened to meet.
            "dist": round(longest, 2),
            # A HEALING SHOT NAMES NOBODY AND CARRIES NO NUMBER. The tracer
            # still flies its full distance so the player can see where the
            # dart went, and the green float over the body it reached is
            # `heal_events`' job — a `hit` here would put an impact spark and a
            # spray of blood on a team-mate.
            "hit": None if weapon.heal > 0 else (primary[0].id if primary is not None else None),
            "dmg": 0 if weapon.heal > 0 else (primary[1] if primary is not None else 0),
        }
        # Both extras are omitted on a one-ray weapon rather than sent empty:
        # every pistol shot in a 30 Hz snapshot would otherwise carry two
        # fields that only the shotgun has ever filled.
        if pellets:
            event["p"] = pellets
        if len(rows) > 1 and weapon.heal <= 0:
            event["hits"] = [{"id": row[0].id, "dmg": row[1]} for row in rows]
        self.shot_events.append(event)

        for crate in struck:
            self.smash_crate(crate, shooter)

        # THE FIELD GUN LEAVES HERE. Its ray was cast against the same target
        # list as everybody else's — which is the rule, not an oversight: a
        # dart stops on the zombie standing between you and the person you
        # were aiming at, and that is what makes a support weapon a question
        # about POSITION rather than a button that heals whoever is lowest.
        if weapon.heal > 0:
            for victim, _total, _vx, _vy in rows:
                if isinstance(victim, Player):
                    self.heal_player(victim, weapon.heal, source=shooter, key=weapon.key)
            return

        dealt = 0
        for victim, total, vx, vy in rows:
            dealt += total
            if isinstance(victim, boss.Boss):
                self.damage_boss(total, shooter, vx, vy)
            elif isinstance(victim, Enemy):
                self.damage_enemy(victim, total, shooter, vx, vy)
            else:
                self.damage_player(victim, total, shooter, ox, oy)
        # BILLED ON WHAT THE PULL ACTUALLY DID, once, after the fact — so a
        # shell that opened three bodies is worth three bodies and a miss is
        # worth nothing. Charging on the press would make the bar a rate of
        # fire, which would hand the fastest trigger in the game the fastest
        # ultimate as well.
        self._charge_ult(shooter, weapon, ultimates.CHARGE_DAMAGE, dealt)

    def damage_player(
        self,
        target: Player,
        amount: int,
        source: Player | None,
        from_x: float | None = None,
        from_y: float | None = None,
    ) -> None:
        """Hurt a player, through everything that stands between the blow and them.

        THE ONE DOOR, and everything defensive in the game is written here
        rather than at each of the things that can hurt you — a zombie's claw,
        a shotgun, the Sawyer's bar. A mitigation written at three call sites
        is a mitigation that will be missing from the fourth.

        THREE LAYERS, IN THIS ORDER, AND THE ORDER IS THE ARGUMENT:

          1. THE SHIELD, which is not mitigation at all — it is a wall. If it
             is up and the blow came from in front of it, the blow does not
             happen: the shield eats every point of it and loses that much of
             itself. That is the only thing in this game that takes a hit to
             zero, and it is why the shield costs a gun cell, only faces one
             way, and breaks.
          2. WORN ARMOUR, which is attrition. One blow lands on one part
             (`armor.Loadout.absorb`), the plate there takes its material's
             share onto its own durability, and the rest carries on. The
             plate that breaks doing it still did its job on the way out.
          3. TOUGHNESS (`Mods.armor`), which is the body rather than the
             gear: a multiplier a skill bought and nothing can take away. It
             applies to WHAT GOT THROUGH, because being hard to hurt is about
             the blow that reached you.

        `from_x` / `from_y` are where the blow came from, and only the shield
        reads them — everything else in this game is direction-blind on
        purpose. A caller that does not know passes nothing, and a shield
        that cannot tell where it was hit from does not block: guessing would
        make the one honest thing about the shield (that it has a back) into
        a coin flip.
        """
        if not target.alive:
            return
        # BEING HIT ENDS A POUR. A body standing over an open backpack while
        # something eats it is the one frame of this ceremony that would read
        # as the game having stopped listening.
        target.pour = None
        # AND IT ENDS A HEAL, WHICH IS THE ENTIRE COST OF ONE.
        #
        # This is what makes medicine a decision about POSITION rather than a
        # second health bar. If a blow did not interrupt, the correct play
        # would be to hold 4 the moment anything touched you and keep walking
        # backwards — the seconds would cost nothing, and the "stand still in
        # the open" that the whole verb is built on would never happen.
        #
        # It costs the seconds and NOT the kit: `_step_use` only spends the
        # cell on the frame the channel completes, so an interrupted heal
        # leaves the item on the belt. Taking the kit too would punish the
        # player twice for one mistake, and what interrupts a heal is precisely
        # the thing they were healing because of.
        #
        # Note this sits ABOVE the shield and the plate on purpose: a blow that
        # is fully absorbed still returns early, and a heal that survived
        # because a plate happened to eat the hit would make armour into
        # "keep healing through it", which is a rule nobody designed.
        #
        # `Sangue Frio` (`skills.Mods.steady`) is the one thing that survives
        # it, and it survives ONLY a heal. A vault is a different bargain: its
        # stake is the noise, and a force that could not be interrupted would
        # make the loudest object in the game free to open. The skill that
        # answers the vault is `Mãos de Veludo`, and it answers the noise.
        if not (target.skills.mods.steady and target.using is not None
                and target.using.kind == USE_HEAL):
            target.using = None

        amount = self._block_with_shield(target, amount, from_x, from_y)
        if amount <= 0:
            return
        amount = self._soak_with_armor(target, amount)

        # `max(1, ...)`: a hit that got past the plate always costs something,
        # or a fully-armoured player standing in a pack takes zero forever.
        target.hp -= max(1, round(amount * target.skills.mods.armor))
        if target.hp <= 0:
            target.hp = 0
            target.alive = False
            target.deaths += 1
            target.vx = target.vy = 0.0
            # WHICH KIND OF DEATH THIS IS, AND IT IS THE ZONE THAT DECIDES.
            #
            # Nothing in the camp or the shop can kill you except another
            # player, and a knife at the merchant's counter is a fumble rather
            # than the end of four nights' work — so those keep the two-second
            # respawn they always had. A hostile zone does not respawn anybody
            # any more: the body goes DOWN and stays there, and the run ends
            # only when nobody is left standing to carry it out (`_check_wipe`).
            if self.zone.hostile:
                target.downed = True
                target.respawn_timer = 0.0
                # AND THE WOODS NOTICE. The room says what happened and does
                # not know or care whether anything answers it — see
                # `events.EventDirector.report`. A room that called a named
                # handler here would be a room that knows the event catalog.
                self.events.report("downed", self)
            else:
                target.respawn_timer = RESPAWN_DELAY
            if source is not None and source.id != target.id:
                source.kills += 1
            self.kill_events.append(
                {
                    "kind": "player",
                    "killer": source.id if source else None,
                    "victim": target.id,
                    "x": round(target.x, 2),
                    "y": round(target.y, 2),
                    "xp": 0,
                    "gold": 0,
                }
            )

    def _block_with_shield(
        self,
        target: Player,
        amount: int,
        from_x: float | None,
        from_y: float | None,
    ) -> int:
        """Put the blow into the shield, if the shield is up and facing it.

        ALL OR NOTHING, up to what is left of the shield. A blow bigger than
        the shield's remaining life takes the shield apart and the rest goes
        through — the last thing a riot shield does is spend itself, and the
        Sawyer's bar going through the wreckage of one is the moment the
        player learns what "126" meant.

        The arc is tested against the AIM, not against the facing: the shield
        is drawn where the mouse is pointing, so the thing that decides
        whether it caught a blow has to be the thing the player was looking
        at when they turned to face it.
        """
        piece = target.shield
        if piece is None or not target.blocking or piece.spent:
            return amount
        if from_x is None or from_y is None:
            return amount
        weapon = target.hotbar.equipped()
        if weapon is None or weapon.shield is None or weapon.key != piece.key:
            return amount

        dx = from_x - target.x
        dy = from_y - target.y
        length = math.hypot(dx, dy)
        if length > 1e-6:
            # Facing is the aim, and both are unit vectors, so the dot IS the
            # cosine of the angle between them.
            facing = dx / length * target.aim_x + dy / length * target.aim_y
            if facing < weapon.shield.half_arc_cos:
                return amount

        soaked = piece.take(amount)
        self._roster_dirty = True
        broke = piece.spent
        if broke:
            self._break_shield(target)
        self.armor_events.append(
            {
                "by": target.id,
                "slot": "shield",
                "k": piece.key,
                "dmg": soaked,
                "left": 0 if broke else piece.hp,
                "broke": broke,
                "x": round(target.x, 2),
                "y": round(target.y, 2),
            }
        )
        return amount - soaked

    def _break_shield(self, target: Player) -> None:
        """Take the wreckage off the belt. The cell it was in goes empty.

        Not dropped: a shield at zero is not a shield, and leaving one on the
        floor would invite somebody to pick up a thing that cannot do
        anything. It is the one piece of gear in the game that leaves nothing
        behind, which is also the clearest possible statement that it is
        gone.
        """
        target.shield = None
        bar = target.hotbar
        for index, key in enumerate(bar.slots):
            if weapons.is_shield(key):
                bar.slots[index] = None
                if bar.held == index:
                    bar.held = -1
        target.blocking = False
        target.block_speed = 1.0

    def _soak_with_armor(self, target: Player, amount: int) -> int:
        """Land the blow on one part of the body and let the plate there take its share."""
        if not target.armor.worn:
            return amount
        through, slot, key, broke = target.armor.absorb(amount)
        if key is None:
            # Nothing there. No event, no roster churn — a blow that hit a
            # bare leg is not news about armour.
            return amount
        self._roster_dirty = True
        piece = target.armor.get(slot)
        self.armor_events.append(
            {
                "by": target.id,
                "slot": slot,
                "k": key,
                "dmg": amount - through,
                "left": piece.hp if piece is not None else 0,
                "broke": broke,
                "x": round(target.x, 2),
                "y": round(target.y, 2),
            }
        )
        return through

    def damage_enemy(
        self,
        target: Enemy,
        amount: int,
        source: Player | None,
        dx: float = 0.0,
        dy: float = 0.0,
    ) -> None:
        """Hurt an enemy; on death pay xp, scatter gold, and leave a corpse."""
        if not target.alive:
            return
        target.hp -= amount
        # Shot in the back is still shot: damage wakes it regardless of where
        # its sight cone happens to be pointing.
        ai.alarm(target, source)
        if target.hp > 0:
            target.take_stagger(amount)
            return

        target.hp = 0
        target.alive = False
        self.enemies.pop(target.id, None)

        reward = target.type
        paid_xp = reward.xp
        if source is not None:
            source.kills += 1
            paid_xp = max(1, round(reward.xp * source.skills.mods.xp))
            source.xp += paid_xp
            self._sync_spins(source)
            # A BODY IS A CHARGE SOURCE IN ITS OWN RIGHT, one unit per corpse.
            # No row in the catalog uses it today and the constant exists
            # anyway, because the alternative is a `CHARGE_KILL` that is real
            # in `ultimates.py` and imaginary here — which is a trap for
            # whoever writes the fifth ultimate.
            held = source.hotbar.equipped()
            if held is not None:
                self._charge_ult(source, held, ultimates.CHARGE_KILL, 1)
        # xp is what the kill is worth and never varies; coins are what fell
        # out of this particular corpse, which does.
        dropped = coins.roll_drop(
            reward.gold,
            skills.luck_chance(source.skills.mods) if source is not None else None,
        )
        self.drop_coins(target.x, target.y, dropped)
        length = math.hypot(dx, dy)
        fall_x = dx / length if length > 0.001 else target.aim_x
        fall_y = dy / length if length > 0.001 else target.aim_y
        body = Corpse(
            id=target.id,
            x=target.x,
            y=target.y,
            t=reward.key,
            variant=target.variant,
            hat=target.hat,
            cloth=target.cloth,
            ax=target.aim_x,
            ay=target.aim_y,
            dx=fall_x,
            dy=fall_y,
        )
        self.corpses[body.id] = body
        self._corpses_dirty = True
        kill: dict = {
            "kind": "enemy",
            "killer": source.id if source else None,
            "victim": target.id,
            "x": round(target.x, 2),
            "y": round(target.y, 2),
            "xp": paid_xp,
            "gold": dropped,
            "t": reward.key,
            "v": target.variant,
            "ax": round(target.aim_x, 3),
            "ay": round(target.aim_y, 3),
            "dx": round(fall_x, 3),
            "dy": round(fall_y, 3),
        }
        if target.hat >= 0:
            kill["hat"] = target.hat
        if target.cloth >= 0:
            kill["cloth"] = target.cloth
        self.kill_events.append(kill)

    def drop_coins(self, x: float, y: float, count: int) -> None:
        """Scatter `count` single-value coins from a death point."""
        total = max(0, count)
        for i in range(total):
            self._coin_id += 1
            coin = coins.spawn_burst(f"c{self._coin_id}", x, y, i, total)
            self.coins[coin.id] = coin

    def respawn(self, player: Player) -> None:
        # In the CAMP you come back to your own seat at the fire, not to a ring
        # tile somewhere in the trees.
        #
        # Keyed on the zone KIND rather than on `hostile`, and the difference
        # is not academic: the merchant's camp is also non-hostile and also has
        # a fire tile now, so the old test sent anyone knifed at the shop to a
        # seat on a ring around the trader's campfire — a ring that runs
        # straight through his treeline. Seats are the camp's, and only the
        # camp's; everywhere else has a spawn ring for exactly this.
        if self.zone.kind == zones.KIND_CAMP and player.id in self.seating:
            player.x, player.y = camp.seat_position(
                self.world, self.seating.index(player.id), len(self.seating)
            )
        else:
            player.x, player.y = self.pick_spawn()
        player.hp = player.max_hp
        player.alive = True
        player.downed = False
        player.using = None
        player.vx = player.vy = 0.0
        # A new body is a rested one. The bar is not a punishment that outlives
        # the death that emptied it.
        player.stamina = STAMINA_MAX
        player.winded = False
        player.respawn_timer = 0.0
        player.idle_ticks = 0
        player.combo_step = 0
        player.combo_left = 0.0
        # Grace period: respawning into a waiting pack is not a fair death.
        player.hurt_immunity = RESPAWN_IMMUNITY
        # And the limp goes with the body that had it. Coming back still
        # dragging from the blow that killed you is being punished twice for
        # one death, and it lands in the exact second the grace window above
        # exists to protect.
        player.stagger = 0.0
        player.last_input = InputCmd(sequence=player.last_processed_seq)

    # --- networking ---------------------------------------------------------
    async def broadcast(self, payload: dict) -> None:
        """Send one identical payload to every socket. Lobby state, not snapshots."""
        if not self.sockets:
            return
        text = protocol.dumps(payload)
        await asyncio.gather(
            *(
                self._safe_send(pid, socket, text)
                for pid, socket in list(self.sockets.items())
            ),
            return_exceptions=True,
        )

    async def broadcast_lobby(self) -> None:
        await self.broadcast(self.lobby_payload())

    async def broadcast_snapshot(self) -> None:
        """One payload, one dump, N writes — see the ack note in protocol.py."""
        due = self.tick % ROSTER_EVERY_N_TICKS == 0 or self._roster_dirty
        roster = [p.to_payload() for p in self.players.values()] if due else None
        self._roster_dirty = False
        loot_rows = (
            [drop.to_payload() for drop in self.drops.values()] if self._loot_dirty else None
        )
        self._loot_dirty = False
        crate_rows = (
            [crate.to_payload() for crate in self.crates.values()] if self._crates_dirty else None
        )
        self._crates_dirty = False
        corpse_rows = (
            [row.to_payload() for row in self.corpses.values()] if self._corpses_dirty else None
        )
        self._corpses_dirty = False
        rift_rows = (
            [row.state_payload() for row in self.rifts] if self._rift_dirty else None
        )
        self._rift_dirty = False
        entrance_row = (
            self.gate.state_payload() if (self.gate and self._entrance_dirty) else None
        )
        self._entrance_dirty = False
        tile_patches = (
            [[tx, ty, kind] for tx, ty, kind in self._tile_patches]
            if self._tile_patches
            else None
        )
        self._tile_patches = []
        quest_rows = [q.payload() for q in self.quests] if self._quests_dirty else None
        self._quests_dirty = False
        egress_row = (
            self.egress.geometry_payload() if (self.egress and self._egress_dirty) else None
        )
        self._egress_dirty = False
        blackout_flag = True if self._blackout_dirty else None
        self._blackout_dirty = False
        # THE DARK IS STATE, NOT AN EVENT, and the distinction is the same one
        # `blackout` makes: it has a DURATION, so a client that joined or
        # reconnected in the middle of one has to be told the lamps are off —
        # an event it missed would leave it predicting a light that cannot
        # come on. Shipped as seconds remaining, on both edges.
        dark_row = round(self.dark_left, 2) if self._dark_dirty else None
        self._dark_dirty = False
        # And the script's own rows, which ARE events: each one is a thing that
        # happened once, and a client that dropped the packet must never
        # replay it.
        self.event_rows.extend(self.events.drain())
        stand_rows = (
            [row.to_payload() for row in self.stands] if self._stands_dirty else None
        )
        self._stands_dirty = False
        box_rows = (
            [box.to_payload() for box in self.ammo_boxes] if self._boxes_dirty else None
        )
        self._boxes_dirty = False
        balance_row = self.balance if self._balance_dirty else None
        self._balance_dirty = False
        spin_price_row = self.spin_price if self._spin_price_dirty else None
        self._spin_price_dirty = False
        reroll_price_row = self.reroll_price if self._reroll_price_dirty else None
        self._reroll_price_dirty = False
        boss_row = self.boss.to_payload() if (self.boss and self._boss_dirty) else None
        self._boss_dirty = False
        # STATE, NOT EVENT — see the note in `protocol.snapshot`. It rides
        # every tick of the hold rather than once, so a client that joined or
        # reconnected halfway through still gets the black screen.
        wipe_row = (
            {"day": self._wipe_day} if (self._wipe_day and self._wipe_hold > 0.0) else None
        )
        await self.broadcast(
            protocol.snapshot(
                self.tick,
                [p.snapshot_payload() for p in self.players.values()],
                [e.to_payload() for e in self.enemies.values()],
                [c.to_payload() for c in self.coins.values()],
                self.shot_events,
                self.attack_events,
                self.kill_events,
                self.pickup_events,
                swings=self.swing_events or None,
                departing=self.departing,
                arriving=self.arriving,
                zone_key=self.zone.key,
                roster=roster,
                loot=loot_rows,
                loot_pickups=self.loot_pickup_events or None,
                pours=self.pour_events or None,
                crates=crate_rows,
                crate_breaks=self.crate_break_events or None,
                armor_hits=self.armor_events or None,
                corpses=corpse_rows,
                rifts=rift_rows,
                entrance=entrance_row,
                tile_patches=tile_patches,
                quests=quest_rows,
                egress=egress_row,
                blackout=blackout_flag,
                stands=stand_rows,
                boxes=box_rows,
                buys=self.buy_events or None,
                spins=self.spin_events or None,
                balance=balance_row,
                spin_price=spin_price_row,
                boss=boss_row,
                boss_events=self.boss_events or None,
                wipe=wipe_row,
                hordes=self.horde_events or None,
                heals=self.heal_events or None,
                events=self.event_rows or None,
                dark=dark_row,
                reroll_price=reroll_price_row,
                rerolls=self.reroll_events or None,
                spits=[
                    {
                        "id": shot.id,
                        "x": round(shot.x, 1),
                        "y": round(shot.y, 1),
                        "dx": round(shot.dx, 1),
                        "dy": round(shot.dy, 1),
                    }
                    for shot in self.shots
                ]
                or None,
                spit_events=self.spit_events or None,
                spit_bursts=self.shot_bursts or None,
                ults=self.ult_events or None,
                volleys=[
                    {
                        "id": shot.id,
                        "k": shot.look,
                        "x": round(shot.x, 1),
                        "y": round(shot.y, 1),
                        "dx": round(shot.dx, 1),
                        "dy": round(shot.dy, 1),
                        # The SWEEP, in world pixels. A crescent is drawn at
                        # its own width rather than at a constant, so a second
                        # volley with a different radius arrives already the
                        # right size on screen — the client has no table.
                        "r": round(shot.radius, 1),
                    }
                    for shot in self.ult_shots
                ]
                or None,
                ult_bursts=self.ult_bursts or None,
            )
        )

    async def _safe_send(self, pid: str, socket, text: str) -> None:
        try:
            await socket.send_text(text)
        except Exception:
            self.remove_player(pid)

    async def run(self) -> None:
        next_time = time.perf_counter()
        while True:
            next_time += DT
            self.tick += 1
            self.step(DT)
            # THE HOLD RAN OUT AND THE RUN GOES BACK TO NIGHT ONE. Checked
            # before the transitions below because a wiped party has no
            # pending crossing worth honouring — the map they were walking
            # toward belongs to a run that no longer exists.
            if self._wipe_day and self._wipe_hold <= 0.0:
                await self.broadcast_snapshot()
                await self.wipe()
                continue
            if self._pending_embark:
                await self.embark()
                continue
            if self._pending_return:
                await self.broadcast_snapshot()
                await self.advance_zone()
                continue
            if self.tick % SNAPSHOT_EVERY_N_TICKS == 0:
                await self.broadcast_snapshot()
                self.shot_events = []
                self.ult_events = []
                self.ult_bursts = []
                self.swing_events = []
                self.attack_events = []
                self.kill_events = []
                self.pickup_events = []
                self.loot_pickup_events = []
                self.pour_events = []
                self.crate_break_events = []
                self.armor_events = []
                self.buy_events = []
                self.horde_events = []
                self.heal_events = []
                self.event_rows = []
                self.reroll_events = []
                self.spit_events = []
                self.shot_bursts = []
                self.spin_events = []
                self.boss_events = []
            delay = next_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Fell behind: drop the accumulated debt instead of spiralling.
                next_time = time.perf_counter()
