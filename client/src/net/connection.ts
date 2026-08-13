/**
 * Thin WebSocket wrapper: auto-reconnect, RTT measurement, multicast delivery.
 * Knows nothing about the game — it only moves JSON messages.
 *
 * Delivery is a listener SET rather than one callback because a room socket
 * has two readers with different lifetimes: the session (which owns the
 * connection from the lobby onward) and the `Game` (which exists only while
 * the arena is mounted). Each subscribes and unsubscribes independently;
 * neither can silently steal the other's messages.
 */

import type { ClientMessage, ServerMessage } from './protocol';

export type ConnectionStatus = 'connecting' | 'open' | 'closed';

export type Unsubscribe = () => void;

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

  private readonly messageListeners = new Set<(msg: ServerMessage) => void>();
  private readonly statusListeners = new Set<(status: ConnectionStatus) => void>();

  status: ConnectionStatus = 'connecting';
  rtt = 0;

  constructor(url: string) {
    this.url = url;
  }

  /** Subscribe to every non-`pong` message. Returns its own unsubscribe. */
  onMessage(listener: (msg: ServerMessage) => void): Unsubscribe {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  /** Subscribe to socket status. Fires immediately with the current value. */
  onStatus(listener: (status: ConnectionStatus) => void): Unsubscribe {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
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
      // Copied: a listener may unsubscribe itself while being notified.
      for (const listener of [...this.messageListeners]) listener(msg);
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
    this.messageListeners.clear();
    this.statusListeners.clear();
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
    for (const listener of [...this.statusListeners]) listener(status);
  }
}
