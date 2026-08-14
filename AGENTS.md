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

## Project

Browser-based multiplayer 2D pixel-art zombie roguelike. Python + FastAPI
authoritative server at a fixed 30 Hz, Vite + TypeScript + Canvas 2D client, one
WebSocket carrying JSON. `README.md` is the tour; the rules below bind every
subtree.

- Open a link, pick a name, create or join a room by its 7-character code, wait
  at the campfire, start. One socket (`/ws/{code}`) carries the lobby and the
  run; rooms live in memory and die with their last player.
- A run is an **expedition loop**: prepare at the camp, go out to a level,
  extract with what you found, spend it, and go again. The first lap's
  hand-off exists: in `Preparação` the party readies at the fire, files
  through the black exit, and a second `welcome` drops them in the forest.
  Extract and return are not built.
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
- Rendering knows nothing about the network; networking knows nothing about
  rendering; the server simulation knows nothing about either.
- `assets/processed/` is generated output. Edit the generator in
  `server/tools/`, never the PNG.

## Child DOX Index

- `server/AGENTS.md` — authoritative Python server and the asset pipeline
- `client/AGENTS.md` — browser client: canvas game, React HUD, tokens, build
- `assets/AGENTS.md` — raw source art vs served production art
- `docs/AGENTS.md` — durable reference docs and design specs
- Root-owned files: `README.md`, `.gitignore`, and root-level project
  documentation.