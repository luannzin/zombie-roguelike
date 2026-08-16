/**
 * Run objectives. A Panel under the minimap, same chrome as the belt and the
 * bag. New tasks are announced big at centre, then fly into this card.
 * Completed rows rise, then leave.
 *
 * The store is a snapshot. This keeps departing copies until their leave
 * animation ends, and will not re-show a row it has already dismissed.
 *
 * The announce overlay is NOT dimmed with the rest of the chrome — it is the
 * moment the player is told what to do, and it has to play at full strength.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { HudQuest } from '../../game/hud-store';
import { Panel } from './Panel';
import { QuestAnnounce } from './QuestAnnounce';
import { QuestRow, type QuestRowMode } from './QuestRow';

export interface QuestLogProps {
  quests: HudQuest[];
  /** Hide the card with the rest of the HUD; the centre announce stays up. */
  dimmed: boolean;
}

interface QuestRowState extends HudQuest {
  mode: QuestRowMode;
}

export function QuestLog({ quests, dimmed }: QuestLogProps) {
  const [rows, setRows] = useState<QuestRowState[]>([]);
  const [announce, setAnnounce] = useState<HudQuest | null>(null);
  const [dock, setDock] = useState<HTMLElement | null>(null);
  const dismissed = useRef(new Set<string>());

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
            'w-full px-2.5 py-2 transition-opacity duration-700 ease-out',
            !lastLeaving && 'animate-quest-card',
            dimmed && 'opacity-0 duration-200',
          )}
        >
          <div className="mb-1.5 text-[11px] leading-[11px]">
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
        <QuestAnnounce
          key={announce.id}
          quest={announce}
          dock={dock}
          onLanded={onLanded}
        />
      ) : null}
    </>
  );
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
