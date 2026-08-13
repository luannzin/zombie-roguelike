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
