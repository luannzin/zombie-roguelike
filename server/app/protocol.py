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
   "players":[...],"shots":[...],"kills":[...]}
  {"type":"pong","t":<echoed>}
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


def snapshot(tick: int, ack: int, players: list[dict], shots: list[dict], kills: list[dict]) -> dict:
    return {
        "type": MSG_SNAPSHOT,
        "tick": tick,
        "ack": ack,
        "players": players,
        "shots": shots,
        "kills": kills,
    }
