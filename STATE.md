# STATE

Current project state. Short-lived by design — **this file is meant to be
edited often and never to become history.** Durable rules belong in
`AGENTS.md`; durable design belongs in [`docs/design/`](docs/design/).

**Ambient context, not a required read.** Consult it when the task touches a
recently changed system, when something looks like a regression, before
modifying anything under *Do not touch*, or when the task asks what to work on
next. Skip it for a self-contained change to a stable system.

_Last verified: 2026-08-19 against `main` @ `b1338e5`._

## Current phase

The full expedition loop runs end to end: camp -> forest -> extraction -> exit
-> store -> next night. The last few weeks have been **depth on the beats that
already exist** rather than new systems — the shop became a round clearing, the
knife got a real swing, the shotgun got its own dynamics, the machine got its
ceremony.

## Currently working on

- Shop map iteration (`78da442` is the newest layout; `store.py` offsets are still moving).
- Weapon feel: shotgun cone and melee swing landed; the catalog's derivation from CS2 stats is stable.

## Recently completed

| | |
| --- | --- |
| skill payout | the tin is a canned good at 16x18 (was a 16x24 aerosol tube), it no longer drops onto the machine's tray — it appears over the winner's head and flies to the HUD like any collect |
| loot frames | a frame now comes from the atlas manifest, not from catalog position — the knife and the condensed core had been drawing ammunition boxes, and every gun was drawing another gun. `test_loot_frames.py` guards it |
| dark gold | the purple coin is an ANOMALY SHARD, painted from the rift's prism at both sizes, and both drop taps cut hard so it is a rare find |
| the level-up | it used to be silent: now a summon column on the body plus an `Announce` card, the small mid-run sibling of the arrival title |
| shop | linear glade -> round clearing, man in the middle, six-stall grid, wagon |
| melee | three-beat combo with the blade following its own arc |
| shotgun | one shell, six rays, its own muzzle/impact art and audio |
| stamina | SHIFT sprint on a bar, prediction-replayable, `winded` latch |
| currency | GROUP gold (`Room.balance`) split from PLAYER dark gold (`Player.gold`) |
| skills | levels as spins, the slot cabinet, `Mods` read at every consumer site |
| extraction | cargo platform, the pour, drone pickup, siren + `hunt_all`, carved exit |

## Known problems

- **Additive light does not clamp.** The store's flat-white bug was fixed by spending one budget across four places (`STORE_AMBIENT`, `RING_TORCHES`, `TORCH_LIGHT_TILES`, `layers/payout` alphas). The underlying renderer still has no clamp, so the next zone with many lights will hit it again.
- **Naming drift is permanent and deliberate.** `rift.py` / wire `rifts` mean the extraction platform; `crates.py` / wire `crates` mean all interactive objects. Do not rename either — the cost is twenty client files for nothing.
- **Two giant files** (`server/app/room.py` 2.8k lines, `client/src/game/game.ts` 4.4k lines) — see below. Their section banners were rewritten to be honest (5 → 16 and 5 → 21); the files themselves are unchanged and still unsplit.
- Dark gold currently buys nothing. Intentional, but it means its drop taps are untested against real demand — and they were just cut hard for the shard art, so the first thing it can buy has to be priced against the NEW rate, not the old one.
- **The skill tray was empty for every run until now.** `skills.catalog_payload` shipped a list while the client declared `Record<string, SkillConfig>`, so `config.skills[key]` was `undefined` for all eighteen: no tray row, no hover card, and the payout tin always wore frame 0. Fixed, and `test_config_parity.py` now checks the SHAPE of all four catalogs, not just the top-level key set. The other three were already dicts.
- `Announce` has exactly one caller. It was built as a general mid-run card and that is what it is for; a second caller is welcome, a fork of it is not.

## Next priorities

1. Keep the shop layout stable long enough for `test_store_walk.py` to be a meaningful regression check rather than a per-commit fixture.
2. Something for dark gold to buy (per-player, never party-funded).
3. Ammunition tuning once more guns are routinely owned by day 5+.

## Do not touch

Unless the task is explicitly about them:

- `client/src/components/ui/**` — generated coss/shadcn components. Add with `bunx --bun shadcn@latest add @coss/<name>`, never hand-edit.
- `assets/processed/**` — generated output. Edit the generator in `server/tools/`.
- `assets/raw/**` and `assets/inspiration/**` — never served, never read at runtime.
- `server/.venv/`, `client/node_modules/`, `client/dist/`.
- The **six** mirror pairs, one side alone. Three are line-for-line (`simulation.py`/`simulation.ts`, `protocol.py`/`protocol.ts`, `machine.py`/`machine.ts`); three are the same rule re-derived on the other side (`world.py`/`world.ts`, `Room.collect_loot`+`Inventory.add`/`game/interaction.ts`, `ai.look`/`render/fov.ts`). The full list with the reason for each is in the root `AGENTS.md`.
- `Room.enter_store`'s balance credit — the single settlement point.

## Known technical risks

| risk | why it bites |
| --- | --- |
| mirror drift | one side edited alone: rubber-banding, or a silently dropped wire field. Six pairs, not three — the three undeclared ones (`world.ts`, `interaction.ts`, `fov.ts`) are the ones a reader will not know to check |
| generated-list insertion | inserting into `weapons.WEAPONS` / skills / loot icons shifts every frame index in already-committed sheets |
| `Mods` bypass | a site reading a raw `config.py` constant makes a skill silently do nothing, with no error |
| map generation | `mapgen`/`scenery` failures are seed-dependent; a bad edit ships and breaks one night in twenty |
| light budget | additive, unclamped; new lights saturate a zone rather than erroring |
| `Navigator.invalidate()` | forgetting it after freeing tiles leaves pathing walking into walls that are gone |
| no automated client tests | `bun run typecheck` is the only gate; everything else is two browser tabs. It is a stronger gate than it was: the always-sent half of `GameConfig` is now required, so a hedged constant is a type error rather than a silent stale value |
