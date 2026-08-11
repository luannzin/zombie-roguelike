/**
 * Low-HP danger vignette: radial red/black crush with a heartbeat pulse.
 * Drawn last, in screen space, over everything else.
 *
 * Colours come from the `--danger-*` tokens as bare `R G B` channels, since
 * every stop's alpha is computed here from danger level and heartbeat phase.
 */

import { palette } from '../../theme/palette';

const CRITICAL_DANGER = 0.65;

export function drawVignette(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  danger: number,
  time: number,
): void {
  if (danger <= 0.001) return;

  const cx = width * 0.5;
  const cy = height * 0.5;
  const radius = Math.hypot(cx, cy);

  // Heartbeat: stronger + faster as danger climbs.
  const bpm = 1.1 + danger * 2.4;
  const beat = Math.sin(time * Math.PI * 2 * bpm);
  // Soft asymmetric pulse (lub-dub-ish): sharp attack, slow release.
  const pulse = Math.pow(0.5 + 0.5 * beat, 1.6);
  const intensity = danger * (0.62 + 0.38 * pulse);

  const tone = palette().danger;
  const grad = ctx.createRadialGradient(cx, cy, radius * 0.22, cx, cy, radius * 0.98);
  grad.addColorStop(0, `rgb(${tone.inner} / 0)`);
  grad.addColorStop(0.45, `rgb(${tone.inner} / ${0.08 * intensity})`);
  grad.addColorStop(0.75, `rgb(${tone.mid} / ${0.42 * intensity})`);
  grad.addColorStop(1, `rgb(${tone.outer} / ${0.82 * intensity})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);

  // Critical: full-screen blood wash on the beat peak.
  if (danger > CRITICAL_DANGER) {
    const wash = (danger - CRITICAL_DANGER) / (1 - CRITICAL_DANGER);
    ctx.fillStyle = `rgb(${tone.wash} / ${0.1 * wash * pulse})`;
    ctx.fillRect(0, 0, width, height);
  }

  // Edge bars for a harder crush on the frame (pixel-art readable).
  const edge = Math.max(10, Math.round(Math.min(width, height) * 0.04 * (0.5 + intensity)));
  ctx.fillStyle = `rgb(${tone.edge} / ${0.35 * intensity})`;
  ctx.fillRect(0, 0, width, edge);
  ctx.fillRect(0, height - edge, width, edge);
  ctx.fillRect(0, 0, edge, height);
  ctx.fillRect(width - edge, 0, edge, height);
}
