# Store / merchant hub — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/render/AGENTS.md`](../../client/src/render/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the outdoor apron, the SHOP BUILDING and everything fitted in it, the six-stall grid and its stock roll across THREE ladders (guns, steel, armour), the AMMUNITION CRATES on the south wall, prices, the purchase, the payout ceremony's data, and the party balance |
| **Inputs** | `{type:"buy","id"}`, the night's per-pad takes from `rift.fed`, the day number |
| **Outputs** | `map.store` (`StorePayload`), `snapshot.boxes`, `buy` events, `snapshot.balance`, `payout` rows, the next day's forest on departure |
| **Depends on** | `loot.py` (catalog `value` — prices are derived), `weapons.py` (what a stall can sell, and every ammunition table), `ammo.py` (whose belts decide which crates exist), `rift.py` (the takings), `zones.py` (`STORE_AMBIENT`), `machine.py` |
| **Consumers** | `skills.py` (the cabinet stands here), `client/src/render/layers/store.ts`, `layers/payout.ts` |
| **Authoritative** | `Room.balance`, `Stand.sold`, prices + haggle, stock roll, which calibres have crates, the belt and the reserve after a purchase |
| **Presentation** | the coin spray, the counting balance, the merchant's idle clips, the floating stock, the light budget |

## Invariants

- **This is the only place money is created.** `Room.enter_store` banks `sum(rift.fed)` once, on the crossing. Nothing else anywhere adds to `balance`.
- **The client NEVER settles.** The payout animation is presentation; a reconnect mid-animation must not pay twice.
- **Prices are derived**, never listed: `store.price_of` = catalog `value` x `STORE_MARKUP`, plus a per-stall `_haggle` too small to reorder the ladder.
- **A stall sells once** and the empty table stays on the wire.
- **THE GRID SHOWS `min(6, len(pool))` DIFFERENT THINGS, ALWAYS.**
  `_roll_stock` draws WITHOUT replacement until the shelf is exhausted and only
  then repeats. A duplicate on a table means the merchant genuinely has less
  stock than tables, which is what a duplicate should mean.
- **An ammunition crate NEVER sells out**, and one only exists for a calibre somebody in the room is carrying. The wall is a portrait of the party's belts.
- **A crate's tile is never claimed.** It can arrive mid-visit, after the tile map has gone out — so it stands flat against the south wall where nobody walks and is walked through, exactly like the merchant.
- **Two currencies, never merged**: `Room.balance` (party GOLD) vs `Player.gold` (personal DARK GOLD).
- **The floor and every light on top of it are ONE budget** — see the ambient contract below. Adding a light means taking brightness out of another.
- **The APRON is an ordinary forest map; the SHOP is the game's one building.** A new object should be an existing prop or tile kind before it is a new payload field — and the building itself IS tile kinds (`BRICK` / `TILEFLOOR`), never a rectangle on the wire.
- **Its art may be poor, worn and improvised; it may not be grim.**
- **`BRICK` and `TILEFLOOR` are a MIRRORED pair.** They live in `server/app/world.py` and `client/src/game/world.ts`, and so do `GROUNDS` and `CLEAR`. A kind added to one side alone desyncs collision — it shows up as rubber-banding in the shop's doorway, not as an error.


## The shelf

- **THE ROLL COLLAPSED THE SHOP ONTO ITS TOP TWO ROWS AND NOBODY NOTICED FOR A
  LONG TIME.** Stock was drawn with replacement, weighted `1 + rank * 1.1`
  toward the newest thing unlocked. A day-one pool is nine rows, so the top of
  it carried weight 9.8 against the bottom's 1.0 — ten to one — and six draws
  out of a distribution that steep is not a shelf, it is the same two items
  repeated. Six of eight sampled day-one shops came back holding a duplicate;
  one came back holding four of the same pistol. A grid of six choices was
  routinely offering two.
- **BOTH DIRECTIONS HAVE NOW BEEN WRONG, AND THE FIX IS THE ORDER, NOT THE
  WEIGHTS.** Distinct-only was right for a lane of four tables read in sequence
  and wrong for a grid — it forced the pool to be as long as the shelf, so a
  day-one shop came out as three tables and three gaps. Replacement fixed the
  gaps and broke the shelf. Drawing without replacement FIRST and repeating
  only once every distinct row is on a table keeps both properties: no gaps, no
  accidental duplicates, and a repeat that carries real information — this
  merchant has fewer things than tables tonight.
- **AND THE LEAN CAME DOWN TO A THIRD** (`STOCK_DEPTH_BIAS`, 1.1 -> 0.35). The
  intent behind it was right — the newest unlock should be the likeliest thing
  on a table — but at 1.1 the cheap end of the shelf effectively did not exist,
  which quietly removed the "we came home broke, buy the sidearm" line that the
  price ladder is built to offer.
- **`_haggle` STILL EARNS ITS KEEP.** Two tables holding the same gun at the
  same number would be a duplicate; at two prices it is a merchant. That
  reading was never wrong — it was just being asked to justify a duplicate rate
  it was never meant to cover.

## Danger zones

- Any offset in the pitch block — run `python tests/test_store_walk.py`, which flood-fills and fails if the exit, the merchant, a stall or the cabinet is unreachable.
- `Entrance.bounds` — this is the only map with TWO corridors; a scan without bounds bricks up the exit.
- `zones.STORE_AMBIENT` / `store.RING_TORCHES` / `TORCH_LIGHT_TILES` / `layers/payout` alphas — one budget, moved together.

## The reroll

The shop had exactly one decision in it: **buy what is there, or save.** Both
answers are fine and neither is interesting on the fourth night, because the
shelf is not a choice — it is a hand the party was dealt.

A reroll turns saving into a **gamble against the shelf**, and the price is
what stops that gamble being free.

### It is priced like the spin, on purpose

`Room.reroll_price` is `Room.spin_price`'s shape, copied rather than
re-derived. The two are the same argument about the same kind of purchase —
something with no ceiling, sold repeatedly, inside one visit — and having one
of them be linear would be an accident nobody could defend afterwards.

Doubling means the party always gets to reroll one more time and never gets to
reroll five. It resets on the next night's shop, because a ladder carried
across the run would be a number nobody can reach by night six, and the
mechanic would quietly stop existing.

It is **cheaper than a bought pull**, and the gap is the argument: a pull is a
skill you keep for the rest of the run, a reroll is six things you might not
want either.

### A sold table stays sold

This is the whole difference between a reroll and an infinite-stock exploit.
If a purchase came back on the next spin, the correct play would be to buy the
cheapest thing on the shelf and reroll until the shop had paid for itself —
and the merchant would become a machine for turning gold into more gold.

Nobody reports a shop that is too generous. They just get rich, and the
economy quietly stops mattering.

### And the furniture does not move

Same table, same place, same frame; only what is lying on it changes. A shop
that rearranged itself would make the player re-read a room they had already
learned, which is a cost with no decision in it. The value of a reroll is that
the **answer** changes and the question does not.

### At the merchant, not at the cabinet

The machine sells **skills** and he sells **objects**. A party pressing one
lever for both would have no idea which of the two they were bargaining with —
which is also why the two fixtures stand at opposite ends of the room.

---

## Change surface

| intent | touch |
| --- | --- |
| layout, stalls, gear, torches | `server/app/store.py` (+ `tests/test_store_walk.py`) |
| what is for sale, unlock day | `server/app/store.py` (`SELLABLE`, `STOCK_ORDER`, `_category`, `_unlock_day`) |
| what a table DRAWS when the stock is not a weapon | `client/src/render/layers/store.ts` (`stockSheet`) — a weapon comes off the held atlas, everything else off the loot icon |
| ammunition: where the crates stand, what a box costs | `server/app/store.py` (`AMMO_SPOTS`, `AMMO_RESERVE_SHARE`, `ammo_price_of`) |
| who gets a crate, and buying out of one | `server/app/room.py` (`_sync_ammo_boxes`, `_buy_ammo`) |
| the crates drawn / the drop-in | `client/src/render/layers/store.ts` (`dropOffset`), `server/tools/make_store.py` (`make_ammobox`) |
| prices | `server/app/loot.py` catalog value or `STORE_MARKUP` — never a price list |
| the shop drawn | `client/src/render/layers/store.ts`, `client/src/render/store.ts`, `render/merchant.ts` |
| the walls and floor drawn | `client/src/render/layers/terrain.ts` — they are TILE KINDS, so the pass that paints tiles owns them |
| the shop's art | `server/tools/make_store.py` (+ `make_merchant.py`, `make_machine.py`) |
| payout ceremony | `client/src/game/payout.ts`, `client/src/render/layers/payout.ts` |
| buy prompt | `client/src/components/hud/BuyPrompt.tsx`, `client/src/game/interaction.ts` (`buyPrompt`, `nearStand`, `nearAmmoBox`) |

**Do not touch from here:** `rift.py`'s quota math, inventory authority, the
skills catalog, `weapons.py`'s reserve sizing (`RESERVE_MAX` / `BOX_ROUNDS` —
the shop READS them and must never re-derive one), or the wire protocol pair.

---

## Design law

- **THE SHELF IS THREE LADDERS AND THE DAY WALKS ALL OF THEM AT ONCE.** It
  used to be one list — the guns, cheapest first — so gating by POSITION in it
  was the same as gating by price. That stopped being true the moment armour
  was on it: three cloth rags cost less than the cheapest pistol, so a merged
  sort would have taken the whole opening band and pushed the first firearm
  off night one, which is not a rebalance anybody asked for. So the bands are
  cut inside each CATEGORY (`_category`) and the first band's share is read
  off the guns, which makes the eleven-weapon ladder come out of this
  byte-for-byte what it was before there was anything else to buy. Night one
  is the bottom of every ladder — a sidearm, some rags, an axe — and the
  dearest rung of each is pinned to the last night.
- **A SHELF OF NOTHING BUT GUNS ASKS ONE QUESTION EVERY NIGHT**, and the
  answer is always the most expensive thing the party can afford. Armour is
  what makes it a real question: this night's take is a rifle, or it is a
  helmet and rounds, and a party that has been dying at doorways knows which.
  It is also the first thing the merchant can sell to a party who already own
  everything that shoots. The reasoning for the category is in
  [`docs/design/gear.md`](gear.md); what belongs here is only that the shop is
  one of its two sources and the forest is the other.

- **The STORE is the fourth beat of the loop and the only place money exists.**
  A trader's pitch in a small round forest CLEARING, walked SOUTH TO NORTH
  (`server/app/store.py`): corridor, room, corridor. The party comes up out of
  the arrival throat and the night's PLATFORMS are being lowered onto the apron
  across the south of the room; the trader stands in the MIDDLE of it with his
  wagon behind him, his counter in front of him and his six stalls laid out in
  a 3x2 GRID in front of that; his own gear and his fire are around the rim;
  and the upgrade MACHINE stands on the WEST arc. Get paid, see what it buys,
  spend a level, leave. The way back seals behind them exactly as the
  forest's did; the north end stands open the whole time, and walking out of it
  is the next day — straight into the next night's forest, arriving through an
  edge corridor that seals behind them, exactly as leaving the campfire does.
  - **IT IS A SMALL ROOM WITH THE MAN IN THE MIDDLE, AND IT TOOK TWO GOES.**
    The glade was a long east-west lane first, with the tables strung along it,
    doing exactly one thing: guaranteeing nobody walked past the stock. That is
    a corridor's argument and a weak one — a shop that is a queue is a shop
    nobody stands still in. So it became a round room, and the round room was
    sixteen tiles of radius with the trader on the west rim and the stock on
    the east one, which is not a shop either: it is a FIELD. Twenty tiles to
    read a price and twenty back to pay for it, and two halves that read as two
    unrelated places.
    A SHOP IS A COUNTER YOU STAND AT. The clearing is eleven tiles of radius
    now, the man is in the centre of it with his cart at his back and his goods
    in front of him, and the whole thing is legible from the door in one look.
    The corridors on the ends are the half of the lane that was worth keeping —
    they keep the arrival and the departure as separate events.
  - **THE WAGON IS WHO HE IS.** He had a tent when he was a man camped in a
    glade; he has a CART now, because he did not walk here with six tables on
    his back — he drives, he was somewhere else last week, and that is the
    reason he is worth finding. It is parked BEHIND him: a shopkeeper has a
    back wall. Guns racked along the flank, lanterns strung on a line under the
    eave, crates roped at the wheels, a lamp on the bow.
    **IT USED TO CARRY BONE MASKS AND TWO COVERED BODIES**, on the argument
    that the party should work out where the stock comes from on their own.
    The argument was fine and the result was not: this is the one beat of the
    loop that exists as a relief from the night, and the biggest sprite in it
    was a cart with corpses under a tarp. THE RULE FOR THIS ZONE'S ART, and it
    applies to the man, his kit, his machine and anything added later: it may
    be poor, worn and improvised; it may not be grim.
  - **THE MAN HAS A FACE.** He was a hooded figure with six pixels of void
    where a face goes — the same silhouette the game uses for everything that
    wants to kill you. That was survivable while he stood on a dark rim and is
    not now that he is the thing in the middle of the room, so he has a brimmed
    hat, skin, two eyes and a red scarf, over a GREEN coat that separates him
    from every warm wooden object he is ever seen against.
  - **IT IS THE ONE LIT PLACE, AND THAT IS THE ZONE'S JOB.** Everywhere else a
    party goes is a black wood with a torch in it somewhere; here they can see
    the treeline, the far arc of the room, the way out and each other.
    `Zone.ambient` is how — a floor under the darkness pass, zero in every zone
    somebody can be killed in and `zones.STORE_AMBIENT` here. On top of that
    floor a ring of torches marks the rim, a chain runs down each throat and a
    pair dresses each mouth. It is well under 1: the clearing is visible, not
    daylit, and his fire and the machine's marquee are the brightest things in
    it. The contrast is the reward — a night is only frightening if there is
    somewhere that is not.
    **THE FLOOR AND EVERY LIGHT ON TOP OF IT ARE ONE BUDGET, AND THAT IS THE
    ZONE'S ONE REAL BUG.** The client composites every light with `lighter` —
    scene lights, fires, the shop's flames, the landing platforms — and nothing
    clamps the total, so this room went FLAT WHITE on arrival and the party
    could not see the shop at all. The loudest contributor was the APRON: three
    skids setting down within five tiles of each other, each throwing a
    seven-tile rotor wash at 0.85, which is 1.7 of a full-bright sheet where
    two of them overlapped — before eight rotors and eight strobes went on top,
    on a 0.7 ambient floor with eleven seven-tile torches behind them. The fix
    is one budget spent in four places: the skids land far enough apart that no
    two washes touch, the torch ring is seven at 4.5 tiles, the floor is 0.45,
    and `layers/payout`'s alphas came down with them. Adding a light source
    here means taking brightness out of another one, and the check is walking
    in during a three-platform payout.
  - **THE NIGHT'S PLATFORMS COME HOME WITH THE PARTY, AND GETTING PAID IS AN
    EVENT.** The same four aircraft that took the skids set them down on the
    apron, the lines let go, the drones climb out, and the cargo on the decks
    becomes GOLD: a spray of coins off each platform arcing to the balance on
    the HUD, counting it up, with a large `+N` over the middle that shrinks
    into that number rather than simply vanishing. It is the ONE place group
    gold is ever an object — the moment it is created — because a currency that
    only appears as a HUD digit is a score, and one that visibly comes off a
    machine that visibly came back is money. The balance itself is credited
    server-side on the crossing (`Room.enter_store`); everything above is
    presentation, so a reconnect mid-animation cannot pay anybody twice.
  - **HIS GEAR IS AROUND THE RIM AND NONE OF IT OPENS.** Crates, a barrel of
    rods, a shelf of tins, a padlocked strongbox — out at the edges, behind and
    beside the cart, because the middle of the room belongs to the man and the
    stock. That split teaches what answers E in one visit. The art carries the other half of it: every frame is drawn
    roped, strapped and padlocked, because the player spent the previous night
    learning that a box in this game is a thing you open.
  - **IT IS TWO PLACES WITH A WALK BETWEEN THEM, AND THE BUILDING CAME BACK.**
    The zone was a clearing for a long time, and before that it was an
    interior, and the interior was thrown out for one reason that outweighed
    everything it got right: it was the WHOLE ZONE. The party walked out of a
    corridor and were already inside, so the game had cut to a menu rather than
    taken them anywhere. That objection is exactly right and it is not an
    argument against a building — it is an argument against a building being
    the whole map.
    So the zone is an APRON and a SHOP. The apron is outdoor forest: the same
    soil, the same trees, the same dark, with the night's platforms coming down
    on it, his cart parked beside them and his fire next to that. At the far
    end of the yard is a brick building the party can see from the moment they
    arrive and have to cross the yard to reach. **A door you walk up to is the
    opposite of a cut**, and the walk is what the clearing's version never
    gave: the payout happens outside, in the dark, on ground that still belongs
    to the night, and the shop is what you go INTO afterwards.
  - **THE BUILDING BUYS TWO THINGS A CLEARING NEVER COULD.**
    LIGHT: a closed room is lit from lamps standing in it on a regular grid,
    which is even, calm and arranged. A clearing can only be lit from its rim,
    which is a bright edge around a dark middle — the exact opposite of what a
    shop wants, and the thing the ring of torches was always fighting.
    A BACK WALL: a counter fitted into a corner has a BEHIND. The trader gets a
    pocket that is his — visible from the room, not walkable into — with his
    shelves on the wall over his shoulder. Out in the open his "back" was a
    parked cart and the rest of his life was scattered round a rim.
  - **IT HAS NO ROOF AND THAT IS NOT A SHORTCUT.** The camera looks down at
    about sixty degrees, so the party sees the floor and the far wall at once.
    The masonry carries it: a wall tile's face fills its own tile, and the
    TRIM — the lit top surface — is drawn only on the tiles with no masonry
    north of them. That one question makes the back wall a band with a lit lid,
    the side walls solid vertical bands, and the front wall something the
    camera sees over into the room. No roof to fade, no occlusion pass, no
    special case for any of the three.
  - **THE VALUE ORDER IS THE ROOM.** The wall is DARKER than the floor. That
    was backwards for a pass and it inverted the whole picture: at this
    elevation the plane facing UP catches the key and the planes facing
    sideways do not, so a room drawn the other way has no floor in it — the eye
    reads the lightest large field as the ground. Dark wall, warmer floor
    inside it, a bright trim line where they meet, and the COUNTER as the
    brightest large surface in the game, because it is what the party walked in
    to look at (S13 gives the focal mass the full ramp and leaves the
    background on steps 1-3). Everything else — his crates, his shelves, the
    brick — is background and is toned like it.
  - **THE FLOOR IS PAVED AND THE WALL IS BONDED, AND THEY ARE NOT THE SAME
    PATTERN.** Masonry is laid in running bond — long bricks, every other
    course offset half a brick — because that is how you make a wall stand up.
    A floor is square quarries butted on a grid, because nothing is holding
    anything else up. Running the wall's bond across the ground was the
    loudest thing wrong with the first cut of the room: it read as a wall the
    camera had fallen over onto.
    It is also QUIET. The floor is the largest surface in the game and almost
    none of it is ever looked at directly, so its joint is one step down rather
    than three and its wear is a few scuffs per tile. The temptation on a big
    empty surface is to fill it; filling it is what turns a calm room into a
    busy one.
  - **THE LAMPS STAND ON TABLES; THEY DO NOT HANG.** They hung from chains
    first and the reasoning was sound — a room is lit from above — but it was
    wrong about the CAMERA. A lamp two tiles over the floor is drawn two tiles
    up the screen from the tile it lights, so the flame and its own pool never
    appeared in the same place, and the chain above it ran into a ceiling this
    roofless cutaway does not have. Five lanterns floating in mid-air. A lamp
    on a table has its flame where its light is, sorts like any other prop, and
    is the warmer object besides: a hurricane lamp on a side table is furniture
    somebody put out, where a chain is fixtures somebody installed.
  - **THE WAGON IS STILL WHO HE IS, AND IT IS PARKED OUTSIDE.** A covered cart
    says he DRIVES, he was somewhere else last week, and that is the reason he
    is worth finding. A building says the opposite. The two only work together
    if the cart is what he ARRIVED IN and the shop is what he unloaded into —
    so it stands in the yard, between the party and the door, read on the walk
    up: cart first, then the building it feeds.
    **IT IS NOT A HEARSE.** It used to hang bone masks on a line and lay two
    covered bodies at the front wheel, on the argument that the party should
    work out where the stock comes from on their own. The argument was fine and
    the result was not: this is the one beat of the loop that exists as a
    relief from the night, and the biggest sprite in it was a cart with corpses
    under a tarp. THE RULE FOR THIS ZONE'S ART, and it applies to the man, his
    kit, his machine and anything added later: it may be poor, worn and
    improvised; it may not be grim.
  - **THE STOCK IS THE ONE THING IN THE ROOM THAT WAS ARRANGED.** Six small
    round tables, three across and two deep IN FRONT OF THE MAN, on the grid,
    priced cheapest-first and read south to north — because that is the
    direction the party walks in, so the first table they reach is the one they
    can afford and the last is the one they are saving for. They stand in front
    of him rather than on the opposite rim because the stock is what he is
    SELLING: it belongs between the party and the man. They are also SMALL —
    they used to be taller than the guns lying on them, which put six pieces of
    furniture in the middle of the shop that outweighed everything they were
    selling. Everything AROUND the grid is irregular: the wagon,
    the fire, the gear, the torch ring. The old lane jittered its tables off an
    even rhythm on the argument that four identical stalls at four identical
    intervals is the tell that nobody set this up by hand — which is right
    about a corridor and wrong about a market. A trader who lays goods out in
    rows wants them compared; six prices scattered round a clearing is six
    things to hunt rather than one decision to make.
    The tables are ROUND because they are now walked around: a board has a
    front and a back and reads wrong from three of the four sides a room lets
    you approach it from.
  - **THERE ARE TWO CURRENCIES AND THEY ARE TWO METALS.** GOLD is the GROUP's:
    everything the party loaded onto the night's platforms becomes the balance
    on the way in here, and nothing else, anywhere, adds to it. Loot still in
    the bag is not money, it is loot they failed to extract. The balance is the
    party's, it survives the day, and it is the number a night is scored on —
    it is also never an object, which is why nothing in the world is drawn in
    gold except the sparks off a platform tearing out of the ground.
    DARK GOLD is the PLAYER's, and it is the opposite in every way: an ANOMALY
    SHARD (`server/tools/make_coin.py`) that falls off corpses and out of
    explorables, that somebody has to walk over, that pools in `Player.gold`
    and rides on the `GOLD` row of their own panel behind its own badge. It
    buys nothing yet — it is being saved for things that belong to one player
    rather than to the party — so its taps are set deliberately low, split
    across `config.COIN_DROP_CHANCE` for corpses and `crates.DROP_COIN` for
    objects. Move those two together. Do not merge the two currencies, and do
    not let dark gold pay for anything the group earned.
    **IT STOPPED BEING A COIN, AND THAT DECIDED THE RATE.** A struck purple
    disc said there was a mint somewhere, which is a thing this world does not
    have — the only thing that pays out here is the rift. So it is a fragment
    of the rift, painted from the anomaly's own prism, and once it was that,
    the old rate was wrong by its own art: a piece of the thing the entire
    night is spent feeding cannot fall out of a third of the corpses in the
    forest without becoming litter. Both taps were cut hard (0.22 -> 0.07 on
    corpses, 14 -> 5 weight on objects, with the difference going to EMPTY
    rather than to more items) so that finding one is an event. The old
    constraint it replaces — keeping the purple clear of `--rarity-epic` so a
    lavender glow could not mean two things — is now handled by SHAPE and by
    scarcity instead of by luminance.
  - Each table shows the item's NAME in its rarity colour with a coin and a
    price under it. Walking close FLOATS the weapon off the boards — a slow
    breath, not a fixed offset, because a sprite that rose and stopped is a bug
    and one still moving is an offer — lights a pool under it, and opens the
    buy tooltip; E takes it. A stall sells once and the table stays there
    empty, because the gap is what says you already bought it.
    Prices are the loot catalog's value times a markup, never a second list,
    plus one stall's own HAGGLE either side of it. The catalog's value is
    itself derived — CS2 dollars through a curve anchored so the cheapest
    sidearm lands on day one's whole quota and the AWP lands near four
    hundred (`weapons.catalog_value`) — so a weapon's price, its weight and
    its damage all move together or not at all. The SHELF is sorted by price
    and gated by day in bands (`store.STOCK_ORDER`, `_unlock_day`): four
    sidearms on night one, the last thing on the ladder on night five,
    however long the ladder grows. That spread is what makes
    six stalls six decisions: the stock is rolled WITH REPLACEMENT, so he can
    be holding three of the same pistol, and three tables carrying the same
    number is a shelf rather than a shop. It is small enough never to reorder
    the catalog — a haggled AK never undercuts a full-price FAMAS — because the
    price ladder is teaching what the guns are worth.
    A price the party cannot cover is shown anyway, muted — the AWP priced out
    of reach is doing more work than a tutorial line about saving up would. The
    colour is the whole message; the tooltip does not also spell out that you
    are short.
  - **AMMUNITION IS BOUGHT HERE, AND THE WALL IT IS BOUGHT FROM IS A PORTRAIT
    OF THE PARTY.** `ammo.py` opens with the rule that ammunition is not cargo:
    a round is what you SPEND to fill the bag, never a thing in it. The shop is
    the other half of that sentence — if rounds are the cost of playing, the
    place money exists has to be where you buy them back. Before this the only
    supply was what the forest happened to scatter, which made the calibre you
    owned something you HOPED about rather than something you supplied.
    - **A CRATE ONLY EXISTS IF SOMEBODY CAN SHOOT IT.** That is `ammo.scatter`'s
      second rule standing indoors, and it is why the row against the south
      wall is worth looking at: it says what the party is carrying. A party of
      knives walks into a shop with no ammunition in it at all. **And the
      moment somebody buys a gun of a calibre nobody had, a crate DROPS IN** —
      falls from over the wall, lands hard, bounces twice. A box that simply
      WAS there on the next frame is a box nobody notices, and the arrival is
      the one moment the shop gets to say "you can supply that now". The fall
      is the client's own clock off a row it has not drawn before
      (`AmmoBox.bornAt`); nothing about it is worth a message.
    - **IT NEVER SELLS OUT, and a table always does.** A stall holds one
      specific weapon, so the gap where it was is the information; a crate is a
      SUPPLY, and one that emptied after a purchase would send the fourth
      player in a four-player room into the night dry.
    - **THE PRICE IS DERIVED OFF THE GUN, because the catalog cannot answer.**
      A box is `value` 0 in `loot.py` — deliberately, it is not shippable
      cargo — so the only column that knows what a round is worth is the
      WEAPON that eats it. Filling an empty reserve costs half the cheapest gun
      of that calibre (`AMMO_RESERVE_SHARE`), and one box is its own share of
      that reserve read off `BOX_ROUNDS / RESERVE_MAX`. Pistol rounds come out
      at almost nothing and the sniper's at the most expensive thing on the
      floor that is not a gun — the same shape `weapons.catalog_value` gave the
      guns, for free, with no second price list to disagree with the first.
    - **A PARTIAL FILL IS STILL A FULL PRICE**, exactly as picking a box up off
      the forest floor at 236 of 240 rounds throws the rest away. Pro-rating it
      would be a price that changes with how empty you are, which is a second
      price on the same wall.
    - **THE ART IS THE INTERACTION.** The decoration crates in this room are
      drawn shut and bound specifically to say that nothing in this shop opens;
      these are drawn OPEN — no lid, a dark interior, rounds standing proud of
      the mouth — because they are the boxes you buy out of. The five frames
      are five calibres and they are told apart the way the three mats are: by
      HUE, on a stencil across the front, plus how many rounds are in them and
      how fat those rounds are.
  - It runs the darkness like every other forest map, because it IS one — the
    ambient floor above is a value on the zone, not a branch in the renderer.
    The pitch being the brightest pool in a lit-but-dim clearing is the whole
    picture, and the torches are still NAVIGATION: the lantern is off here, and
    the chain down the south throat is what points a party at the room before
    they can see into it. The merchant
    (`server/tools/make_merchant.py`) is not an entity — he stands still and
    plays an idle loop with three flourishes interrupting it, entirely
    client-side, because nothing about which frame he is on has ever been
    worth a message.

---

## Server contracts

- **THE STORE IS WHERE MONEY IS CREATED, and it is the only place.**
  `Room.enter_store` banks `sum(rift.fed)` into `Room.balance` on the way out
  of the forest — so a night is worth exactly what the party LOADED ONTO THE
  PLATFORMS, which is the one number that measures the thing the night was
  about. Loot still in the bag is not money; it is loot they failed to
  extract, and `_clear_loot` already said so. Nothing else anywhere adds to
  the balance, and no run accumulates it as it goes.
- **`balance` is the PARTY's and `Player.gold` is a person's, and they are two
  different currencies.** The balance is GOLD: a shared bill nobody can
  honestly split after the fact, so it is one number at the top of the snapshot
  rather than a roster column — a field that differed per recipient would cost
  a re-serialisation a tick. `Player.gold` is DARK GOLD: the purple coins
  somebody personally walked over, per-player, spent on nothing yet and
  deliberately scarce (see the corpse roll below and `crates.BASE_DROPS`). Do
  not merge them, and do not let one pay for the other.

- **A store map has TWO corridors and the forest has one**, and they run
  SOUTH (the arrival, which seals) and NORTH (the way on, which never does).
  That is the whole reason `Entrance.bounds` exists: `_ranks` finds a
  corridor's tiles by scanning for VOID, and on this map that scan would hand
  the entrance every tile of the exit as well — bricking up the door the party
  is meant to leave by. (`seal_to` exists for the same family of problem and is
  left at its TREE default here, because the clearing is woods like anywhere
  else.) Nothing about either gate may be hardcoded to a compass point:
  `store.formation_slots` builds its files off `gate.dx/dy` for exactly that
  reason, and the zone turning from east-west to south-north is why.
- **THE APRON IS A FOREST MAP; THE SHOP IS THE ONE BUILDING.** The yard's
  ground, trees and darkness are the ordinary ones and his campfire is a
  `world.FIRE` tile, so almost none of it needs client code. The building is
  two TILE KINDS on the same grid — `world.BRICK` (solid, opaque) and
  `world.TILEFLOOR` (walkable, clear) — stamped by `store._stamp_shop` after
  the forest is generated. Kinds rather than a rectangle on the wire, because
  collision, sight, the terrain bake and `tests/test_store_walk.py` then all
  read the same source and the building can never disagree with the map it
  stands in. The cost is that `GROUNDS` and `CLEAR` are now MIRRORED sets in
  `world.py` / `world.ts`; before this there was one walkable kind and the rule
  was a single comparison.
- **THE BUILDING IS THE ONLY THING IN THE ZONE WITH STRAIGHT EDGES, AND ITS
  YARD IS NOT.** Everything under it — the treeline, the rim's harmonics, the
  neck's wander — is noise, because a clearing is FOUND. A building has a
  square corner and a door in the middle of a wall, so it overwrites
  unconditionally. But clearing a clean rectangle of ground around it just
  draws a second straight line with no wall under it to justify it, so the
  yard's margin is jittered per tile off the same hash the rim uses. Nothing
  is cleared to the NORTH: the exit corridor comes straight off the back wall,
  and open ground behind a shop is somewhere the party can walk and find
  nothing.
- **ITS SHAPE IS A ROOM BETWEEN TWO THROATS, AND THE ROOM IS THE POINT.**
  `_tiles` opens the UNION of a circle (`STORE_CIRCLE_TILES`, breathing on two
  harmonics plus a hash) and a neck that runs the full height of the map. It
  was a long east-west lane first, and that shape had exactly one argument —
  nobody can walk past the stock — which is a corridor's argument and a weak
  one: the party walks the same straight line every night whether or not they
  can afford anything. A round room is somewhere you STAND. Everything is
  visible from the middle at once, two players can be at the trader and at the
  cabinet without walking through each other, and a party with nothing to spend
  crosses it instead of being marched past six prices. The corridors on the
  ends keep the arrival and the departure as separate events, which is the half
  of the lane worth keeping.
  **AND IT IS A SMALL ROOM WITH THE MAN IN THE MIDDLE OF IT.** The first
  circle was sixteen tiles of radius with the trader on the west rim and the
  stalls on the east one, which is not a shop, it is a field: twenty tiles to
  read a price and twenty back to pay for it, and two halves that read as two
  unrelated places. `STORE_CIRCLE_TILES` is 11 now on a 38x46 map, and the
  composition is what every shop the player has ever seen looks like — ONE MAN
  IN THE MIDDLE, his cart behind him, his counter in front of him, his six
  stalls laid out in front of that, and everything else (the cabinet, his gear,
  the torches) around the rim. Every fixture is still authored as a
  `(column, row)` offset from the clearing's centre (`_at`); an offset measured
  from a map edge would move the day the map got taller.
- **THE WAGON IS THE ANSWER TO "WHO IS THIS MAN".** He does not have a tent any
  more — a tent pitched beside a covered cart is the same statement twice. The
  cart carries his shelter and his stock in one silhouette: guns racked on the
  flank, lanterns strung on a line, crates roped at the wheels. It is parked
  BEHIND him and stepped a little west, because a shopkeeper has a back wall
  and a canopy directly over his head is a hat.
  **IT IS NOT A HEARSE ANY MORE.** It used to hang bone masks on that line and
  lay two covered bodies with their boots out at the front wheel, on the
  argument that the party should work out where the stock comes from on their
  own. The argument was fine and the result was not: this is the one beat of
  the loop that exists to be a relief from the night, and the biggest sprite in
  it was a cart with corpses under a tarp. Same rule for anything added here —
  the shop may be poor, worn and improvised; it may not be grim.
- **THE TWO HALVES LIGHT SEPARATELY, AND THAT IS WORTH MORE THAN ANY NUMBER
  IN THE BUDGET.** The apron has the torch ring, the fire and up to three rotor
  washes; the shop has five short lamps and the machine's marquee. The wall
  between them is OPAQUE, so the two sets never sum — which is the difference
  between this layout and the clearing it replaced, where every light in the
  zone landed on one floor and the room went flat white twice.
- **THE TORCHES AND THE AMBIENT FLOOR ARE ONE LIGHT BUDGET.** `RING_TORCHES`
  around the rim, a chain down each neck and a pair at each threshold, all
  `EMBER` `SceneLight`s, all placed clear of anything meant to be LOOKED at
  (`TORCH_CLEAR`). They are the STORE's torches and not the `Entrance`'s on
  purpose: an `Entrance` can carry torches, but those are drawn out of the rift
  atlas and burn cyan, and cold lights at the top of the one warm zone in the
  game would be the wrong note.
  **THE COUNT AND THE REACH ARE PART OF A BUG FIX, NOT A TASTE.** The client
  draws every light in this zone ADDITIVELY over `zones.STORE_AMBIENT` and
  additive pools SUM with nothing clamping the total. The zone went FLAT WHITE
  on arrival, and the loudest contributor was the APRON, not the ring: three
  skids used to land within five tiles of each other at 0.85 alpha of rotor
  wash each — two overlapping washes is 1.7 of a full-bright sheet before eight
  rotors and eight strobes go on top — on a 0.7 floor with eleven seven-tile
  torches behind them. The fix is one budget spent in four places:
  `PAYOUT_SPOTS` spread so no two washes touch, `RING_TORCHES` /
  `TORCH_LIGHT_TILES` cut to 7 / 4.5, `zones.STORE_AMBIENT` down, and
  `layers/payout`'s alphas down with them. They move TOGETHER or not at all,
  and the check is walking in during a three-platform payout.

  **IT CAME DOWN A SECOND TIME, AND THE MISTAKE WAS JUDGING THE FLOOR ALONE.**
  The ambient was doing part of the torches' job: raised until the room read,
  it also raised the rim, and the eleven torch pools on top of it had no dark
  left to pool INTO — the shop was bright everywhere and lit nowhere, which is
  the same failure as white, one stop down. The pass that fixed it moved four
  numbers at once — `zones.STORE_AMBIENT` to 0.36, `layers/store`'s
  `TORCH_FIRE_ALPHA` / `LAMP_FIRE_ALPHA` to 0.55 / 0.42, and
  `layers/darkness`'s scene-pool stops to 0.135 / 0.045 — because cutting any
  one of them on its own only moves which of them is the thing that saturates.
- **`_tiles` clears a SPINE and that is a guarantee, not dressing.** The rim
  and the necks are noise (harmonics plus a hash) and a pinch plus an unlucky
  boulder could in principle wall the room off from its own door. Unlike
  `mapgen`, this module has no retry loop to fall back on — there is exactly
  one store map and the party is already walking into it — so a narrow band up
  the centreline is cleared unconditionally. What it does NOT promise any more
  is a straight walk: the man stands in the middle of his own shop now, so his
  counter, the middle column of stalls and one landing skid all claim tiles on
  the spine and the walk goes AROUND them. The spine is there to stop the
  GENERATOR sealing the room; the guarantee that the party can actually cross
  it is a check rather than a rule — `tests/test_store_walk.py` flood-fills the
  finished map and fails if the exit, the merchant, any stall or the cabinet is
  unreachable. Run it after touching any offset in the pitch block.
- **A stall sells ONCE.** It is a specific weapon on a specific table, not a
  shelf with stock behind it, so `Stand.sold` is checked and set on the same
  tick and the row STAYS on the wire — the gap where a gun was is information,
  and a table that vanished would put a hole in the grid every time somebody
  spent something. A purchase lands on the belt through the same two
  rules a found gun does: it arms an empty hand, and a full belt TRADES
  (`swap_weapon`), leaving the old gun on the shop floor so the decision is
  reversible one step later. A refused trade must not charge.
- Prices are DERIVED — `store.price_of` is the loot catalog's `value` times
  `STORE_MARKUP`. A hand-written price list would be a second opinion about
  what an AK is worth and the two would drift the first time one was
  rebalanced. On top of that each stall rolls its own haggle (`_haggle`,
  `STORE_PRICE_SPREAD`), which is what makes six stalls six decisions: the
  stock is rolled WITH REPLACEMENT against the day (`STOCK_UNLOCK`), so he can
  be holding three of the same pistol, and three tables carrying the same
  number is a shelf rather than a shop. The spread is small enough never to
  reorder the catalog — a haggled AK never undercuts a full-price FAMAS —
  because the price ladder is teaching the value of the guns.
- **The stalls are a GRID, IN FRONT OF THE MAN, and everything around them is
  not.** Three across and two deep on his own axis (`STALL_COLS` /
  `STALL_ROWS`), priced cheapest-first and filled SOUTH TO NORTH, because that
  is the order the party walks in. They are in front of him rather than off on
  the opposite rim because the stock is what he is SELLING: it belongs between
  the party and the man, in the space they are walking into anyway. The old
  lane jittered its tables off an even rhythm on the argument that four
  identical stalls at four identical intervals is the tell that nobody set this
  up by hand — right about a corridor, wrong about a market. A trader who lays
  goods out in rows wants them compared, and six prices scattered round a
  clearing is six things to hunt rather than one decision. The irregularity
  lives in the clearing; the stock is the one thing in it that was arranged.
  The LOW footprint under every fixture is still derived from the sprite WIDTH
  rather than assumed (`_claim`), because a centre is a float and does not land
  on a tile boundary.

- **THE SHOP IS THE ONE LIT PLACE, AND `Zone.ambient` IS HOW.** It is zero in
  every zone a player can be killed in — darkness hiding information is what
  makes exploring mean anything — and `zones.STORE_AMBIENT` in the merchant's
  glade, which is the contrast the whole zone exists for. It is a floor under
  the client's darkness pass, not a replacement for the lights: the fire, the
  torches and the machine's marquee still read as the brightest things in it.
- **THE NIGHT'S PLATFORMS COME HOME WITH THE PARTY.** `Room.enter_store` credits
  the balance and hands `store.build_store` the per-pad takes; the map answers
  with a `payout` row per skid — where it sets down on the apron and what it
  carried. The BALANCE and the CEREMONY are deliberately separate: the client
  animates gold off those decks, and a party that reconnected halfway through
  it must not be paid twice.
