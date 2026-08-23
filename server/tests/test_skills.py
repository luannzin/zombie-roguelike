"""Skills that change a RULE, and skills that COST something.

Run:  python tests/test_skills.py   (from server/)

Thirty-six of the catalog's rows are `(field, number)`, and the honest
description of what they build is: the same survivor with different dials. You
are always the same person moving a bit faster or hitting a bit harder, and no
two runs ever PLAY differently — they only go better or worse.

The five rows added on top of that are the other kind, and everything that can
go wrong with them is silent:

  * A RULE THAT IS NEVER READ. `Mods.steady` defaulting to False and being
    checked nowhere looks exactly like a skill the player has not found yet.
    Nothing errors; the canister lands, the tray shows the tile, and the rule
    does nothing for the rest of the run. Each rule is driven here through the
    real code path it is supposed to change.
  * A RULE READ IN TWO PLACES. `lamp_immune` has to be honoured by `begin_dark`
    AND by `queue_input`, because the first turns lamps off and the second
    stops them being turned back on. Honouring one and not the other produces a
    lamp that lights for exactly one packet, which reads as a broken keybind.
  * A DOWNSIDE THAT IS NOT A DOWNSIDE. A trade-off row whose cost got dropped
    in a rebalance is a strictly-better row, and nobody reports a skill that is
    too good. The costs are asserted as arithmetic.
  * THE ICON ORDER. Catalog order IS the atlas's frame order, so a row inserted
    rather than appended moves every frame index after it and half the tray
    wears somebody else's picture. `make_skills._check_order` fails the build,
    but only if somebody runs it.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import crates, protocol, skills  # noqa: E402
from app.config import DT, TILE_SIZE  # noqa: E402
from app.room import Room  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    async def send_text(self, text: str) -> None:
        pass


def forest_room() -> tuple[Room, str]:
    room = Room(code="SKL")
    room.phase = protocol.PHASE_PLAYING
    pid = room.add_player(Socket(), "P0").id
    asyncio.run(room.embark())
    room.arriving = False
    room.gate = None
    return room, pid


def give(room: Room, pid: str, *keys: str) -> None:
    player = room.players[pid]
    for key in keys:
        player.skills.add(key)


# --- the catalog is well formed ---------------------------------------------

rule_rows = [row for row in skills.SKILLS if row.rules]
check("the catalog has rule rows at all", len(rule_rows) >= 3)

for row in rule_rows:
    # A BOOLEAN CANNOT BE FLIPPED TWICE. A pure rule row with a cap above one
    # is a machine that can hand somebody a canister which does nothing.
    if not row.effects:
        check(f"{row.key} is a pure rule and caps at one", row.cap == 1)
    # And the rule has to be a field that exists, or `flatten` silently drops
    # it and the skill is decoration.
    for rule in row.rules:
        check(
            f"{row.key}'s rule '{rule}' is a real field on Mods",
            hasattr(skills.Mods(), rule),
        )

# EVERY RULE IS REACHABLE. A field on `Mods` that no row can turn on is dead
# machinery, and it is the half of "a rule that is never read" that lives on
# this side.
declared = {
    name
    for name in vars(skills.Mods()).keys()
    if isinstance(getattr(skills.Mods(), name), bool)
}
grantable = {rule for row in skills.SKILLS for rule in row.rules}
check(
    f"every rule on Mods can be granted by some row (orphans: {declared - grantable})",
    declared <= grantable,
)

# THE TRADE-OFFS ACTUALLY COST SOMETHING. A row whose downside was dropped in
# a rebalance is a strictly-better row, and nobody reports one of those.
trade_rows = [
    row
    for row in skills.SKILLS
    # `armor` UP is more damage taken; anything else down is a plain loss.
    if any(
        (field == "armor" and step > 0) or (field != "armor" and step < 0)
        for field, step in row.effects
    )
]
check("the catalog has rows with a real downside", len(trade_rows) >= 2)
for row in trade_rows:
    # A cost with no upside is not a trade, it is a punishment — the machine
    # would be handing out a canister nobody should ever take.
    gains = [
        (f, d)
        for f, d in row.effects
        if (f == "armor" and d < 0) or (f != "armor" and d > 0)
    ]
    check(f"{row.key} pays for its downside", bool(gains))
    # THE COST IS IN THE BLURB. A cost the player discovers by dying is a bug
    # report; a cost they read and took anyway is a build.
    check(f"{row.key} states its cost on the canister", "mas" in row.blurb.lower())


# --- the rules actually change the rules ------------------------------------

# `lamp_immune` — BOTH HALVES. The dark turns lamps off; `queue_input` is what
# stops them being turned back on. Honour one and not the other and the lamp
# lights for exactly one packet.
room, pid = forest_room()
player = room.players[pid]
player.last_input.lantern = True
room.begin_dark(20.0)
check("an ordinary lamp goes out in the dark", not player.last_input.lantern)
room.queue_input(pid, {"sequence": 500, "lantern": True})
check(
    "and cannot be lit again",
    not player.inputs[-1].lantern,
)

room, pid = forest_room()
give(room, pid, "filamento_frio")
player = room.players[pid]
check("the rule is on", player.skills.mods.lamp_immune)
player.last_input.lantern = True
room.begin_dark(20.0)
check("Filamento Frio keeps the lamp through the dark", player.last_input.lantern)
room.queue_input(pid, {"sequence": 501, "lantern": True})
check(
    "and it can still be switched — the OTHER half of the same rule",
    player.inputs[-1].lantern,
)
# THE BLACKOUT IS NOT THE DARK. The run home is the last beat of a map and the
# whole party is meant to be running in it — a skill that lit one of them would
# be rewriting the ending rather than the weather.
room.blackout = True
room.queue_input(pid, {"sequence": 502, "lantern": True})
check("but the extraction blackout still takes it", not player.inputs[-1].lantern)


# `steady` — a blow does not interrupt a HEAL.
room, pid = forest_room()
give(room, pid, "sangue_frio")
player = room.players[pid]
player.hp = 40
player.medical.add("first_aid")
room.use_medical(pid, 0)
check("the heal started", player.using is not None)
room.damage_player(player, 5, None)
check("Sangue Frio holds the bandage through a blow", player.using is not None)
# IT DOES NOT STOP THE DAMAGE. What it buys is the ability to commit to a heal
# somewhere you expect to be hit, not a discount on being wrong.
check("and the blow still landed", player.hp < 40)

# Without it, the same blow ends it — the control that makes the above mean
# something.
room, pid = forest_room()
player = room.players[pid]
player.hp = 40
player.medical.add("first_aid")
room.use_medical(pid, 0)
room.damage_player(player, 5, None)
check("without the skill a blow still ends a heal", player.using is None)

# AND IT DOES NOT COVER A VAULT. That is a different bargain — its stake is the
# noise, and a force that could not be interrupted would make the loudest
# object in the game free to open.
room, pid = forest_room()
give(room, pid, "sangue_frio")
player = room.players[pid]
tx = int(player.x / TILE_SIZE)
ty = int(player.y / TILE_SIZE) + 1
vault = crates.Crate(
    id="v1", kind="vault", x=(tx + 0.5) * TILE_SIZE, y=(ty + 0.5) * TILE_SIZE,
    variant=0, flip=False, tx=tx, ty=ty,
)
room.crates[vault.id] = vault
player.x, player.y = vault.x, vault.y
room.break_crate(pid, vault.id)
check("the force started", player.using is not None)
room.damage_player(player, 5, None)
check("Sangue Frio does NOT hold a vault open", player.using is None)


# `quiet_hands` — forcing makes no noise at all.
room, pid = forest_room()
player = room.players[pid]
tx = int(player.x / TILE_SIZE)
ty = int(player.y / TILE_SIZE) + 1
vault = crates.Crate(
    id="v2", kind="vault", x=(tx + 0.5) * TILE_SIZE, y=(ty + 0.5) * TILE_SIZE,
    variant=0, flip=False, tx=tx, ty=ty,
)
room.crates[vault.id] = vault
player.x, player.y = vault.x, vault.y
room.noises.clear()
room.break_crate(pid, vault.id)
check("an ordinary force announces itself", len(room.noises) == 1)

room, pid = forest_room()
give(room, pid, "maos_de_veludo")
player = room.players[pid]
tx = int(player.x / TILE_SIZE)
ty = int(player.y / TILE_SIZE) + 1
vault = crates.Crate(
    id="v3", kind="vault", x=(tx + 0.5) * TILE_SIZE, y=(ty + 0.5) * TILE_SIZE,
    variant=0, flip=False, tx=tx, ty=ty,
)
room.crates[vault.id] = vault
player.x, player.y = vault.x, vault.y
room.noises.clear()
room.break_crate(pid, vault.id)
check("Mãos de Veludo forces in silence", not room.noises)
check("and the channel still runs", player.using is not None)


# --- a rule does not stack ---------------------------------------------------
#
# Owning one copy and owning three are the same sentence. This is asserted
# because `flatten` sums `effects` and it would be very natural to sum rules
# the same way — which would do nothing visible until somebody wrote a rule
# that was accidentally a count.

one = skills.flatten({"filamento_frio": 1})
many = skills.flatten({"filamento_frio": 5})
check("one copy flips the rule", one.lamp_immune)
check("five copies say the same thing", many.lamp_immune == one.lamp_immune)


# --- the trade-offs are real arithmetic --------------------------------------

base = skills.flatten({})
nervous = skills.flatten({"gatilho_nervoso": 1})
check("Gatilho Nervoso hits harder", nervous.gun > base.gun)
check("and takes more doing it", nervous.armor > base.armor)

mule = skills.flatten({"mula_de_carga": 1})
check("Mula de Carga carries more", mule.carry > base.carry)
check("and moves slower", mule.speed < base.speed)
# The cap matters: enough copies of a speed cost would stop a player moving.
capped = skills.flatten({"mula_de_carga": 99})
check("and its cost is capped short of standing still", capped.speed > 0.5)


# --- the wire ----------------------------------------------------------------

payload = skills.flatten({"filamento_frio": 1}).payload()
check("the client is told about the lamp rule", payload.get("lampImmune") is True)
# The rules the client does NOT predict must stay off the wire: shipping one is
# inviting somebody to re-implement a decision the server already owns.
check("server-only rules stay server-side", "steady" not in payload)
check("...both of them", "quietHands" not in payload)

catalog = skills.catalog_payload()
for row in rule_rows:
    entry = catalog.get(row.key)
    check(f"{row.key} is in the shipped catalog", entry is not None)
    # A rule row has no number, so the BLURB is the entire explanation the
    # player ever gets. An empty one is a tile that means nothing.
    if entry:
        check(f"{row.key} explains itself", bool(entry["blurb"].strip()))


# --- icon order --------------------------------------------------------------
#
# Catalog order IS frame order. A row inserted rather than appended moves every
# index after it and half the tray wears somebody else's picture — and nothing
# at runtime notices, because a modulo always lands on something.

manifest_frames = skills.FRAME
for index, row in enumerate(skills.SKILLS):
    check(f"{row.key} is at its catalog index", manifest_frames[row.key] == index)


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
