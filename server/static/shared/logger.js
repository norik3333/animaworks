// ── Frontend Unified Logger ──────────────────────────────────
// Dual output: console + server (via navigator.sendBeacon).
// Usage:
//   import { createLogger } from '../shared/logger.js';
//   const logger = createLogger('websocket');
//   logger.info('Connected', { url });

const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
const FLUSH_INTERVAL = 5000;
const MAX_BUFFER_SIZE = 100;
const SERVER_ENDPOINT = '/api/system/frontend-logs';

let _buffer = [];
let _flushTimer = null;
let _sessionId = null;
let _flushListenersAttached = false;

function _getSessionId() {
  if (!_sessionId) {
    _sessionId = sessionStorage.getItem('animaworks_session_id');
    if (!_sessionId) {
      _sessionId = crypto.randomUUID().slice(0, 12);
      sessionStorage.setItem('animaworks_session_id', _sessionId);
    }
  }
  return _sessionId;
}

function _flush() {
  if (_buffer.length === 0) return;
  const entries = _buffer.splice(0);
  // navigator.sendBeacon is reliable even during page unload
  const ok = navigator.sendBeacon(
    SERVER_ENDPOINT,
    new Blob([JSON.stringify(entries)], { type: 'application/json' })
  );
  if (!ok) {
    // Fallback: fetch (fire-and-forget)
    fetch(SERVER_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entries),
      keepalive: true,
    }).catch(() => {}); // Swallow errors to prevent infinite loop
  }
}

function _ensureFlushTimer() {
  if (_flushTimer) return;
  _flushTimer = setInterval(_flush, FLUSH_INTERVAL);
  if (!_flushListenersAttached) {
    _flushListenersAttached = true;
    // Flush on page hide/unload
    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') _flush();
    });
    window.addEventListener('beforeunload', _flush);
  }
}

class Logger {
  constructor(module) {
    this.module = module;
    _ensureFlushTimer();
  }

  _log(level, ...args) {
    const threshold = localStorage.getItem('animaworks_log_level') || 'INFO';
    if (LOG_LEVELS[level] < LOG_LEVELS[threshold]) return;

    const ts = new Date().toISOString();
    const prefix = `[${ts}] [${level}] [${this.module}]`;

    // 1. Console output
    const consoleFn = level === 'ERROR' ? 'error' : level === 'WARN' ? 'warn' : 'log';
    console[consoleFn](prefix, ...args);

    // 2. Buffer for server send
    const message = args.map(a =>
      typeof a === 'object' ? JSON.stringify(a) : String(a)
    ).join(' ');

    const entry = {
      ts,
      level,
      module: this.module,
      msg: message,
      session_id: _getSessionId(),
      url: location.href,
      ua: navigator.userAgent.slice(0, 100),
    };

    _buffer.push(entry);
    if (_buffer.length > MAX_BUFFER_SIZE) _buffer.shift();

    // ERROR: flush immediately
    if (level === 'ERROR') _flush();
  }

  debug(...args) { this._log('DEBUG', ...args); }
  info(...args)  { this._log('INFO', ...args); }
  warn(...args)  { this._log('WARN', ...args); }
  error(...args) { this._log('ERROR', ...args); }
}

export function createLogger(module) { return new Logger(module); }
