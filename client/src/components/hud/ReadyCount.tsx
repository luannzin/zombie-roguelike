/**
 * Party ready count during preparation. Top-centre, no panel — a count, not a
 * widget. Hidden by the parent when the HUD chrome is off.
 */

export interface ReadyCountProps {
  ready: { here: number; total: number } | null;
}

export function ReadyCount({ ready }: ReadyCountProps) {
  if (!ready) return null;

  return (
    <p className="pixel-text text-center text-[11px] leading-[17px] tracking-[0.14em] uppercase">
      <span className="text-ink">
        {ready.here}/{ready.total}
      </span>
      <span className="text-ink-muted"> prontos</span>
    </p>
  );
}
