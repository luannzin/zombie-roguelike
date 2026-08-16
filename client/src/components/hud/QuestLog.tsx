/**
 * Run objectives. Top-centre with the ready count — a list, not a panel.
 * Hidden by the parent while HUD chrome is off, so the first row lands
 * after the woods have swallowed the way in.
 *
 * The store is a snapshot; rows that disappear still need a leave beat.
 * This keeps a departing copy until QuestRow finishes its out animation.
 */

import { useCallback, useEffect, useState } from 'react';
import type { HudQuest } from '../../game/hud-store';
import { QuestRow } from './QuestRow';

export interface QuestLogProps {
  quests: HudQuest[];
}

interface QuestRowState extends HudQuest {
  leaving: boolean;
}

export function QuestLog({ quests }: QuestLogProps) {
  const [rows, setRows] = useState<QuestRowState[]>([]);

  useEffect(() => {
    setRows((prev) => {
      const live = new Map(quests.map((quest) => [quest.id, quest]));
      const next: QuestRowState[] = [];
      const kept = new Set<string>();

      for (const row of prev) {
        const fresh = live.get(row.id);
        if (fresh) {
          next.push({ ...fresh, leaving: false });
          kept.add(row.id);
          continue;
        }
        if (row.leaving) {
          next.push(row);
          continue;
        }
        next.push({ ...row, leaving: true });
      }

      for (const quest of quests) {
        if (kept.has(quest.id)) continue;
        next.push({ ...quest, leaving: false });
      }

      return next;
    });
  }, [quests]);

  const onGone = useCallback((id: string) => {
    setRows((prev) => prev.filter((row) => row.id !== id));
  }, []);

  if (rows.length === 0) return null;

  return (
    <div className="flex flex-col items-center gap-0.5">
      {rows.map((row, index) => (
        <QuestRow
          key={row.id}
          quest={row}
          index={index}
          leaving={row.leaving}
          onGone={onGone}
        />
      ))}
    </div>
  );
}
