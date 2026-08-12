"""FastAPI entrypoint: one WebSocket endpoint + a health route.

Run with:  uvicorn app.main:app --reload --port 8000   (from server/)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import protocol
from .room import get_room


@asynccontextmanager
async def lifespan(app: FastAPI):
    room = get_room()
    room.start()
    yield
    await room.stop()


app = FastAPI(title="zombie-roguelike server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    room = get_room()
    return {
        "ok": True,
        "tick": room.tick,
        "players": len(room.players),
        "enemies": len(room.enemies),
    }


@app.websocket("/ws")
async def game_socket(ws: WebSocket):
    await ws.accept()
    room = get_room()
    player = room.add_player(ws)
    try:
        await ws.send_text(json.dumps(room.welcome_payload(player)))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind == protocol.MSG_INPUT:
                room.queue_input(player.id, msg)
            elif kind == protocol.MSG_PING:
                await ws.send_text(
                    json.dumps({"type": protocol.MSG_PONG, "t": msg.get("t")})
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        room.remove_player(player.id)
