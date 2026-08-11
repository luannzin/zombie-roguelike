/**
 * Shared HUD progress bar (HP now, XP later).
 * Drive fill via --progress (0..1) and optional tone for fill color.
 */

export type ProgressTone = 'hp' | 'xp' | 'neutral';

export interface ProgressBarUpdate {
  current: number;
  max: number;
  /** Left-side caption, e.g. "HP" / "XP". */
  label?: string;
  tone?: ProgressTone;
}

function hpLevel(ratio: number): 'high' | 'mid' | 'low' {
  if (ratio > 0.5) return 'high';
  if (ratio > 0.25) return 'mid';
  return 'low';
}

export class ProgressBar {
  private readonly fill: HTMLElement;
  private readonly value: HTMLElement;
  private readonly caption: HTMLElement;

  constructor(private readonly root: HTMLElement) {
    this.fill = root.querySelector('.progress-fill') as HTMLElement;
    this.value = root.querySelector('.progress-value') as HTMLElement;
    this.caption = root.querySelector('.progress-caption') as HTMLElement;
    if (!this.fill || !this.value || !this.caption) {
      throw new Error('progress-bar: missing .progress-fill / .progress-value / .progress-caption');
    }
  }

  set({ current, max, label, tone = 'neutral' }: ProgressBarUpdate): void {
    const safeMax = Math.max(0, max);
    const clamped = Math.max(0, Math.min(safeMax, current));
    const ratio = safeMax > 0 ? clamped / safeMax : 0;

    this.root.style.setProperty('--progress', String(ratio));
    this.root.dataset.tone = tone;
    if (tone === 'hp') this.root.dataset.level = hpLevel(ratio);
    else delete this.root.dataset.level;

    if (label !== undefined) this.caption.textContent = label;
    this.value.textContent = `${Math.round(clamped)} / ${Math.round(safeMax)}`;
  }

  clear(): void {
    this.root.style.setProperty('--progress', '0');
    this.value.textContent = '— / —';
    delete this.root.dataset.level;
  }
}
