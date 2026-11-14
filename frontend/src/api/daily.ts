import { api } from './client';
import type { Level } from './puzzles';
import { toResult, type ApiResult } from './puzzles';
import type { components } from './schema';

/*
 * Today's Puzzle: GET /api/v1/daily. Everyone who asks for the same date and
 * level gets the same puzzle, so the puzzle that comes back is an ordinary
 * puzzle of one of the games, played with the ordinary check and hint calls.
 *
 * The date is the child's: it comes from the device clock, as a local
 * calendar date. Never toISOString(), which is UTC and would turn over at
 * 21:00 in Buenos Aires. The server accepts any date within a day of its own.
 */

export type DailyPuzzle = components['schemas']['DailyPuzzle'];
/** The games that take turns as Today's Puzzle. The puzzle's `game` says which one came. */
export type DailyGame = DailyPuzzle['puzzle']['game'];

const two = (value: number) => String(value).padStart(2, '0');

/** `now` as the device sees it, in YYYY-MM-DD. */
export function localDate(now: Date = new Date()): string {
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

export function getDailyPuzzle(
  date: string,
  level: Level,
  signal?: AbortSignal,
): Promise<ApiResult<DailyPuzzle>> {
  return toResult(api.GET('/api/v1/daily', { params: { query: { date, level } }, signal }));
}
