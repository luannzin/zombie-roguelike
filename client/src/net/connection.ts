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
  private reconnectTimer: number | null = null;
  /**
   * Set by `close()`. Without it, closing the socket only triggers the
   * onclose reconnect — the connection would be impossible to stop, because
   * closing it IS the signal to reopen it.
   */
  private disposed = false;

  status: ConnectionStatus = 'connecting';
  rtt = 0;

  onMessage: (msg: ServerMessage) => void = () => {};
  onStatus: (status: ConnectionStatus) => void = () => {};

  constructor(url: string = defaultUrl()) {
    this.url = url;
  }

  connect(): void {
    if (this.disposed) return;
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
      if (this.disposed) return;
      this.setStatus('closed');
      this.reconnectTimer = window.setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 5000);
    };

    ws.onerror = () => ws.close();
  }

  /**
   * Permanently stop this connection: no reconnect, no ping, no callbacks.
   * Required for React effect cleanup, HMR and leaving a room. Idempotent.
   */
  close(): void {
    this.disposed = true;
    this.stopPing();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      // Drop handlers first so the in-flight close cannot call back into a
      // game that is already torn down.
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    }
    this.onMessage = () => {};
    this.onStatus = () => {};
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
