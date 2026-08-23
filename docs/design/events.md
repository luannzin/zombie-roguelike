# The night's script

*A slope has no moments in it.*

---

## The problem this exists for

T-02 made the forest fill up as the night goes on, and that is the right
pressure: staying out costs something, and the player reads it by looking
around rather than at a clock. But it is a **slope**, and nobody has ever
noticed a population ceiling move. Ask somebody what happened on their last
night and they will not say "the ambient density rose by eleven percent" —
they will say *the lights went out while I was carrying four things*.

A night made only of slope is a night with nothing in it to remember, and
every night is the same shape as the last. That is what this subsystem is
for: **moments on the slope.**

It is deliberately not a difficulty system. The slope is the difficulty. These
are the things that make one night different from another, and about half of
what makes a night memorable is not a threat at all.

---

## Three triggers, and there is no fourth

Every event anybody sketched for this game fell into one of three shapes, so
those are the triggers and the file does not accept another.

| trigger | when | why it earns a place |
| --- | --- | --- |
| **TIME** | a point in the night | It is the only kind of danger you can be **early for**. A player who learns that the dark falls around three and a half minutes in starts planning around it, and a plan is the most valuable thing a roguelike can give somebody. |
| **CHANCE** | rolled, with the odds climbing | It is what stops a learned night from becoming a script. Nobody can plan around it, so the plan has to survive being wrong. |
| **ACTION** | the world answers something the party did | The only one where the **player is the cause**. Worth more than its mechanical weight: a consequence you caused teaches something a scheduled one cannot. |

**The odds climb rather than sitting flat**, and that is not a tuning choice.
A flat per-roll chance is memoryless, which permits a twenty-minute night with
nothing in it — the single outcome this whole subsystem exists to prevent.
Climbing turns *"nothing yet"* into *"soon"*, which is a completely different
thing to sit inside.

**At least one trigger is used twice**, on purpose, and `test_events.py` fails
if that stops being true. A trigger is a mechanism, not a category. If the
second user of one costs anything, the abstraction was never real.

---

## The catalog

| event | trigger | what it is |
| --- | --- | --- |
| `horde` | chance | A wave, from one bearing, announced before it arrives. |
| `dark` | time | Every lantern on the map goes out for a while. |
| `airdrop` | chance | Supplies come down, a long walk away, under a beacon. |
| `blood` | action (`downed`) | A body falls and the woods turn toward it. |

### Why the airdrop is in here

It is the only row that is an **opportunity**, and it is what keeps the others
honest. If every scheduled thing is a threat, then the correct answer to "an
event fired" is always the same — *leave* — and a night with one answer is not
a night with decisions in it.

It also asks its question at the worst possible time, which is the whole
design. The crate is across the map, the forest is fuller than it was an hour
ago, and the bag is already worth something. **It lands away from the party
deliberately**: a crate at your feet is a reward, a crate two clearings out is
a decision, and the walk *is* the event.

### Why the dark is on the TIME trigger

Every other row **adds** something to the map. This one **subtracts**, and what
it subtracts is a decision the player had been making for themselves all night
— the lantern trade, see it or be seen.

That asymmetry is the argument for the trigger. Taking the lamp away at random
is a punishment. Taking it away at a moment the party can learn, and be
somewhere sensible for, is a plan. It is also gated off night one: it is the
only event that changes a rule the player has been relying on, and doing that
before they have relied on it is noise rather than drama.

### Why `blood` is a noise and not a hunt

`ai.hear` with no source turns heads and raises awareness without telling
anything where the party is standing. So the forest stirs **toward the fall**
rather than every creature on the map committing to the survivors.

A blanket `hunt_all` here would make one player going down equivalent to
pressing the extraction siren — a far larger event than a fall should be. What
it does instead is make the **rescue** the hard part, which under permadeath
(T-01) is the most important decision the party makes.

---

## The rules that are not on the rows

### The gate

Nothing fires during a pickup, the run for the exit, an arrival, a departure,
in the shop, or in the arena. Every one of those is a beat the game has already
committed the player to, and an event landing inside one is not tension — it is
two things asking for the same attention with no way to answer either.

**It lives in `EventDirector.update`, not on the rows**, so a new event cannot
forget it. A row that genuinely wanted to fire during extraction would have to
say so explicitly, and none does.

### The clock stops but the cooldowns do not

Opposite answers to the same question, and both deliberate.

A **cooldown** means *"that just happened, let it breathe"*, which stays true
while the party is running for the exit. The night's **elapsed time** is what
the TIME trigger and the climbing odds are measured against — letting it run
through a two-minute extraction would mean a party that came home arrived into
an event that had been building while nothing could happen.

### An effect that refuses costs nothing

An effect returns `None` when it did not happen: no spot on the map, nobody
left standing, a wave already in the air. That must not spend the cooldown or
the per-night allowance.

This is the quietest failure mode in the subsystem. A rare event silently
consumed by a firing the player never saw is **invisible from inside the game**
— they see a night with no crate in it and have no way to know one was sent
into a wall. `test_events.py` pins it.

### One director per map

A night is a fresh script rather than a continuation, so every clock, cooldown
and allowance restarts at an entrance — the same call `EnemyDirector` makes,
for the same reason.

---

## Change surface

| intent | touch |
| --- | --- |
| add an event | a row in `server/app/events.py` `EVENTS` + its effect function above it + a copy row in `client/src/game/events.ts`. Nothing else. |
| tune an event | `server/app/config.py`, the `EVENT_*` block |
| change what an event DOES | the `Room` door it calls (`send_horde`, `begin_dark`, `drop_supplies`, `stir_at_downed`) — never the row |
| add a new KIND of trigger | `events.py` only, and be sure it is genuinely a fourth shape rather than one of the three wearing a hat |
| what an event looks / sounds like | `client/src/game/events.ts` — the server ships a key and no copy |

**Do not touch from here:** the population ramp (`ai.EnemyDirector` — that is
the slope, this is the moments on it), the extraction sequence, or the boss.

### The one honest caveat

"Adding an event is a data row" is true on each side and there are two sides:
a row in `events.py`, and a row in `client/src/game/events.ts`. That is the
same split every other piece of copy in this game makes — `server/app/` holds
no interface text — and it is not a leak. But it is two files, not one, and
the doc says so rather than letting somebody discover it.

---

## Verification

`python tests/test_events.py` from `server/`.

It drives all three triggers with nobody watching, because a trigger that never
fires is indistinguishable from one whose odds are low, and nobody plays enough
permanent nights to tell the difference. It also asserts the two claims that rot
quietest — that a refusing effect spends nothing, and that a new event really is
a data row, checked against a row the test builds itself and drives through the
unmodified director.
