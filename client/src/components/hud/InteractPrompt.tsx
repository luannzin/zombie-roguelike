/**
 * Proximity prompt at the bonfire. Mounted only while the player can press E,
 * so the enter animation is the approach, not a 5 Hz flicker.
 */

export interface InteractPromptProps {
  prompt: 'ready' | null;
}

export function InteractPrompt({ prompt }: InteractPromptProps) {
  if (!prompt) return null;

  return (
    <p className="interact-prompt pixel-text text-ink flex items-center gap-1.5 text-[11px] leading-[17px]">
      Aperte
      <kbd className="border-panel-border text-ink inline-flex h-[17px] min-w-[17px] items-center justify-center border px-0.5 text-[11px] leading-[11px]">
        E
      </kbd>
      para ficar pronto
    </p>
  );
}
