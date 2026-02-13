// ── WebSocket Connection Manager ──────────────────────
// Auto-reconnect + event dispatch.

import { setState } from "./state.js";

const WS_RECONNECT_DELAY = 3000;

let ws = null;
let reconnectTimer = null;
const eventHandlers = new Map(); // type -> Set<callback>

function getWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  ws = new WebSocket(getWsUrl());

  ws.addEventListener("open", () => {
    setState({ wsConnected: true });
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  });

  ws.addEventListener("message", (event) => {
    try {
      const msg = JSON.parse(event.data);
      const handlers = eventHandlers.get(msg.type);
      if (handlers) {
        handlers.forEach((fn) => fn(msg.data, msg.type));
      }
      // Also fire wildcard listeners
      const wildcards = eventHandlers.get("*");
      if (wildcards) {
        wildcards.forEach((fn) => fn(msg.data, msg.type));
      }
    } catch {
      // ignore non-JSON messages
    }
  });

  ws.addEventListener("close", () => {
    setState({ wsConnected: false });
    scheduleReconnect();
  });

  ws.addEventListener("error", () => {
    setState({ wsConnected: false });
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, WS_RECONNECT_DELAY);
}

/**
 * Register handler for a WebSocket event type.
 * Use "*" to listen to all events.
 * Returns unsubscribe function.
 */
export function onEvent(type, fn) {
  if (!eventHandlers.has(type)) {
    eventHandlers.set(type, new Set());
  }
  eventHandlers.get(type).add(fn);
  return () => eventHandlers.get(type).delete(fn);
}

export function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
}
