/**
 * Frontend logger utility for TerminalAccessManager.
 *
 * - Unified log format with timestamp, level, module
 * - Production: only warn/error output
 * - Development: all levels output
 * - Local storage buffer for recent warn/error logs (for debugging)
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  module: string;
  message: string;
  data?: unknown;
}

const isDev = import.meta.env?.DEV ?? false;

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const MIN_LEVEL: LogLevel = isDev ? 'debug' : 'warn';

// In-memory buffer for recent logs
const logBuffer: LogEntry[] = [];
const MAX_BUFFER_SIZE = 100;
const STORAGE_KEY = 'tam_log_buffer';
const MAX_STORAGE_SIZE = 50;

function formatTimestamp(): string {
  // Use local timezone with offset (e.g. "2026-06-09T14:30:00.123+08:00")
  // instead of UTC "Z" suffix, so logs match the user's local time
  const d = new Date();
  const pad = (n: number, len = 2) => String(n).padStart(len, '0');
  const offset = -d.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const absOffset = Math.abs(offset);
  const offsetStr = `${sign}${pad(Math.floor(absOffset / 60))}:${pad(absOffset % 60)}`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}${offsetStr}`;
}

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[MIN_LEVEL];
}

function persistToStorage(entry: LogEntry): void {
  try {
    const stored: LogEntry[] = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    stored.push(entry);
    while (stored.length > MAX_STORAGE_SIZE) stored.shift();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // localStorage may be full or unavailable
  }
}

function log(level: LogLevel, module: string, message: string, data?: unknown): void {
  const entry: LogEntry = {
    timestamp: formatTimestamp(),
    level,
    module,
    message,
    data,
  };

  // Add to memory buffer
  logBuffer.push(entry);
  while (logBuffer.length > MAX_BUFFER_SIZE) logBuffer.shift();

  // Persist warn/error to localStorage
  if (level === 'warn' || level === 'error') {
    persistToStorage(entry);
  }

  // Console output based on level
  if (!shouldLog(level)) return;

  const prefix = `[${entry.timestamp}] [${level.toUpperCase()}] [${module}]`;

  switch (level) {
    case 'debug':
      console.debug(prefix, message, data ?? '');
      break;
    case 'info':
      console.info(prefix, message, data ?? '');
      break;
    case 'warn':
      console.warn(prefix, message, data ?? '');
      break;
    case 'error':
      console.error(prefix, message, data ?? '');
      break;
  }
}

export const logger = {
  debug: (module: string, message: string, data?: unknown) => log('debug', module, message, data),
  info: (module: string, message: string, data?: unknown) => log('info', module, message, data),
  warn: (module: string, message: string, data?: unknown) => log('warn', module, message, data),
  error: (module: string, message: string, data?: unknown) => log('error', module, message, data),

  /** Get recent log entries from memory buffer */
  getBuffer(): readonly LogEntry[] {
    return logBuffer;
  },

  /** Get persisted log entries from localStorage */
  getStored(): LogEntry[] {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  },

  /** Export all logs (memory + storage) as JSON string */
  exportLogs(): string {
    const stored = this.getStored();
    const all = [...stored, ...logBuffer];
    // Deduplicate by timestamp+level+module+message
    const seen = new Set<string>();
    const unique = all.filter((entry) => {
      const key = `${entry.timestamp}|${entry.level}|${entry.module}|${entry.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return JSON.stringify(unique, null, 2);
  },

  /** Clear all stored logs */
  clearLogs(): void {
    logBuffer.length = 0;
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  },
};
