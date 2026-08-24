"""The vault: the one object you have to stand still for.

Run:  python tests/test_containers.py   (from server/)

Every other container in this game opens on a keypress, which means looting has
never been an ACT — it is something you do while walking past. `open_time` is
what makes one object ask a real question instead, and four things about it are
invisible from inside the game:

  * THE NOISE GOES OUT AT THE START. A slow open whose noise fired on
    completion would be a gamble with no stake in it — you would hear whether
    it was worth it before anything heard you. This is the whole arrangement
    that makes "open it now or come back later" a question, and it is one line
    away from being backwards at all times.
  * AN INTERRUPTED FORCE COSTS THE SECONDS AND NOT THE OBJECT. The vault stays
    shut and can be tried again. Spending it on the first frame instead looks
    identical right up until somebody gets hit, and then it has eaten the
    richest container in the game for nothing.
  * ONE PAIR OF HANDS PER OBJECT. Two players forcing the same vault would both
    complete and it would pay twice — a duplication bug that looks exactly like
    good luck, which is the kind nobody reports.
  * IT HAS TO ACTUALLY BE ON THE MAP. `chest` and `strongbox` sat in the
    catalog, the footprint table and `CONTAINER_KINDS` for months while no
    scene placed either — the domed lid `make_chest` argues about at length had
    never once appeared in a game. Nothing at runtime notices a catalog row
    that can never spawn.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import crates, mapgen, protocol, scenery  # noqa: E402
from app.config import DT, TILE_SIZE  # noqa: E402
from app.entities import USE_CRATE  # noqa: E402
from app.room import Room  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    async def send_text(self, text: str) -> None:
        pass


def forest_room(players: int = 1) -> tuple[Room, list[str]]:
    room = Room(code="VLT")
    room.phase = protocol.PHASE_PLAYING
    ids = [room.add_player(Socket(), f"P{i}").id for i in range(players)]
    asyncio.run(room.embark())
    room.arriving = False
    room.gate = None
    return room, ids


def plant(room: Room, kind: str) -> crates.Crate:
    """Put one object on the map next to the first player, and stand them at it."""
    player = next(iter(room.players.values()))
    tx = int(player.x / TILE_SIZE)
    ty = int(player.y / TILE_SIZE) + 1
    crate = crates.Crate(
        id="obj-under-test",
        kind=kind,
        x=(tx + 0.5) * TILE_SIZE,
        y=(ty + 0.5) * TILE_SIZE,
        variant=0,
        flip=False,
        tx=tx,
        ty=ty,
    )
    room.crates[crate.id] = crate
    # Standing on top of it, so reach is never what this file is measuring.
    player.x, player.y = crate.x, crate.y
    return crate


def force(room: Room, pid: str, seconds: float) -> None:
    player = room.players[pid]
    for _ in range(int(seconds / DT)):
        if player.using is None:
            return
        room._step_use(player, DT)


# --- the catalog ------------------------------------------------------------

vault = crates.type_of("vault")
check("the vault takes real seconds", vault.open_time > 0.0)
check(
    "and it is the ONLY object that does",
    [t.key for t in crates.TYPES if t.open_time > 0.0] == ["vault"],
)
# IT PAYS OFF THE SHRINE TABLE, which is what the seconds are being charged
# for. A vault on ordinary odds would be a slow chest, which is a tax.
check("the vault pays off SHRINE_ODDS", vault.rarity is crates.SHRINE_ODDS)
check("and it always pays something", vault.drops.get(crates.DROP_ITEM) == 100)
# THE WARNING IS THE COST ON THE PROMPT, NOT A RARER WORD FOR THE SAME ACT.
# The label used to be "arrombar" so the sentence would look different; what
# actually tells the player this press is not free is `openTime` reaching the
# client, because the HUD swaps the whole sentence off it — a press becomes a
# HOLD (`Room.cancel_force`) and the seconds are printed beside it. A vault
# whose duration stopped shipping would be a trap: same words, and the body
# plants itself.
check(
    "an ordinary lid ships no cost, so its prompt stays a press",
    crates.type_of("chest").client_payload()["openTime"] == 0.0,
)
# LOUDER THAN ANYTHING ELSE THAT OPENS — the noise is the stake.
opens = [t for t in crates.TYPES if t.verb == crates.VERB_OPEN and t.key != "vault"]
check(
    "nothing else that opens is as loud",
    all(t.noise_tiles < vault.noise_tiles for t in opens),
)
# And the client is told, or the first vault anybody meets is a surprise.
check("openTime ships to the client", vault.client_payload()["openTime"] == vault.open_time)


# --- it takes time, and then it opens ---------------------------------------

room, ids = forest_room()
pid = ids[0]
crate = plant(room, "vault")
room.noises.clear()

room.break_crate(pid, crate.id)
player = room.players[pid]
check("pressing E opens a channel", player.using is not None)
assert player.using is not None
check("and the channel is a force", player.using.kind == USE_CRATE)
check("it runs for the authored time", player.using.total == vault.open_time)
check("it knows what it is working on", player.using.target == crate.id)
check("nothing opened on the keypress", not crate.opened)

# THE NOISE IS ALREADY OUT. The stake is committed before the payoff is known.
check("the noise went out at the START", len(room.noises) == 1)
check("and it reaches the vault's full radius", room.noises[0].radius == vault.noise)

# Halfway: still nothing.
force(room, pid, vault.open_time * 0.5)
check("halfway through, still shut", not crate.opened)
check("and still channelling", player.using is not None)

# The body is planted.
player.vx, player.vy = 9.0, 9.0
room._step_use(player, DT)
check("a forcing body does not move", player.vx == 0.0 and player.vy == 0.0)

loot_before = len(room.drops)
coins_before = len(room.coins)
force(room, pid, vault.open_time)
check("it opens at the end", crate.opened)
check("the channel closed", player.using is None)
# The vault always pays, so this is a strict increase over what the map was
# already holding rather than a "there is loot somewhere" check.
check(
    "and something fell out of it",
    len(room.drops) > loot_before or len(room.coins) > coins_before,
)
# ONE ANNOUNCEMENT PER OBJECT. Shouting again on completion would double a
# very large radius and undo the arrangement above.
check("it did not announce itself twice", len(room.noises) == 1)


# --- a blow costs the seconds and not the vault -----------------------------

room, ids = forest_room()
pid = ids[0]
crate = plant(room, "vault")
# A generated forest already has scatter on it, so what is under test is the
# DELTA — what the interrupted force added, not what the map was holding.
before_drops = len(room.drops)
room.break_crate(pid, crate.id)
force(room, pid, vault.open_time * 0.6)
check("still forcing when the blow lands", room.players[pid].using is not None)

room.damage_player(room.players[pid], 5, None)
check("a blow ends the force", room.players[pid].using is None)
check("the vault is still shut", not crate.opened)
check("and nothing fell out", len(room.drops) == before_drops)

# AND IT CAN BE TRIED AGAIN. The price of trying is payable more than once —
# what it cost was the seconds and the attention of everything in earshot.
room.break_crate(pid, crate.id)
check("it can be forced again", room.players[pid].using is not None)


# --- letting go of the key ---------------------------------------------------
#
# THE OPEN IS A HOLD. Releasing E stops it, and the seconds already spent are
# gone — the same trade an interrupted force has always made, except the player
# chose it. Two things have no symptom if they break: a release that did NOT
# stop the channel (the vault opens four seconds after the key came up, which
# reads as the game ignoring you), and a release that reached a HEAL (holding 4
# would become free, and standing still in the open is the entire cost of
# medicine).

room, ids = forest_room()
pid = ids[0]
crate = plant(room, "vault")
room.break_crate(pid, crate.id)
force(room, pid, vault.open_time * 0.5)
room.cancel_force(pid)
check("letting go ends the force", room.players[pid].using is None)
check("and the vault is still shut", not crate.opened)
# The seconds are spent: what comes next is a fresh channel, not a resumed one.
room.break_crate(pid, crate.id)
check("a second press starts from the top", room.players[pid].using is not None)
assert room.players[pid].using is not None
check(
    "with the whole duration to run again",
    room.players[pid].using.left == vault.open_time,
)
# A RELEASE WITH NOTHING TO CANCEL IS A NO-OP, which is what lets the client
# send one on every E release rather than tracking the object's cost.
room.cancel_force(pid)
room.cancel_force(pid)
check("cancelling twice is harmless", room.players[pid].using is None)

# AND IT NEVER REACHES A HEAL.
healer, hids = forest_room()
hplayer = healer.players[hids[0]]
hplayer.hp = 10
hplayer.medical.add("first_aid")
healer.use_medical(hids[0], 0)
check("the heal opened", hplayer.using is not None)
healer.cancel_force(hids[0])
check("E does not abort a heal", hplayer.using is not None)


# --- one pair of hands per object -------------------------------------------

room, ids = forest_room(players=2)
crate = plant(room, "vault")
for pid in ids:
    room.players[pid].x, room.players[pid].y = crate.x, crate.y

room.break_crate(ids[0], crate.id)
check("the first player starts", room.players[ids[0]].using is not None)
room.break_crate(ids[1], crate.id)
check(
    "the second is refused rather than queued",
    room.players[ids[1]].using is None,
)

# And even if both somehow completed, the object pays ONCE — `smash_crate`
# refuses an already-open crate, so a race resolves to a miss.
force(room, ids[0], vault.open_time + DT)
check("the vault opened", crate.opened)
before = len(room.drops)
room._finish_force(room.players[ids[1]], crate.id)
check("a second completion pays nothing", len(room.drops) == before)


# --- an ordinary container is untouched -------------------------------------

room, ids = forest_room()
pid = ids[0]
box = plant(room, "box")
room.break_crate(pid, box.id)
check("an untimed object still opens on the keypress", box.opened)
check("and opens no channel", room.players[pid].using is None)


# --- the tier is actually on the map ----------------------------------------
#
# The one nothing at runtime notices: a catalog row that can never spawn.

counts: Counter[str] = Counter()
for seed in range(40):
    world = mapgen.build_forest(seed=seed, day=3, calibres={"pistol"})
    for row in world.crates or []:
        counts[row.get("t", "?")] += 1

for kind in ("vault", "chest", "strongbox"):
    check(f"{kind} actually appears on generated maps", counts[kind] > 0)
# The vault is the rarest of the three by design — one landmark, and not every
# time. A vault on every map is a vending machine.
check(
    "the vault is not on every map",
    counts["vault"] < 40,
)
check("the vault is in the container set", "vault" in scenery.CONTAINER_KINDS)


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
