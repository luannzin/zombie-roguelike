/**
 * The room code, as the thing you hand to a friend.
 *
 * Both copy targets are here because they answer different questions: the code
 * is what somebody types into "entrar em uma sala", the link is what you paste
 * into a chat. Each confirms in place for a beat — a copy with no feedback is
 * indistinguishable from a copy that failed.
 */

import { useEffect, useRef, useState } from 'react';

type Copied = 'code' | 'link' | null;

export interface RoomCodeProps {
  code: string;
}

export function RoomCode({ code }: RoomCodeProps) {
  const [copied, setCopied] = useState<Copied>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const copy = async (what: Exclude<Copied, null>, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
    } catch {
      // Clipboard denied (insecure origin, or the user said no). The code is
      // on screen in 22px type either way.
      return;
    }
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(null), 1400);
  };

  return (
    <div className="flex flex-col gap-2">
      <span className="pixel-text text-[11px] leading-[17px] tracking-[0.18em] text-ink-muted uppercase">
        Código da sala
      </span>

      <button
        type="button"
        onClick={() => void copy('code', code)}
        title="Copiar o código"
        className="crt-scanlines group relative cursor-pointer border border-panel-border bg-track px-3 py-3 text-center shadow-[0_0_0_1px_var(--panel-inset)] transition-colors hover:border-ink-accent focus-visible:border-ink-accent focus-visible:outline-none"
      >
        <span className="pixel-text block text-[22px] leading-[26px] tracking-[0.42em] indent-[0.42em] text-ink-accent">
          {code}
        </span>
        <span className="pixel-text mt-1 block text-[11px] leading-[17px] text-ink-muted uppercase">
          {copied === 'code' ? 'copiado!' : 'clique para copiar'}
        </span>
      </button>

      <button
        type="button"
        onClick={() => void copy('link', window.location.href)}
        className="pixel-text cursor-pointer self-start text-[11px] leading-[17px] text-ink-muted uppercase underline-offset-4 transition-colors hover:text-ink hover:underline focus-visible:text-ink focus-visible:outline-none"
      >
        {copied === 'link' ? '✓ link copiado' : 'copiar link do convite'}
      </button>
    </div>
  );
}
