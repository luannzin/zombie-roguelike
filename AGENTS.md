# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- Guns are a 3-slot hotbar above the battery (keys 1/2/3, same key holsters).
  They collect onto the belt, not the pocket. The held sprite follows the
  mouse and flips when aiming left. No laser sight. The AWP zooms the camera
  out while holding to shoot. Tracers start at the barrel. Each gun has its
  own weight (slows the walk) and feel. Ammo types are named; magazines are
  not built yet.

## Project

Browser-based multiplayer 2D pixel-art zombie roguelike. Python + FastAPI
authoritative server at a fixed 30 Hz, Vite + TypeScript + Canvas 2D client, one
WebSocket carrying JSON. `README.md` is the tour; the rules below bind every
subtree.

- Open a link, pick a name, create or join a room by its 7-character code, wait
  at the campfire, start. One socket (`/ws/{code}`) carries the lobby and the
  run; rooms live in memory and die with their last player.
- A run is an **expedition loop**: prepare at the camp, go out to a level,
  extract with what you found, spend it, and go again. The first lap's hand-off
  exists — in `Preparação` the party readies at the fire, files through the
  black exit, and a second `welcome` drops them in the forest.
- **EXTRACTION is the core loop and it is not built.** The shape it will take:
  a point appears somewhere in the level, the party carries what they collected
  to it, and then they come back. The world is already laid out for it and new
  work must keep it that way — `server/app/scenery.py` returns the ROUTE its
  scenes are strung along (a walk outward from spawn ending at the landmark),
  `SceneLight`/`BEACON` is the channel a beacon arrives on, and the boot prints
  players leave behind are navigation for the trip back. Adding extraction
  should be placement and rules, never a rendering change.
- The room's ZONE (`server/app/zones.py`) says where the run is and how that
  place behaves: its title card, whether enemies spawn and guns fire
  (`hostile`), and whether the lantern may be switched on (`lantern`). The
  client is told all three and infers none of them from the map.
- **The camp is one place, not two.** The lobby draws the map the server sent
  in `hello`, with every player on the coordinates the simulation is holding
  for them; starting the run changes what answers your input, not where anybody
  is standing. Nothing may teleport at that transition. Leaving the camp is
  different: the walk-out is a puppeted march into the VOID corridor, and the
  forest `welcome` that follows is a new map. The title screen frames
  the same fire on the same rest shot (`campFireAnchor`); entering a room must
  not jump it.
- Entering a zone is an EVENT, and it is one continuous move: the lobby's chrome
  slides away while its own camera drifts off the fire onto your character and
  pushes in to game scale; the arena takes over on the frame that lands, holds
  you still and facing the camera with no HUD while the title names the day,
  and then hands back the controls and the chrome together. Every zone gets it.
- Nothing is persisted server-side. The only durable client datum is the
  player's name, in `localStorage`.
- The server is authoritative. Clients send inputs, never positions.
- Every gameplay constant lives in `server/app/config.py` and reaches the client
  in `welcome.config`. Never hardcode one client-side.
- These pairs are mirrors and change together:
  - `server/app/simulation.py` ↔ `client/src/game/simulation.ts`
  - `server/app/protocol.py` ↔ `client/src/net/protocol.ts`
- Sizes, speeds and distances are authored in tiles/seconds and multiplied by
  `TILE_SIZE`. No raw pixel numbers.
- All colours and type live in `client/src/styles/index.css`, read by the canvas
  through `client/src/theme/`.
- **Sound is generated art, like every pixel.** `server/tools/make_audio.py`
  synthesises the whole catalog into `assets/processed/audio/` — deterministic,
  stdlib only, one DSP vocabulary at the top that every recipe is written in —
  and the manifest carries each sound's gain and bus, so the mix is generated
  output rather than numbers scattered through the client. The client half is
  `client/src/audio/`: it knows about a listener at a point and sounds at other
  points, and nothing about players, zombies or zones. Sounds are SPATIAL,
  which is what makes the lantern pay off — a creature you cannot see but can
  place is the difference between tension and ambush. Ambience is stated, never
  started: a zone declares what it sounds like and the beds crossfade to it.
- Rendering knows nothing about the network; networking knows nothing about
  rendering; the server simulation knows nothing about either.
- `assets/processed/` is generated output. Edit the generator in
  `server/tools/`, never the PNG.
- The world arrives in two halves and they are placed by two different systems.
  TEXTURE — soil, grass, ferns, litter, prop variants — is scattered by the
  client from the map seed, because one rock is as good as another. SCENES —
  a cabin and its fence, a camp somebody left in a hurry, boot prints and the
  blood at the end of them — are placed by `server/app/scenery.py` and shipped
  on the map payload, because their meaning is the relationship between the
  pieces and a hash cannot agree on that. Anything decidable from
  `(tx, ty, seed)` belongs to the client; anything that means something belongs
  to a scene.
- Collectable loot is placed by the server next to those scenes
  (`server/app/loot.py`), not hashed from the seed. Five rarities (common
  white, uncommon green, rare blue, epic purple, legendary gold). E collects
  when close; the name in the tooltip takes the rarity colour. Epic and
  legendary get a small looping beam; every rarity also throws a few
  rarity-coloured motes. The sprite hides in the dark; the motes and
  aura leak a whisper so a drop can be felt before the lantern reaches
  it. Camp maps have none. The pocket is
  `server/app/inventory.py`: a few slots (upgradeable), stacking by key,
  and a weight in kg that may go past max. The open bag shows
  `current / maxkg` and the bag's item-value total. Past 20% of max carry the walk slows
  and the footsteps read heavier.   TAB expands the bag on the left HUD. A collected item is held over the
  head, the bag opens so the slot is visible, then the sprite flies into
  that cell — the slot stays empty (border, value, weight) until the
  fly lands, so the roster cannot pop a second copy. Hovering a filled
  cell is a pointer and opens a card tooltip (name, rarity, weight,
  value) that flips or shifts to stay on screen; name and rarity both
  take the rarity colour. Slot value is a small HUD coin plus the
  number. Dragging a cell
  off the panel sends `{type:"drop","slot"}`; the server places the
  stack on walkable floor near the player's feet. A full bag (no slot
  and no stack) keeps the drop tooltip and reads "Inventário Cheio".
  Guns are loot too, but they land on a 3-slot HOTBAR (`server/app/weapons.py`),
  not in the pocket — they do not stack. Everyone starts with a Glock 18.
  1 / 2 / 3 selects a slot; the same key holsters. An empty hand does not
  fire. The held sprite follows the mouse and flips when the cursor is left
  of the body. There is no laser sight. The AWP eases the camera out
  (`scopeZoom`) while the trigger is held, for more forest in frame. Tracers
  start at the barrel (`gunMuzzle`). Carry weight is bag PLUS belt. Ammo
  types (pistol / rifle / awp) are named and unused.
- Boxes, barrels and the other wood on the crate sheet are live objects
  (`server/app/crates.py`), not scenery. Scenery still places them; after
  the stamp they are pulled onto the map as crates so a smash can remove
  one. The sheet is kinds × break frames (idle is frame 0). Shoot the
  sprite (the full box, not just the foot tile) or stand close and press
  E ("E para destruir"). A smash opens the
  LOW tile to floor and rolls empty (wind VFX), a few coins, or one
  catalog item on that same tile. Camp maps have none. Interact is loot,
  then crate, then ready.
- **A hit shows on the body, and it keeps showing.** A landed shot throws
  debris BACK along the ray and blood FORWARD out the far side, so the two
  read as a round passing through something rather than stopping on it, and
  it leaves a WOUND — one frame of `assets/processed/gore/` pinned to the
  sprite and masked to its silhouette, so the mark is ON the creature and
  carried through the walk cycle until it dries. Damage the player
  can only read off a health bar is a number; damage they can see on the
  creature is damage. Only flesh bleeds: wood takes splinters and a swing the
  i-frames ate takes nothing.
- **A corpse pays a ROLL.** A creature's `gold` is the ceiling, not the
  payout — each point is flipped on its own (`COIN_DROP_CHANCE`), so the
  usual zombie drops 0 to 3 coins with both ends rare, and none of it is
  credited: the coins land on the ground and somebody has to walk over them.
  xp does not vary, because what a kill is WORTH is a rule and what fell out
  of it is luck.

## Child DOX Index

- `server/AGENTS.md` — authoritative Python server and the asset pipeline
- `client/AGENTS.md` — browser client: canvas game, React HUD, tokens, build
- `assets/AGENTS.md` — raw source art vs served production art
- `docs/AGENTS.md` — durable reference docs and design specs
- Root-owned files: `README.md`, `.gitignore`, and root-level project
  documentation.