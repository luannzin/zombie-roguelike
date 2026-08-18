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
   "aim":{"x":0.72,"y":-0.69},"shoot":true,"lantern":true,"held":0}
  {"type":"ping","t":<client ms>}
  {"type":"start"}                      host only; ignored otherwise
  {"type":"ready"}                      toggle ready, camp only, near the fire
  {"type":"collect","id":"l3"}          pick up a loot drop; ignored if too far
                                        or the destination (bag / hotbar) is
                                        full. An AMMO drop is refused unless
                                        the collecting player's own belt holds
                                        that calibre and has room for it
  {"type":"break","id":"k3"}            USE the object at `id` — break a
                                        barrel, open a boot, lift an altar
                                        slab. One message for both verbs:
                                        which one it is belongs to the object
                                        (`config.objects[t].verb`), not to
                                        the key. Ignored if too far. A shot
                                        that hits a BREAKABLE object's sprite
                                        box does the same; openable ones
                                        ignore bullets.
  {"type":"drop","slot":0}              pull a bag slot back onto the ground
                                        near the player's feet; ignored in camp
  {"type":"activate","id":"r0"}         press a rift console or feed an open
                                        platform from the bag. `id` is the pad;
                                        omitted = nearest in range.
  {"type":"buy","id":"s2"}              take the weapon off a shop table and
                                        charge the party balance. Store zone
                                        only; ignored if too far, already
                                        sold, unaffordable, or the belt is
                                        full with no legal trade.

server -> client
  {"type":"hello","playerId":"...","code":"ABC1234",
   "config":{...},"map":{...},"zone":{...}}          once, first message
  {"type":"lobby","code":"ABC1234","hostId":"...","phase":"lobby"|"playing",
   "zone":{...},"players":[{"id","name","color","x","y"}]}
                                        on every membership/phase change
  {"type":"error","code":"room_not_found"}  followed by a close
  {"type":"welcome","playerId":"...","player":{...},"config":{...},"map":{...},
   "zone":{...},"ack":<last processed input seq for you>,"quests":[...],
   "blackout":true}
  {"type":"snapshot","tick":N,"departing":false,"arriving":false,"zoneKey":"camp-1",
   "players":[...],"enemies":[...],"coins":[...],
   "shots":[...],"swings":[...],"attacks":[...],"kills":[...],"pickups":[...],
   "loot":[...],"lootPickups":[...],"pours":[...],
   "crates":[...],"crateBreaks":[...],
   "corpses":[...],
   "entrance":{...},"tilePatches":[...],"quests":[...],
   "rifts":[...],"egress":{...},"blackout":true,
   "stands":[...],"buys":[...],"balance":240,
   "roster":[...]}                    only every ROSTER_EVERY_N_TICKS ticks
  {"type":"pong","t":<echoed>}

`hello` exists because `lobby` is one payload broadcast to everybody: telling
each client which row is theirs has to happen in a message only they receive.
It also carries the MAP, because the lobby is not a picture of the camp — it is
the camp, drawn before anyone may walk on it. The roster rows carry real world
positions for the same reason: the seat a player is standing on at the fire is
the tile they start `preparation` on, so the lobby cannot invent its own layout.

`zone` says where the room is and how that place behaves — see zones.py
(title, hostile, lantern, weather). It is on all three messages because all
three can be the first thing a client learns about a room it just joined.

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
Interactive objects are pulled out of `props` into `crates`
(`{id,t,x,y,v,flip}`) so using one can remove it without rewriting the scenery
list. `t` is the object TYPE key — `barrel`, `ambulance`, `altar` — and it
indexes `welcome.config.objects`, which carries the sheet, the sheet row, the
verb, the prompt and the hit box. Their tiles stay solid on `tiles` until the
object is used, then become FLOOR; a vehicle frees FOUR of them.

A snapshot is IDENTICAL for every socket in the room — it is serialised once a
tick and the same string is written to all of them. That is why the per-player
ack rides on each player's own row (`seq`) instead of at the top level: one
field that differed per recipient would cost a re-serialisation each.

Snapshot arrays:
  players   what moves, every tick; `seq` is that player's own input ack.
            `held` is the hotbar slot in hand (-1 holstered); `ads` is the
            trigger held (AWP spends `aimDelay` from this).
  roster    the same players with their name, colour, score board and
            `guns` (3-slot belt), sent every ROSTER_EVERY_N_TICKS and on
            any membership change. A client caches it: those fields feed a
            5 Hz HUD and never change per tick
  enemies   live enemies only; `t` keys into welcome.config.enemyTypes.
            `aw` is the 0..1 detection meter — it fills while a player stands
            in the creature's sight cone and is pinned at 1 while it hunts.
            The client fills the hunt diamond with it; the cone's own reach
            and width are per-type and ride the config, not the tick, and
            are not drawn. `v` is the body-variant index into
            `enemyTypes[t].variants`. `hat` / `cloth` are optional indices
            into those overlay pools — omitted when the zombie wears none.
  coins     live gold pickups (one per gold point dropped)
  shots     hitscan tracers fired since the last snapshot; `k` is the
            weapon key, `dmg` the damage dealt (0 on a miss / crate)
  swings    PLAYER melee arcs that CONNECTED since the last snapshot. A
            whiff is never sent: the swinger already drew their own arc and
            a blade waving at nothing is not news. `step` is which beat of
            the chain it was (slash, slash, cut) and the reach and width of
            that beat ride `welcome.config.weapons[k].melee`, not the tick —
            the same split as an enemy's sight cone. `hits` is one row per
            body opened, because the finisher goes through more than one.
  attacks   enemy melee swings; `dmg` is 0 when the victim's i-frames ate it
  kills     deaths since the last snapshot, players and enemies alike
            ({"kind":"enemy"} entries: xp paid now; gold = coins spawned;
            t/v/hat/cloth/ax/ay/dx/dy so the corpse can fall in the right
            clothes, facing the killing blow)
  corpses      remaining dead bodies; attached like crates — on welcome,
               and again on a snapshot only when one was added. The kill
               event is the juice; this list is the record that stays.
  pickups   coins collected since the last snapshot
  loot      remaining world drops; attached like the roster — on welcome,
            and again on a snapshot only when the ground list changed
            (collect or a bag toss)
  lootPickups  drops collected since the last snapshot (juice). `slot` is
               the bag or hotbar index it landed in; `dest` is `hotbar`
               for a gun and omitted for the pocket. The client flies
               the sprite onto that HUD cell.
  pours        items tipped out of a backpack onto a platform since the last
               snapshot (juice). `by` is the body doing it, `r` the pad, `k`
               the catalog key, `v` what it paid, `s` the drawn size when the
               item carries its own (a condensed core), and `n` the pad's own
               running pile index — the client stacks the deck off that, so
               every client in the room lands the same crate in the same
               place. The player row's `pour` field is the beat the body is
               on (walk / lift / dump / stow, absent when not pouring)
  crates       remaining interactive objects; attached like loot — on the map
               payload, and again on a snapshot only when one was used
  crateBreaks  objects used since the last snapshot (juice). `t` names the
               type so the client can play the right sheet for something that
               is already gone from the live list; `drop` is empty / coin /
               item; `k` is the catalog key when it is an item; `amb` is set
               when what came out was a passenger rather than loot
  stands       the shop's tables, attached like crates — on the map payload,
               and again on a snapshot only when one was bought from. A sold
               table keeps its row and its price; `sold` is what empties it,
               because the gap where a weapon was is information
  buys         purchases since the last snapshot (juice). `slot` is the belt
               cell it landed in; the client flies the sprite there and
               counts the balance down
  balance      THE PARTY'S money, not a player's, so it is one number at the
               top of the snapshot rather than a column on the roster. Sent
               only when it changes — see `Player.gold` for the other,
               personal, one

The store's fixtures ride the MAP payload (`store`), not the snapshot: where
the merchant stands and where his tables are is decided once when the corridor
is built, the same as a rift's geometry. Only what SELLS moves.
"""

from __future__ import annotations

import json

MSG_INPUT = "input"
MSG_PING = "ping"
MSG_START = "start"
MSG_READY = "ready"
MSG_COLLECT = "collect"
MSG_BREAK = "break"
MSG_DROP = "drop"
MSG_ACTIVATE = "activate"
MSG_BUY = "buy"

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
    corpses: list[dict] | None = None,
    quests: list[dict] | None = None,
    blackout: bool = False,
    balance: int = 0,
) -> dict:
    payload = {
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
        "corpses": corpses or [],
        # Always sent, even at zero: it is the party's whole spending power and
        # a client that had to wait for the first change to learn it would draw
        # an empty purse over a corridor full of price tags.
        "balance": balance,
    }
    if quests:
        payload["quests"] = quests
    if blackout:
        payload["blackout"] = True
    return payload


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
    swings: list[dict] | None = None,
    departing: bool = False,
    arriving: bool = False,
    zone_key: str | None = None,
    roster: list[dict] | None = None,
    loot: list[dict] | None = None,
    loot_pickups: list[dict] | None = None,
    pours: list[dict] | None = None,
    crates: list[dict] | None = None,
    crate_breaks: list[dict] | None = None,
    corpses: list[dict] | None = None,
    rifts: list[dict] | None = None,
    entrance: dict | None = None,
    tile_patches: list | None = None,
    quests: list[dict] | None = None,
    egress: dict | None = None,
    blackout: bool | None = None,
    stands: list[dict] | None = None,
    buys: list[dict] | None = None,
    balance: int | None = None,
) -> dict:
    payload = {
        "type": MSG_SNAPSHOT,
        "tick": tick,
        "departing": departing,
        "arriving": arriving,
        "zoneKey": zone_key,
        "players": players,
        "enemies": enemies,
        "coins": coins,
        "shots": shots,
        "attacks": attacks,
        "kills": kills,
        "pickups": pickups,
    }
    # Absent on most ticks: a swing that connected is rarer than a shot, and
    # the empty list would ride every tick of a run nobody is knifing through.
    if swings:
        payload["swings"] = swings
    # Absent on most ticks — see ROSTER_EVERY_N_TICKS.
    if roster is not None:
        payload["roster"] = roster
    if loot is not None:
        payload["loot"] = loot
    if loot_pickups:
        payload["lootPickups"] = loot_pickups
    if pours:
        payload["pours"] = pours
    if crates is not None:
        payload["crates"] = crates
    if crate_breaks:
        payload["crateBreaks"] = crate_breaks
    if corpses is not None:
        payload["corpses"] = corpses
    # Rift rows when any pad changed state. The client runs the ceremony
    # between those snapshots off its own clock.
    if rifts is not None:
        payload["rifts"] = rifts
    if entrance is not None:
        payload["entrance"] = entrance
    if tile_patches:
        payload["tilePatches"] = tile_patches
    if quests is not None:
        payload["quests"] = quests
    if egress is not None:
        payload["egress"] = egress
    if blackout:
        payload["blackout"] = True
    if stands is not None:
        payload["stands"] = stands
    if buys:
        payload["buys"] = buys
    # `is not None` rather than truthiness: spending down to nothing is the one
    # balance change a party most needs to see land.
    if balance is not None:
        payload["balance"] = balance
    return payload
