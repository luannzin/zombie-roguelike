"""Wire protocol.

Everything is JSON text over a single WebSocket. Keep this file the single
source of truth for message shapes; client/src/net/protocol.ts mirrors it.

client -> server
  {"type":"input","sequence":183,
   "movement":{"up":true,"down":false,"left":false,"right":true},
   "aim":{"x":0.72,"y":-0.69},"shoot":true}
  {"type":"ping","t":<client ms>}

server -> client
  {"type":"welcome","playerId":"...","player":{...},"config":{...},"map":{...}}
  {"type":"snapshot","tick":N,"ack":<last processed input seq for you>,
   "players":[...],"enemies":[...],"coins":[...],
   "shots":[...],"attacks":[...],"kills":[...],"pickups":[...]}
  {"type":"pong","t":<echoed>}

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

MSG_WELCOME = "welcome"
MSG_SNAPSHOT = "snapshot"
MSG_PONG = "pong"


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
