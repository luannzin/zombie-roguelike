/**
 * One socket, for as long as the room screen is mounted.
 *
 * This hook is the reason the lobby and the arena share a connection: the
 * player who is standing at the campfire is already `player.id` on the server,
 * and starting the run must not mean reconnecting and becoming somebody else.
 * It owns the `Connection`, tracks the lobby roster, and hands the `welcome`
 * to whoever renders the arena.
 *
 * The socket auto-reconnects. A reconnect is a NEW player server-side, so the
 * fresh `welcome` carries a new `playerId` — arena consumers key on it and
 * rebuild rather than trying to patch a game whose identity changed.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CampView } from '../game/lobby-scene';
import { Connection, type ConnectionStatus } from '../net/connection';
import { roomSocketUrl } from '../net/endpoints';
import type { LobbyMessage, ServerMessage, WelcomeMessage } from '../net/protocol';

export interface RoomSession {
  connection: Connection | null;
  status: ConnectionStatus;
  /** Roster + phase. Null until the first `lobby` message lands. */
  lobby: LobbyMessage | null;
  /** Your own player id in this room, from `hello`. */
  selfId: string | null;
  /**
   * The camp, from `hello`. The lobby draws this exact map, which is the same
   * one the run starts on — see game/lobby-scene.ts.
   */
  camp: CampView | null;
  /** Set once the host starts; the arena is built from this. */
  welcome: WelcomeMessage | null;
  /** A server refusal code, e.g. `room_not_found`. Terminal. */
  error: string | null;
  /** True when you are the one who can press start. */
  isHost: boolean;
  start: () => void;
}

export function useRoomSession(code: string, name: string): RoomSession {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [lobby, setLobby] = useState<LobbyMessage | null>(null);
  const [selfId, setSelfId] = useState<string | null>(null);
  const [camp, setCamp] = useState<CampView | null>(null);
  const [welcome, setWelcome] = useState<WelcomeMessage | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The name is fixed for the life of the screen: letting it into the effect's
  // deps would tear the socket down on every keystroke of a rename.
  const nameRef = useRef(name);

  useEffect(() => {
    const socket = new Connection(roomSocketUrl(code, nameRef.current));

    const handle = (msg: ServerMessage) => {
      switch (msg.type) {
        case 'hello':
          setSelfId(msg.playerId);
          setCamp({ map: msg.map, config: msg.config });
          setError(null);
          break;
        case 'lobby':
          setLobby(msg);
          // Dropping back to the campfire (a fresh room after a reconnect)
          // must not leave a stale world behind.
          if (msg.phase === 'lobby') setWelcome(null);
          break;
        case 'welcome':
          setWelcome(msg);
          break;
        case 'error':
          setError(msg.code);
          break;
        default:
          break;
      }
    };

    const unsubscribe = [socket.onMessage(handle), socket.onStatus(setStatus)];
    socket.connect();
    setConnection(socket);

    return () => {
      for (const off of unsubscribe) off();
      socket.close();
      setConnection(null);
      setLobby(null);
      setSelfId(null);
      setCamp(null);
      setWelcome(null);
    };
  }, [code]);

  const start = useCallback(() => {
    connection?.send({ type: 'start' });
  }, [connection]);

  return {
    connection,
    status,
    lobby,
    selfId,
    camp,
    welcome,
    error,
    isHost: selfId !== null && lobby?.hostId === selfId,
    start,
  };
}
