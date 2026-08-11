import './style.css';
import { Game } from './game/game';
import { ProgressBar } from './ui/progress-bar';

const canvas = document.getElementById('game') as HTMLCanvasElement;
const hud = {
  status: document.getElementById('hud-status')!,
  net: document.getElementById('hud-net')!,
  minimap: document.getElementById('minimap') as HTMLCanvasElement,
  vitals: document.getElementById('vitals')!,
  name: document.getElementById('vitals-name')!,
  kd: document.getElementById('vitals-kd-value')!,
  state: document.getElementById('vitals-state')!,
  hp: new ProgressBar(document.getElementById('vitals-hp')!),
};

const game = new Game(canvas, hud);
game.start().catch((err) => {
  console.error(err);
  hud.status.textContent = 'failed to start — see console';
});
