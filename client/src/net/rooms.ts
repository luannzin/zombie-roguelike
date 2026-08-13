/**
 * Room REST calls. The socket carries the game; these two carry the menu.
 *
 * Kept out of `connection.ts` on purpose: creating and checking a room happens
 * before there is anything to connect to.
 */

import { httpUrl } from './endpoints';

export interface RoomInfo {
  code: string;
  phase: 'lobby' | 'playing';
  players: number;
}

/** Create a room (and its forest) server-side. Resolves to its code. */
export async function createRoom(): Promise<string> {
  const response = await fetch(httpUrl('/rooms'), { method: 'POST' });
  if (!response.ok) throw new Error(`create room failed (${response.status})`);
  const body = (await response.json()) as { code: string };
  return body.code;
}

/** `null` when the code does not name a live room. Throws only if unreachable. */
export async function findRoom(code: string): Promise<RoomInfo | null> {
  const response = await fetch(httpUrl(`/rooms/${encodeURIComponent(code)}`));
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`room lookup failed (${response.status})`);
  return (await response.json()) as RoomInfo;
}
