import ReconnectingWebSocket from "reconnecting-websocket";

/**
 * Single multiplexed WebSocket connection.
 *
 * Channels:
 *   orders:{accountId}          order events / fills
 *   positions:{accountId}       live position updates
 *   notifications:{userId}      alerts and notifications
 *   prices:{symbol}             market data ticks
 *
 * Subscription protocol (JSON):
 *   client → server: {"action":"subscribe","channel":"orders:acc-123"}
 *   client → server: {"action":"unsubscribe","channel":"orders:acc-123"}
 *   server → client: {"channel":"...","event":"...","data":{...}}
 */

type Listener = (payload: unknown) => void;

class WsHub {
  private socket: ReconnectingWebSocket | null = null;
  private listeners = new Map<string, Set<Listener>>();

  connect(token: string | null) {
    const url = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}/ws`;
    const wsUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    this.socket = new ReconnectingWebSocket(wsUrl, [], { maxReconnectionDelay: 10_000 });

    this.socket.addEventListener("message", (event) => {
      try {
        const msg = JSON.parse(event.data) as { channel: string; event: string; data: unknown };
        this.listeners.get(msg.channel)?.forEach((cb) => cb(msg));
      } catch {
        // Non-JSON frame — ignore.
      }
    });
  }

  subscribe(channel: string, cb: Listener): () => void {
    const set = this.listeners.get(channel) ?? new Set();
    set.add(cb);
    this.listeners.set(channel, set);
    this.send({ action: "subscribe", channel });
    return () => {
      set.delete(cb);
      if (set.size === 0) {
        this.listeners.delete(channel);
        this.send({ action: "unsubscribe", channel });
      }
    };
  }

  private send(payload: object) {
    if (this.socket?.readyState === 1) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  close() {
    this.socket?.close();
    this.socket = null;
    this.listeners.clear();
  }
}

export const wsHub = new WsHub();
