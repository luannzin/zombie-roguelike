/** Connection state, top-left. Turns red while the game is unusable. */

import { cn } from '../../lib/cn';
import type { ConnectionStatus } from '../../net/connection';

export interface StatusLineProps {
  status: string;
  connection: ConnectionStatus;
  error: string | null;
}

export function StatusLine({ status, connection, error }: StatusLineProps) {
  return (
    <div className={cn('text-ink-accent', (error || connection === 'closed') && 'text-hp-low')}>
      {error ?? status}
    </div>
  );
}
