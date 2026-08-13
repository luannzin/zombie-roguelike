/**
 * "Entrar em uma sala" — the code prompt.
 *
 * Built on the coss `Dialog` (portal, focus trap, escape handling, scroll
 * lock: all things worth not rewriting) with the panel dressed in HUD chrome.
 *
 * The code is checked against the server BEFORE routing anywhere. Sending
 * someone to a room screen that immediately fails is a worse answer than
 * telling them here, in the field they are still looking at.
 */

import { useEffect, useRef, useState } from 'react';
import { Dialog, DialogPopup } from '@/components/ui/dialog';
import { HudInput } from './HudInput';
import { MenuButton } from './MenuButton';
import { findRoom } from '@/net/rooms';

/** Server codes are 7 characters — see CODE_LENGTH in server/app/rooms.py. */
const CODE_LENGTH = 7;

export interface JoinRoomDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJoin: (code: string) => void;
}

/** Uppercase, alphanumerics only, capped. Also survives a pasted invite link. */
function sanitize(raw: string): string {
  const tail = raw.trim().split(/[/?#]/).filter(Boolean).pop() ?? '';
  return tail.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, CODE_LENGTH);
}

export function JoinRoomDialog({ open, onOpenChange, onJoin }: JoinRoomDialogProps) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  /** Bumped on every rejection so the shake animation restarts. */
  const [attempt, setAttempt] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setCode('');
    setError(null);
    setChecking(false);
    // The dialog animates in; focusing on the next frame lands after it.
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const submit = async () => {
    if (code.length !== CODE_LENGTH || checking) return;
    setChecking(true);
    setError(null);
    try {
      const room = await findRoom(code);
      if (!room) {
        setError('sala não encontrada');
        setAttempt((n) => n + 1);
        inputRef.current?.select();
        return;
      }
      onJoin(room.code);
    } catch {
      setError('servidor fora do ar');
      setAttempt((n) => n + 1);
    } finally {
      setChecking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup
        showCloseButton={false}
        bottomStickOnMobile={false}
        className="crt-scanlines max-w-sm border-panel-border bg-panel shadow-[0_0_0_1px_var(--panel-inset)] before:hidden"
        aria-label="Entrar em uma sala"
      >
        <form
          className="flex flex-col gap-5 p-6"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="flex flex-col gap-1">
            <h2 className="pixel-text text-[22px] leading-[26px] tracking-[0.1em] text-ink uppercase">
              Entrar em uma sala
            </h2>
            <p className="pixel-text text-[11px] leading-[17px] text-ink-muted">
              Peça o código de 7 dígitos para quem criou a sala.
            </p>
          </div>

          <div key={attempt} className={error ? 'animate-toast-error-odd' : undefined}>
            <HudInput
              ref={inputRef}
              label="Código da sala"
              placeholder="ABC1234"
              value={code}
              invalid={Boolean(error)}
              hint={error ?? `${code.length}/${CODE_LENGTH}`}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              inputMode="text"
              className="text-center text-[22px] leading-[30px] tracking-[0.5em] indent-[0.5em]"
              onChange={(event) => {
                setCode(sanitize(event.target.value));
                setError(null);
              }}
            />
          </div>

          <div className="flex gap-2">
            <MenuButton variant="quiet" onClick={() => onOpenChange(false)}>
              Cancelar
            </MenuButton>
            <MenuButton
              type="submit"
              variant="primary"
              disabled={code.length !== CODE_LENGTH || checking}
            >
              {checking ? 'Procurando…' : 'Entrar'}
            </MenuButton>
          </div>
        </form>
      </DialogPopup>
    </Dialog>
  );
}
