import { useCallback } from 'react';
import { isLevel, type Level, type PuzzleOf } from '../../api/puzzles';
import {
  DEFAULT_TIMING,
  usePuzzleSession,
  type PuzzleSession,
  type PuzzleSessionConfig,
  type SessionState,
  type SessionTiming,
} from '../usePuzzleSession';

/*
 * "Next in Line" on top of the shared puzzle session. Everything about
 * loading, checking, hints, errors and leaving is in ../usePuzzleSession.ts.
 * This file says how a round picks its puzzles.
 *
 * A round is five puzzles. Each puzzle is a row of numbers with one or two
 * blanks, solved left to right; the server checks every answer.
 *
 * - "Play": before every puzzle the backend is asked what to play, and its
 *   level is used. Sequences have no recommendation policy yet, so today the
 *   answer is always level 1, but nothing here knows that: when the backend
 *   starts recommending, this follows. With no answer the puzzle is level 1.
 * - A chosen level: all five puzzles at that level; the backend is not asked.
 *
 * A sequence has no parameters besides its level: the server's seed decides
 * the numbers, the length and where the blanks are.
 */

/** Number of puzzles in a round. */
export const ROUND_SIZE = 5;
/** What "Play" uses when the backend has no recommendation. */
export const FALLBACK_LEVEL: Level = 1;

export { DEFAULT_TIMING };
export type GameTiming = SessionTiming;
export type SequencePuzzle = PuzzleOf<'sequences'>;

/** How the puzzles of a round are picked. */
type Plan = { kind: 'adaptive' } | { kind: 'fixed'; level: Level };

export type GameState = SessionState<SequencePuzzle, Plan, Level>;

const SESSION: PuzzleSessionConfig<'sequences', Plan, Level> = {
  game: 'sequences',
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

export interface SequencesGame extends Omit<PuzzleSession<'sequences', Plan, Level>, 'start'> {
  /** Starts a round that follows the backend's recommendation, puzzle by puzzle. */
  play: () => void;
  /** Starts a round at one level. */
  chooseLevel: (level: Level) => void;
}

export function useSequencesGame(timing: GameTiming = DEFAULT_TIMING): SequencesGame {
  const { start, ...session } = usePuzzleSession(SESSION, timing);
  return {
    ...session,
    play: useCallback(() => start({ kind: 'adaptive' }), [start]),
    chooseLevel: useCallback((level: Level) => start({ kind: 'fixed', level }), [start]),
  };
}
