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

from . import ai, camp, coins, combat, crates, loot, mapgen, protocol, zones
from .ai import EnemyDirector
from .coins import Coin
from .config import (
    CRATE_BREAK_DIST,
    CRATE_NOISE_DIST,
    DT,
    FIRE_COOLDOWN,
    LOOT_COLLECT_DIST,
    MARCH_SPEED,
    MAX_HP,
    MAX_INPUT_QUEUE,
    MAX_INPUTS_PER_TICK,
    MELEE_IMMUNITY,
    MUZZLE_OFFSET,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    RESPAWN_DELAY,
    RESPAWN_IMMUNITY,
    ROSTER_EVERY_N_TICKS,
    SHOT_DAMAGE,
    SHOT_NOISE_DIST,
    SHOT_RANGE,
    SNAPSHOT_EVERY_N_TICKS,
    SPAWN_RING,
    SPAWN_SEPARATION,
    TILE_SIZE,
    client_config,
)
from .crates import Crate
from .loot import Drop
from .enemies import Enemy, EnemyType
from .world import FLOOR
from .entities import InputCmd, Player, clean_name, pick_color, random_name
from .pathing import Navigator
from .simulation import apply_input


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
        self.spawn_points = self.world.free_spawn_points(PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT)
        # Spawn candidates, best first: closest to the ring around the centre
        # clearing. Sorted once here so pick_spawn is a linear scan, not a sort
        # on every join and every respawn.
        centre_x = self.world.pixel_width / 2
        centre_y = self.world.pixel_height / 2
        # The jitter matters: without it the list is ordered by distance alone,
        # so a filling room hands out spawns that walk monotonically around the
        # ring instead of landing wherever there is room.
        self.spawn_ring = sorted(
            self.spawn_points,
            key=lambda p: (
                abs(math.hypot(p[0] - centre_x, p[1] - centre_y) - SPAWN_RING)
                + random.uniform(0.0, SPAWN_SEPARATION)
            ),
        )
        self.players: dict[str, Player] = {}
        self.enemies: dict[str, Enemy] = {}
        self.coins: dict[str, Coin] = {}
        self.drops: dict[str, Drop] = {}
        self.crates: dict[str, Crate] = {}
        self.sockets: dict[str, object] = {}
        self.director = EnemyDirector(self.spawn_points)
        self.navigator = Navigator(self.world)
        self.tick = 0
        self.shot_events: list[dict] = []
        #: Things enemies can HEAR, made this tick and consumed by the next
        #: `ai.update`. A gunshot is the only source so far; anything else the
        #: player does loudly is one more append (see `ai.Noise`).
        self.noises: list[ai.Noise] = []
        self.attack_events: list[dict] = []
        self.kill_events: list[dict] = []
        self.pickup_events: list[dict] = []
        self.loot_pickup_events: list[dict] = []
        self.crate_break_events: list[dict] = []
        self._shot_id = 0
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
        #: Someone joined or left: attach the roster to the next snapshot
        #: instead of making the party wait out the interval for a name.
        self._roster_dirty = True
        #: A drop was collected or tossed: attach the remaining loot list next tick.
        self._loot_dirty = True
        self._loot_seq = 0
        self._crates_dirty = True
        self._load_drops()
        self._load_crates()

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
        """A tile on the ring around the centre clearing, clear of teammates.

        Co-op: everyone lands together in the middle. The separation test only
        stops players from spawning inside each other — it does not push them
        apart, so a full room still starts as one group.
        """
        living = [p for p in self.players.values() if p.alive]
        minimum = SPAWN_SEPARATION * SPAWN_SEPARATION
        for x, y in self.spawn_ring:
            if all((p.x - x) ** 2 + (p.y - y) ** 2 >= minimum for p in living):
                return x, y
        # Every ring tile is occupied (a very full room): take the centre-most
        # one anyway rather than scattering someone across the map.
        return self.spawn_ring[0] if self.spawn_ring else random.choice(self.spawn_points)

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
        if self.phase != protocol.PHASE_PLAYING or self.departing:
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
        if self.phase != protocol.PHASE_PLAYING or self.departing:
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
        slot = player.inventory.add(drop.key)
        if slot is None:
            return
        del self.drops[drop_id]
        self.loot_pickup_events.append(
            loot.LootPickup(drop.id, player.id, drop.key, drop.x, drop.y, slot).to_payload()
        )
        self._loot_dirty = True
        self._roster_dirty = True

    def break_crate(self, pid: str, crate_id: str) -> None:
        """Smash a crate if this player is standing on it.

        Walk-out is too late. Distance is measured from the feet, the same
        way collect is. Camp allows it — the stores are furniture, not scenery
        you cannot touch. A shot that lands on the tile does the same work
        through `smash_crate`.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing:
            return
        player = self.players.get(pid)
        if player is None or not player.alive:
            return
        crate = self.crates.get(crate_id)
        if crate is None:
            return
        feet_y = player.y + PLAYER_HALF_HEIGHT
        if (crate.x - player.x) ** 2 + (crate.y - feet_y) ** 2 > CRATE_BREAK_DIST * CRATE_BREAK_DIST:
            return
        self.smash_crate(crate, player)

    def smash_crate(self, crate: Crate, source: Player | None) -> None:
        """Remove a crate, open its tile, and roll what falls out."""
        if crate.id not in self.crates:
            return
        del self.crates[crate.id]
        self.world.set_tile(crate.tx, crate.ty, FLOOR)
        self.world.crates = [row.to_payload() for row in self.crates.values()]
        self.navigator.invalidate()
        self._crates_dirty = True

        if source is not None:
            self.noises.append(
                ai.Noise(x=crate.x, y=crate.y, radius=CRATE_NOISE_DIST, source_id=source.id)
            )

        rng = random.Random()
        kind, item_key, coin_count = crates.roll_drop(rng)
        if kind == crates.DROP_COIN:
            self.drop_coins(crate.x, crate.y, coin_count)
        elif kind == crates.DROP_ITEM and item_key:
            drop_id = self._next_drop_id()
            self.drops[drop_id] = Drop(
                id=drop_id,
                key=item_key,
                x=(crate.tx + 0.5) * TILE_SIZE,
                y=(crate.ty + 0.5) * TILE_SIZE,
            )
            self._loot_dirty = True

        self.crate_break_events.append(
            crates.CrateBreak(
                crate.id, crate.x, crate.y, crate.variant, crate.flip, kind, item_key
            ).to_payload()
        )

    def drop_loot(self, pid: str, slot: int) -> None:
        """Toss a bag slot onto the ground near this player's feet.

        Camp has none, and the walk-out is too late. A stack becomes one
        world drop per unit — the ground list has no quantity. Placement
        is walkable floor around the feet; the server picks the tiles.
        """
        if self.phase != protocol.PHASE_PLAYING or self.departing:
            return
        if self.zone.kind == zones.KIND_CAMP:
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
            self.drops[drop_id] = Drop(id=drop_id, key=taken.key, x=px, y=py)
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

        Same phase, new zone, new map. The client treats a second `welcome` as
        arriving somewhere: intro, title card, lantern on. Nobody is persisted
        across this — gold and xp they have not earned yet stay zero.
        """
        if self.zone.kind != zones.KIND_CAMP:
            self._pending_embark = False
            return
        self.departing = False
        self._pending_embark = False
        self._depart_phase = None
        self._slots = {}
        self.zone = zones.forest(self.day)
        self.world = mapgen.build_forest()
        self.spawn_points = self.world.free_spawn_points(
            PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT
        )
        centre_x = self.world.pixel_width / 2
        centre_y = self.world.pixel_height / 2
        self.spawn_ring = sorted(
            self.spawn_points,
            key=lambda p: (
                abs(math.hypot(p[0] - centre_x, p[1] - centre_y) - SPAWN_RING)
                + random.uniform(0.0, SPAWN_SEPARATION)
            ),
        )
        self.navigator = Navigator(self.world)
        self.director = EnemyDirector(self.spawn_points)
        self.enemies.clear()
        self.coins.clear()
        self.noises.clear()
        self._load_drops()
        self._load_crates()
        self.crate_break_events = []
        for player in self.players.values():
            player.ready = False
            player.x, player.y = self.pick_spawn()
            player.vx = player.vy = 0.0
            player.aim_x = 0.0
            player.aim_y = 1.0
            player.inputs.clear()
            player.idle_ticks = 0
            # Sequence is NOT reset. The client has been numbering packets since
            # the camp, and queue_input drops anything ≤ last_processed_seq.
            player.last_input = InputCmd(sequence=player.last_processed_seq)
        for pid, socket in list(self.sockets.items()):
            player = self.players.get(pid)
            if player is not None:
                await self._safe_send(
                    pid, socket, protocol.dumps(self.welcome_payload(player))
                )

    # --- input --------------------------------------------------------------
    def queue_input(self, pid: str, msg: dict) -> None:
        player = self.players.get(pid)
        if player is None:
            return
        cmd = InputCmd.from_message(msg)
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
        self.step_enemies(dt)
        self.step_coins(dt)

    def step_players(self, dt: float) -> None:
        if self.departing:
            self.step_depart(dt)
            return
        for player in self.players.values():
            if player.fire_cooldown > 0.0:
                player.fire_cooldown = max(0.0, player.fire_cooldown - dt)
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
                self.handle_shooting(player, cmd, dt)
                player.last_processed_seq = cmd.sequence
                player.last_input = cmd
                consumed += 1

            if consumed == 0:
                # Network jitter: briefly extrapolate the last known input so
                # remote viewers do not see a stutter.
                if player.idle_ticks < 3:
                    apply_input(player, player.last_input, self.world, dt)
                    self.handle_shooting(player, player.last_input, dt)
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

    def step_enemies(self, dt: float) -> None:
        """Advance the pack, resolve its swings, then top the population up."""
        # A safe zone has no director and, having never spawned anything, no
        # pack to advance. Checked here rather than in `step` so a zone that
        # turns hostile mid-run still finishes whatever is already on the map.
        if not self.zone.hostile and not self.enemies:
            self.noises.clear()
            return
        outcome = ai.update(
            self.enemies.values(),
            self.players.values(),
            self.world,
            self.navigator,
            dt,
            self.noises,
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
        self.enemies[enemy.id] = enemy
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

    def handle_shooting(self, player: Player, cmd: InputCmd, dt: float) -> None:
        # Nobody fires in a safe zone. The camp has nothing to shoot at except
        # the person standing next to you at the fire.
        if not self.zone.hostile:
            return
        if not cmd.shoot or not player.alive or player.fire_cooldown > 0.0:
            return
        player.fire_cooldown = FIRE_COOLDOWN
        self.fire(player, cmd.aim_x, cmd.aim_y)

    def fire(self, shooter: Player, dx: float, dy: float) -> None:
        ox = shooter.x + dx * MUZZLE_OFFSET
        oy = shooter.y + dy * MUZZLE_OFFSET
        # A gun is loud. Everything in earshot that has not already noticed
        # somebody now has a direction to look in — and, close enough to the
        # muzzle, a person to walk at. See ai.Noise.
        self.noises.append(
            ai.Noise(x=shooter.x, y=shooter.y, radius=SHOT_NOISE_DIST, source_id=shooter.id)
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
            SHOT_RANGE,
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
                "x": round(ox, 2),
                "y": round(oy, 2),
                "dx": round(dx, 3),
                "dy": round(dy, 3),
                "dist": round(dist, 2),
                "hit": victim.id if victim is not None else None,
            }
        )
        if crate is not None:
            self.smash_crate(crate, shooter)
        elif isinstance(victim, Enemy):
            self.damage_enemy(victim, SHOT_DAMAGE, shooter)
        elif victim is not None:
            self.damage_player(victim, SHOT_DAMAGE, shooter)

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

    def damage_enemy(self, target: Enemy, amount: int, source: Player | None) -> None:
        """Hurt an enemy; on death pay xp and scatter gold as world coins."""
        if not target.alive:
            return
        target.hp -= amount
        # Shot in the back is still shot: damage wakes it regardless of where
        # its sight cone happens to be pointing.
        ai.alarm(target, source)
        if target.hp > 0:
            return

        target.hp = 0
        target.alive = False
        self.enemies.pop(target.id, None)

        reward = target.type
        if source is not None:
            source.kills += 1
            source.xp += reward.xp
        self.drop_coins(target.x, target.y, reward.gold)
        self.kill_events.append(
            {
                "kind": "enemy",
                "killer": source.id if source else None,
                "victim": target.id,
                "x": round(target.x, 2),
                "y": round(target.y, 2),
                "xp": reward.xp,
                "gold": reward.gold,
            }
        )

    def drop_coins(self, x: float, y: float, count: int) -> None:
        """Scatter `count` single-value coins from a death point."""
        total = max(0, count)
        for i in range(total):
            self._coin_id += 1
            coin = coins.spawn_burst(f"c{self._coin_id}", x, y, i, total)
            self.coins[coin.id] = coin

    def respawn(self, player: Player) -> None:
        # In a safe zone you come back to your own seat at the fire, not to a
        # ring tile somewhere in the trees.
        if not self.zone.hostile and player.id in self.seating:
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
                departing=self.departing,
                zone_key=self.zone.key,
                roster=roster,
                loot=loot_rows,
                loot_pickups=self.loot_pickup_events or None,
                crates=crate_rows,
                crate_breaks=self.crate_break_events or None,
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
            if self.tick % SNAPSHOT_EVERY_N_TICKS == 0:
                await self.broadcast_snapshot()
                self.shot_events = []
                self.attack_events = []
                self.kill_events = []
                self.pickup_events = []
                self.loot_pickup_events = []
                self.crate_break_events = []
            delay = next_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Fell behind: drop the accumulated debt instead of spiralling.
                next_time = time.perf_counter()
