import './style.css';
import { Game } from './game/game';

const canvas = document.getElementById('game') as HTMLCanvasElement;
const hud = {
  status: document.getElementById('hud-status')!,
  you: document.getElementById('hud-you')!,
  net: document.getElementById('hud-net')!,
};

const game = new Game(canvas, hud);
game.start().catch((err) => {
  console.error(err);
  hud.status.textContent = 'failed to start — see console';
});
