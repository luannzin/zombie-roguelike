"""Things that travel, and are therefore things you can WALK AWAY FROM.

WHY THIS IS NOT A RAYCAST
=========================
`combat.raycast` is how guns work: a line that arrives on the frame it was
fired. That is correct for a bullet and it is exactly wrong for everything in
this module, because a hit that cannot be avoided after it is thrown is not an
attack the player answers — it is a number the game subtracts.

Every projectile here is SLOW ENOUGH TO OUTWALK. It moves a fixed distance per
tick and tests a circle, so a player who keeps moving is essentially never hit
and a player standing still is always hit. That asymmetry is the whole design:
it is the only mechanic in the game that punishes standing still, which makes
it the only mechanic that makes POSITION a decision rather than a preference.

WHY IT IS SHARED
================
The boss's thrown crescent was the first of these, and it was written inside
`boss.py` because it was the only one. A creature that attacks at range wants
exactly the same object — a disc with a lifetime, that passes through a party
billing each body once, and that dies on a wall — and re-deriving it beside the
first would produce two implementations of "slow enough to walk away from"
which would drift the first time either was tuned.

So the MECHANIC lives here and the two callers keep their own presentation.
`boss.Crescent` still carries the boss's wire shape (the client draws it off
`boss.crest`, and rewriting that wire buys nothing); what it no longer owns is
the arithmetic.

PASSES THROUGH, BILLS ONCE
==========================
A projectile does not stop on the first body it meets. Stopping would make a
party of four into a wall the person at the back stands safely behind, which is
the opposite of what a ranged attack should do to a formation — it should make
bunching up worse, not better. `struck` is what keeps it honest: each body pays
at most once, however long the disc is inside them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from .world import TileMap


@dataclass
class Projectile:
    """One thing in the air. The mechanic, with no opinion about what it looks
    like — see the module header for why presentation stays with the caller."""

    id: int
    x: float
    y: float
    #: World pixels per second, already multiplied out.
    dx: float
    dy: float
    #: Seconds left. A projectile ALWAYS has one: a disc with no expiry is a
    #: disc that crosses the whole map and hits somebody who never saw it
    #: thrown, which reads as being shot by the scenery.
    life: float
    #: World pixels. The disc's own half-width; the victim's radius is added.
    radius: float
    damage: int
    #: Everybody it has already billed. See the module header.
    struck: set[str] = field(default_factory=set)
    #: WHO PUT IT IN THE AIR, or "". Bookkeeping for the caller and nothing
    #: else — `advance` never reads it. It is on the projectile rather than in
    #: a table beside the list because a disc outlives whoever threw it, and a
    #: parallel dict keyed by id would be one more thing to remember to clean
    #: up on the tick the disc bursts.
    owner: str = ""
    #: WHICH SPRITE THE CLIENT DRAWS. Presentation stays with the caller (see
    #: the module header) and this is the whole of what the wire says about
    #: how a projectile looks: a string the room copies onto the row and never
    #: interprets. Bile and a thrown crescent are the same mechanic and must
    #: never be the same picture.
    look: str = "spit"


@dataclass
class Impact:
    """What one tick of flight produced. The caller applies all of it."""

    #: `(body, damage, source_x, source_y, owner)`.
    #:
    #: THE OWNER IS THE FIFTH COLUMN AND IT IS THE ONE THAT IS NOT ABOUT THE
    #: BLOW. The other four are what happened and where; this is whose it was,
    #: copied straight off the projectile because the projectile is the only
    #: thing that still knows — by the time a caller reads a hit the disc may
    #: already have burst on the next wall.
    #:
    #: The boss's moves append to this same list with an empty owner, which is
    #: honest rather than a placeholder: a chainsaw swing has no player behind
    #: it, and `Room` reads the column to decide who gets the xp.
    hits: list = field(default_factory=list)
    #: `(x, y)` where a projectile ended. The caller turns these into whatever
    #: burst it draws — this module names no effect.
    bursts: list[tuple[float, float]] = field(default_factory=list)


def advance(
    shots: list[Projectile],
    living: Iterable,
    world: TileMap,
    dt: float,
) -> tuple[list[Projectile], Impact]:
    """Move every projectile one tick. Returns the survivors and what they did.

    THE ORDER MATTERS AND IT IS THE ONE SUBTLE THING HERE: a projectile is
    moved, THEN tested for a wall, THEN tested against bodies. Testing bodies
    first would let a disc bill somebody standing on the far side of a wall it
    is about to die on, which is a hit through cover — and cover is most of
    what a ranged attacker is supposed to make the player think about.
    """
    keep: list[Projectile] = []
    out = Impact()
    bodies = list(living)
    for shot in shots:
        shot.life -= dt
        shot.x += shot.dx * dt
        shot.y += shot.dy * dt
        # A small box rather than a point: a disc that only died when its
        # centre was inside a wall would visibly clip half of itself into
        # a tree before it burst.
        if shot.life <= 0.0 or world.box_blocked(shot.x, shot.y, 2.0, 2.0):
            out.bursts.append((shot.x, shot.y))
            continue
        for player in bodies:
            if player.id in shot.struck:
                continue
            reach = shot.radius + player.radius
            if math.hypot(player.x - shot.x, player.y - shot.y) > reach:
                continue
            shot.struck.add(player.id)
            out.hits.append((player, shot.damage, shot.x, shot.y, shot.owner))
        keep.append(shot)
    return keep, out
