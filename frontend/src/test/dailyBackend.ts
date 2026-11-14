import { http, HttpResponse, type HttpHandler } from 'msw';
import type { components } from '../api/schema';

/*
 * A pretend GET /api/v1/daily for the Today's Puzzle tests. It serves one
 * game, and borrows that game's mock backend to issue the puzzle, so the
 * ordinary check and hint handlers know it afterwards, as the real backend
 * would (a daily puzzle is an ordinary puzzle).
 */

type Schemas = components['schemas'];
type DailyPuzzle = Schemas['DailyPuzzle'];
type Puzzle = DailyPuzzle['puzzle'];

/** A status code to answer with, or 'network' for no answer at all. */
type Failure = number | 'network';

export interface DailyBackend {
  handlers: HttpHandler[];
  /** The game of the day. Change it between tests to serve another game. */
  game: Puzzle['game'];
  /** Every request, in order: the query as it was sent. */
  requests: { date: string | null; level: string | null }[];
  /** Make the next call fail once. */
  failNext: (failure: Failure) => void;
}

/**
 * `issue(level)` makes a puzzle in a game backend and registers it there.
 * Called once per request: a daily puzzle is deterministic on the real
 * server, but the mock backends number theirs, and nothing here depends on
 * two requests giving the same id.
 */
export function createDailyBackend(
  game: Puzzle['game'],
  issue: (level: number) => Puzzle,
): DailyBackend {
  const pending: Failure[] = [];
  const backend: DailyBackend = {
    handlers: [],
    game,
    requests: [],
    failNext: (failure) => pending.push(failure),
  };

  backend.handlers = [
    http.get('*/api/v1/daily', ({ request }) => {
      const url = new URL(request.url);
      const date = url.searchParams.get('date');
      const level = url.searchParams.get('level');
      backend.requests.push({ date, level });
      const failure = pending.shift();
      if (failure === 'network') return HttpResponse.error();
      if (failure !== undefined) {
        return HttpResponse.json({ detail: 'Unavailable' }, { status: failure });
      }
      if (date === null || level === null || !/^[123]$/.test(level)) {
        return HttpResponse.json({ detail: [{ loc: ['query'], msg: 'bad' }] }, { status: 422 });
      }
      const body: DailyPuzzle = {
        date,
        game: backend.game,
        level: Number(level),
        puzzle: issue(Number(level)),
      };
      return HttpResponse.json(body);
    }),
  ];
  return backend;
}
