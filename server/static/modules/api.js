/* ── API Helper ────────────────────────────── */

import { createLogger } from "../shared/logger.js";

const logger = createLogger("api");

export async function api(path, opts) {
  try {
    const res = await fetch(path, opts);
    if (!res.ok) {
      logger.error("API request failed", { url: path, status: res.status, statusText: res.statusText });
      throw new Error(`API ${res.status}: ${res.statusText}`);
    }
    return res.json();
  } catch (err) {
    if (err.message && !err.message.startsWith("API ")) {
      logger.error("Network error", { url: path, error: err.message });
    }
    throw err;
  }
}
