import { api } from './client';
import type { components } from './schema';

/*
 * Typed calls to the puzzle API. Each returns an ApiResult, so components
 * branch on a named outcome and never look at an HTTP status code.
 */

export type PuzzlePublic = components['schemas']['PuzzlePublic'];
export type PuzzleStepPublic = components['schemas']['PuzzleStepPublic'];
export type Equation = components['schemas']['Equation'];
export type EquationToken = Equation['left'][number];
export type LinkedToken = components['schemas']['LinkedToken'];
export type CheckResult = components['schemas']['CheckResult'];
export type Diagnosis = components['schemas']['DiagnosisPublic'];
export type Hint = components['schemas']['HintOut'];

export type Level = 1 | 2 | 3;

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

export function newMissingNumber(
  request: { level: Level; length: number; seed?: number },
  signal?: AbortSignal,
): Promise<ApiResult<PuzzlePublic>> {
  return toResult(api.POST('/api/v1/puzzles/missing-number', { body: request, signal }));
}

export function getPuzzle(
  puzzleId: string,
  signal?: AbortSignal,
): Promise<ApiResult<PuzzlePublic>> {
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
