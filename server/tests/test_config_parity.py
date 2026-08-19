"""`client_config()` against the client's `GameConfig`, in both directions.

Run:  python tests/test_config_parity.py   (from server/)

THIS TEST EXISTS BECAUSE THE CONTRACT HAS NO RUNTIME SYMPTOM. Every gameplay
constant is supposed to live here and reach the client in `welcome.config`
(see the root `AGENTS.md`). The client used to hedge — `config.staminaMax ?? 100`
— which meant a constant moving on this side kept working while the client
silently ran on a copy of the old number. Two of them had already drifted that
way (`INVENTORY_SLOTS` 3 -> 5, `CARRY_MAX_WEIGHT` 10 -> 14) with nothing
failing anywhere.

The fix was to declare every always-sent field REQUIRED in
`client/src/net/protocol.ts` and delete the fallbacks, which makes `tsc` the
enforcement — but only for as long as the two files agree on what "always
sent" means. That is what this checks:

  * every key the client declares REQUIRED is actually in the payload, and
    is not None (a null would land as `undefined` behind a non-optional type)
  * every key the payload sends is declared by the client, so a constant
    added here without a mirror row is caught at the source rather than by
    somebody wondering why the value never arrived

Optional (`?:`) fields on `GameConfig` are ignored in both directions: those
are the client's declared "may be absent" surface and it hedges for them
deliberately.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import client_config  # noqa: E402

PROTOCOL_TS = (
    Path(__file__).resolve().parents[2] / "client" / "src" / "net" / "protocol.ts"
)

#: One `  name: type;` or `  name?: type;` line at the top level of an interface.
#: Anchored at exactly two spaces so nested object literals are skipped — those
#: are separate interfaces (`rift`, `machine`, `ammo`) with their own shapes,
#: and this test is about the TOP-LEVEL config surface only.
_FIELD = re.compile(r"^  (?P<name>[a-zA-Z][a-zA-Z0-9]*)(?P<opt>\??): ", re.M)


def game_config_fields() -> tuple[set[str], set[str]]:
    """(required, optional) field names on the client's `GameConfig`."""
    source = PROTOCOL_TS.read_text(encoding="utf-8")
    start = source.index("export interface GameConfig {")
    end = source.index("\n}\n", start)
    body = source[start:end]
    required: set[str] = set()
    optional: set[str] = set()
    for match in _FIELD.finditer(body):
        (optional if match.group("opt") else required).add(match.group("name"))
    return required, optional


def main() -> None:
    payload = client_config()
    required, optional = game_config_fields()

    assert required, "parsed no required fields — has GameConfig moved or been renamed?"

    # 1. Everything the client trusts must actually arrive.
    missing = required - set(payload)
    assert not missing, (
        f"GameConfig declares {sorted(missing)} required, but client_config() "
        "does not send them. Either send them or mark them `?:` — a missing "
        "key behind a non-optional type is `undefined` at runtime with no error."
    )

    # 2. ...and must not arrive as null, which is the same failure wearing a
    #    key. `_finite` returns None for the rift's "never" sentinels, but
    #    those live INSIDE `rift`, not at the top level.
    nulls = sorted(key for key in required if payload[key] is None)
    assert not nulls, (
        f"client_config() sends {nulls} as null behind a required type. "
        "JSON null parses to `null`, which every consumer will read as a number."
    )

    # 3. Nothing may be sent that the client has no row for. This is the half
    #    that catches the real mistake: adding a constant here, wiring it into
    #    the payload, and forgetting the mirror — the value ships, costs
    #    bandwidth every welcome, and is unreachable.
    undeclared = set(payload) - required - optional
    assert not undeclared, (
        f"client_config() sends {sorted(undeclared)}, which `GameConfig` does "
        "not declare. Add the field in client/src/net/protocol.ts — the two "
        "files are one contract."
    )

    # 4. The sight-symmetry pair specifically, because it is the one contract
    #    here whose breakage is invisible: `render/fov.ts` draws the player's
    #    vision at these reaches and `ai.look` tests the creature's cone
    #    against the same ones. A client left to guess would show a radius the
    #    creatures do not respect, and nothing anywhere would say so.
    assert "enemyViewDarkScale" in required and "enemyViewLitScale" in required, (
        "the sight scales must be REQUIRED client-side — a hedged default is "
        "exactly the drift this pair cannot survive"
    )

    print("ok")


if __name__ == "__main__":
    main()
