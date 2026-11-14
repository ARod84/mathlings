import { useCallback } from 'react';
import { isLevel, type Level, type PuzzleOf } from '../../api/puzzles';
import {
  DEFAULT_TIMING,
  usePuzzleSession,
  type PuzzleSession,
  type PuzzleSessionConfig,
  type SessionState,
  type SessionTiming,
  type SinglePuzzle,
} from '../usePuzzleSession';

/*
 * Sum Grid on top of the shared puzzle session. Everything about loading,
 * checking, hints, errors and leaving is in ../usePuzzleSession.ts. This
 * file says how a round picks its puzzles.
 *
 * A round is five puzzles. Each puzzle is a grid with blanks, solved in the
 * order the server gives; the server checks every answer.
 *
 * - "Play": before every puzzle the backend is asked what to play, and its
 *   level is used. Sum Grid has no recommendation policy yet, so today the
 *   answer is always level 1; nothing here knows that. With no answer the
 *   puzzle is level 1.
 * - A chosen level: all five puzzles at that level; the backend is not asked.
 */

/** Number of puzzles in a round. */
export const ROUND_SIZE = 5;
/** What "Play" uses when the backend has no recommendation. */
export const FALLBACK_LEVEL: Level = 1;

export { DEFAULT_TIMING };
export type GameTiming = SessionTiming;
export type SumGridPuzzle = PuzzleOf<'sum-grid'>;
/** One grid to play on its own, outside a round (Today's Puzzle). */
export type SingleSumGrid = SinglePuzzle<'sum-grid', Level>;

/** How the puzzles of a round are picked. */
type Plan = { kind: 'adaptive' } | { kind: 'fixed'; level: Level };

export type GameState = SessionState<SumGridPuzzle, Plan, Level>;

const SESSION: PuzzleSessionConfig<'sum-grid', Plan, Level> = {
  game: 'sum-grid',
  roundSize: ROUND_SIZE,
  asksBackend: (plan) => plan.kind === 'adaptive',
  fixedLevel: (plan) => (plan.kind === 'fixed' ? plan.level : null),
  choose: (plan, _puzzleIndex, recommended) => {
    let level: Level = FALLBACK_LEVEL;
    if (plan.kind === 'fixed') level = plan.level;
    else if (recommended !== null && isLevel(recommended.level)) level = recommended.level;
    return { level, request: { level } };
  },
  hintTiers: (puzzle, stepIndex) => puzzle.steps[stepIndex]?.hint_tiers ?? 0,
};

export interface SumGridGame extends Omit<PuzzleSession<'sum-grid', Plan, Level>, 'start'> {
  /** Starts a round that follows the backend's recommendation, puzzle by puzzle. */
  play: () => void;
  /** Starts a round at one level. */
  chooseLevel: (level: Level) => void;
}

export function useSumGridGame(
  timing: GameTiming = DEFAULT_TIMING,
  single?: SingleSumGrid,
): SumGridGame {
  const { start, ...session } = usePuzzleSession(SESSION, timing, single);
  return {
    ...session,
    play: useCallback(() => start({ kind: 'adaptive' }), [start]),
    chooseLevel: useCallback((level: Level) => start({ kind: 'fixed', level }), [start]),
  };
}
