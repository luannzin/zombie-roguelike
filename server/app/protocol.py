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
   "aim":{"x":0.72,"y":-0.69},"shoot":true,"lantern":true,"sprint":true,
   "held":0}                            `sprint` is SHIFT, and it is a request:
                                        what it buys is decided server-side
                                        against the breath the body has left
                                        (`simulation.running`). The answer
                                        comes back on the player row as `st`
                                        (breath left) plus `wind` while the bar
                                        is spent and the key is locked out
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
  {"type":"spin"}                       pull the upgrade machine's lever.
                                        Store zone only; ignored if too far or
                                        while another player's pull is still
                                        running. Spends a banked LEVEL; with
                                        none owed it spends GOLD instead, at
                                        `snapshot.spinPrice`, and is ignored if
                                        the party cannot cover it
  {"type":"buy","id":"s2"}              take the weapon off a shop table and
                                        charge the party balance. Store zone
                                        only; ignored if too far, already
                                        sold, unaffordable, or the belt is
                                        full with no legal trade.
                                        An `id` naming an AMMUNITION CRATE
                                        ("b_rifle") buys one box of that
                                        calibre instead: the crate never sells
                                        out, and it is refused for a calibre
                                        this player is not carrying or a
                                        reserve already at its cap

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
   "stands":[...],"boxes":[...],"buys":[...],"balance":240,"spinPrice":100,
   "spins":[...],
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
            `sl` is set only while a creature is ASLEEP, and it is the one
            piece of the AI's mode that ships: a sleeper is drawn from a
            different sheet entirely (`enemyTypes[t].sleepSprite`), so unlike
            patrolling-versus-walking-home it is not something the client can
            be left to guess. Omitted for everything awake, which is
            everything except a miniboss nobody has found yet.
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
               the index it landed on in whichever container took it; `dest`
               says WHICH container — `hotbar` for a weapon, `ammo` for a
               calibre, `worn` for a piece of armour (and then `slot` indexes
               `armor.SLOTS`) — and is omitted for the pocket. The client
               flies the sprite onto that HUD cell.
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
  armorHits    blows that landed on GEAR since the last snapshot (juice).
               `slot` is which piece took it — `head` / `body` / `legs`, or
               the literal `shield` — `k` the piece, `dmg` what it stopped,
               `left` what is still on it, and `broke` the one frame it came
               apart on. The DURABILITY rides the roster (`armor`, `shield`);
               this is the EVENT, the same split `kills` keeps from
               `enemies`. A client that missed a packet must never replay a
               piece breaking
  crateBreaks  objects used since the last snapshot (juice). `t` names the
               type so the client can play the right sheet for something that
               is already gone from the live list; `drop` is empty / coin /
               item; `k` is the catalog key when it is an item; `amb` is set
               when what came out was a passenger rather than loot
  stands       the shop's tables, attached like crates — on the map payload,
               and again on a snapshot only when one was bought from. A sold
               table keeps its row and its price; `sold` is what empties it,
               because the gap where a weapon was is information
  boxes        the shop's AMMUNITION CRATES, one row per calibre somebody in
               the room is carrying — `c` the calibre, `n` the rounds one
               purchase hands over, `v` the frame on the ammunition sheet
               (the calibre's index in `weapons.AMMO_TYPES`, shipped so the
               art's frame order stays one side's fact). Sent when the wall
               CHANGES, which is arriving and buying a calibre nobody had;
               a row the client has not seen before is what it drops in.
               A crate never sells out, so there is no `sold` here
  buys         purchases since the last snapshot (juice). `slot` is the belt
               cell it landed in; the client flies the sprite there and
               counts the balance down. `dest` is "ammo" for a crate-load —
               the sprite flies at the GUN it fed rather than into a cell it
               never occupied — and `n` is how many rounds arrived
  spins        lever pulls since the last snapshot (juice). ONE ROW IS A
               WHOLE CEREMONY: `k` is the skill that came out, `r` its
               rarity, `n` how many copies the puller holds now, `left`
               how many pulls they have banked after it. Everything the
               four seconds of reels, eject and settle look like is flown
               by each client off this row plus `config.machine` — the
               roll is already decided, so the reels are telling the
               player something rather than deciding it. The stacks and
               the spin count also ride the ROSTER (`skills`, `spins`),
               which is what a client that joined mid-pull reads. `cost` is
               present only when the pull was BOUGHT rather than owed
  balance      THE PARTY'S money, not a player's, so it is one number at the
               top of the snapshot rather than a column on the roster. Sent
               only when it changes — see `Player.gold` for the other,
               personal, one
  spinPrice    what the NEXT bought pull costs, for a party holding no level.
               Doubles per purchase and resets on the walk into each night's
               shop (`Room.spin_price`). Party-wide like the balance it
               spends, and sent only when it moves

The store's fixtures ride the MAP payload (`store`), not the snapshot: where
the merchant stands and where his tables are is decided once when the corridor
is built, the same as a rift's geometry. Only what SELLS moves — and the
ammunition crates, which are the one fixture in the room whose EXISTENCE is a
fact about the party rather than about the map.
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
MSG_SPIN = "spin"
#: Buy a new shelf. `{type:"reroll"}` — no payload: what is rerolled is every
#: unsold table, and there has never been a reason to reroll one of them.
MSG_REROLL = "reroll"
#: Spend one medical cell. `{type:"use","slot":0|1}` — the CELL, not the item
#: key, because two cells may hold the same kit and the server has to empty the
#: one the player pressed.
MSG_USE = "use"
#: R. `{type:"ult"}` — NO PAYLOAD, and that is the contract: which ultimate
#: fires is decided entirely by what is in the player's hands, on the server,
#: on the frame the message lands. A client that named one would be a client
#: that could fire the katana's while holding the minigun, one dropped hotbar
#: packet later.
#:
#: A MESSAGE AND NOT A FIELD ON THE INPUT PACKET, unlike the lantern and the
#: belt. Those two are STATES the client predicts; this is a one-shot with no
#: local half at all — nothing about it is drawn before the server answers,
#: because an ultimate that flashed and then did not happen would be the
#: worst-feeling frame in the game.
MSG_ULT = "ult"
#: Pick a downed teammate up, or put the one in your arms down.
#: `{type:"carry"}` — NO TARGET, and for the same reason `ult` carries none:
#: there is only ever one answer. Carrying, it puts that body down; not
#: carrying, it takes the nearest downed teammate inside `CARRY_REACH_DIST`.
#: A client that named a body could name one across the map, and a client that
#: named the WRONG one would be a rescue that silently picked up somebody else
#: — which, with two bodies on the floor in the dark, is exactly the frame
#: where being wrong is unrecoverable.
MSG_CARRY = "carry"
#: Take your own dropped pack back. `{type:"pack"}` — no id, same argument:
#: the only pack any player may pick up is theirs, so naming one adds a way to
#: be wrong and no way to be right.
MSG_PACK = "pack"

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
    spin_price: int = 0,
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
        # Always sent too, and for the same reason: the cabinet's prompt names
        # a price the moment a body walks up to it, and a client that had to
        # wait for the first purchase to learn the ladder would offer the first
        # bought pull for nothing.
        "spinPrice": spin_price,
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
    armor_hits: list[dict] | None = None,
    corpses: list[dict] | None = None,
    rifts: list[dict] | None = None,
    entrance: dict | None = None,
    tile_patches: list | None = None,
    quests: list[dict] | None = None,
    egress: dict | None = None,
    blackout: bool | None = None,
    stands: list[dict] | None = None,
    boxes: list[dict] | None = None,
    buys: list[dict] | None = None,
    balance: int | None = None,
    spin_price: int | None = None,
    spins: list[dict] | None = None,
    boss: dict | None = None,
    boss_events: list[dict] | None = None,
    wipe: dict | None = None,
    hordes: list[dict] | None = None,
    heals: list[dict] | None = None,
    events: list[dict] | None = None,
    dark: float | None = None,
    reroll_price: int | None = None,
    rerolls: list[dict] | None = None,
    spits: list[dict] | None = None,
    spit_events: list[dict] | None = None,
    spit_bursts: list[dict] | None = None,
    ults: list[dict] | None = None,
    volleys: list[dict] | None = None,
    ult_bursts: list[dict] | None = None,
    packs: list[dict] | None = None,
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
    # ULTIMATES. Three lists and they are three different KINDS of thing,
    # which is why they are not one:
    #
    #   ults        somebody PRESSED R. A one-shot: the burst, the shake, the
    #               sound, the name across the screen. Never replayed.
    #   volleys     what is in the air right now, every tick, like `spits`.
    #               State, because a client that missed a packet still has to
    #               draw the crescent that is halfway across the clearing.
    #   ultBursts   where one ENDED. A one-shot again.
    #
    # All three absent on almost every tick of almost every night, which is
    # the point of sending them this way rather than as fields on a row.
    if ults:
        payload["ults"] = ults
    if volleys:
        payload["volleys"] = volleys
    if ult_bursts:
        payload["ultBursts"] = ult_bursts
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
    # Blows that landed on GEAR. Absent on almost every tick — the roster is
    # what carries the durability, and this is only the frames it moved.
    if armor_hits:
        payload["armorHits"] = armor_hits
    if corpses is not None:
        payload["corpses"] = corpses
    # BAGS ON THE GROUND. `is not None` rather than truthiness, like `loot`
    # and `corpses`: the list going EMPTY is the news — somebody walked back
    # and picked theirs up — and a falsy check would leave the last pack drawn
    # in the grass forever.
    if packs is not None:
        payload["packs"] = packs
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
    # The ammunition crates, when the wall changed — which in practice is the
    # frame somebody walks into the shop and the frame they buy a calibre
    # nobody had. A row appearing is what the client animates the drop off.
    if boxes is not None:
        payload["boxes"] = boxes
    if buys:
        payload["buys"] = buys
    if spins:
        payload["spins"] = spins
    # THE BOSS RIDES AS ONE ROW WITH HIS OWN PLAYHEAD ON IT. `s` is his state
    # and `t` is how long he has been in it, and the client animates off those
    # two rather than off a local clock — a 30 Hz position with a locally
    # timed animation over it disagrees with the server about which frame the
    # bar landed on, and that frame is the entire fight. Absent on every map
    # that has no boss, which is all of them but one.
    if boss is not None:
        payload["boss"] = boss
    # What he DID: the shake, the dust, the sound and the gore. Separate from
    # the row for the same reason `kills` is separate from `enemies` — a state
    # is a thing that is true, an event is a thing that happened, and a client
    # that missed a packet must never replay the second.
    if boss_events:
        payload["bossEvents"] = boss_events
    # `is not None` rather than truthiness: spending down to nothing is the one
    # balance change a party most needs to see land.
    if balance is not None:
        payload["balance"] = balance
    # Moves on exactly two events — a pull bought, and the walk into the next
    # night's shop — so it rides its own dirty flag rather than the balance's.
    if spin_price is not None:
        payload["spinPrice"] = spin_price
    # THE RUN IS OVER. Present on every tick the death card is holding and
    # absent on every other, which makes it a STATE rather than an event on
    # purpose: a client that missed the one frame a run ended would otherwise
    # walk a party out of a camp it never saw them arrive in. Whoever
    # reconnects mid-hold gets the black screen too, and the fresh `welcome`
    # that follows is what clears it.
    if wipe is not None:
        payload["wipe"] = wipe
    # A WAVE IS COMING, and from over there. One row per horde announced this
    # tick, carrying only where the howl is — the bodies arrive as ordinary
    # enemies a few seconds later and need no special wire of their own. It is
    # an EVENT and never replayed: a client that missed it gets the horde
    # without the warning, which is worse than useless but is at least not a
    # phantom howl from a wave that already landed.
    if hordes:
        payload["hordes"] = hordes
    # A kit spent. An EVENT — the health bar moving is a fact the roster
    # already carries, and this is the flash, the sound and the number, which a
    # client that dropped a packet must never replay.
    if heals:
        payload["heals"] = heals
    # THE NIGHT'S SCRIPT FIRED. One row per event, `{k, x?, y?}` — the key is
    # what the client looks its copy and its cue up by, and the place is there
    # only for the events that HAVE one (a crate that came down, a body that
    # fell). An EVENT and never replayed.
    #
    # ONE ARRAY FOR THE WHOLE CATALOG, deliberately: a fourth event must not be
    # a fourth wire field, or "adding an event is a data row" stops being true
    # the first time anybody tries it.
    if events:
        payload["events"] = events
    # SECONDS LEFT OF AN EVENT DARK. STATE, not an event, and the same call
    # `blackout` makes for the same reason — it has a duration, so a client
    # that joined halfway through one has to be told the lamps are off rather
    # than left predicting a light that cannot come on. Sent on both edges
    # (`0.0` is the lift), and omitted on every tick between.
    if dark is not None:
        payload["dark"] = dark
    # WHAT THE NEXT REROLL COSTS. STATE, like `spinPrice` beside it and for the
    # same reason: it is a price tag, and a client that missed the event that
    # moved it would show the party a number the server will refuse.
    if reroll_price is not None:
        payload["rerollPrice"] = reroll_price
    # And the shelf turning over. An EVENT — the tables themselves ride the
    # `stands` row, and this is the lever, the coin and the sound.
    if rerolls:
        payload["rerolls"] = rerolls
    # WHAT IS IN THE AIR — creature projectiles, NOT the hitscan `shots`
    # above, which are gunfire and arrive on the frame they were fired.
    #
    # STATE, not an event, and it is the one thing here
    # that has to be: a disc takes three seconds to cross a clearing, so a
    # client that dropped the launch packet must still be able to draw the
    # thing about to hit it. Sent whole every tick it is non-empty, which is
    # almost never — the array costs nothing on a quiet forest and a delta
    # scheme for at most a handful of rows would cost more than it saved.
    if spits:
        payload["spits"] = spits
    # It LEFT something. An EVENT — the wet cough, the muzzle-of-a-mouth burst
    # — and never replayed: a client that missed it gets the disc without the
    # sound, which is worse than hearing it and far better than hearing a
    # throw that already landed.
    if spit_events:
        payload["spitFired"] = spit_events
    # And where one ENDED. Also an event, for the splash.
    if spit_bursts:
        payload["spitBurst"] = spit_bursts
    return payload
