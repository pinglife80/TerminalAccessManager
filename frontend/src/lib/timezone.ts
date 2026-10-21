/**
 * Runtime timezone for date formatting.
 *
 * The configured timezone is fetched from the backend `/health` endpoint at
 * startup and cached here, so client-side date formatting follows the server's
 * `TZ` config instead of a hard-coded value. Falls back to Asia/Shanghai when
 * the backend is unreachable or the value is missing.
 */

let currentTimezone = 'Asia/Shanghai';

export function setTimezone(tz: string | undefined | null): void {
  if (tz) {
    currentTimezone = tz;
  }
}

export function getTimezone(): string {
  return currentTimezone;
}