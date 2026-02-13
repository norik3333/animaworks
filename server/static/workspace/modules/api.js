// ── API Client ──────────────────────
// Thin fetch wrapper for all REST endpoints.

const BASE = "";

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

function post(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Person ──────────────────────

export function fetchPersons() {
  return request("/api/persons");
}

export function fetchPersonDetail(name) {
  return request(`/api/persons/${encodeURIComponent(name)}`);
}

// ── Chat ──────────────────────

export function sendChat(name, message, userName) {
  return post(`/api/persons/${encodeURIComponent(name)}/chat`, {
    message,
    from_person: userName || "human",
  });
}

/**
 * Start SSE chat stream. Returns the raw Response for manual reading.
 */
export function sendChatStream(name, message, userName) {
  return fetch(`/api/persons/${encodeURIComponent(name)}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, from_person: userName || "human" }),
  });
}

// ── Memory ──────────────────────

export function fetchEpisodes(name) {
  return request(`/api/persons/${encodeURIComponent(name)}/episodes`);
}

export function fetchEpisode(name, date) {
  return request(`/api/persons/${encodeURIComponent(name)}/episodes/${encodeURIComponent(date)}`);
}

export function fetchKnowledge(name) {
  return request(`/api/persons/${encodeURIComponent(name)}/knowledge`);
}

export function fetchKnowledgeTopic(name, topic) {
  return request(`/api/persons/${encodeURIComponent(name)}/knowledge/${encodeURIComponent(topic)}`);
}

export function fetchProcedures(name) {
  return request(`/api/persons/${encodeURIComponent(name)}/procedures`);
}

export function fetchProcedure(name, proc) {
  return request(`/api/persons/${encodeURIComponent(name)}/procedures/${encodeURIComponent(proc)}`);
}

// ── Session ──────────────────────

export function fetchSessions(name) {
  return request(`/api/persons/${encodeURIComponent(name)}/sessions`);
}

export function fetchSession(name, sessionId) {
  return request(`/api/persons/${encodeURIComponent(name)}/sessions/${encodeURIComponent(sessionId)}`);
}

export function fetchConversationFull(name, limit = 50) {
  return request(`/api/persons/${encodeURIComponent(name)}/conversation/full?limit=${limit}`);
}

export function fetchTranscript(name, date) {
  return request(`/api/persons/${encodeURIComponent(name)}/transcripts/${encodeURIComponent(date)}`);
}

// ── System ──────────────────────

export function fetchSystemStatus() {
  return request("/api/system/status");
}

export function fetchSharedUsers() {
  return request("/api/shared/users");
}

export function reloadSystem() {
  return post("/api/system/reload", {});
}

export function triggerHeartbeat(name) {
  return post(`/api/persons/${encodeURIComponent(name)}/trigger`, {});
}
