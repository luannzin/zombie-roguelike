"""The upgrade machine: one clock, shared by three files.

A cabinet with three reels, a lever and a tray, standing at the far end of the
merchant's glade. A level buys one pull; a pull pays one skill. That is the
entire mechanic, and almost none of it is here — `skills.py` owns what can come
out, `store.py` owns where it stands, `room.py` owns the press, and the client
owns every frame of what it looks like.

WHAT IS HERE IS THE TIMELINE, and it is here for the same reason `rift.py`
holds the pickup's: the ceremony is four seconds long, it is watched by
everybody in the glade, and it must not be resolved at snapshot rate. The
server decides WHAT came out on the frame the lever moves and says so once; the
client flies the arm, the reels, the lamps and the canister off these constants
plus that one timestamp, on its own render clock. Three files, one set of
numbers.

THE ANTICIPATION IS AUTHORED, AND IT IS THE POINT.
The reels do not stop together. They stop left to right, and the gap before the
LAST one lands is `hold_for(rarity)` — longer the better the pull is. That is
the whole trick a slot machine runs on: the moment worth having is not seeing
the prize, it is the second and a half where two reels agree and the third has
not decided yet. Because the roll already happened server-side, that hold is
honest — the machine is not deciding late, it is taking its time telling you.
"""

from __future__ import annotations

from .config import STORE_SPIN_TILES

#: The lever comes down and the cabinet takes it. Nothing has spun yet.
ARM_TIME = 0.34
#: Reels up to speed, all three blurred.
SPIN_UP = ARM_TIME + 0.18
#: When reel 0 and reel 1 land. Fixed, so the rhythm of a pull is a thing the
#: player learns and the only variable is the wait at the end of it.
REEL_ONE = SPIN_UP + 0.85
REEL_TWO = REEL_ONE + 0.52

#: How long the third reel keeps spinning after the second lands, by rarity.
#: A common is over almost as soon as the second reel stops; a legendary sits
#: there for nearly two seconds with two thirds of the answer already showing.
#:
#: THE LADDER IS THE TELL AND IT IS ALLOWED TO BE. By the third or fourth shop
#: a player knows that a long third reel is good news, and that knowledge is
#: what turns the wait into tension instead of latency — the machine is not
#: hiding the outcome, it is letting them work it out a beat early and then
#: confirming it.
REEL_HOLD: dict[str, float] = {
    "common": 0.30,
    "uncommon": 0.55,
    "rare": 0.95,
    "epic": 1.45,
    "legendary": 1.95,
}

#: Between the last reel locking and the canister leaving the tray. Short: the
#: machine has already said what it is, and a pause here is dead air rather
#: than suspense.
EJECT_LAG = 0.26
#: How long the canister is in the air before it settles on the tray lip.
EJECT_FLIGHT = 0.55
#: How long it sits there being looked at before it flies to the HUD tray.
HOLD_TIME = 1.15
#: The lamps coming down and the arm going back up.
RESET_TIME = 0.6


def lock_at(rarity: str) -> float:
    """When the third reel lands, in seconds from the pull."""
    return REEL_TWO + REEL_HOLD.get(rarity, REEL_HOLD["common"])


def eject_at(rarity: str) -> float:
    """When the canister leaves the tray."""
    return lock_at(rarity) + EJECT_LAG


def settle_at(rarity: str) -> float:
    """When the canister is down and readable."""
    return eject_at(rarity) + EJECT_FLIGHT


def claim_at(rarity: str) -> float:
    """When it flies into the HUD tray and the tile counts up."""
    return settle_at(rarity) + HOLD_TIME


def duration(rarity: str) -> float:
    """Whole pull, press to idle. `Room` uses it to lock the lever."""
    return claim_at(rarity) + RESET_TIME


def client_payload() -> dict:
    """`welcome.config.machine`. The whole flight plan, in seconds."""
    return {
        "armTime": ARM_TIME,
        "spinUp": SPIN_UP,
        "reelOne": REEL_ONE,
        "reelTwo": REEL_TWO,
        "reelHold": dict(REEL_HOLD),
        "ejectLag": EJECT_LAG,
        "ejectFlight": EJECT_FLIGHT,
        "holdTime": HOLD_TIME,
        "resetTime": RESET_TIME,
        # Echoed so the client's reach test and the server's are one number
        # even though they are read out of two different config blocks.
        "reachTiles": STORE_SPIN_TILES,
    }
