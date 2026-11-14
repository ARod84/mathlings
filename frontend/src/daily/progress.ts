import { isLevel, type Level } from '../api/puzzles';
import { localDate } from '../api/daily';

/*
 * What this device remembers about Today's Puzzle: which levels were solved
 * on which days. It lives in localStorage only; the server is never told.
 *
 *   mathlings.daily = { "2026-03-10": [1, 3], "2026-03-11": [2] }
 *
 * NO STREAKS. On purpose, and please keep it that way. A streak that breaks
 * turns a missed day into a failure, which is exactly the feeling this site
 * is trying to keep away from children who already find math stressful. So
 * there is no count of days in a row, nothing resets, and nothing is ever
 * said about a day that was not played. What the home screen shows instead
 * is the gentle "Days played this week", seven dots from Monday to Sunday,
 * which starts afresh every week without anyone being told so.
 *
 * Storage can be blocked (private mode); then nothing is remembered and the
 * puzzle plays as usual.
 */

export const DAILY_KEY = 'mathlings.daily';

/** Date (YYYY-MM-DD, the device's local day) to the levels solved that day. */
export type DailyRecord = Record<string, Level[]>;

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function read(): DailyRecord {
  try {
    const raw = window.localStorage.getItem(DAILY_KEY);
    if (raw === null) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
    const record: DailyRecord = {};
    for (const [date, levels] of Object.entries(parsed)) {
      if (!DATE.test(date) || !Array.isArray(levels)) continue;
      const kept = levels.filter(
        (level): level is Level => typeof level === 'number' && isLevel(level),
      );
      if (kept.length > 0) record[date] = [...new Set(kept)].sort();
    }
    return record;
  } catch {
    return {};
  }
}

function write(record: DailyRecord): void {
  try {
    window.localStorage.setItem(DAILY_KEY, JSON.stringify(record));
  } catch {
    // Storage is blocked: the puzzle still plays, it is just not remembered.
  }
}

/** The levels solved on `date`, in order. Empty when none, or when storage is blocked. */
export function solvedLevels(date: string): Level[] {
  return read()[date] ?? [];
}

/** Remembers that `level` was solved on `date`. Solving it twice changes nothing. */
export function markSolved(date: string, level: Level): void {
  const record = read();
  const levels = record[date] ?? [];
  if (levels.includes(level)) return;
  write({ ...record, [date]: [...levels, level].sort() });
}

/** The seven local dates of the week `today` is in, Monday first. */
export function weekOf(today: Date): string[] {
  // getDay() counts from Sunday; the week here starts on Monday.
  const sinceMonday = (today.getDay() + 6) % 7;
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    day.setDate(day.getDate() - sinceMonday + index);
    return localDate(day);
  });
}

/**
 * For each day of the week `today` is in, Monday to Sunday: was Today's
 * Puzzle played (any level solved) that day? Days still to come are false.
 */
export function daysPlayedThisWeek(today: Date = new Date()): boolean[] {
  const record = read();
  return weekOf(today).map((date) => (record[date]?.length ?? 0) > 0);
}
