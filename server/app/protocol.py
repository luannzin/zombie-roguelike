"""Wire protocol.

Everything is JSON text over a single WebSocket. Keep this file the single
source of truth for message shapes; client/src/net/protocol.ts mirrors it.

The socket is opened at `/ws/{code}?name=...` and carries BOTH phases of a
room. A connection starts in the lobby (`hello`, then `lobby` on every
membership change) and moves into the arena when the host sends `start`, at
which point everyone receives `welcome` and the snapshot stream begins. There
is no second socket and no re-handshake.

client -> server
  {"type":"input","sequence":183,
   "movement":{"up":true,"down":false,"left":false,"right":true},
   "aim":{"x":0.72,"y":-0.69},"shoot":true,"lantern":true}
  {"type":"ping","t":<client ms>}
  {"type":"start"}                      host only; ignored otherwise
  {"type":"ready"}                      toggle ready, camp only, near the fire
  {"type":"collect","id":"l3"}          pick up a loot drop; ignored if too far
                                        or the bag has no slot for that key
  {"type":"drop","slot":0}              pull a bag slot back onto the ground
                                        near the player's feet; ignored in camp

server -> client
  {"type":"hello","playerId":"...","code":"ABC1234",
   "config":{...},"map":{...},"zone":{...}}          once, first message
  {"type":"lobby","code":"ABC1234","hostId":"...","phase":"lobby"|"playing",
   "zone":{...},"players":[{"id","name","color","x","y"}]}
                                        on every membership/phase change
  {"type":"error","code":"room_not_found"}  followed by a close
  {"type":"welcome","playerId":"...","player":{...},"config":{...},"map":{...},
   "zone":{...},"ack":<last processed input seq for you>}
  {"type":"snapshot","tick":N,"departing":false,"zoneKey":"camp-1",
   "players":[...],"enemies":[...],"coins":[...],
   "shots":[...],"attacks":[...],"kills":[...],"pickups":[...],
   "loot":[...],"lootPickups":[...],
   "roster":[...]}                    only every ROSTER_EVERY_N_TICKS ticks
  {"type":"pong","t":<echoed>}

`hello` exists because `lobby` is one payload broadcast to everybody: telling
each client which row is theirs has to happen in a message only they receive.
It also carries the MAP, because the lobby is not a picture of the camp — it is
the camp, drawn before anyone may walk on it. The roster rows carry real world
positions for the same reason: the seat a player is standing on at the fire is
the tile they start `preparation` on, so the lobby cannot invent its own layout.

`zone` says where the room is and how that place behaves — see zones.py. It is
on all three messages because all three can be the first thing a client learns
about a room it just joined.

The `map` payload is `{width, height, tileSize, seed, tiles, propKinds, props}`.
`seed` is what the client hashes with a tile coordinate to scatter the FOREST —
soil, grass, ferns, litter — so texture costs four bytes and never repeats.
`props` is the other half and it is the opposite kind of thing: the SCENES
`scenery.py` placed, which cannot be re-derived from a hash because their whole
value is that the pieces know about each other. Each row is
`[kindIndex, x, y, variant, flip, layer]` against the `propKinds` legend, with
x/y in world pixels — a contact point for a standing prop, a centre for a flat
one — and `layer` 0 flat / 1 standing. `variant` is taken modulo the sheet's
frame count client-side, except for `tracks`, where it is a compass point.

A snapshot is IDENTICAL for every socket in the room — it is serialised once a
tick and the same string is written to all of them. That is why the per-player
ack rides on each player's own row (`seq`) instead of at the top level: one
field that differed per recipient would cost a re-serialisation each.

Snapshot arrays:
  players   what moves, every tick; `seq` is that player's own input ack
  roster    the same players with their name, colour and score board, sent
            every ROSTER_EVERY_N_TICKS and on any membership change. A client
            caches it: those fields feed a 5 Hz HUD and never change per tick
  enemies   live enemies only; `t` keys into welcome.config.enemyTypes.
            `aw` is the 0..1 detection meter — it fills while a player stands
            in the creature's sight cone and is pinned at 1 while it hunts.
            The client fills the hunt diamond with it; the cone's own reach
            and width are per-type and ride the config, not the tick, and
            are not drawn
  coins     live gold pickups (one per gold point dropped)
  shots     hitscan tracers fired since the last snapshot
  attacks   enemy melee swings; `dmg` is 0 when the victim's i-frames ate it
  kills     deaths since the last snapshot, players and enemies alike
            ({"kind":"enemy"} entries: xp paid now; gold = coins spawned)
  pickups   coins collected since the last snapshot
  loot      remaining world drops; attached like the roster — on welcome,
            and again on a snapshot only when the ground list changed
            (collect or a bag toss)
  lootPickups  drops collected since the last snapshot (juice). `slot` is
               the bag index it landed in, so the client can fly the sprite
               from the world onto that HUD cell.
"""

from __future__ import annotations

import json

MSG_INPUT = "input"
MSG_PING = "ping"
MSG_START = "start"
MSG_READY = "ready"
MSG_COLLECT = "collect"
MSG_DROP = "drop"

MSG_HELLO = "hello"
MSG_LOBBY = "lobby"
MSG_ERROR = "error"
MSG_WELCOME = "welcome"
MSG_SNAPSHOT = "snapshot"
MSG_PONG = "pong"

PHASE_LOBBY = "lobby"
PHASE_PLAYING = "playing"

# Error codes. The client owns the wording — these only have to be stable.
ERR_ROOM_NOT_FOUND = "room_not_found"


def hello(
    player_id: str, code: str, config: dict, map_payload: dict, zone: dict
) -> dict:
    return {
        "type": MSG_HELLO,
        "playerId": player_id,
        "code": code,
        "config": config,
        "map": map_payload,
        "zone": zone,
    }


def lobby(
    code: str, host_id: str | None, phase: str, zone: dict, players: list[dict]
) -> dict:
    return {
        "type": MSG_LOBBY,
        "code": code,
        "hostId": host_id,
        "phase": phase,
        "zone": zone,
        "players": players,
    }


def error(code: str) -> dict:
    return {"type": MSG_ERROR, "code": code}


def welcome(
    player_payload: dict,
    config: dict,
    map_payload: dict,
    zone: dict,
    ack: int = 0,
    loot: list[dict] | None = None,
) -> dict:
    return {
        "type": MSG_WELCOME,
        "playerId": player_payload["id"],
        "player": player_payload,
        "config": config,
        "map": map_payload,
        "zone": zone,
        # Same meaning as snapshot.ack: the client must keep issuing sequences
        # above this, or queue_input drops every packet as a replay.
        "ack": ack,
        "loot": loot or [],
    }


def dumps(payload: dict) -> str:
    """The only place a message becomes text. Compact separators, because at
    30 Hz the default `", "` / `": "` padding is ~14% of every snapshot."""
    return json.dumps(payload, separators=(",", ":"))


def snapshot(
    tick: int,
    players: list[dict],
    enemies: list[dict],
    coins: list[dict],
    shots: list[dict],
    attacks: list[dict],
    kills: list[dict],
    pickups: list[dict],
    departing: bool = False,
    zone_key: str | None = None,
    roster: list[dict] | None = None,
    loot: list[dict] | None = None,
    loot_pickups: list[dict] | None = None,
) -> dict:
    payload = {
        "type": MSG_SNAPSHOT,
        "tick": tick,
        "departing": departing,
        "zoneKey": zone_key,
        "players": players,
        "enemies": enemies,
        "coins": coins,
        "shots": shots,
        "attacks": attacks,
        "kills": kills,
        "pickups": pickups,
    }
    # Absent on most ticks — see ROSTER_EVERY_N_TICKS.
    if roster is not None:
        payload["roster"] = roster
    if loot is not None:
        payload["loot"] = loot
    if loot_pickups:
        payload["lootPickups"] = loot_pickups
    return payload
