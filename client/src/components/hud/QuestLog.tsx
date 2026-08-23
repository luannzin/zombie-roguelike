/**
 * Run objectives. A Panel under the minimap, same chrome as the belt and the
 * bag, right-aligned with the map. New tasks are announced at top-centre,
 * then fly into this card the way a collect flies into the bag.
 * Completed rows rise, then leave.
 *
 * The store is a snapshot. This keeps departing copies until their leave
 * animation ends, and will not re-show a row it has already dismissed.
 *
 * THAT MEMORY IS PER MAP, AND FORGETTING TO SAY SO WAS A REAL BUG. Quest ids
 * are stable strings — `extract`, `feed`, `exit` — not per-run uniques, and
 * this component is never unmounted for the whole of a run. So the `extract`
 * row finishing on night one put `extract` in `dismissed` permanently, and
 * the objective never appeared again on any later night: the server was
 * sending it, the store had it, and this quietly filtered it out. `zoneKey`
 * is what scopes the memory to the map the ids belong to.
 *
 * The announce overlay is NOT dimmed with the rest of the chrome — it is the
 * moment the player is told what to do, and it has to play at full strength.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { HudAnnounce, HudQuest } from '../../game/hud-store';
import { Panel } from './Panel';
import { AnnounceDock } from './Announce';
import { QuestRow, type QuestRowMode } from './QuestRow';

export interface QuestLogProps {
  quests: HudQuest[];
  /** Hide the card with the rest of the HUD; the centre announce stays up. */
  dimmed: boolean;
  /**
   * The map these ids belong to (`welcome.zone.key`). Changing it forgets
   * every dismissed row — see the note in the header.
   */
  zoneKey: string | null;
}

interface QuestRowState extends HudQuest {
  mode: QuestRowMode;
}

export function QuestLog({ quests, dimmed, zoneKey }: QuestLogProps) {
  const [rows, setRows] = useState<QuestRowState[]>([]);
  const [announce, setAnnounce] = useState<HudQuest | null>(null);
  const [dock, setDock] = useState<HTMLElement | null>(null);
  const dismissed = useRef(new Set<string>());
  const seenZone = useRef<string | null>(null);

  // A new map is a new set of objectives that happen to reuse the same ids.
  // Cleared during the render that first sees the new key rather than in an
  // effect, so the merge below cannot run once against the previous map's
  // memory and drop a row before the effect catches up.
  if (seenZone.current !== zoneKey) {
    seenZone.current = zoneKey;
    dismissed.current.clear();
  }

  useEffect(() => {
    setRows((prev) => mergeRows(prev, quests, dismissed.current));
  }, [quests]);

  useEffect(() => {
    const ghost = rows.find((row) => row.mode === 'ghost');
    setAnnounce((current) => {
      if (current && ghost?.id === current.id) return current;
      return ghost ?? null;
    });
  }, [rows]);

  const onLanded = useCallback(() => {
    setRows((prev) =>
      prev.map((row) => {
        if (row.mode !== 'ghost') return row;
        if (announce && row.id !== announce.id) return row;
        return { ...row, mode: row.done ? 'leaving' : 'live' };
      }),
    );
  }, [announce]);

  const onRowGone = useCallback((id: string) => {
    dismissed.current.add(id);
    setRows((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const bindDock = useCallback((node: HTMLElement | null) => {
    setDock((prev) => (prev === node ? prev : node));
  }, []);

  if (rows.length === 0) return null;

  const flying = announce && rows.some((row) => row.id === announce.id && row.mode === 'ghost');
  const lastLeaving = rows.length === 1 && rows[0].mode === 'leaving';

  return (
    <>
      <div
        className={lastLeaving ? 'animate-quest-leave' : undefined}
        onAnimationEnd={(event) => {
          if (event.target !== event.currentTarget) return;
          if (lastLeaving) onRowGone(rows[0].id);
        }}
      >
        <Panel
          className={cn(
            'w-max max-w-none px-2.5 py-2 transition-opacity duration-700 ease-out',
            !lastLeaving && 'animate-quest-card',
            dimmed && 'opacity-0 duration-200',
          )}
        >
          <div className="mb-1.5 text-[11px] leading-[11px] whitespace-nowrap">
            <span className="text-ink-muted tracking-[0.06em]">OBJETIVOS</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {rows.map((row) => (
              <QuestRow
                key={row.id}
                quest={row}
                mode={lastLeaving ? 'shown' : row.mode}
                dockRef={flying && row.id === announce.id ? bindDock : undefined}
                onGone={onRowGone}
              />
            ))}
          </div>
        </Panel>
      </div>
      {flying && !dimmed ? (
        <AnnounceDock
          key={announce.id}
          announce={announceCard(announce)}
          dock={dock}
          onLanded={onLanded}
        />
      ) : null}
    </>
  );
}

/**
 * A new objective as the mid-run card. The TITLE is the kind of news, the
 * label is the line under it — same shape as the level-up, and the same
 * reason: at 24px a whole sentence is a cutscene, and the player needs to
 * know what KIND of thing just interrupted them before they read it.
 * A gold quota rides the card's coin slot, so the number the row will carry
 * all night is already denominated when it is announced.
 */
function announceCard(quest: HudQuest): HudAnnounce {
  return {
    key: quest.id,
    title: 'Novo Objetivo',
    subtitle: quest.label,
    ...(quest.gold ? { amount: quest.need } : {}),
  };
}

function mergeRows(
  prev: QuestRowState[],
  quests: HudQuest[],
  dismissed: Set<string>,
): QuestRowState[] {
  const live = new Map(quests.map((quest) => [quest.id, quest]));
  const next: QuestRowState[] = [];
  const kept = new Set<string>();

  for (const row of prev) {
    const fresh = live.get(row.id);
    if (!fresh) {
      next.push(row.mode === 'leaving' ? row : { ...row, mode: 'leaving' });
      kept.add(row.id);
      continue;
    }
    next.push({ ...fresh, mode: nextMode(row.mode, fresh) });
    kept.add(row.id);
  }

  for (const quest of quests) {
    if (kept.has(quest.id) || dismissed.has(quest.id)) continue;
    next.push({ ...quest, mode: quest.done ? 'leaving' : 'ghost' });
  }

  return next;
}

function nextMode(mode: QuestRowMode, fresh: HudQuest): QuestRowMode {
  if (mode === 'leaving') return mode;
  if (fresh.done && mode === 'live') return 'leaving';
  return mode;
}
