// ── Shared History Loader ──────────────────────
// DOM-independent state management for conversation history pagination.

/**
 * Create a fresh history state object for a single thread.
 * @returns {{ sessions: Array, hasMore: boolean, nextBefore: string|null, loading: boolean }}
 */
export function createHistoryState() {
  return { sessions: [], hasMore: false, nextBefore: null, loading: false };
}

/**
 * Apply API response data to a history state object.
 * Handles both initial load and pagination (prepend older sessions).
 * @param {object} hs - History state to mutate
 * @param {object} data - API response { sessions, has_more, next_before }
 * @param {object} [options]
 * @param {boolean} [options.prepend=false] - If true, prepend sessions (for loading older)
 * @returns {object} The mutated history state
 */
export function applyHistoryData(hs, data, options) {
  const prepend = options?.prepend || false;

  if (!data || !data.sessions || data.sessions.length === 0) {
    if (!prepend) {
      hs.sessions = [];
    }
    hs.hasMore = false;
    hs.loading = false;
    return hs;
  }

  if (prepend) {
    hs.sessions = [...data.sessions, ...hs.sessions];
  } else {
    hs.sessions = data.sessions;
  }

  hs.hasMore = data.has_more || false;
  hs.nextBefore = data.next_before || null;
  hs.loading = false;
  return hs;
}

/**
 * Merge polled conversation data with existing history state.
 * Preserves older sessions that were loaded via pagination while
 * updating the most recent sessions from the polling response.
 * @param {object} prev - Previous history state
 * @param {object} pollData - Poll API response { sessions, has_more, next_before }
 * @returns {{ changed: boolean, merged: object }} Whether data changed and the merged state
 */
function _sessionsEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].session_start !== b[i].session_start) return false;
    if (a[i].session_end !== b[i].session_end) return false;
    const aMsgs = a[i].messages || [];
    const bMsgs = b[i].messages || [];
    if (aMsgs.length !== bMsgs.length) return false;
    if (aMsgs.length > 0 && bMsgs.length > 0) {
      const aLast = aMsgs[aMsgs.length - 1];
      const bLast = bMsgs[bMsgs.length - 1];
      if (aLast.ts !== bLast.ts) return false;
    }
  }
  return true;
}

export function mergePolledHistory(prev, pollData) {
  if (!pollData || !Array.isArray(pollData.sessions)) {
    return { changed: false, merged: prev };
  }

  if (!prev || prev.sessions.length === 0) {
    return {
      changed: true,
      merged: {
        sessions: pollData.sessions,
        hasMore: pollData.has_more || false,
        nextBefore: pollData.next_before || null,
        loading: false,
      },
    };
  }

  if (prev.loading) return { changed: false, merged: prev };

  const pollOldestStart = pollData.sessions[0]?.session_start || "";
  const olderSessions = pollOldestStart
    ? prev.sessions.filter(s => s.session_start && s.session_start < pollOldestStart)
    : [];
  const currentPolledPart = pollOldestStart
    ? prev.sessions.filter(s => !s.session_start || s.session_start >= pollOldestStart)
    : prev.sessions;

  const changed = !_sessionsEqual(currentPolledPart, pollData.sessions);
  if (!changed) return { changed: false, merged: prev };

  const merged = {
    ...prev,
    sessions: [...olderSessions, ...pollData.sessions],
  };
  if (olderSessions.length === 0) {
    merged.hasMore = pollData.has_more || false;
    merged.nextBefore = pollData.next_before || null;
  }

  return { changed: true, merged };
}
