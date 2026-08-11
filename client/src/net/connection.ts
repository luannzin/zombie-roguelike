/**
 * Thin WebSocket wrapper: auto-connect, auto-reconnect, RTT measurement.
 * Knows nothing about the game — it only moves JSON messages.
 */

import type { ClientMessage, ServerMessage } from './protocol';

export type ConnectionStatus = 'connecting' | 'open' | 'closed';

function defaultUrl(): string {
  const env = import.meta.env.VITE_SERVER_URL as string | undefined;
  if (env) return env;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Dev default: Vite on :5173, FastAPI on :8000 of the same host.
  const host = location.hostname || 'localhost';
  return `${proto}//${host}:8000/ws`;
}

export class Connection {
  readonly url: string;
  private ws: WebSocket | null = null;
  private reconnectDelay = 500;
  private pingTimer: number | null = null;

  status: ConnectionStatus = 'connecting';
  rtt = 0;

  onMessage: (msg: ServerMessage) => void = () => {};
  onStatus: (status: ConnectionStatus) => void = () => {};

  constructor(url: string = defaultUrl()) {
    this.url = url;
  }

  connect(): void {
    this.setStatus('connecting');
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectDelay = 500;
      this.setStatus('open');
      this.startPing();
    };

    ws.onmessage = (event) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data as string) as ServerMessage;
      } catch {
        return;
      }
      if (msg.type === 'pong') {
        this.rtt = Math.round(performance.now() - msg.t);
        return;
      }
      this.onMessage(msg);
    };

    ws.onclose = () => {
      this.stopPing();
      this.setStatus('closed');
      window.setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 5000);
    };

    ws.onerror = () => ws.close();
  }

  send(msg: ClientMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => {
      this.send({ type: 'ping', t: performance.now() });
    }, 1000);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.onStatus(status);
  }
}
