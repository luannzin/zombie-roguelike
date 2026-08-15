/**
 * One labelled value on a loot card (PESO, VALOR, QTD).
 */

export interface LootCardRowProps {
  label: string;
  value: string;
}

export function LootCardRow({ label, value }: LootCardRowProps) {
  return (
    <p className="flex justify-between gap-3">
      <span className="text-ink-muted">{label}</span>
      <span className="text-ink tabular-nums">{value}</span>
    </p>
  );
}
