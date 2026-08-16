/**
 * Pixel diamond caret. Same 5-row silhouette the hunt diamond language
 * uses, painted in the HUD gold.
 */

const ROWS = [0, 1, 2, 1, 0] as const;
const UNIT = 3;

export function PixelCaret() {
  const size = UNIT * 5;
  const mid = (ROWS.length - 1) / 2;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      {ROWS.flatMap((half, row) => {
        const cells = [];
        for (let col = -half; col <= half; col++) {
          cells.push(
            <span
              key={`${row}:${col}`}
              className="bg-ink-accent absolute"
              style={{
                left: Math.round((mid + col) * UNIT),
                top: Math.round(row * UNIT),
                width: UNIT,
                height: UNIT,
                boxShadow: '1px 1px 0 var(--hud-text-shadow)',
              }}
            />,
          );
        }
        return cells;
      })}
    </div>
  );
}
