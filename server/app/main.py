"""FastAPI entrypoint: room REST + one WebSocket endpoint per room.

Run with:  uvicorn app.main:app --reload --port 8000   (from server/)

    POST /rooms          -> {"code": "ABC1234"}   creates a room + its forest
    GET  /rooms/{code}   -> {"code","phase","players"}  or 404
    WS   /ws/{code}?name=…                        lobby, then arena

The REST pair exists so the menu can tell a player their code is wrong while
they are still typing it, instead of routing them into a room screen that
immediately fails.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import protocol, rooms


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Every live room owns a tick task; leaving them running past shutdown
    # keeps the event loop alive and hangs reload.
    for room in rooms.all_rooms():
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
    live = rooms.all_rooms()
    return {
        "ok": True,
        "rooms": len(live),
        "players": sum(len(r.players) for r in live),
    }


@app.post("/rooms")
async def create_room():
    return {"code": rooms.create().code}


@app.get("/rooms/{code}")
async def room_info(code: str):
    room = rooms.get(code)
    if room is None:
        raise HTTPException(status_code=404, detail=protocol.ERR_ROOM_NOT_FOUND)
    return {"code": room.code, "phase": room.phase, "players": len(room.players)}


@app.websocket("/ws/{code}")
async def game_socket(ws: WebSocket, code: str, name: str | None = None):
    await ws.accept()
    room = rooms.get(code)
    if room is None:
        await ws.send_text(protocol.dumps(protocol.error(protocol.ERR_ROOM_NOT_FOUND)))
        await ws.close()
        return

    player = room.add_player(ws, name)
    try:
        # `hello` carries the camp map: the lobby draws the real thing, so this
        # is the first and only time it has to travel for a player who never
        # leaves it.
        await ws.send_text(protocol.dumps(room.hello_payload(player)))
        await room.broadcast_lobby()
        # Joining a run already in progress: skip the campfire and drop straight
        # into whatever zone the room is in.
        if room.phase == protocol.PHASE_PLAYING:
            await ws.send_text(protocol.dumps(room.welcome_payload(player)))

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
                    protocol.dumps({"type": protocol.MSG_PONG, "t": msg.get("t")})
                )
            elif kind == protocol.MSG_START and player.id == room.host_id:
                await room.begin()
            elif kind == protocol.MSG_READY:
                room.toggle_ready(player.id)
            elif kind == protocol.MSG_COLLECT:
                drop_id = msg.get("id")
                if isinstance(drop_id, str):
                    room.collect_loot(player.id, drop_id)
            elif kind == protocol.MSG_BREAK:
                crate_id = msg.get("id")
                if isinstance(crate_id, str):
                    room.break_crate(player.id, crate_id)
            elif kind == protocol.MSG_ACTIVATE:
                rift_id = msg.get("id")
                room.activate_rift(
                    player.id, rift_id if isinstance(rift_id, str) else None
                )
            elif kind == protocol.MSG_BUY:
                stand_id = msg.get("id")
                room.buy(player.id, stand_id if isinstance(stand_id, str) else None)
            elif kind == protocol.MSG_SPIN:
                room.spin(player.id)
            elif kind == protocol.MSG_REROLL:
                room.reroll(player.id)
            elif kind == protocol.MSG_USE:
                slot = msg.get("slot")
                if isinstance(slot, int) and not isinstance(slot, bool):
                    room.use_medical(player.id, slot)
            elif kind == protocol.MSG_DROP:
                slot = msg.get("slot")
                if isinstance(slot, int) and not isinstance(slot, bool):
                    room.drop_loot(player.id, slot)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        room.remove_player(player.id)
        if room.players:
            await room.broadcast_lobby()
        else:
            # Last one out: the room's whole content was its players.
            await rooms.drop(room.code)
