"""The game room: authoritative state + fixed-tick simulation loop.

One process currently hosts exactly one room (`get_room()`), which is all the
vertical slice needs. Multiple rooms later = a dict of Room instances keyed by
id, plus a room id in the WebSocket path; nothing in this class assumes it is
a singleton.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import uuid

from . import ai, combat, protocol
from .ai import EnemyDirector
from .config import (
    DT,
    FIRE_COOLDOWN,
    MAX_HP,
    MAX_INPUT_QUEUE,
    MAX_INPUTS_PER_TICK,
    MELEE_IMMUNITY,
    MUZZLE_OFFSET,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    RESPAWN_DELAY,
    RESPAWN_IMMUNITY,
    SHOT_DAMAGE,
    SHOT_RANGE,
    SNAPSHOT_EVERY_N_TICKS,
    client_config,
)
from .enemies import Enemy, EnemyType
from .entities import InputCmd, Player, random_color, random_name
from .maps import build_arena
from .pathing import Navigator
from .simulation import apply_input


class Room:
    def __init__(self):
        self.world = build_arena()
        self.spawn_points = self.world.free_spawn_points(PLAYER_HALF_WIDTH, PLAYER_HALF_HEIGHT)
        self.players: dict[str, Player] = {}
        self.enemies: dict[str, Enemy] = {}
        self.sockets: dict[str, object] = {}
        self.director = EnemyDirector(self.spawn_points)
        self.navigator = Navigator(self.world)
        self.tick = 0
        self.shot_events: list[dict] = []
        self.attack_events: list[dict] = []
        self.kill_events: list[dict] = []
        self._shot_id = 0
        self._enemy_id = 0
        self._task: asyncio.Task | None = None

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
        """Random free tile, biased away from other players."""
        best = None
        best_score = -1.0
        for _ in range(12):
            x, y = random.choice(self.spawn_points)
            if not self.players:
                return x, y
            score = min(
                (p.x - x) ** 2 + (p.y - y) ** 2 for p in self.players.values() if p.alive
            ) if any(p.alive for p in self.players.values()) else 1e9
            if score > best_score:
                best_score = score
                best = (x, y)
        return best or random.choice(self.spawn_points)

    def add_player(self, socket) -> Player:
        pid = uuid.uuid4().hex[:8]
        x, y = self.pick_spawn()
        player = Player(
            id=pid,
            name=random_name({p.name for p in self.players.values()}),
            color=random_color(),
            x=x,
            y=y,
        )
        self.players[pid] = player
        self.sockets[pid] = socket
        return player

    def remove_player(self, pid: str) -> None:
        self.players.pop(pid, None)
        self.sockets.pop(pid, None)

    def welcome_payload(self, player: Player) -> dict:
        return protocol.welcome(
            player.to_payload(), client_config(), self.world.to_payload()
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

    def step_players(self, dt: float) -> None:
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

    def step_enemies(self, dt: float) -> None:
        """Advance the pack, resolve its swings, then top the population up."""
        outcome = ai.update(
            self.enemies.values(), self.players.values(), self.world, self.navigator, dt
        )
        for attack in outcome.attacks:
            self.resolve_attack(attack)
        for stranded in outcome.despawned:
            self.enemies.pop(stranded.id, None)

        for enemy_type, x, y in self.director.update(dt, self.players.values(), len(self.enemies)):
            self.spawn_enemy(enemy_type, x, y)

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
        if not cmd.shoot or not player.alive or player.fire_cooldown > 0.0:
            return
        player.fire_cooldown = FIRE_COOLDOWN
        self.fire(player, cmd.aim_x, cmd.aim_y)

    def fire(self, shooter: Player, dx: float, dy: float) -> None:
        ox = shooter.x + dx * MUZZLE_OFFSET
        oy = shooter.y + dy * MUZZLE_OFFSET
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
        self._shot_id += 1
        victim = hit.target
        self.shot_events.append(
            {
                "id": self._shot_id,
                "by": shooter.id,
                "x": round(ox, 2),
                "y": round(oy, 2),
                "dx": round(dx, 3),
                "dy": round(dy, 3),
                "dist": round(hit.distance, 2),
                "hit": victim.id if victim is not None else None,
            }
        )
        if isinstance(victim, Enemy):
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
        """Hurt an enemy; on death pay its stat block out to the killer."""
        if not target.alive:
            return
        target.hp -= amount
        if target.hp > 0:
            return

        target.hp = 0
        target.alive = False
        self.enemies.pop(target.id, None)

        reward = target.type
        if source is not None:
            source.kills += 1
            source.xp += reward.xp
            source.gold += reward.gold
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

    def respawn(self, player: Player) -> None:
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
    async def broadcast_snapshot(self) -> None:
        if not self.sockets:
            return
        players = [p.to_payload() for p in self.players.values()]
        enemies = [e.to_payload() for e in self.enemies.values()]
        shots = self.shot_events
        attacks = self.attack_events
        kills = self.kill_events

        sends = []
        for pid, socket in list(self.sockets.items()):
            player = self.players.get(pid)
            ack = player.last_processed_seq if player else 0
            payload = protocol.snapshot(self.tick, ack, players, enemies, shots, attacks, kills)
            sends.append(self._safe_send(pid, socket, json.dumps(payload)))
        await asyncio.gather(*sends, return_exceptions=True)

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
            if self.tick % SNAPSHOT_EVERY_N_TICKS == 0:
                await self.broadcast_snapshot()
                self.shot_events = []
                self.attack_events = []
                self.kill_events = []
            delay = next_time - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Fell behind: drop the accumulated debt instead of spiralling.
                next_time = time.perf_counter()


_room: Room | None = None


def get_room() -> Room:
    global _room
    if _room is None:
        _room = Room()
    return _room
