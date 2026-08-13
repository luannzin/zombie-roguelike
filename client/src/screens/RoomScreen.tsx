/**
 * A room, at `/r/:code` — the link you send to a friend.
 *
 * One socket serves both halves of this screen (see `useRoomSession`), so the
 * lobby and the arena are two renders of one connection, not two connections.
 * Which one is shown is decided by a single fact: whether a `welcome` has
 * arrived.
 *
 * The arena is keyed on `playerId`. A reconnect makes you a new player
 * server-side, and a `Game` cannot be patched into a different identity.
 */

import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { MenuButton } from '@/components/menu/MenuButton';
import { useRoomSession } from '@/hooks/useRoomSession';
import { loadName } from '@/lib/identity';
import { ArenaScreen } from './ArenaScreen';
import { LobbyScreen } from './LobbyScreen';

const ERRORS: Record<string, string> = {
  room_not_found: 'Esta sala não existe mais.',
};

export function RoomScreen() {
  const { code = '' } = useParams();
  const navigate = useNavigate();
  // Read once: the name is fixed for the life of the room, and re-reading it
  // would tear down the socket.
  const [name] = useState(loadName);
  const session = useRoomSession(code.toUpperCase(), name);

  const leave = () => void navigate('/');

  if (session.error) {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center gap-5 bg-surface">
        <p className="pixel-text text-[22px] leading-[26px] tracking-[0.1em] text-hp-low uppercase">
          {ERRORS[session.error] ?? 'Não foi possível entrar.'}
        </p>
        <div className="w-64">
          <MenuButton onClick={leave}>← Voltar ao menu</MenuButton>
        </div>
      </div>
    );
  }

  if (session.connection && session.welcome) {
    return (
      <ArenaScreen
        key={session.welcome.playerId}
        connection={session.connection}
        welcome={session.welcome}
      />
    );
  }

  return <LobbyScreen code={session.lobby?.code ?? code.toUpperCase()} session={session} onLeave={leave} />;
}
