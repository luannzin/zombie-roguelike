/**
 * Who the player is, before the server knows anything about them.
 *
 * The name box is never empty: a fresh visitor gets a generated survivor name
 * they can accept in one click. It is remembered in `localStorage` so the
 * second visit is one click shorter — there is no account and nothing here is
 * worth a database.
 */

const STORAGE_KEY = 'zr:name';
/** Mirrors MAX_NAME_LENGTH in server/app/entities.py, which enforces it. */
export const MAX_NAME_LENGTH = 16;

const ADJECTIVES = [
  'PALE', 'GRIM', 'LOST', 'RUST', 'ASH', 'DUSK', 'COLD', 'MUTE',
  'FERAL', 'STILL', 'HOLLOW', 'QUIET',
];
const NOUNS = [
  'WALKER', 'EMBER', 'CROW', 'LANTERN', 'HUNTER', 'MOTH', 'WIDOW',
  'SCOUT', 'WARDEN', 'SHADE', 'PILGRIM', 'HOUND',
];

function pick(list: readonly string[]): string {
  return list[Math.floor(Math.random() * list.length)];
}

/** A generated survivor name, always inside the server's length cap. */
export function randomName(): string {
  const name = `${pick(ADJECTIVES)}_${pick(NOUNS)}`;
  return name.slice(0, MAX_NAME_LENGTH);
}

export function loadName(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)?.trim();
    if (stored) return stored.slice(0, MAX_NAME_LENGTH);
  } catch {
    // Private mode / blocked storage: a generated name is a fine answer.
  }
  return randomName();
}

export function saveName(name: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, name.slice(0, MAX_NAME_LENGTH));
  } catch {
    // Nothing to do — the name still travels in the socket URL.
  }
}
