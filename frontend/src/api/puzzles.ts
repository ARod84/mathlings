import { api } from './client';
import type { components } from './schema';

/*
 * Typed calls to the puzzle API. Each returns an ApiResult, so components
 * branch on a named outcome and never look at an HTTP status code.
 *
 * The four routes are the same for every game. What differs per game is the
 * body of a new-puzzle request and the puzzle that comes back: GameShapes
 * names both for each game.
 */

export type PuzzlePublic = components['schemas']['PuzzlePublic'];
export type PuzzleStepPublic = components['schemas']['PuzzleStepPublic'];
export type Equation = components['schemas']['Equation'];
export type EquationToken = Equation['left'][number];
export type LinkedToken = components['schemas']['LinkedToken'];
export type CheckResult = components['schemas']['CheckResult'];
export type Diagnosis = components['schemas']['DiagnosisPublic'];
export type Hint = components['schemas']['HintOut'];
/** A mistake rule's name. Used only to pass a focus through; never shown to the child. */
export type MistakeRule = components['schemas']['MistakeRule'];

export type Level = 1 | 2 | 3;

/** True for a level number the games have. A level from the server is checked with this. */
export const isLevel = (value: number): value is Level => value === 1 || value === 2 || value === 3;

/**
 * What each game sends to start a puzzle, and what it gets back. The key is
 * the game's name in the URL. A new backend puzzle type gets an entry here.
 */
export interface GameShapes {
  'missing-number': {
    request: components['schemas']['NewPuzzleRequest'];
    puzzle: PuzzlePublic;
  };
  /** "Next in Line". */
  sequences: {
    request: components['schemas']['NewSequenceRequest'];
    puzzle: components['schemas']['SequencePublic'];
  };
  /** Sum Grid. */
  'sum-grid': {
    request: components['schemas']['NewSumGridRequest'];
    puzzle: components['schemas']['SumGridPublic'];
  };
}

/** A game the backend has puzzles for. */
export type GameId = keyof GameShapes;
export type NewPuzzleRequest<G extends GameId> = GameShapes[G]['request'];
export type PuzzleOf<G extends GameId> = GameShapes[G]['puzzle'];
/** A puzzle of any game. Its `game` field says which. */
export type AnyPuzzle = PuzzleOf<GameId>;

export type ApiResult<T> =
  | { status: 'ok'; data: T }
  /** The puzzle, step or hint does not exist (a bad or tampered id). */
  | { status: 'notFound' }
  /** The puzzle is from an older generator version. Start a new one. */
  | { status: 'gone' }
  /** The server answered, but cannot do this right now. */
  | { status: 'unavailable' }
  /** No answer at all: offline, or the backend is not running. */
  | { status: 'network' };

type Outcome<T> = { data?: T; response: Response };

async function toResult<T>(request: Promise<Outcome<T>>): Promise<ApiResult<T>> {
  let outcome: Outcome<T>;
  try {
    outcome = await request;
  } catch {
    return { status: 'network' };
  }
  const { data, response } = outcome;
  if (response.ok && data !== undefined) return { status: 'ok', data };
  if (response.status === 404) return { status: 'notFound' };
  if (response.status === 410) return { status: 'gone' };
  return { status: 'unavailable' };
}

/** Starts a new puzzle of any game. `request` is that game's own body. */
export function newPuzzle<G extends GameId>(
  game: G,
  request: NewPuzzleRequest<G>,
  signal?: AbortSignal,
): Promise<ApiResult<PuzzleOf<G>>> {
  // The server picks the response shape from the game in the path. The API
  // document can only say "one of the games' puzzles", so the narrowing to
  // this game's puzzle is stated here, once, for every caller.
  return toResult(
    api.POST('/api/v1/puzzles/{game}', {
      params: { path: { game } },
      body: request,
      signal,
    }),
  ) as Promise<ApiResult<PuzzleOf<G>>>;
}

export function newMissingNumber(
  request: { level: Level; length: number; seed?: number; focus?: MistakeRule },
  signal?: AbortSignal,
): Promise<ApiResult<PuzzlePublic>> {
  return newPuzzle('missing-number', request, signal);
}

/** Rebuilds a puzzle from its id. The id says which game it is, so any game's can come back. */
export function getPuzzle(puzzleId: string, signal?: AbortSignal): Promise<ApiResult<AnyPuzzle>> {
  return toResult(
    api.GET('/api/v1/puzzles/{puzzle_id}', { params: { path: { puzzle_id: puzzleId } }, signal }),
  );
}

export function checkStep(
  puzzleId: string,
  stepIndex: number,
  answer: number,
  signal?: AbortSignal,
): Promise<ApiResult<CheckResult>> {
  return toResult(
    api.POST('/api/v1/puzzles/{puzzle_id}/steps/{index}/check', {
      params: { path: { puzzle_id: puzzleId, index: stepIndex } },
      body: { answer },
      signal,
    }),
  );
}

export function getHint(
  puzzleId: string,
  stepIndex: number,
  tier: number,
  signal?: AbortSignal,
): Promise<ApiResult<Hint>> {
  return toResult(
    api.GET('/api/v1/puzzles/{puzzle_id}/steps/{index}/hints/{tier}', {
      params: { path: { puzzle_id: puzzleId, index: stepIndex, tier } },
      signal,
    }),
  );
}
