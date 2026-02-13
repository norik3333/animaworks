// ── State Management ──────────────────────
// Simple Pub/Sub state store. No framework needed.

let state = {
  currentUser: localStorage.getItem("animaworks_user") || null,
  persons: [],
  selectedPerson: null,
  personDetail: null,
  chatMessages: [],
  wsConnected: false,
  activeRightTab: "state",
  activeMemoryTab: "episodes",
  sessionList: null,
};

const listeners = new Set();

export function getState() {
  return state;
}

export function setState(partial) {
  state = { ...state, ...partial };
  listeners.forEach((fn) => fn(state));
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
