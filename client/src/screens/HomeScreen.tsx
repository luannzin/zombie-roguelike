/**
 * The title screen.
 *
 * Two stages on one route: the menu, and the play panel it opens into. They
 * are not separate routes because there is nothing to link to or come back to
 * — the only durable addresses in this game are `/` and a room.
 *
 * The campfire behind it is the same scene the lobby draws, with nobody in it,
 * framed on the same rest shot. That is the whole point: an empty fire waiting
 * for a party, that does not jump when you walk into a room.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { setBeds } from '@/audio';
import { CampfireCanvas } from '@/components/lobby/CampfireCanvas';
import { AudioOptions } from '@/components/menu/AudioOptions';
import { HudInput } from '@/components/menu/HudInput';
import { JoinRoomDialog } from '@/components/menu/JoinRoomDialog';
import { MenuButton } from '@/components/menu/MenuButton';
import { loadName, MAX_NAME_LENGTH, randomName, saveName } from '@/lib/identity';
import { cn } from '@/lib/utils';
import { createRoom } from '@/net/rooms';

/** Nobody is at the fire on the title screen. Hoisted so it is a stable ref. */
const NOBODY = Object.freeze([]) as never[];
/**
 * How long a menu choice is acknowledged before it is obeyed, in ms. Matches
 * the `menu-select` keyframes in styles/index.css; changing one without the
 * other either cuts the flick short or leaves a dead pause after it.
 */
const CONFIRM_MS = 360;

type Stage = 'menu' | 'play' | 'options';

interface MenuEntry {
  label: string;
  onSelect: () => void;
}

export function HomeScreen() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>('menu');
  const [name, setName] = useState(loadName);
  const [creating, setCreating] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  // Memoised because the key handler below depends on it; a fresh array each
  // render would resubscribe the window listener on every keystroke.
  const entries = useMemo<MenuEntry[]>(
    () => [
      { label: 'Jogar', onSelect: () => setStage('play') },
      { label: 'Opções', onSelect: () => setStage('options') },
    ],
    [],
  );
  const [selected, setSelected] = useState(0);
  /** Label of the item playing its confirm flick, if any. */
  const [confirming, setConfirming] = useState<string | null>(null);
  const confirmTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (confirmTimer.current !== null) window.clearTimeout(confirmTimer.current);
    },
    [],
  );

  /**
   * Acknowledge a menu choice, then act on it.
   *
   * The delay is the feature: the item flicks and desaturates first (see the
   * `menu-select` keyframes) and the screen only changes once that has played.
   * Acting immediately is faster and feels like a web page.
   */
  const select = useCallback((entry: MenuEntry) => {
    if (confirmTimer.current !== null) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      entry.onSelect();
      return;
    }
    setConfirming(entry.label);
    confirmTimer.current = window.setTimeout(() => {
      confirmTimer.current = null;
      setConfirming(null);
      entry.onSelect();
    }, CONFIRM_MS);
  }, []);

  /** The name is committed on the way out, not on every keystroke. */
  const commitName = useCallback((): string => {
    const trimmed = name.trim().slice(0, MAX_NAME_LENGTH) || randomName();
    if (trimmed !== name) setName(trimmed);
    saveName(trimmed);
    return trimmed;
  }, [name]);

  const enterRoom = useCallback(
    (code: string) => {
      commitName();
      void navigate(`/r/${code}`);
    },
    [commitName, navigate],
  );

  const create = async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      enterRoom(await createRoom());
    } catch {
      setError('não foi possível falar com o servidor');
      setCreating(false);
    }
  };

  // Menu keyboard: a title screen that only answers the mouse feels like a web
  // page. Only bound in the menu stage, so it never eats a keystroke meant for
  // the name field or the join dialog.
  useEffect(() => {
    if (stage !== 'menu') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowDown') {
        setSelected((i) => (i + 1) % entries.length);
      } else if (event.key === 'ArrowUp') {
        setSelected((i) => (i - 1 + entries.length) % entries.length);
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const entry = entries[selected];
        if (entry) select(entry);
      } else {
        return;
      }
      event.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stage, selected, entries, select]);

  // Escape backs out of either panel — but not while the dialog owns it.
  useEffect(() => {
    if (stage === 'menu' || joinOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setStage('menu');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stage, joinOpen]);

  /**
   * THE TITLE SCREEN IS SILENT.
   *
   * The fire behind the menu is a picture, not a place you are standing in —
   * it belongs to a camp you have not reached yet, and hearing it here spends
   * the arrival before the player has gone anywhere. Stated on mount rather
   * than left alone, because leaving a lobby comes back to this screen with
   * the bonfire still burning (`LobbyScreen` deliberately does not clear it,
   * so the hand-off into a run has no gap). Whoever mounts declares the mix.
   */
  useEffect(() => {
    setBeds({});
  }, []);

  useEffect(() => {
    if (stage === 'play') nameRef.current?.focus();
  }, [stage]);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-surface">
      <CampfireCanvas members={NOBODY} className="absolute inset-0" />
      {/* Legibility scrim: the menu sits on top of a live scene. */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-surface via-surface/78 to-transparent" />

      <div className="relative flex h-full max-w-xl flex-col justify-center gap-10 px-8 sm:px-14">
        <h1 className="pixel-text animate-sign-flicker select-none">
          <span className="block text-[33px] leading-[37px] tracking-[0.3em] text-ink uppercase">
            Zombie
          </span>
          <span className="block text-[55px] leading-[59px] tracking-[0.1em] text-ink-accent uppercase drop-shadow-[0_3px_0_var(--hud-text-shadow)]">
            Roguelike
          </span>
        </h1>

        {stage === 'menu' ? (
          <nav
            className={cn(
              'flex w-64 flex-col items-start gap-1',
              // No second choice while one is being acknowledged.
              confirming && 'pointer-events-none',
            )}
          >
            {entries.map((entry, index) => (
              <button
                key={entry.label}
                type="button"
                onMouseEnter={() => setSelected(index)}
                onClick={() => select(entry)}
                className={cn(
                  'pixel-text group flex cursor-pointer items-center gap-3 py-1.5 text-[22px] leading-[26px] tracking-[0.16em] uppercase transition-colors focus-visible:outline-none',
                  index === selected ? 'text-ink-accent' : 'text-ink-muted hover:text-ink',
                  // The keyframes drive `color` directly, so they win over the
                  // classes above for as long as the flick is running.
                  confirming === entry.label && 'animate-menu-select',
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    'inline-block transition-[opacity,translate] duration-150',
                    index === selected
                      ? 'translate-x-0 opacity-100'
                      : '-translate-x-2 opacity-0',
                  )}
                >
                  ▸
                </span>
                {entry.label}
              </button>
            ))}
          </nav>
        ) : stage === 'options' ? (
          <div className="animate-in fade-in slide-in-from-bottom-2 flex w-full max-w-sm flex-col gap-6 duration-200">
            <h2 className="pixel-text text-[22px] leading-[26px] tracking-[0.16em] text-ink-accent uppercase">
              Opções
            </h2>

            <section className="flex flex-col gap-4">
              <h3 className="pixel-text text-[11px] leading-[17px] tracking-[0.2em] text-ink-muted uppercase">
                Áudio
              </h3>
              <AudioOptions />
            </section>

            <MenuButton variant="quiet" onClick={() => setStage('menu')}>
              ← Voltar (esc)
            </MenuButton>
          </div>
        ) : (
          <div className="animate-in fade-in slide-in-from-bottom-2 flex w-full max-w-sm flex-col gap-5 duration-200">
            <HudInput
              ref={nameRef}
              label="Seu nome"
              value={name}
              maxLength={MAX_NAME_LENGTH}
              autoComplete="off"
              spellCheck={false}
              hint={
                <button
                  type="button"
                  onClick={() => setName(randomName())}
                  className="cursor-pointer uppercase underline-offset-4 hover:text-ink hover:underline"
                >
                  ⟳ sortear outro nome
                </button>
              }
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void create();
              }}
            />

            <div className="flex flex-col gap-2">
              <MenuButton variant="primary" disabled={creating} onClick={() => void create()}>
                {creating ? 'Acendendo a fogueira…' : 'Criar uma sala'}
              </MenuButton>
              <MenuButton onClick={() => setJoinOpen(true)}>Entrar em uma sala</MenuButton>
              <MenuButton variant="quiet" onClick={() => setStage('menu')}>
                ← Voltar (esc)
              </MenuButton>
            </div>

            {error ? (
              <p className="pixel-text text-[11px] leading-[17px] text-hp-low">{error}</p>
            ) : null}
          </div>
        )}
      </div>

      <p className="pixel-text pointer-events-none absolute bottom-3 left-4 text-[11px] leading-[17px] text-ink-muted uppercase">
        Zombie Roguelike — vertical slice
      </p>

      <JoinRoomDialog open={joinOpen} onOpenChange={setJoinOpen} onJoin={enterRoom} />
    </div>
  );
}
