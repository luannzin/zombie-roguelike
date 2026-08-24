# docs/ — durable documentation

## Purpose

Long-form reference that is too detailed for `README.md` and too durable to
live in a code comment.

## Ownership

- `netcode.md` — the protocol tour: loop, message shapes, prediction and
  reconciliation, interpolation
- `superpowers/specs/` — dated design specs for features, kept as the record of
  what a feature was meant to be

## Local Contracts

- These are reference docs, not work contracts. Binding instructions live in
  `AGENTS.md` files; a doc here must not contradict one.
- Code is the source of truth for shapes and constants. `netcode.md` explains
  `server/app/protocol.py` and must be updated in the same change as a wire
  format change.
- Specs are dated (`YYYY-MM-DD-<slug>.md`) and describe intent. Leave a shipped
  spec as written rather than rewriting history; if the implementation diverged
  durably, record the current behaviour in the owning `AGENTS.md`.

## Work Guidance

- Prefer updating an existing doc over adding one. A new file here needs a
  durable audience beyond the change that produced it.

## Child DOX Index

- `design/` — per-subsystem DESIGN LAW: the argument behind each system, its
  ownership, invariants, danger zones and change surface. Ten files, one per
  subsystem, indexed from the root `AGENTS.md`. They are the "why"; the
  `AGENTS.md` chain is the "must". A rule that binds work belongs in an
  `AGENTS.md`; the reasoning that produced it belongs here.
  Do not add an eleventh without a subsystem to match it. The eighth was
  `gear.md`, and it earned the split: worn armour, the shield and the blade
  cell are one question — what stands between a blow and a player — asked
  across four files (`armor.py`, `weapons.py`, `room.py`, `store.py`), and
  `player.md` was already the longest doc here before any of it existed.
  The tenth is `ultimates.md`, and it earned it on the same test for the
  opposite reason: it is the one system that is not about a weapon OR about
  armour but about the JOIN between them. Filing it under either would have put
  half its reasoning in a doc nobody reading the other half would open.
