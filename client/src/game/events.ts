/**
 * What the night's events LOOK and SOUND like. One row per `events.py` key.
 *
 * THE SERVER SHIPS A KEY AND NOTHING ELSE, which is deliberate and is the same
 * split every other piece of copy in this game makes: `server/app/` holds no
 * interface text, no colours and no sounds, and an event is not the exception.
 * The wire row is `{k, x?, y?}` — what happened, and where if that means
 * anything — and everything a player actually perceives is decided here.
 *
 * WHY A TABLE AND NOT A SWITCH. Adding an event should be a row on each side
 * and nothing else. A `switch (row.k)` in the snapshot handler would work
 * exactly as well for four events and would be the thing somebody has to
 * untangle at twelve, and it would put the copy for the airdrop several
 * hundred lines away from the copy for the horde.
 *
 * A KEY WITH NO ROW IS NOT AN ERROR. A client can be older than the server it
 * is talking to, and the correct behaviour when an unknown event arrives is to
 * ignore it rather than to throw inside the snapshot handler — the alternative
 * is one unrecognised string taking the whole frame loop down.
 */

export interface EventPresentation {
  /** The card. Both lines, in the game's voice. */
  title: string;
  subtitle: string;
  /**
   * The cue, from the generated library. Played AT `x`/`y` when the row
   * carries one, so an event with a place is heard as a bearing.
   */
  sfx: string;
  /**
   * How hard the lens flinches. Zero for events that are not a shock — an
   * airdrop is good news and a camera that kicked for it would read as a
   * threat before the player had read the card.
   */
  trauma: number;
  /**
   * Push a beacon at the row's place. Only for events the party is meant to be
   * able to FIND: an opportunity nobody can locate is a threat with extra
   * steps. Same channel the extraction pad's lamp uses.
   */
  beacon?: boolean;
}

export const EVENT_PRESENTATION: Record<string, EventPresentation> = {
  /*
   * THE WAVE. It already has a spatial howl of its own on the `hordes` wire —
   * that is the channel that works with your back turned, and it plays at the
   * bearing the bodies will come from. So this row deliberately carries NO
   * sound: two cues for one event would be the game shouting twice, and the
   * one that matters is the one with a direction in it.
   */
  horde: {
    title: 'A MATA SE MEXE',
    subtitle: 'Algo grande vem vindo',
    sfx: '',
    trauma: 0,
  },
  /*
   * THE DARK. No bearing, because it is not in a direction — see `_dark` in
   * `events.py`. The cue is the void, which is the game's own "something has
   * been taken away" sound, and the lens flinch is the largest of any event
   * here: it is the only one that changes a rule the player had been relying
   * on all night.
   */
  dark: {
    title: 'A NOITE FECHA',
    subtitle: 'As luzes morrem',
    sfx: 'void',
    trauma: 0.5,
  },
  /*
   * THE CRATE. The only good news in the catalog, and everything here says so:
   * no flinch, a beacon so it can actually be walked to, and the summon cue
   * rather than anything with teeth in it.
   */
  airdrop: {
    title: 'SUPRIMENTOS',
    subtitle: 'Algo caiu na mata',
    sfx: 'summon',
    trauma: 0,
    beacon: true,
  },
  /*
   * A BODY WENT DOWN AND THE WOODS HEARD IT. Played AT the fall, so the cue
   * points at the teammate who needs reaching — which under permadeath is the
   * single most important direction on the map.
   */
  blood: {
    title: 'SANGUE NA MATA',
    subtitle: 'Elas sentiram',
    sfx: 'dread',
    trauma: 0.25,
  },
};
