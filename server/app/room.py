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
"""

from __future__ import annotations

import asyncio
import math
import random
import time
import uuid

from . import (
    ai, ammo, camp, coins, combat, crates, entrance, loot, mapgen, protocol,
    quests, rift, store, weapons, zones,
)
from .ai import EnemyDirector
from .coins import Coin
from .config import (
    CRATE_BREAK_DIST,
    CRATE_NOISE_DIST,
    DT,
    LOOT_COLLECT_DIST,
    MARCH_SPEED,
    RIFT_ACTIVATE_DIST,
    EXIT_CROSS_TILES,
    STORE_BUY_DIST,
    MAX_HP,
    MAX_INPUT_QUEUE,
    MAX_INPUTS_PER_TICK,
    MELEE_IMMUNITY,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    RESPAWN_DELAY,
    RESPAWN_IMMUNITY,
    ROSTER_EVERY_N_TICKS,
    SNAPSHOT_EVERY_N_TICKS,
    SPAWN_RING,
    SPAWN_SEPARATION,
    TILE_SIZE,
    client_config,
)
from .corpses import Corpse
from .crates import Crate
from .entrance import Entrance
from .rift import Rift
from .store import Stand
from .loot import Drop
from .quests import Quest
from .enemies import Enemy, EnemyType, dress
from .world import FLOOR, VOID
from .entities import InputCmd, Player, clean_name, pick_color, random_name
from .pathing import Navigator
from .simulation import apply_input

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
        #: The shop's tables. Empty on every map that is not the store.
        self.stands: list[Stand] = []
        self._stands_dirty = False
        self._balance_dirty = False
        self.corpses: dict[str, Corpse] = {}
        self.sockets: dict[str, object] = {}
        self.director = EnemyDirector(self.spawn_points)
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
        self.crate_break_events: list[dict] = []
        #: Purchases made this tick. The juice: the client flies the gun onto
        #: the belt cell and counts the balance down.
        self.buy_events: list[dict] = []
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
        if item is not None and item.pocket == "hotbar":
            # A gun goes straight to the hand when there was no gun in it.
            # The knife counts as no gun for this: a run opens holding the
            # blade, so testing "is the hand empty" would mean nobody's
            # FIRST pickup ever equipped itself, which is the one time this
            # matters most. A second gun does not steal the hand.
            held = player.hotbar.equipped()
            unarmed = held is None or held.melee is not None
            slot = player.hotbar.add(drop.key)
            dest = "hotbar"
            if slot is not None and unarmed:
                player.hotbar.held = slot
            elif slot is None:
                # Belt full: trade whatever is in the hand for this. See
                # `swap_weapon` — refuses unless a GUN is held.
                slot = self.swap_weapon(player, drop.key)
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

    def swap_weapon(self, player: Player, key: str) -> int | None:
        """Trade the gun in hand for `key`, dropping the old one at the feet.

        The way OUT of a full belt, and it is deliberately narrow: the hand
        has to be holding a GUN. Holding the knife refuses, because the knife
        is not yours to trade away — it is the one thing on the belt that
        cannot be lost, and letting a pickup consume its cell would turn the
        floor under the whole loadout into something you can stand on by
        accident. Holstered refuses for the same reason it cannot fire: an
        empty hand is not a choice about which gun to keep.

        Returns the slot the new gun landed in, or None if no trade was legal.
        """
        bar = player.hotbar
        held = bar.held
        if held < 0 or held >= weapons.GUN_SLOTS:
            return None
        old = bar.slots[held]
        if old is None or old == weapons.STARTING_MELEE:
            return None

        bar.slots[held] = key
        # The gun you gave up lands where you are standing, not in the void:
        # a trade you can change your mind about one step later is a trade,
        # and one that eats the loser is a punishment for experimenting.
        feet_y = player.y + PLAYER_HALF_HEIGHT
        occupied = [
            (d.x / TILE_SIZE - 0.5, d.y / TILE_SIZE - 0.5) for d in self.drops.values()
        ]
        pos = loot.place_near(self.world.tiles, player.x, feet_y, occupied, random.Random())
        if pos is None:
            pos = (player.x, feet_y)
        drop_id = self._next_drop_id()
        self.drops[drop_id] = Drop(id=drop_id, key=old, x=pos[0], y=pos[1])
        return held

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
        self.smash_crate(crate, player)

    def smash_crate(self, crate: Crate, source: Player | None) -> None:
        """Remove an object, free the ground it stood on, roll what was in it.

        The same path for both verbs, because everything downstream of the
        animation is identical: the object stops existing, its tiles go back
        to floor, something or nothing falls out, and whatever heard it comes
        looking. The verb only ever decides which sheet the client plays and
        how loud the noise is.
        """
        if crate.id not in self.crates:
            return
        kind = crate.type
        del self.crates[crate.id]
        # Every tile, not one: a vehicle is four wide, and leaving three of
        # them solid would leave an invisible wall where the car used to be.
        for tx, ty in crate.cells():
            self.world.set_tile(tx, ty, FLOOR)
        self.world.crates = [row.to_payload() for row in self.crates.values()]
        self.navigator.invalidate()
        self._crates_dirty = True

        if source is not None:
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
        """
        nests = getattr(self.world, "nests", None)
        if not nests or not self.zone.hostile:
            return
        types = [entry for entry, _ in ai.SPAWN_TABLE]
        if not types:
            return
        rng = random.Random(self.world.seed ^ 0x4E57)
        for x, y in nests:
            for _ in range(rng.randint(*NEST_PACK)):
                angle = rng.uniform(0, math.tau)
                radius = rng.uniform(NEST_INNER, NEST_SPREAD) * TILE_SIZE
                spot = loot.place_near(
                    self.world.tiles,
                    x + math.cos(angle) * radius,
                    y + math.sin(angle) * radius * 0.7,
                    [],
                    rng,
                )
                if spot is None:
                    continue
                self.spawn_enemy(rng.choice(types), spot[0], spot[1])

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

        THE LAST PAD OF THE NIGHT NEVER OFFERS TO KEEP LOADING. An overpayment
        only comes back while there is another console to carry it to
        (`_drop_excess`), so on the final pad saturating it buys nothing and
        the bag-reading rule would quietly eat a full pocket on the way out.
        Paid means launched there, whatever you are carrying.

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
            if target.ready and (
                not self._pads_left() or player.inventory.bag_value() <= 0
            ):
                self._shut_rift(target)
            else:
                self._feed_rift(player, target)

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

    def _feed_rift(self, player: Player, target: Rift) -> None:
        """Load the pocket onto this platform. Guns stay on the belt.

        Under the quota this pays TOWARD it and stops on the nose, so a bag
        full of relics is not swallowed whole to settle a bill of 30. Past it
        the pad takes the lot: that is the `over` path, and it is only reached
        by a player who keeps pressing a console that is already offering to
        launch.
        """
        remaining = target.need - target.fed
        if remaining <= 0:
            paid = player.inventory.spend_all()
        else:
            paid = player.inventory.spend_toward(remaining)
        if paid <= 0:
            return
        target.fed += paid
        self._rift_dirty = True
        self._roster_dirty = True
        self._sync_feed_quest(target)
        self.noises.append(
            ai.Noise(
                x=target.x,
                y=target.y,
                radius=RIFT_ACTIVATE_DIST * 3.0,
                source_id=player.id,
            )
        )

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
        target = self._stand_in_reach(player, stand_id)
        if target is None or target.sold:
            return
        if target.price > self.balance:
            return

        held = player.hotbar.equipped()
        unarmed = held is None or held.melee is not None
        slot = player.hotbar.add(target.key)
        if slot is not None and unarmed:
            player.hotbar.held = slot
        elif slot is None:
            # Belt full: the same trade a pickup gets. It refuses while the
            # knife is in hand or the hand is empty, and a refused trade must
            # not charge for a gun that was never handed over.
            slot = self.swap_weapon(player, target.key)
        if slot is None:
            return

        self.balance -= target.price
        # A GUN COMES LOADED. The merchant is the only source of firearms in
        # the game, so a purchase that handed over an empty weapon would ask
        # the party to survive a night before the thing they just spent the
        # last night earning does anything at all.
        player.ammo.grant_for(target.key)
        target.sold = True
        self._balance_dirty = True
        self._stands_dirty = True
        self._roster_dirty = True
        self._sync_store_payload()
        self.buy_events.append(
            {
                "id": target.id,
                "by": player.id,
                "k": target.key,
                "price": target.price,
                "slot": slot,
                "x": round(target.x, 2),
                "y": round(target.y, 2),
            }
        )

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
            await self.enter_store()
            return
        await self.depart_store()

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
        if self.zone.kind != zones.KIND_FOREST:
            self._pending_return = False
            return
        earned = sum(max(0, row.fed) for row in self.rifts)
        self.balance += earned
        self._balance_dirty = True
        await self._swap_map(
            zones.store(self.day),
            store.build_store(self.day, random.randrange(1, 2**31)),
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
        self._load_drops()
        self._load_crates()
        self._load_rifts()
        self._load_stands()
        self._load_entrance()
        self._rebuild_spawns()
        self.director = EnemyDirector(self.spawn_points)
        self._seed_nests()
        self.begin_arrive()
        for player in self.players.values():
            player.ready = False
            # Anybody who was down on the way out comes back up here. The
            # crossing does not tick respawn timers, so a body that fell in the
            # last seconds of the run would otherwise arrive dead somewhere
            # with nothing that could have killed it.
            player.hp = MAX_HP
            player.alive = True
            player.respawn_timer = 0.0
            player.hurt_immunity = 0.0
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
        if self.blackout:
            cmd.lantern = False
        # Ignore out-of-order / replayed inputs.
        if cmd.sequence <= player.last_processed_seq:
            return
        if player.inputs and cmd.sequence <= player.inputs[-1].sequence:
            return
        player.inputs.append(cmd)
        while len(player.inputs) > MAX_INPUT_QUEUE:
            player.inputs.popleft()

    # --- simulation ---------------------------------------------------------
    def step(self, dt: float) -> None:
        self.step_players(dt)
        self.step_seal(dt)
        self.step_quests()
        self.step_enemies(dt)
        self.step_coins(dt)
        self.step_rift(dt)

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
    def sirening(self) -> bool:
        """Any pad has called for a pickup and the aircraft are still working."""
        return any(row.alarm for row in self.rifts)

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
        for player in self.players.values():
            if player.fire_cooldown > 0.0:
                player.fire_cooldown = max(0.0, player.fire_cooldown - dt)
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
                player.respawn_timer -= dt
                if player.respawn_timer <= 0.0:
                    self.respawn(player)
                continue

            budget = MAX_INPUTS_PER_TICK if len(player.inputs) > 3 else 1
            consumed = 0
            while player.inputs and consumed < budget:
                cmd = player.inputs.popleft()
                apply_input(player, cmd, self.world, dt)
                player.hotbar.apply_held(cmd.held)
                self.handle_attack(player, cmd, dt)
                player.last_processed_seq = cmd.sequence
                player.last_input = cmd
                consumed += 1

            if consumed == 0:
                # Network jitter: briefly extrapolate the last known input so
                # remote viewers do not see a stutter.
                if player.idle_ticks < 3:
                    apply_input(player, player.last_input, self.world, dt)
                    player.hotbar.apply_held(player.last_input.held)
                    self.handle_attack(player, player.last_input, dt)
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
            self.director = EnemyDirector(self.spawn_points)
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
        for enemy_type, x, y in self.director.update(dt, self.players.values(), len(self.enemies)):
            self.spawn_enemy(enemy_type, x, y)

    def step_coins(self, dt: float) -> None:
        outcome = coins.step(self.coins, self.players.values(), dt)
        for pickup in outcome.collected:
            self.pickup_events.append(pickup.to_payload())

    def spawn_enemy(self, enemy_type: EnemyType, x: float, y: float) -> Enemy:
        self._enemy_id += 1
        enemy = Enemy(id=f"e{self._enemy_id}", type=enemy_type, x=x, y=y)
        dress(enemy)
        self.enemies[enemy.id] = enemy
        if self.panic:
            living = [p for p in self.players.values() if p.alive]
            if living:
                target = min(
                    living,
                    key=lambda p: (p.x - enemy.x) ** 2 + (p.y - enemy.y) ** 2,
                )
                ai.commit(enemy, target)
        return enemy

    def resolve_attack(self, attack: ai.Attack) -> None:
        """Apply one melee swing, honouring the victim's i-frames.

        A blocked swing is still broadcast: the player needs to see that the
        zombie hit them and it did nothing, otherwise the immunity window reads
        as the server dropping hits.
        """
        enemy = attack.enemy
        target = attack.target
        blocked = not target.alive or target.hurt_immunity > 0.0
        damage = 0 if blocked else enemy.type.damage

        if not blocked:
            target.hurt_immunity = MELEE_IMMUNITY
            self.damage_player(target, damage, None)

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
        if not player.ammo.spend(ammo.calibre_of(weapon.key)):
            player.fire_cooldown = weapon.fire_cooldown
            return
        player.fire_cooldown = weapon.fire_cooldown
        self._roster_dirty = True
        self.fire(player, cmd.aim_x, cmd.aim_y, weapon)

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

        self._swing_id += 1
        rows = []
        for hit in hits:
            rows.append({"id": hit.target.id, "dmg": step.damage})
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

        for hit in hits:
            victim = hit.target
            if isinstance(victim, Enemy):
                self.damage_enemy(victim, step.damage, attacker, hit.dx, hit.dy)
            else:
                self.damage_player(victim, step.damage, attacker)

    def fire(self, shooter: Player, dx: float, dy: float, weapon: weapons.WeaponDef) -> None:
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
        hit = combat.raycast(
            self.world,
            ox,
            oy,
            dx,
            dy,
            weapon.range,
            targets,
            ignore_id=shooter.id,
        )
        # The foot tile is only the contact. Aiming at the barrel has to
        # count, so the sprite box is tested against the same ray — closer
        # than the wall or the body the DDA already found.
        crate, crate_dist = crates.along_ray(self.crates, ox, oy, dx, dy, hit.distance)
        self._shot_id += 1
        victim = None if crate is not None else hit.target
        dist = crate_dist if crate is not None else hit.distance
        self.shot_events.append(
            {
                "id": self._shot_id,
                "by": shooter.id,
                "k": weapon.key,
                "x": round(ox, 2),
                "y": round(oy, 2),
                "dx": round(dx, 3),
                "dy": round(dy, 3),
                "dist": round(dist, 2),
                "hit": victim.id if victim is not None else None,
                "dmg": weapon.damage if victim is not None else 0,
            }
        )
        if crate is not None:
            self.smash_crate(crate, shooter)
        elif isinstance(victim, Enemy):
            self.damage_enemy(victim, weapon.damage, shooter, dx, dy)
        elif victim is not None:
            self.damage_player(victim, weapon.damage, shooter)

    def damage_player(self, target: Player, amount: int, source: Player | None) -> None:
        if not target.alive:
            return
        target.hp -= amount
        if target.hp <= 0:
            target.hp = 0
            target.alive = False
            target.deaths += 1
            target.respawn_timer = RESPAWN_DELAY
            target.vx = target.vy = 0.0
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
        if source is not None:
            source.kills += 1
            source.xp += reward.xp
        # xp is what the kill is worth and never varies; coins are what fell
        # out of this particular corpse, which does.
        dropped = coins.roll_drop(reward.gold)
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
            "xp": reward.xp,
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
        player.hp = MAX_HP
        player.alive = True
        player.vx = player.vy = 0.0
        player.respawn_timer = 0.0
        player.idle_ticks = 0
        player.combo_step = 0
        player.combo_left = 0.0
        # Grace period: respawning into a waiting pack is not a fair death.
        player.hurt_immunity = RESPAWN_IMMUNITY
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
        stand_rows = (
            [row.to_payload() for row in self.stands] if self._stands_dirty else None
        )
        self._stands_dirty = False
        balance_row = self.balance if self._balance_dirty else None
        self._balance_dirty = False
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
                crates=crate_rows,
                crate_breaks=self.crate_break_events or None,
                corpses=corpse_rows,
                rifts=rift_rows,
                entrance=entrance_row,
                tile_patches=tile_patches,
                quests=quest_rows,
                egress=egress_row,
                blackout=blackout_flag,
                stands=stand_rows,
                buys=self.buy_events or None,
                balance=balance_row,
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
                self.swing_events = []
                self.attack_events = []
                self.kill_events = []
                self.pickup_events = []
                self.loot_pickup_events = []
                self.crate_break_events = []
                self.buy_events = []
            delay = next_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Fell behind: drop the accumulated debt instead of spiralling.
                next_time = time.perf_counter()
