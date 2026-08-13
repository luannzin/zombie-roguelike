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

server -> client
  {"type":"hello","playerId":"...","code":"ABC1234"}   once, first message
  {"type":"lobby","code":"ABC1234","hostId":"...","phase":"lobby"|"playing",
   "players":[{"id","name","color"}]}   on every membership/phase change
  {"type":"error","code":"room_not_found"}  followed by a close
  {"type":"welcome","playerId":"...","player":{...},"config":{...},"map":{...}}
  {"type":"snapshot","tick":N,"ack":<last processed input seq for you>,
   "players":[...],"enemies":[...],"coins":[...],
   "shots":[...],"attacks":[...],"kills":[...],"pickups":[...]}
  {"type":"pong","t":<echoed>}

`hello` exists because `lobby` is one payload broadcast to everybody: telling
each client which row is theirs has to happen in a message only they receive.

Snapshot arrays:
  players   full state, every tick
  enemies   live enemies only; `t` keys into welcome.config.enemyTypes
  coins     live gold pickups (one per gold point dropped)
  shots     hitscan tracers fired since the last snapshot
  attacks   enemy melee swings; `dmg` is 0 when the victim's i-frames ate it
  kills     deaths since the last snapshot, players and enemies alike
            ({"kind":"enemy"} entries: xp paid now; gold = coins spawned)
  pickups   coins collected since the last snapshot
"""

from __future__ import annotations

MSG_INPUT = "input"
MSG_PING = "ping"
MSG_START = "start"

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


def hello(player_id: str, code: str) -> dict:
    return {"type": MSG_HELLO, "playerId": player_id, "code": code}


def lobby(code: str, host_id: str | None, phase: str, players: list[dict]) -> dict:
    return {
        "type": MSG_LOBBY,
        "code": code,
        "hostId": host_id,
        "phase": phase,
        "players": players,
    }


def error(code: str) -> dict:
    return {"type": MSG_ERROR, "code": code}


def welcome(player_payload: dict, config: dict, map_payload: dict) -> dict:
    return {
        "type": MSG_WELCOME,
        "playerId": player_payload["id"],
        "player": player_payload,
        "config": config,
        "map": map_payload,
    }


def snapshot(
    tick: int,
    ack: int,
    players: list[dict],
    enemies: list[dict],
    coins: list[dict],
    shots: list[dict],
    attacks: list[dict],
    kills: list[dict],
    pickups: list[dict],
) -> dict:
    return {
        "type": MSG_SNAPSHOT,
        "tick": tick,
        "ack": ack,
        "players": players,
        "enemies": enemies,
        "coins": coins,
        "shots": shots,
        "attacks": attacks,
        "kills": kills,
        "pickups": pickups,
    }
